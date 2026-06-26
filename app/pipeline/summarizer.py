from __future__ import annotations

import asyncio

from app.clients.llm import LLMClient
from app.core.logging import get_logger
from app.models.score import ProspectSummary, ScoredCompany

log = get_logger(__name__)


async def summarize_scored(
    llm: LLMClient,
    scored: list[ScoredCompany],
    *,
    min_score: int,
    max_concurrency: int = 5,
) -> int:
    """Mutates scored entries in place. Returns number summarized."""
    sem = asyncio.Semaphore(max_concurrency)

    async def _one(item: ScoredCompany) -> None:
        if item.total_score < min_score:
            item.summary = None
            return
        async with sem:
            try:
                item.summary = await llm.summarize_prospect(
                    company=item.company,
                    contacts=item.contacts,
                    signals=item.signals,
                    breakdown=item.breakdown,
                    total_score=item.total_score,
                    enriched=(
                        item.enriched_profile.model_dump()
                        if item.enriched_profile
                        else None
                    ),
                    relevance_reasoning=(
                        item.relevance.reasoning if item.relevance else None
                    ),
                )
            except Exception as exc:
                log.warning(
                    "summarizer.error",
                    company=item.company.zoominfo_id,
                    error=str(exc),
                )
                item.summary = ProspectSummary()

    await asyncio.gather(*(_one(s) for s in scored))
    return sum(1 for s in scored if s.summary is not None)
