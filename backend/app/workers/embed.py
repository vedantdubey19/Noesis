import asyncio
import logging
from typing import List, Optional

import redis
from celery import shared_task

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.chunker import SemanticChunker
from app.services.embedder import EmbeddingService

logger = logging.getLogger(__name__)


@shared_task(name="noesis.workers.embed.embed_pending_documents", bind=True, max_retries=3)
def embed_pending_documents(self, document_ids: Optional[List[str]] = None):
    db = SessionLocal()
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    total_chunks = 0
    processed_docs = 0
    try:
        if document_ids:
            docs = db.query(Document).filter(Document.id.in_(document_ids)).all()
        else:
            embedded = db.query(Chunk.document_id).distinct().all()
            embedded_ids = [row[0] for row in embedded]
            if embedded_ids:
                docs = db.query(Document).filter(~Document.id.in_(embedded_ids)).all()
            else:
                docs = db.query(Document).all()

        chunker = SemanticChunker(
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            min_chars=settings.chunk_min_chars,
        )
        embedder = EmbeddingService()

        for doc in docs:
            chunks = chunker.chunk_document(doc)
            if not chunks:
                continue

            db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
            vectors = asyncio.run(embedder.embed_chunks(chunks))

            chunk_rows = []
            for chunk_data, vector in zip(chunks, vectors):
                chunk_rows.append(
                    Chunk(
                        document_id=doc.id,
                        chunk_index=chunk_data.chunk_index,
                        text=chunk_data.text,
                        token_count=chunk_data.token_count,
                        embedding=vector,
                        source=doc.source.value if hasattr(doc.source, "value") else str(doc.source),
                        doc_title=doc.title or "",
                        doc_url=doc.url or "",
                    )
                )

            db.bulk_save_objects(chunk_rows)
            db.commit()
            total_chunks += len(chunk_rows)
            processed_docs += 1
            logger.info("Embedded document %s with %s chunks", doc.id, len(chunk_rows))

        redis_client.set("noesis:bm25_cache_invalid", "1")
        total_rows = db.query(Chunk).count()
        if total_rows < 100:
            logger.warning(
                "chunks table has fewer than 100 rows (%s); ivfflat index may not help yet",
                total_rows,
            )
        logger.info("Embedding complete. documents=%s chunks=%s", processed_docs, total_chunks)
        return {"documents": processed_docs, "chunks": total_chunks}
    finally:
        db.close()
