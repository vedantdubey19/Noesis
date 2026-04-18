import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import verify_auth_header
from app.core.database import get_db
from app.models.pipeline_log import PipelineLog
from app.services.ingestion import IngestionService
from app.services.pipeline import PageContext, PipelineOrchestrator
from app.services.search import HybridSearchService
from app.workers.embed import embed_pending_documents


router = APIRouter(dependencies=[Depends(verify_auth_header)])


class ContextRequest(BaseModel):
    url: str
    title: str
    page_text: str


class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    source: Optional[str] = None


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/context")
async def get_context(payload: ContextRequest, db: Session = Depends(get_db)):
    page_ctx = PageContext(
        url=payload.url,
        title=payload.title,
        page_text=(payload.page_text or "")[:1500],
        timestamp=datetime.now(timezone.utc),
    )
    orchestrator = PipelineOrchestrator(db)
    result = await orchestrator.run(page_ctx)
    return {
        "context_cards": [asdict(c) for c in result.surface.context_cards],
        "summary": result.surface.summary,
        "suggested_action": result.surface.suggested_action,
        "cached": result.cached,
        "latency_ms": result.total_latency_ms,
        "topic": result.observe.topic if result.observe else None,
        "activity_type": result.extract.content_type if result.extract else None,
    }


@router.get("/pipeline/stats")
def pipeline_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    logs = db.query(PipelineLog).order_by(PipelineLog.created_at.desc()).limit(100).all()
    if not logs:
        return {
            "runs": 0,
            "avg_stage_latency_ms": {"stage1": 0, "stage2": 0, "stage3": 0, "stage4": 0},
            "cache_hit_rate": 0.0,
            "content_type_distribution": {},
            "avg_cards_returned": 0.0,
            "avg_total_latency_ms": 0.0,
        }

    def _avg(field: str) -> float:
        vals = [getattr(r, field) for r in logs if getattr(r, field) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    cached_hits = sum(1 for r in logs if r.cached)
    dist: dict[str, int] = {}
    for r in logs:
        ct = r.extract_content_type or "unknown"
        dist[ct] = dist.get(ct, 0) + 1

    return {
        "runs": len(logs),
        "avg_stage_latency_ms": {
            "stage1": round(_avg("stage1_latency_ms"), 2),
            "stage2": round(_avg("stage2_latency_ms"), 2),
            "stage3": round(_avg("stage3_latency_ms"), 2),
            "stage4": round(_avg("stage4_latency_ms"), 2),
        },
        "cache_hit_rate": round(cached_hits / len(logs), 4),
        "content_type_distribution": dist,
        "avg_cards_returned": round(sum(r.num_cards_returned for r in logs) / len(logs), 4),
        "avg_total_latency_ms": round(sum(r.total_latency_ms for r in logs) / len(logs), 2),
    }


@router.post("/search")
def search(payload: SearchRequest, db: Session = Depends(get_db)):
    service = HybridSearchService(db)
    results = asyncio.run(
        service.search(query=payload.query, limit=payload.limit, source=payload.source)
    )
    return [item.to_dict() for item in results]


@router.post("/sync/notion")
def sync_notion(db: Session = Depends(get_db)):
    ingestion = IngestionService(db)
    count = ingestion.ingest_notion(limit=5)
    queued_document_ids = ingestion.pop_embed_queue()
    if queued_document_ids:
        embed_pending_documents.delay(document_ids=queued_document_ids)
    return {"status": "synced", "source": "notion", "count": count}


@router.post("/sync/gmail")
def sync_gmail(db: Session = Depends(get_db)):
    ingestion = IngestionService(db)
    count = ingestion.ingest_gmail(days=90, limit=30)
    queued_document_ids = ingestion.pop_embed_queue()
    if queued_document_ids:
        embed_pending_documents.delay(document_ids=queued_document_ids)
    return {"status": "synced", "source": "gmail", "count": count}


@router.post("/sync/all")
def sync_all(db: Session = Depends(get_db)):
    ingestion = IngestionService(db)
    notion_count = ingestion.ingest_notion(limit=10)
    gmail_count = ingestion.ingest_gmail(days=90, limit=30)
    queued_document_ids = ingestion.pop_embed_queue()
    if queued_document_ids:
        embed_pending_documents.delay(document_ids=queued_document_ids)
    return {
        "status": "synced",
        "message": "data synced",
        "counts": {"notion": notion_count, "gmail": gmail_count},
    }
