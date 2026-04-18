import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings

from app.services.pipeline.base import (
    ExtractOutput,
    ObserveOutput,
    PageContext,
    PipelineResult,
    RelateOutput,
    SurfaceOutput,
)
from app.services.pipeline.orchestrator import PipelineOrchestrator
from app.services.pipeline.stage1_observe import ObserveStage
from app.services.pipeline.stage2_extract import ExtractStage
from app.services.pipeline.stage3_relate import RelateStage
from app.services.pipeline.stage4_surface import SurfaceStage
from app.services.search import SearchResult


def _page() -> PageContext:
    return PageContext(
        url="https://example.com/doc",
        title="API design",
        page_text="We need to decide between REST and GraphQL for the new service.",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_stage1_work_page():
    stage = ObserveStage()
    out = {
        "intent": "Choose an API style for a new service.",
        "topic": "API design decision",
        "entities": ["REST", "GraphQL"],
        "emotional_tone": "focused",
        "is_work_related": True,
    }
    with patch.object(stage, "_call_llm", new_callable=AsyncMock, return_value=out):
        observe, ms = await stage.run(_page())
    assert observe.is_work_related is True
    assert "API" in observe.topic
    assert ms >= 0


@pytest.mark.asyncio
async def test_stage1_non_work_page():
    stage = ObserveStage()
    out = {
        "intent": "Watch entertainment.",
        "topic": "online video",
        "entities": [],
        "emotional_tone": "exploratory",
        "is_work_related": False,
    }
    with patch.object(stage, "_call_llm", new_callable=AsyncMock, return_value=out):
        observe, _ = await stage.run(_page())
    assert observe.is_work_related is False


@pytest.mark.asyncio
async def test_stage1_json_retry():
    stage = ObserveStage()
    payload = {
        "intent": "x",
        "topic": "y z",
        "entities": [],
        "emotional_tone": "focused",
        "is_work_related": True,
    }
    bad_resp = MagicMock()
    bad_resp.content = [MagicMock(text="not json at all")]
    good_resp = MagicMock()
    good_resp.content = [MagicMock(text=json.dumps(payload))]
    with patch.object(stage.client.messages, "create", new_callable=AsyncMock, side_effect=[bad_resp, good_resp]):
        observe, _ = await stage.run(_page())
    assert observe.intent == "x"


@pytest.mark.asyncio
async def test_stage2_decision_classification():
    stage = ExtractStage()
    observe = ObserveOutput(
        intent="Decide caching",
        topic="caching choice",
        entities=["Redis"],
        emotional_tone="decisive",
        is_work_related=True,
    )
    out = {
        "content_type": "decision",
        "reasoning": "Evaluating options.",
        "urgency": "high",
        "open_question": None,
        "decision_context": "Pick a cache for sessions.",
    }
    with patch.object(stage, "_call_llm", new_callable=AsyncMock, return_value=out):
        extract, _ = await stage.run(_page(), observe)
    assert extract.content_type == "decision"
    assert extract.decision_context is not None


@pytest.mark.asyncio
async def test_stage2_question_extraction():
    stage = ExtractStage()
    observe = ObserveOutput(
        intent="Find answer",
        topic="auth question",
        entities=[],
        emotional_tone="focused",
        is_work_related=True,
    )
    out = {
        "content_type": "question",
        "reasoning": "Seeks answer.",
        "urgency": "medium",
        "open_question": "How does OAuth2 PKCE work?",
        "decision_context": None,
    }
    with patch.object(stage, "_call_llm", new_callable=AsyncMock, return_value=out):
        extract, _ = await stage.run(_page(), observe)
    assert extract.open_question == "How does OAuth2 PKCE work?"


@pytest.mark.asyncio
async def test_stage3_query_generation():
    db = MagicMock(spec=Session)
    stage = RelateStage(db)
    search_mock = MagicMock()
    search_mock.search = AsyncMock(
        return_value=[
            SearchResult(
                chunk_id="1",
                document_id="d1",
                text="t1",
                doc_title="Doc",
                doc_url="u",
                source="notion",
                score=0.9,
                vector_score=0.5,
                bm25_score=0.5,
            )
        ]
    )
    stage._search = search_mock
    page = _page()
    observe = ObserveOutput(
        intent="x",
        topic="topic label",
        entities=["A", "B"],
        emotional_tone="focused",
        is_work_related=True,
    )
    extract = ExtractOutput(
        content_type="decision",
        reasoning="r",
        urgency="high",
        open_question=None,
        decision_context="choose db",
    )
    with patch.object(stage, "_call_llm", new_callable=AsyncMock) as llm:
        llm.side_effect = [
            {"queries": ["broad topic notes", "specific entity decision", "last quarter decision"]},
            {"scores": [0.85]},
        ]
        relate, _ = await stage.run(page, observe, extract)
    assert 2 <= len(relate.search_queries) <= 3
    assert len(relate.retrieved_chunks) >= 1


@pytest.mark.asyncio
async def test_stage3_reranking():
    db = MagicMock(spec=Session)
    stage = RelateStage(db)
    search_mock = MagicMock()
    chunks = [
        SearchResult("1", "d", "text", "D", "u", "notion", 0.9, 0.5, 0.5),
        SearchResult("2", "d", "text", "D", "u", "notion", 0.8, 0.5, 0.5),
    ]
    search_mock.search = AsyncMock(return_value=chunks)
    stage._search = search_mock
    page = _page()
    observe = ObserveOutput("i", "t", [], "focused", True)
    extract = ExtractOutput("reference", "r", "low", None, None)
    with patch.object(stage, "_call_llm", new_callable=AsyncMock) as llm:
        llm.side_effect = [{"queries": ["q1", "q2"]}, {"scores": [0.2, 0.85]}]
        relate, _ = await stage.run(page, observe, extract)
    assert all(s >= 0.4 for s in relate.relevance_scores)
    assert len(relate.retrieved_chunks) == 1


@pytest.mark.asyncio
async def test_stage4_card_limit():
    stage = SurfaceStage()
    page = _page()
    observe = ObserveOutput("i", "t", [], "focused", True)
    extract = ExtractOutput("task", "r", "high", None, None)
    relate = RelateOutput(
        search_queries=["q"],
        retrieved_chunks=[
            SearchResult("1", "d", "x", "D", "u", "notion", 0.9, 0.5, 0.5, relevance_score=0.9)
        ],
        relevance_scores=[0.9],
        related_topics=[],
    )
    big = {
        "context_cards": [
            {
                "text": "a",
                "doc_title": "d",
                "doc_url": "u",
                "source": "notion",
                "relevance_score": 0.9,
                "card_type": "related_note",
            }
        ]
        * 5,
        "summary": "summary",
        "suggested_action": None,
    }
    with patch.object(stage, "_call_llm", new_callable=AsyncMock, return_value=big):
        surface, _ = await stage.run(page, observe, extract, relate)
    assert len(surface.context_cards) <= 3


@pytest.mark.asyncio
async def test_stage4_empty_relate():
    stage = SurfaceStage()
    page = _page()
    observe = ObserveOutput("i", "t", [], "focused", True)
    extract = ExtractOutput("reference", "r", "low", None, None)
    relate = RelateOutput(search_queries=[], retrieved_chunks=[], relevance_scores=[], related_topics=[])
    surface, ms = await stage.run(page, observe, extract, relate)
    assert surface.context_cards == []
    assert "No relevant context" in surface.summary
    assert ms == 0


@pytest.mark.asyncio
async def test_orchestrator_cache_hit():
    db = MagicMock(spec=Session)
    cached = PipelineResult(
        page_context=_page(),
        observe=ObserveOutput("i", "t", [], "focused", True),
        extract=ExtractOutput("reference", "r", "low", None, None),
        relate=None,
        surface=SurfaceOutput([], "cached summary", None),
        total_latency_ms=10,
        stage_latencies_ms={"stage1": 10},
        cached=False,
    )
    orch = PipelineOrchestrator(db)
    with patch.object(orch, "_log"):
        with patch.object(orch.cache, "get", new_callable=AsyncMock, return_value=cached):
            with patch.object(orch, "_run_inner", new_callable=AsyncMock) as inner:
                result = await orch.run(_page())
    inner.assert_not_called()
    assert result.cached is True


@pytest.mark.asyncio
async def test_orchestrator_timeout():
    db = MagicMock(spec=Session)
    orch = PipelineOrchestrator(db)

    async def slow(*_a, **_kw):
        await asyncio.sleep(10)
        return MagicMock()

    with patch.object(orch.cache, "get", new_callable=AsyncMock, return_value=None):
        with patch.object(orch, "_run_inner", side_effect=slow):
            with patch.object(settings, "pipeline_timeout_seconds", 0.01):
                with patch.object(settings, "pipeline_max_retries", 0):
                    with patch.object(orch.stage1, "run", new_callable=AsyncMock) as s1:
                        with patch.object(orch.stage2, "run", new_callable=AsyncMock) as s2:
                            s1.return_value = (
                                ObserveOutput("i", "t", [], "focused", True),
                                1,
                            )
                            s2.return_value = (
                                ExtractOutput("reference", "r", "low", None, None),
                                1,
                            )
                            result = await orch.run(_page())
    assert "Context loading" in result.surface.summary
