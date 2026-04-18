from __future__ import annotations

import logging
import time
from typing import Tuple

import redis

from app.core.config import settings
from app.services.pipeline.base import BasePipelineStage, ExtractOutput, ObserveOutput, PageContext

logger = logging.getLogger(__name__)

STAGE2_SYSTEM = """You are an AI that classifies the cognitive activity of a knowledge worker
based on their current page context and observed intent.
Classify the activity into exactly one of these types:

decision: The user is evaluating options and needs to make a choice
question: The user is trying to answer a specific question
task: The user is working on executing something concrete
reference: The user is reading background material / learning
reflection: The user is reviewing past work or outcomes

Also assess:

urgency: how time-sensitive is this activity? (high | medium | low)
open_question: if type is "question", state the question exactly as the user
would phrase it. Otherwise null.
decision_context: if type is "decision", describe what is being decided in
one sentence. Otherwise null.
reasoning: briefly explain your classification in one sentence.

Respond ONLY with valid JSON:
{
"content_type": "decision | question | task | reference | reflection",
"reasoning": "string",
"urgency": "high | medium | low",
"open_question": "string | null",
"decision_context": "string | null"
}"""


def _log_content_type_distribution(content_type: str) -> None:
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        key = f"noesis:pipeline:content_type:{content_type}"
        r.incr(key)
    except Exception as e:
        logger.warning("Redis content_type counter failed: %s", e)


class ExtractStage(BasePipelineStage):
    async def run(self, page: PageContext, observe: ObserveOutput) -> Tuple[ExtractOutput, int]:
        user_message = (
            f"Page URL: {page.url}\n"
            f"Page title: {page.title}\n"
            f"Observed intent: {observe.intent}\n"
            f"Topic: {observe.topic}\n"
            f"Entities: {', '.join(observe.entities)}\n"
            f"Emotional tone: {observe.emotional_tone}\n"
            f"Page text excerpt:\n{page.page_text[:800]}"
        )
        t0 = time.perf_counter()
        data = await self._call_llm(
            STAGE2_SYSTEM,
            user_message,
            max_tokens=settings.stage2_max_tokens,
            expect_json=True,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if not isinstance(data, dict):
            raise ValueError("Extract stage expected JSON object")
        ctype = str(data.get("content_type", "reference")).lower()
        allowed = {"decision", "question", "task", "reference", "reflection"}
        if ctype not in allowed:
            ctype = "reference"
        urgency = str(data.get("urgency", "medium")).lower()
        if urgency not in ("high", "medium", "low"):
            urgency = "medium"
        oq = data.get("open_question")
        dc = data.get("decision_context")
        out = ExtractOutput(
            content_type=ctype,
            reasoning=str(data.get("reasoning", "")).strip(),
            urgency=urgency,
            open_question=str(oq).strip() if oq not in (None, "", "null") else None,
            decision_context=str(dc).strip() if dc not in (None, "", "null") else None,
        )
        _log_content_type_distribution(out.content_type)
        return out, latency_ms
