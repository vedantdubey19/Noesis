from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.pipeline.base import BasePipelineStage, ExtractOutput, ObserveOutput, PageContext, RelateOutput
from app.services.search import HybridSearchService, SearchResult

logger = logging.getLogger(__name__)

STAGE3A_SYSTEM = """You are a search query generator for a personal knowledge base system.
Given what a user is currently working on, generate 2-3 diverse search queries
that would surface the most relevant past notes, decisions, and emails.
Rules:

Make queries specific to the user's actual context, not generic
Vary the queries: one broad (topic-level), one specific (entity or decision),
one temporal if relevant ("decision about X last quarter")
If the activity is a "decision", generate queries that find past similar decisions
If the activity is a "question", generate queries that find answers or prior research
Do NOT repeat the page title verbatim as a query

Respond ONLY with valid JSON:
{
"queries": ["string", "string", "string"]
}"""

STAGE3C_SYSTEM = """You are a relevance judge for a personal AI assistant. Given what a user is
currently working on and a list of retrieved text chunks from their notes and
emails, score each chunk's relevance to the user's current context.
Score from 0.0 to 1.0:

1.0: Directly relevant — this is exactly what the user needs right now
0.7-0.9: Highly relevant — same topic or decision type
0.4-0.6: Somewhat relevant — related entities or themes
0.0-0.3: Coincidental match — surface-level keyword overlap only

Respond ONLY with valid JSON:
{
"scores": [0.0, 0.0]
}"""


def _dedupe_top_chunks(per_query: List[List[SearchResult]], max_unique: int) -> List[SearchResult]:
    best: dict[str, SearchResult] = {}
    for group in per_query:
        for item in group:
            prev = best.get(item.chunk_id)
            if prev is None or item.score > prev.score:
                best[item.chunk_id] = item
    ranked = sorted(best.values(), key=lambda x: x.score, reverse=True)
    return ranked[:max_unique]


def _related_topics_from_chunks(chunks: List[SearchResult]) -> List[str]:
    topics: List[str] = []
    seen: set[str] = set()
    for c in chunks:
        parts = re.split(r"[\|\–\-]+", c.doc_title or "")
        t = (parts[0] if parts else "").strip()
        if len(t) >= 3:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                topics.append(t[:120])
        if len(topics) >= 5:
            break
    return topics


class RelateStage(BasePipelineStage):
    def __init__(self, db: Session) -> None:
        super().__init__()
        self.db = db
        self._search: Optional[HybridSearchService] = None

    def _get_search(self) -> Any:
        if self._search is None:
            self._search = HybridSearchService(self.db)
        return self._search

    async def run(
        self,
        page: PageContext,
        observe: ObserveOutput,
        extract: ExtractOutput,
    ) -> Tuple[RelateOutput, int]:
        t0 = time.perf_counter()
        user_3a = (
            f"Current activity type: {extract.content_type}\n"
            f"Topic: {observe.topic}\n"
            f"Intent: {observe.intent}\n"
            f"Entities: {', '.join(observe.entities)}\n"
            f"Open question: {extract.open_question or 'none'}\n"
            f"Decision context: {extract.decision_context or 'none'}"
        )
        q_data = await self._call_llm(
            STAGE3A_SYSTEM,
            user_3a,
            max_tokens=min(256, settings.stage3_max_tokens),
            expect_json=True,
        )
        if not isinstance(q_data, dict):
            raise ValueError("Relate query generation expected JSON object")
        raw_queries = q_data.get("queries") or []
        if not isinstance(raw_queries, list):
            raw_queries = []
        queries = [str(q).strip() for q in raw_queries if str(q).strip()][:3]
        if not queries:
            fb = (observe.topic or page.title or "notes").strip()
            queries = [fb] if fb else ["notes"]

        search_svc = self._get_search()
        search_tasks = [search_svc.search(q, limit=10, source=None) for q in queries]
        search_results = await asyncio.gather(*search_tasks)
        merged = _dedupe_top_chunks(list(search_results), max_unique=8)

        if not merged:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return (
                RelateOutput(
                    search_queries=queries,
                    retrieved_chunks=[],
                    relevance_scores=[],
                    related_topics=[],
                ),
                latency_ms,
            )

        chunk_lines: List[str] = []
        for i, chunk in enumerate(merged):
            excerpt = (chunk.text or "")[:300].replace("\n", " ")
            chunk_lines.append(
                f"[{i}] Source: {chunk.source} | Doc: {chunk.doc_title}\n{excerpt}"
            )
        user_3c = (
            f"User's current context:\n"
            f"Activity: {extract.content_type}\n"
            f"Intent: {observe.intent}\n"
            f"Topic: {observe.topic}\n"
            f"Decision context: {extract.decision_context or 'none'}\n"
            f"Retrieved chunks (in order):\n"
            + "\n\n".join(chunk_lines)
        )
        score_data = await self._call_llm(
            STAGE3C_SYSTEM,
            user_3c,
            max_tokens=min(512, settings.stage3_max_tokens),
            expect_json=True,
        )
        if not isinstance(score_data, dict):
            raise ValueError("Relate re-rank expected JSON object")
        raw_scores = score_data.get("scores") or []
        scores: List[float] = []
        for i in range(len(merged)):
            if i < len(raw_scores):
                try:
                    scores.append(float(raw_scores[i]))
                except (TypeError, ValueError):
                    scores.append(0.0)
            else:
                scores.append(0.0)

        filtered_pairs: List[Tuple[SearchResult, float]] = []
        for ch, sc in zip(merged, scores):
            if sc >= 0.4:
                ch.relevance_score = sc
                filtered_pairs.append((ch, sc))
        filtered_pairs.sort(key=lambda x: x[1], reverse=True)
        filtered_pairs = filtered_pairs[:5]
        final_chunks = [p[0] for p in filtered_pairs]
        final_scores = [p[1] for p in filtered_pairs]

        related_topics = _related_topics_from_chunks(final_chunks)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return (
            RelateOutput(
                search_queries=queries,
                retrieved_chunks=final_chunks,
                relevance_scores=final_scores,
                related_topics=related_topics,
            ),
            latency_ms,
        )
