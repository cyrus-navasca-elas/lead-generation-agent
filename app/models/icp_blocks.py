from __future__ import annotations

from pydantic import BaseModel, Field


class ZoomInfoICPBlock(BaseModel):
    technologies_present: list[str] = Field(default_factory=list)
    technologies_absent: list[str] = Field(default_factory=list)


class CSLBICPBlock(BaseModel):
    classifications: list[str] = Field(default_factory=list)
    business_types: list[str] = Field(default_factory=list)
    counties: list[str] = Field(default_factory=list)
    min_bond_amount: int | None = None
    primary_status: list[str] = Field(default_factory=lambda: ["CLEAR"])
