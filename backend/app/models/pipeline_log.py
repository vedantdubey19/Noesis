from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.document import Base


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    page_title: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    observe_topic: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    extract_content_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    stage1_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage2_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage3_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage4_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_cards_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_stage: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
