from __future__ import annotations

from app.core.config import Settings
from app.models.company import Company, Scoop
from app.models.contact import Contact
from app.models.plan import SearchPlan


class RealZoomInfoClient:
    """Stub — real ZoomInfo integration lands once API access is granted."""

    name: str = "zoominfo"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def search_companies(self, plan: SearchPlan, *, limit: int) -> list[Company]:
        raise NotImplementedError("ZoomInfo client awaiting API access.")

    async def enrich_company(self, company: Company) -> Company:
        raise NotImplementedError("ZoomInfo client awaiting API access.")

    async def search_contacts(
        self, company_id: str, *, limit: int = 10
    ) -> list[Contact]:
        raise NotImplementedError("ZoomInfo client awaiting API access.")

    async def fetch_scoops(self, company_id: str) -> list[Scoop]:
        raise NotImplementedError("ZoomInfo client awaiting API access.")


# Backwards-compat alias for any imports that still reference the old name.
ZoomInfoClient = RealZoomInfoClient


def build_zoominfo_client(settings: Settings) -> RealZoomInfoClient:
    return RealZoomInfoClient(settings)
