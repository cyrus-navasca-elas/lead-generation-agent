from __future__ import annotations

from app.clients.llm import LLMClient
from app.models.company import SourceName
from app.models.icp import ICP
from app.models.plan import SearchPlan


async def plan_search(
    llm: LLMClient,
    objective: str,
    icp: ICP | None,
    filters: dict,
    *,
    source: SourceName = "zoominfo",
) -> SearchPlan:
    return await llm.plan_search(
        objective=objective, icp=icp, filters=filters, source=source
    )
