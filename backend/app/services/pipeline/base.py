from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Type, TypeVar, Union

import anthropic

from app.core.config import settings
from app.services.search import SearchResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class PageContext:
    url: str
    title: str
    page_text: str
    timestamp: datetime


@dataclass
class ObserveOutput:
    intent: str
    topic: str
    entities: list[str]
    emotional_tone: str
    is_work_related: bool


@dataclass
class ExtractOutput:
    content_type: str
    reasoning: str
    urgency: str
    open_question: Optional[str]
    decision_context: Optional[str]


@dataclass
class RelateOutput:
    search_queries: list[str]
    retrieved_chunks: list[SearchResult]
    relevance_scores: list[float]
    related_topics: list[str]


@dataclass
class ContextCard:
    text: str
    doc_title: str
    doc_url: str
    source: str
    relevance_score: float
    card_type: str


@dataclass
class SurfaceOutput:
    context_cards: list[ContextCard]
    summary: str
    suggested_action: Optional[str]


@dataclass
class PipelineResult:
    page_context: PageContext
    observe: Optional[ObserveOutput]
    extract: Optional[ExtractOutput]
    relate: Optional[RelateOutput]
    surface: SurfaceOutput
    total_latency_ms: int
    stage_latencies_ms: dict[str, int]
    cached: bool = False


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _parse_json_object(raw: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(raw)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


class BasePipelineStage:
    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)
        self.model = settings.anthropic_model

    async def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        expect_json: bool = True,
    ) -> Union[dict[str, Any], str]:
        last_error: Optional[Exception] = None
        message_text = user_message
        for attempt in range(2):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": message_text}],
                )
                block = response.content[0]
                text = block.text if hasattr(block, "text") else str(block)
                if not expect_json:
                    return text
                return _parse_json_object(str(text))
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                logger.warning("LLM JSON parse failed (attempt %s): %s", attempt + 1, e)
                message_text = user_message + "\n\nRespond only with JSON, no other text."
            except Exception as e:
                last_error = e
                raise
        if last_error:
            raise last_error
        raise RuntimeError("LLM call failed without exception detail")


def search_result_from_dict(d: dict[str, Any]) -> SearchResult:
    return SearchResult(
        chunk_id=str(d["chunk_id"]),
        document_id=str(d["document_id"]),
        text=str(d.get("text", "")),
        doc_title=str(d.get("doc_title", "")),
        doc_url=str(d.get("doc_url", "")),
        source=str(d.get("source", "")),
        score=float(d.get("score", 0.0)),
        vector_score=float(d.get("vector_score", 0.0)),
        bm25_score=float(d.get("bm25_score", 0.0)),
        relevance_score=float(d.get("relevance_score", 0.0)),
    )


def page_context_from_dict(d: dict[str, Any]) -> PageContext:
    ts = d.get("timestamp")
    if isinstance(ts, str):
        timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif isinstance(ts, datetime):
        timestamp = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    else:
        timestamp = datetime.now(timezone.utc)
    return PageContext(
        url=str(d["url"]),
        title=str(d["title"]),
        page_text=str(d.get("page_text", "")),
        timestamp=timestamp,
    )


def _deserialize_dataclass(cls: Type[T], data: dict[str, Any]) -> T:
    field_names = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in data.items() if k in field_names}
    if cls is RelateOutput and kwargs.get("retrieved_chunks"):
        kwargs["retrieved_chunks"] = [
            search_result_from_dict(x) if isinstance(x, dict) else x for x in kwargs["retrieved_chunks"]
        ]
    return cls(**kwargs)  # type: ignore[arg-type]


def pipeline_result_to_serializable(result: PipelineResult) -> dict[str, Any]:
    def convert(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.astimezone(timezone.utc).isoformat()
        if isinstance(obj, SearchResult):
            return obj.to_dict()
        if is_dataclass(obj) and not isinstance(obj, type):
            d = asdict(obj)
            return {k: convert(v) for k, v in d.items()}
        if isinstance(obj, list):
            return [convert(x) for x in obj]
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        return obj

    return convert(result)  # type: ignore[return-value]


def pipeline_result_from_serializable(data: dict[str, Any]) -> PipelineResult:
    pc = page_context_from_dict(data["page_context"])
    observe = None
    if data.get("observe"):
        o = data["observe"]
        observe = ObserveOutput(
            intent=str(o.get("intent", "")),
            topic=str(o.get("topic", "")),
            entities=[str(x) for x in (o.get("entities") or [])],
            emotional_tone=str(o.get("emotional_tone", "focused")),
            is_work_related=bool(o.get("is_work_related", True)),
        )
    extract = None
    if data.get("extract"):
        x = data["extract"]
        extract = ExtractOutput(
            content_type=str(x.get("content_type", "reference")),
            reasoning=str(x.get("reasoning", "")),
            urgency=str(x.get("urgency", "medium")),
            open_question=x.get("open_question"),
            decision_context=x.get("decision_context"),
        )
    relate = _deserialize_dataclass(RelateOutput, data["relate"]) if data.get("relate") else None
    surf = data["surface"]
    cards = [_deserialize_dataclass(ContextCard, c) for c in (surf.get("context_cards") or [])]
    surface = SurfaceOutput(
        context_cards=cards,
        summary=str(surf.get("summary", "")),
        suggested_action=surf.get("suggested_action"),
    )
    return PipelineResult(
        page_context=pc,
        observe=observe,
        extract=extract,
        relate=relate,
        surface=surface,
        total_latency_ms=int(data.get("total_latency_ms", 0)),
        stage_latencies_ms=dict(data.get("stage_latencies_ms") or {}),
        cached=bool(data.get("cached", False)),
    )
