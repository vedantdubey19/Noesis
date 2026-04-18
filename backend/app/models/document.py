from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DocumentSource(str, Enum):
    NOTION = "notion"
    GMAIL = "gmail"
    WEB = "web"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_documents_source_source_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    source: Mapped[DocumentSource] = mapped_column(SAEnum(DocumentSource), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
