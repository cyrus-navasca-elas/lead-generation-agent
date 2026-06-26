from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class Scoop(BaseModel):
    """Hiring/funding/expansion event surfaced by ZoomInfo Scoops."""

    category: str
    title: str
    detail: str | None = None
    date: str | None = None


SourceName = Literal["zoominfo", "cslb"]


class Company(BaseModel):
    zoominfo_id: str  # historically named — used as the universal company key
    name: str
    source: SourceName = "zoominfo"

    industry: str | None = None
    employee_count: int | None = None
    revenue: int | None = None
    website: str | None = None
    technologies: list[str] = Field(default_factory=list)
    description: str | None = None
    location: str | None = None
    location_count: int | None = None
    growth_rate: float | None = None
    scoops: list[Scoop] = Field(default_factory=list)

    # CSLB-only fields (None for ZoomInfo-sourced rows).
    license_number: str | None = None
    license_classifications: list[str] = Field(default_factory=list)
    license_status: str | None = None
    license_issue_date: date | None = None
    license_expiration_date: date | None = None
    license_reissue_date: date | None = None
    bond_amount: int | None = None
    business_type: str | None = None
    has_workers_comp: bool | None = None
    county: str | None = None

    raw: dict[str, Any] = Field(default_factory=dict)
