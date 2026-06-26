from __future__ import annotations

from typing import Protocol

from app.models.company import Company, Scoop
from app.models.contact import Contact
from app.models.plan import SearchPlan


class LeadSource(Protocol):
    """A pluggable data source for the lead generation pipeline.

    Both `ZoomInfoClient` and `CSLBClient` conform structurally. Sources that
    don't have a particular signal (e.g. CSLB has no scoops/news) return
    an empty list or no-op.
    """

    name: str

    async def search_companies(
        self, plan: SearchPlan, *, limit: int
    ) -> list[Company]: ...

    async def enrich_company(self, company: Company) -> Company: ...

    async def search_contacts(
        self,
        company_id: str,
        *,
        limit: int = 10,
    ) -> list[Contact]: ...

    async def fetch_scoops(self, company_id: str) -> list[Scoop]: ...
