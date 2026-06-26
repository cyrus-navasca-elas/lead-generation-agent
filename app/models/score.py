from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.company import Company
from app.models.contact import Contact
from app.models.signal import Signal


class ScoreBreakdown(BaseModel):
    rule_id: str
    label: str
    points: int


class ProspectSummary(BaseModel):
    fit_reason: str = ""
    pain_points: list[str] = Field(default_factory=list)
    erp_relevance: str = ""
    recommended_contacts: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class ScoredCompany(BaseModel):
    company: Company
    contacts: list[Contact] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    breakdown: list[ScoreBreakdown] = Field(default_factory=list)
    total_score: int = 0
    summary: ProspectSummary | None = None
