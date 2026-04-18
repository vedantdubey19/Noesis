from __future__ import annotations

import logging
import time
from typing import Tuple

from app.core.config import settings
from app.services.pipeline.base import (
    BasePipelineStage,
    ContextCard,
    ExtractOutput,
    ObserveOutput,
    PageContext,
    RelateOutput,
    SurfaceOutput,
)

logger = logging.getLogger(__name__)

STAGE4_SYSTEM = """You are Noesis — a personal AI that silently monitors what a knowledge worker
is doing and surfaces the most relevant context from their past notes and emails.
Your output appears as cards in a Chrome extension popup. The user has NOT asked
you anything — you are proactively surfacing what they might need right now.
Rules for context cards:

Maximum 3 cards. Fewer is better — only surface cards that are genuinely useful.
Each card text must be under 200 characters
Be specific, not generic. "You decided to use Redis over Memcached in March
because of pub/sub requirements" is good. "You have notes about caching" is bad.
Card types:
past_decision: A relevant decision the user made previously
related_note: A note or document directly relevant to current work
open_question: A question the user previously left unanswered
person_context: Something relevant about a person mentioned on the page
suggested_action: One optional sentence starting with "You might want to..."
Only include if there's a genuinely useful action to suggest.
summary: One sentence explaining what Noesis is showing and why.
Example: "Surfacing 2 past decisions about API design based on your current work."

Respond ONLY with valid JSON:
{
"context_cards": [
{
"text": "string (max 200 chars)",
"doc_title": "string",
"doc_url": "string",
"source": "notion | gmail",
"relevance_score": 0.0,
"card_type": "past_decision | related_note | open_question | person_context"
}
],
"summary": "string",
"suggested_action": "string | null"
}"""


def _fallback_cards(relate: RelateOutput) -> SurfaceOutput:
    cards: list[ContextCard] = []
    for ch in relate.retrieved_chunks[:3]:
        if ch.relevance_score < 0.5:
            continue
        cards.append(
            ContextCard(
                text=(ch.text or "")[:200],
                doc_title=ch.doc_title,
                doc_url=ch.doc_url,
                source=ch.source,
                relevance_score=ch.relevance_score,
                card_type="related_note",
            )
        )
    summary = (
        f"Surfacing {len(cards)} items from your knowledge base."
        if cards
        else "No relevant context found in your knowledge base for this page."
    )
    return SurfaceOutput(context_cards=cards, summary=summary, suggested_action=None)


class SurfaceStage(BasePipelineStage):
    async def run(
        self,
        page: PageContext,
        observe: ObserveOutput,
        extract: ExtractOutput,
        relate: RelateOutput,
    ) -> Tuple[SurfaceOutput, int]:
        if not relate.retrieved_chunks:
            return (
                SurfaceOutput(
                    context_cards=[],
                    summary="No relevant context found in your knowledge base for this page.",
                    suggested_action=None,
                ),
                0,
            )

        card_sections: list[str] = []
        for ch in relate.retrieved_chunks[:5]:
            excerpt = (ch.text or "")[:400].replace("\n", " ")
            card_sections.append(
                f"[Score: {ch.relevance_score:.2f}] {ch.source.upper()} — {ch.doc_title}\n{excerpt}"
            )
        user_message = (
            f"What the user is doing right now:\n"
            f"URL: {page.url}\n"
            f"Title: {page.title}\n"
            f"Activity type: {extract.content_type}\n"
            f"Intent: {observe.intent}\n"
            f"Urgency: {extract.urgency}\n"
            f"Most relevant chunks from their knowledge base:\n"
            + "\n\n".join(card_sections)
            + "\n\nGenerate 1-3 context cards. Only include cards with relevance_score >= 0.5.\n"
            "If no chunks are relevant enough, return an empty context_cards array."
        )
        if extract.content_type == "reference" and extract.urgency == "low":
            user_message += "\n\nThe user is casually reading reference material with low urgency — surface at most 1 card."

        t0 = time.perf_counter()
        data = await self._call_llm(
            STAGE4_SYSTEM,
            user_message,
            max_tokens=settings.stage4_max_tokens,
            expect_json=True,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if not isinstance(data, dict):
            raise ValueError("Surface stage expected JSON object")

        raw_cards = data.get("context_cards") or []
        cards: list[ContextCard] = []
        if isinstance(raw_cards, list):
            for item in raw_cards:
                if not isinstance(item, dict):
                    continue
                try:
                    score = float(item.get("relevance_score", 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                if score < 0.5:
                    continue
                text = str(item.get("text", ""))[:200]
                ctype = str(item.get("card_type", "related_note"))
                if ctype not in (
                    "past_decision",
                    "related_note",
                    "open_question",
                    "person_context",
                ):
                    ctype = "related_note"
                cards.append(
                    ContextCard(
                        text=text,
                        doc_title=str(item.get("doc_title", "")),
                        doc_url=str(item.get("doc_url", "")),
                        source=str(item.get("source", "notion")),
                        relevance_score=score,
                        card_type=ctype,
                    )
                )

        cards = [c for c in cards if c.relevance_score >= 0.5]
        cards.sort(key=lambda c: c.relevance_score, reverse=True)
        max_cards = 1 if extract.content_type == "reference" and extract.urgency == "low" else 3
        cards = cards[:max_cards]

        summary = str(data.get("summary", "")).strip() or (
            f"Surfacing {len(cards)} context cards based on your current page."
            if cards
            else "No relevant context found in your knowledge base for this page."
        )
        sa = data.get("suggested_action")
        suggested = str(sa).strip() if sa not in (None, "", "null") else None

        return (
            SurfaceOutput(context_cards=cards, summary=summary, suggested_action=suggested),
            latency_ms,
        )
