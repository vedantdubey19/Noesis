import json

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentSource
from app.services.gmail import GmailService
from app.services.notion import NotionService


class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.notion = NotionService()
        self.gmail = GmailService()
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)

    def ingest_notion(self, limit: int = 5) -> int:
        pages = self.notion.search_pages(limit=limit)
        count = 0
        for page in pages:
            source_id = page.get("id", "")
            title = _extract_notion_title(page)
            blocks = self.notion.get_page_blocks(source_id, limit=100)
            databases = self.notion.search_databases(limit=5)
            content = json.dumps(
                {"page": page, "blocks": blocks, "workspace_databases": databases}, default=str
            )
            page_url = page.get("url", "")
            self._upsert_document(DocumentSource.NOTION, source_id, title, content, page_url)
            count += 1
        self.db.commit()
        return count

    def ingest_gmail(self, days: int = 90, limit: int = 20) -> int:
        messages = self.gmail.fetch_recent_messages(days=days, limit=limit)
        count = 0
        for msg in messages:
            self._upsert_document(
                DocumentSource.GMAIL,
                msg.get("id", ""),
                msg.get("subject", ""),
                msg.get("body", ""),
                "",
            )
            count += 1
        self.db.commit()
        return count

    def ingest_web_context(self, url: str, title: str, content: str) -> None:
        self._upsert_document(DocumentSource.WEB, url, title, content, url)
        self.db.commit()

    def _upsert_document(
        self, source: DocumentSource, source_id: str, title: str, content: str, url: str
    ) -> Document:
        existing = (
            self.db.query(Document)
            .filter(Document.source == source, Document.source_id == source_id)
            .one_or_none()
        )
        if existing:
            existing.title = title
            existing.content = content
            existing.url = url or existing.url
            self.redis.lpush("noesis:embed_queue", str(existing.id))
            return existing
        doc = Document(source=source, source_id=source_id, title=title, content=content, url=url or "")
        self.db.add(doc)
        self.db.flush()
        self.redis.lpush("noesis:embed_queue", str(doc.id))
        return doc

    def pop_embed_queue(self) -> list[str]:
        ids: list[str] = []
        while True:
            value = self.redis.rpop("noesis:embed_queue")
            if value is None:
                break
            ids.append(value)
        # deduplicate while preserving order
        seen = set()
        unique = []
        for doc_id in ids:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            unique.append(doc_id)
        return unique


def _extract_notion_title(page: dict) -> str:
    title_data = page.get("properties", {}).get("title", {}).get("title", [])
    if title_data:
        return title_data[0].get("plain_text", "")
    return "Untitled"
