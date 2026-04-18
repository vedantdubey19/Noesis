import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import redis
from rank_bm25 import BM25Okapi
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chunk import Chunk
from app.services.embedder import EmbeddingService

logger = logging.getLogger(__name__)

BM25_CACHE = {"index": None, "chunk_ids": [], "chunks": {}}


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    text: str
    doc_title: str
    doc_url: str
    source: str
    score: float
    vector_score: float
    bm25_score: float

    def to_dict(self) -> dict:
        return asdict(self)


class HybridSearchService:
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def search(self, query: str, limit: int = 5, source: Optional[str] = None) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []

        has_chunks = self.db.query(Chunk.id).first()
        if not has_chunks:
            return []

        query_embedding = await self._get_query_embedding(query)
        vector_limit = max(limit, settings.vector_max_results) * 2
        vector_results = await self._vector_search(query_embedding, vector_limit, source=source)
        bm25_results = await self._bm25_search(query, vector_limit, source=source)
        merged = await self._rrf_merge(vector_results, bm25_results)
        return merged[:limit]

    async def _get_query_embedding(self, query: str) -> List[float]:
        cache_key = f"noesis:query_embedding:{query.lower()[:200]}"
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        vector = (await self.embedding_service.embed_texts([query]))[0]
        self.redis.setex(cache_key, 3600, json.dumps(vector))
        return vector

    async def _vector_search(
        self, query_embedding: List[float], limit: int, source: Optional[str] = None
    ) -> List[Tuple[Chunk, float]]:
        base_sql = """
        SELECT
          id, document_id, chunk_index, text, token_count, source, doc_title, doc_url, created_at,
          1 - (embedding <=> :query_vector) AS cosine_score
        FROM chunks
        WHERE 1 - (embedding <=> :query_vector) > :threshold
        """
        params = {
            "query_vector": query_embedding,
            "threshold": settings.vector_similarity_threshold,
            "limit": limit,
        }
        if source:
            base_sql += " AND source = :source "
            params["source"] = source
        base_sql += " ORDER BY embedding <=> :query_vector LIMIT :limit"

        rows = self.db.execute(text(base_sql), params).mappings().all()
        results: List[Tuple[Chunk, float]] = []
        for row in rows:
            chunk = Chunk(
                id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                text=row["text"],
                token_count=row["token_count"],
                embedding=query_embedding,
                source=row["source"],
                doc_title=row["doc_title"],
                doc_url=row["doc_url"],
                created_at=row["created_at"],
            )
            results.append((chunk, float(row["cosine_score"])))
        return results

    async def _bm25_search(self, query: str, limit: int, source: Optional[str] = None) -> List[Tuple[Chunk, float]]:
        self._ensure_bm25_index()
        bm25: BM25Okapi = BM25_CACHE["index"]
        if bm25 is None:
            return []

        chunk_ids = BM25_CACHE["chunk_ids"]
        chunk_map: Dict[str, Chunk] = BM25_CACHE["chunks"]
        scores = bm25.get_scores(query.lower().split())
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)

        results: List[Tuple[Chunk, float]] = []
        for idx, score in ranked:
            if len(results) >= limit:
                break
            chunk = chunk_map.get(str(chunk_ids[idx]))
            if not chunk:
                continue
            if source and chunk.source != source:
                continue
            results.append((chunk, float(score)))
        return results

    async def _rrf_merge(
        self, vector_results: List[Tuple[Chunk, float]], bm25_results: List[Tuple[Chunk, float]]
    ) -> List[SearchResult]:
        if not vector_results and not bm25_results:
            return []

        vector_rank = {str(chunk.id): idx + 1 for idx, (chunk, _score) in enumerate(vector_results)}
        bm25_rank = {str(chunk.id): idx + 1 for idx, (chunk, _score) in enumerate(bm25_results)}
        vector_score_map = {str(chunk.id): score for chunk, score in vector_results}
        bm25_score_map = {str(chunk.id): score for chunk, score in bm25_results}
        chunk_map = {str(chunk.id): chunk for chunk, _ in vector_results + bm25_results}

        max_rank = max(len(vector_results), len(bm25_results), 1)
        merged: List[SearchResult] = []

        for chunk_id, chunk in chunk_map.items():
            v_rank = vector_rank.get(chunk_id, max_rank + 1)
            b_rank = bm25_rank.get(chunk_id, max_rank + 1)
            raw_rrf = (settings.vector_weight / (settings.rrf_k + v_rank)) + (
                settings.bm25_weight / (settings.rrf_k + b_rank)
            )
            merged.append(
                SearchResult(
                    chunk_id=str(chunk.id),
                    document_id=str(chunk.document_id),
                    text=chunk.text,
                    doc_title=chunk.doc_title,
                    doc_url=chunk.doc_url,
                    source=chunk.source,
                    score=raw_rrf,
                    vector_score=float(vector_score_map.get(chunk_id, 0.0)),
                    bm25_score=float(bm25_score_map.get(chunk_id, 0.0)),
                )
            )

        merged.sort(key=lambda item: item.score, reverse=True)
        if not merged:
            return merged
        max_score = merged[0].score
        for item in merged:
            item.score = round(item.score / max_score, 6) if max_score > 0 else 0.0
        return merged

    def _ensure_bm25_index(self) -> None:
        invalid = self.redis.get("noesis:bm25_cache_invalid")
        if BM25_CACHE["index"] is not None and invalid != "1":
            return

        chunks = self.db.query(Chunk).all()
        if not chunks:
            BM25_CACHE["index"] = None
            BM25_CACHE["chunk_ids"] = []
            BM25_CACHE["chunks"] = {}
            return

        tokenized = [(chunk.text or "").lower().split() for chunk in chunks]
        BM25_CACHE["index"] = BM25Okapi(tokenized)
        BM25_CACHE["chunk_ids"] = [str(chunk.id) for chunk in chunks]
        BM25_CACHE["chunks"] = {str(chunk.id): chunk for chunk in chunks}
        self.redis.set("noesis:bm25_cache_invalid", "0")


def run_search_sync(db: Session, query: str, limit: int = 5, source: Optional[str] = None) -> List[SearchResult]:
    service = HybridSearchService(db)
    return asyncio.run(service.search(query=query, limit=limit, source=source))
