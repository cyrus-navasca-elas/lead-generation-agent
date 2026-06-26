from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.clients.source import LeadSource
from app.core.logging import get_logger
from app.models.company import Company
from app.models.contact import Contact
from app.models.plan import SearchPlan

log = get_logger(__name__)


@dataclass
class RetrievalResult:
    companies: list[Company]
    contacts_by_company: dict[str, list[Contact]]


async def retrieve(
    client: LeadSource,
    plan: SearchPlan,
    *,
    max_companies: int,
    max_concurrency: int,
) -> RetrievalResult:
    companies = await client.search_companies(plan, limit=max_companies)
    log.info("retrieval.search_companies", count=len(companies))

    sem = asyncio.Semaphore(max_concurrency)

    async def _per_company(company: Company) -> tuple[Company, list[Contact]]:
        async with sem:
            enriched = await client.enrich_company(company)
            scoops = await client.fetch_scoops(company.zoominfo_id)
            enriched.scoops = scoops
            contacts = await client.search_contacts(
                company.zoominfo_id, limit=10
            )
            return enriched, contacts

    results = await asyncio.gather(*(_per_company(c) for c in companies))

    enriched_companies: list[Company] = []
    contacts_by_company: dict[str, list[Contact]] = {}
    seen: set[str] = set()
    for company, contacts in results:
        if company.zoominfo_id in seen:
            continue
        seen.add(company.zoominfo_id)
        enriched_companies.append(company)
        contacts_by_company[company.zoominfo_id] = contacts

    total_contacts = sum(len(v) for v in contacts_by_company.values())
    log.info(
        "retrieval.enriched",
        companies=len(enriched_companies),
        contacts=total_contacts,
    )
    return RetrievalResult(
        companies=enriched_companies,
        contacts_by_company=contacts_by_company,
    )
