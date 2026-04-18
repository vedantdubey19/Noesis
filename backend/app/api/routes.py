import asyncio
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import verify_auth_header
from app.core.database import get_db
from app.services.ingestion import IngestionService
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
def ingest_context(payload: ContextRequest, db: Session = Depends(get_db)):
    ingestion = IngestionService(db)
    ingestion.ingest_web_context(payload.url, payload.title, payload.page_text)
    query = f"{payload.title} {(payload.page_text or '')[:200]}".strip()
    search_service = HybridSearchService(db)
    results = asyncio.run(search_service.search(query=query, limit=3))
    cards = [
        {
            "text": item.text[:200],
            "doc_title": item.doc_title,
            "doc_url": item.doc_url,
            "source": item.source,
            "score": item.score,
        }
        for item in results
    ]
    return {"status": "received", "message": "data synced", "url": payload.url, "context_cards": cards}


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
