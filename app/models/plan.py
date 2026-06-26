from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.icp_blocks import CSLBICPBlock, ZoomInfoICPBlock


class SearchPlan(BaseModel):
    industries: list[str] = Field(default_factory=list)
    employee_min: int | None = None
    employee_max: int | None = None
    revenue_min: int | None = None
    revenue_max: int | None = None
    technologies: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)

    zoominfo: ZoomInfoICPBlock | None = None
    cslb: CSLBICPBlock | None = None

    rationale: str = ""
