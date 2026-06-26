from __future__ import annotations

from pydantic import BaseModel


class Contact(BaseModel):
    zoominfo_id: str
    company_zoominfo_id: str
    name: str
    title: str | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None
