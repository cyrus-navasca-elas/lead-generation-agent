from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.company import SourceName

RunStatus = Literal[
    "queued",
    "planning",
    "retrieving",
    "enriching",
    "scoring",
    "summarizing",
    "exporting",
    "done",
    "error",
]


class RunRequest(BaseModel):
    objective: str
    source: SourceName = "zoominfo"
    icp_id: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    max_companies: int | None = None


class RunCounts(BaseModel):
    companies_planned: int = 0
    companies_retrieved: int = 0
    contacts_retrieved: int = 0
    companies_scored: int = 0
    companies_summarized: int = 0


class RunArtifacts(BaseModel):
    excel: str | None = None
    json_export: str | None = None
    log: str | None = None
    manifest: str | None = None


class RunState(BaseModel):
    run_id: str
    status: RunStatus = "queued"
    objective: str
    source: SourceName = "zoominfo"
    icp_id: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    counts: RunCounts = Field(default_factory=RunCounts)
    error: str | None = None
    artifacts: RunArtifacts = Field(default_factory=RunArtifacts)


class RunSummary(BaseModel):
    """Lightweight projection of RunState used in list responses."""

    run_id: str
    status: RunStatus
    objective: str
    source: SourceName
    created_at: datetime
    finished_at: datetime | None
    counts: RunCounts
