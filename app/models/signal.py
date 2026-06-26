from __future__ import annotations

from pydantic import BaseModel, Field


class Signal(BaseModel):
    key: str
    label: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
