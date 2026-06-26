from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.agents.enrich import EnrichAgent
from app.agents.relevance import RelevanceAgent
from app.core.logging import get_logger
from app.models.enrichment import EnrichedProfile, RelevanceScore
from app.models.icp import ICP
from app.models.score import ScoredCompany

log = get_logger(__name__)


@dataclass
class EnrichmentOutput:
    profiles: dict[str, EnrichedProfile]
    relevance: dict[str, RelevanceScore]


async def enrich_top_k(
    scored: list[ScoredCompany],
    *,
    enrich_agent: EnrichAgent,
    relevance_agent: RelevanceAgent,
    objective: str,
    icp: ICP | None,
    top_k: int,
    max_concurrency: int,
) -> EnrichmentOutput:
    targets = scored[:top_k]
    if not targets:
        return EnrichmentOutput(profiles={}, relevance={})

    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _one(item: ScoredCompany) -> tuple[str, EnrichedProfile, RelevanceScore | None]:
        async with sem:
            company = item.company
            try:
                profile = await enrich_agent.enrich(company)
            except Exception as exc:
                log.warning("enrich.exception", company=company.name, error=str(exc))
                profile = EnrichedProfile(confidence="error", error_message=str(exc))

            relevance: RelevanceScore | None = None
            if profile.confidence not in ("error",):
                try:
                    relevance = await relevance_agent.score(
                        company,
                        profile,
                        objective=objective,
                        icp=icp,
                    )
                except Exception as exc:
                    log.warning(
                        "relevance.exception", company=company.name, error=str(exc)
                    )
            return company.zoominfo_id, profile, relevance

    results = await asyncio.gather(*[_one(t) for t in targets])

    profiles: dict[str, EnrichedProfile] = {}
    relevance_map: dict[str, RelevanceScore] = {}
    for key, profile, rel in results:
        profiles[key] = profile
        if rel is not None:
            relevance_map[key] = rel
    return EnrichmentOutput(profiles=profiles, relevance=relevance_map)


def blend(base_score: int, relevance: int | None, alpha: float) -> int:
    if relevance is None:
        return base_score
    alpha = max(0.0, min(1.0, alpha))
    return int(round(alpha * base_score + (1.0 - alpha) * relevance))
