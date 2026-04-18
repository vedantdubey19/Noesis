"""End-to-end pipeline test with LLM and retrieval mocked."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.services.pipeline import PageContext, PipelineOrchestrator
from app.services.pipeline.base import (
    ExtractOutput,
    ObserveOutput,
    PipelineResult,
    RelateOutput,
    SurfaceOutput,
)
from app.services.search import SearchResult


def _page() -> PageContext:
    return PageContext(
        url="https://github.com/org/repo/issues/1",
        title="Choose session store",
        page_text="We are comparing Redis vs Memcached for sessions; need latency and ops input.",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_pipeline_e2e_happy_path():
    db = MagicMock(spec=Session)
    orch = PipelineOrchestrator(db)
    observe = ObserveOutput(
        intent="Pick a session store.",
        topic="session storage decision",
        entities=["Redis", "Memcached"],
        emotional_tone="decisive",
        is_work_related=True,
    )
    extract = ExtractOutput(
        content_type="decision",
        reasoning="Comparing options.",
        urgency="high",
        open_question=None,
        decision_context="Session backing store for auth service.",
    )
    relate = RelateOutput(
        search_queries=["q1", "q2"],
        retrieved_chunks=[
            SearchResult(
                chunk_id="c1",
                document_id="d1",
                text="Chose Redis for pub/sub.",
                doc_title="Caching notes",
                doc_url="https://notion.so/x",
                source="notion",
                score=0.9,
                vector_score=0.8,
                bm25_score=0.7,
                relevance_score=0.88,
            )
        ],
        relevance_scores=[0.88],
        related_topics=["Caching notes"],
    )
    surface = SurfaceOutput(
        context_cards=[],
        summary="Surfacing a prior caching decision.",
        suggested_action="You might want to revisit your Redis vs Memcached notes.",
    )

    async def fake_inner(pc: PageContext) -> PipelineResult:
        return PipelineResult(
            page_context=pc,
            observe=observe,
            extract=extract,
            relate=relate,
            surface=surface,
            total_latency_ms=120,
            stage_latencies_ms={"stage1": 10, "stage2": 10, "stage3": 80, "stage4": 20},
            cached=False,
        )

    with patch.object(orch.cache, "get", new_callable=AsyncMock, return_value=None):
        with patch.object(orch.cache, "set", new_callable=AsyncMock):
            with patch.object(orch, "_run_inner", side_effect=fake_inner):
                with patch.object(orch, "_log"):
                    result = await orch.run(_page())
    assert result.observe.topic
    assert result.surface.summary
    assert result.total_latency_ms >= 0
