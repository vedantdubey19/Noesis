from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.ingestion import IngestionService
from app.workers.embed import embed_pending_documents


celery_app = Celery("noesis_sync", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(30.0 * 60.0, sync_notion.s(), name="sync notion every 30 minutes")
    sender.add_periodic_task(
        crontab(minute=30),
        embed_pending_documents.s(),
        name="embed pending every hour",
    )


@celery_app.task
def sync_notion() -> dict:
    db = SessionLocal()
    try:
        ingestion = IngestionService(db)
        count = ingestion.ingest_notion(limit=10)
        queued_document_ids = ingestion.pop_embed_queue()
        if queued_document_ids:
            embed_pending_documents.delay(document_ids=queued_document_ids)
        return {"status": "synced", "count": count}
    finally:
        db.close()
