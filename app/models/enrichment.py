from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WebSearchResult(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""


class EnrichedProfile(BaseModel):
    website: str | None = None
    description: str | None = None
    services: list[str] = Field(default_factory=list)
    estimated_employees: int | None = None
    years_in_business: int | None = None
    signals: list[str] = Field(default_factory=list)
    contact_emails: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none", "error"] = "none"
    scraped_chars: int = 0
    error_message: str | None = None


class RelevanceScore(BaseModel):
    score: int = 0
    reasoning: str = ""
    pain_points: list[str] = Field(default_factory=list)
    outreach_priority: Literal["high", "medium", "low"] = "low"
