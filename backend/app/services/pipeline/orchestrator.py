from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Coroutine, Optional, TypeVar

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.pipeline_log import PipelineLog
from app.services.context_cache import ContextCache
from app.services.pipeline.base import (
    ExtractOutput,
    ObserveOutput,
    PageContext,
    PipelineResult,
    RelateOutput,
    SurfaceOutput,
)
from app.services.pipeline.stage1_observe import ObserveStage
from app.services.pipeline.stage2_extract import ExtractStage
from app.services.pipeline.stage3_relate import RelateStage
from app.services.pipeline.stage4_surface import SurfaceStage, _fallback_cards

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_EXTRACT = ExtractOutput(
    content_type="reference",
    reasoning="Default after extract stage failure.",
    urgency="low",
    open_question=None,
    decision_context=None,
)


async def _with_retries(
    name: str,
    factory: Callable[[], Coroutine[None, None, T]],
) -> T:
    last: Optional[Exception] = None
    attempts = max(1, settings.pipeline_max_retries + 1)
    for i in range(attempts):
        try:
            return await factory()
        except Exception as e:
            last = e
            logger.warning("Stage %s attempt %s failed: %s", name, i + 1, e)
            if i == attempts - 1:
                raise
    raise last  # type: ignore[misc]


class PipelineOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.stage1 = ObserveStage()
        self.stage2 = ExtractStage()
        self.stage3 = RelateStage(db)
        self.stage4 = SurfaceStage()
        self.cache = ContextCache()

    def _log(
        self,
        page: PageContext,
        observe: Optional[ObserveOutput],
        extract: Optional[ExtractOutput],
        stage_ms: dict[str, int],
        total_ms: int,
        surface: SurfaceOutput,
        cached: bool,
        error_stage: Optional[str],
        error_message: Optional[str],
    ) -> None:
        try:
            row = PipelineLog(
                url=page.url[:2048],
                page_title=(page.title or "")[:1024],
                observe_topic=(observe.topic if observe else None),
                extract_content_type=(extract.content_type if extract else None),
                stage1_latency_ms=stage_ms.get("stage1"),
                stage2_latency_ms=stage_ms.get("stage2"),
                stage3_latency_ms=stage_ms.get("stage3"),
                stage4_latency_ms=stage_ms.get("stage4"),
                total_latency_ms=total_ms,
                num_cards_returned=len(surface.context_cards),
                cached=cached,
                error_stage=error_stage,
                error_message=error_message,
            )
            self.db.add(row)
            self.db.commit()
        except Exception as e:
            logger.error("Pipeline log insert failed: %s", e)
            self.db.rollback()

    async def _timeout_degrade(self, page: PageContext) -> PipelineResult:
        t0 = time.perf_counter()
        stage_ms: dict[str, int] = {}
        observe: Optional[ObserveOutput] = None
        extract: Optional[ExtractOutput] = None
        try:
            observe, s1 = await _with_retries("stage1", lambda: self.stage1.run(page))
            stage_ms["stage1"] = s1
        except Exception as e:
            logger.error("Timeout degrade stage1 failed: %s", e)
            surface = SurfaceOutput(
                context_cards=[],
                summary="Context loading — try again in a moment.",
                suggested_action=None,
            )
            total_ms = int((time.perf_counter() - t0) * 1000)
            self._log(page, None, None, stage_ms, total_ms, surface, False, "timeout_degrade", str(e))
            return PipelineResult(
                page_context=page,
                observe=None,
                extract=None,
                relate=None,
                surface=surface,
                total_latency_ms=total_ms,
                stage_latencies_ms=stage_ms,
                cached=False,
            )
        try:
            extract, s2 = await _with_retries("stage2", lambda: self.stage2.run(page, observe))
            stage_ms["stage2"] = s2
        except Exception as e:
            logger.error("Timeout degrade stage2 failed: %s", e)
            extract = DEFAULT_EXTRACT
        surface = SurfaceOutput(
            context_cards=[],
            summary="Context loading — try again in a moment.",
            suggested_action=None,
        )
        total_ms = int((time.perf_counter() - t0) * 1000)
        self._log(page, observe, extract, stage_ms, total_ms, surface, False, "timeout", None)
        return PipelineResult(
            page_context=page,
            observe=observe,
            extract=extract,
            relate=None,
            surface=surface,
            total_latency_ms=total_ms,
            stage_latencies_ms=stage_ms,
            cached=False,
        )

    async def _run_inner(self, page: PageContext) -> PipelineResult:
        t0 = time.perf_counter()
        stage_ms: dict[str, int] = {}
        error_stage: Optional[str] = None
        error_message: Optional[str] = None

        observe: Optional[ObserveOutput] = None
        extract: Optional[ExtractOutput] = None
        relate: Optional[RelateOutput] = None
        surface: Optional[SurfaceOutput] = None

        try:
            observe, s1 = await _with_retries("stage1", lambda: self.stage1.run(page))
            stage_ms["stage1"] = s1
        except Exception as e:
            error_stage = "stage1"
            error_message = str(e)
            surface = SurfaceOutput(
                context_cards=[],
                summary="Couldn't read this page context — try again.",
                suggested_action=None,
            )
            total_ms = int((time.perf_counter() - t0) * 1000)
            self._log(page, None, None, stage_ms, total_ms, surface, False, error_stage, error_message)
            return PipelineResult(
                page_context=page,
                observe=None,
                extract=None,
                relate=None,
                surface=surface,
                total_latency_ms=total_ms,
                stage_latencies_ms=stage_ms,
                cached=False,
            )

        if not observe.is_work_related:
            surface = SurfaceOutput(
                context_cards=[],
                summary="Personal browsing — work context not surfaced.",
                suggested_action=None,
            )
            total_ms = int((time.perf_counter() - t0) * 1000)
            self._log(page, observe, None, stage_ms, total_ms, surface, False, None, None)
            return PipelineResult(
                page_context=page,
                observe=observe,
                extract=None,
                relate=None,
                surface=surface,
                total_latency_ms=total_ms,
                stage_latencies_ms=stage_ms,
                cached=False,
            )

        try:
            extract, s2 = await _with_retries("stage2", lambda: self.stage2.run(page, observe))
            stage_ms["stage2"] = s2
        except Exception as e:
            logger.warning("Stage 2 failed, using default extract: %s", e)
            extract = DEFAULT_EXTRACT
            stage_ms["stage2"] = 0

        try:
            relate, s3 = await _with_retries("stage3", lambda: self.stage3.run(page, observe, extract))
            stage_ms["stage3"] = s3
        except Exception as e:
            error_stage = "stage3"
            error_message = str(e)
            surface = SurfaceOutput(
                context_cards=[],
                summary="Could not load related notes from your knowledge base.",
                suggested_action=None,
            )
            total_ms = int((time.perf_counter() - t0) * 1000)
            self._log(page, observe, extract, stage_ms, total_ms, surface, False, error_stage, error_message)
            return PipelineResult(
                page_context=page,
                observe=observe,
                extract=extract,
                relate=None,
                surface=surface,
                total_latency_ms=total_ms,
                stage_latencies_ms=stage_ms,
                cached=False,
            )

        try:
            surface, s4 = await _with_retries("stage4", lambda: self.stage4.run(page, observe, extract, relate))
            stage_ms["stage4"] = s4
        except Exception as e:
            error_stage = "stage4"
            error_message = str(e)
            surface = _fallback_cards(relate)
            stage_ms["stage4"] = 0

        total_ms = int((time.perf_counter() - t0) * 1000)
        self._log(page, observe, extract, stage_ms, total_ms, surface, False, error_stage, error_message)
        return PipelineResult(
            page_context=page,
            observe=observe,
            extract=extract,
            relate=relate,
            surface=surface,
            total_latency_ms=total_ms,
            stage_latencies_ms=stage_ms,
            cached=False,
        )

    async def run(self, page_context: PageContext) -> PipelineResult:
        cached = await self.cache.get(page_context.url, page_context.title)
        if cached:
            c = cached
            c.cached = True
            self._log(
                page_context,
                c.observe,
                c.extract,
                c.stage_latencies_ms,
                c.total_latency_ms,
                c.surface,
                True,
                None,
                None,
            )
            return c

        try:
            result = await asyncio.wait_for(
                self._run_inner(page_context),
                timeout=settings.pipeline_timeout_seconds,
            )
        except asyncio.TimeoutError:
            result = await self._timeout_degrade(page_context)

        try:
            await self.cache.set(page_context.url, page_context.title, result)
        except Exception as e:
            logger.warning("Pipeline cache set skipped: %s", e)

        return result
