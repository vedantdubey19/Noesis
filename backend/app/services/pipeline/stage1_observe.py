from __future__ import annotations

import logging
import time
from typing import Tuple

from app.core.config import settings
from app.services.pipeline.base import BasePipelineStage, ObserveOutput, PageContext

logger = logging.getLogger(__name__)

STAGE1_SYSTEM = """You are an AI assistant that analyses what a knowledge worker is currently
focused on based on their browser context.
Given a webpage URL, title, and visible text, identify:

The user's likely intent (one sentence — what are they trying to accomplish?)
The core topic (2-5 word label)
Key entities mentioned (people, projects, tools, technologies, companies)
The emotional/cognitive tone (focused | exploratory | stressed | decisive)
Whether this is work-related content (true/false)

Respond ONLY with valid JSON matching this exact schema:
{
"intent": "string",
"topic": "string",
"entities": ["string"],
"emotional_tone": "focused | exploratory | stressed | decisive",
"is_work_related": boolean
}
Be concise. intent must be one sentence. topic must be 2-5 words.
Do not include any text outside the JSON object."""


class ObserveStage(BasePipelineStage):
    async def run(self, page: PageContext) -> Tuple[ObserveOutput, int]:
        user_message = (
            f"URL: {page.url}\n"
            f"Title: {page.title}\n"
            f"Visible text (first 1500 chars):\n{page.page_text}"
        )
        t0 = time.perf_counter()
        data = await self._call_llm(
            STAGE1_SYSTEM,
            user_message,
            max_tokens=settings.stage1_max_tokens,
            expect_json=True,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if not isinstance(data, dict):
            raise ValueError("Observe stage expected JSON object")
        tone = str(data.get("emotional_tone", "focused")).lower()
        if tone not in ("focused", "exploratory", "stressed", "decisive"):
            tone = "focused"
        entities = data.get("entities") or []
        if not isinstance(entities, list):
            entities = []
        entities = [str(e) for e in entities][:32]
        out = ObserveOutput(
            intent=str(data.get("intent", "")).strip(),
            topic=str(data.get("topic", "")).strip(),
            entities=entities,
            emotional_tone=tone,
            is_work_related=bool(data.get("is_work_related", True)),
        )
        logger.debug("Observe stage done in %sms", latency_ms)
        return out, latency_ms
