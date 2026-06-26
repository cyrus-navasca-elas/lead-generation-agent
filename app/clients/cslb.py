from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import aiosqlite

from app.clients.cslb_ingest import (
    SQL_COLUMNS,
    normalize_classifications,
    parse_iso_date,
)
from app.core.logging import get_logger
from app.models.company import Company, Scoop
from app.models.contact import Contact
from app.models.icp_blocks import CSLBICPBlock
from app.models.plan import SearchPlan

log = get_logger(__name__)


class CSLBClient:
    name: str = "cslb"

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def search_companies(
        self, plan: SearchPlan, *, limit: int
    ) -> list[Company]:
        block = plan.cslb or CSLBICPBlock()

        where: list[str] = []
        params: list[Any] = []

        statuses = block.primary_status or ["CLEAR"]
        where.append(
            "primary_status IN (" + ",".join("?" * len(statuses)) + ")"
        )
        params.extend(statuses)

        if block.counties:
            where.append(
                "county IN (" + ",".join("?" * len(block.counties)) + ")"
            )
            params.extend(block.counties)

        if block.business_types:
            where.append(
                "business_type IN ("
                + ",".join("?" * len(block.business_types))
                + ")"
            )
            params.extend(block.business_types)

        if block.classifications:
            ors = []
            for c in block.classifications:
                norm = normalize_classifications(c)
                token = norm.strip("|")
                if token:
                    ors.append("classifications_norm LIKE ?")
                    params.append(f"%|{token}|%")
            if ors:
                where.append("(" + " OR ".join(ors) + ")")

        if block.min_bond_amount is not None:
            where.append("cb_amount >= ?")
            params.append(block.min_bond_amount)

        # Always require an unexpired license.
        today_iso = date.today().isoformat()
        where.append("(expiration_date IS NULL OR expiration_date >= ?)")
        params.append(today_iso)

        sql = (
            "SELECT " + ", ".join(SQL_COLUMNS) + " FROM licenses "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY cb_amount DESC NULLS LAST, license_no ASC "
            "LIMIT ?"
        )
        params.append(limit)

        # SQLite's NULLS LAST is supported from 3.30+ but to be safe drop it.
        sql = sql.replace("NULLS LAST", "")

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()

        log.info("cslb.search", returned=len(rows), filters=block.model_dump())
        return [self._row_to_company(dict(r)) for r in rows]

    async def enrich_company(self, company: Company) -> Company:
        # CSLB rows are already fully populated by `search_companies`.
        return company.model_copy(deep=True)

    async def search_contacts(
        self,
        company_id: str,
        *,
        limit: int = 10,
    ) -> list[Contact]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT business_name, business_name_2, name_tp_2, "
                "full_business_name, business_phone FROM licenses "
                "WHERE license_no = ? LIMIT 1",
                (company_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return []

        licensee_name = (
            row["name_tp_2"]
            or row["business_name_2"]
            or row["full_business_name"]
            or row["business_name"]
        )
        if not licensee_name:
            return []

        return [
            Contact(
                zoominfo_id=f"CSLB-{company_id}-L1",
                company_zoominfo_id=company_id,
                name=licensee_name.strip(),
                title="Licensee",
                department=None,
                email=None,
                phone=(row["business_phone"] or "").strip() or None,
            )
        ]

    async def fetch_scoops(self, company_id: str) -> list[Scoop]:
        return []

    def _row_to_company(self, row: dict[str, Any]) -> Company:
        classifications = _parse_classifications(row.get("classifications_norm"))
        location_bits = [row.get("city"), row.get("state")]
        location = ", ".join([b for b in location_bits if b]) or None

        return Company(
            zoominfo_id=row["license_no"],
            name=row.get("business_name") or row.get("full_business_name") or "",
            source="cslb",
            industry=_industry_from_classifications(classifications),
            employee_count=None,
            revenue=None,
            website=None,
            technologies=[],
            description=_describe_license(row, classifications),
            location=location,
            location_count=None,
            growth_rate=None,
            license_number=row.get("license_no"),
            license_classifications=classifications,
            license_status=row.get("primary_status"),
            license_issue_date=parse_iso_date(row.get("issue_date")),
            license_expiration_date=parse_iso_date(row.get("expiration_date")),
            license_reissue_date=parse_iso_date(row.get("reissue_date")),
            bond_amount=row.get("cb_amount"),
            business_type=row.get("business_type"),
            has_workers_comp=bool(row.get("wc_insurance_company")),
            county=row.get("county"),
            raw=row,
        )


def _parse_classifications(norm: str | None) -> list[str]:
    if not norm:
        return []
    return [p for p in norm.split("|") if p]


# A small label map for the most common classifications so the Excel/UI shows
# readable industries instead of bare codes. Anything we don't know becomes
# "Contractor — <code>".
_CLASSIFICATION_LABEL = {
    "A": "General Engineering",
    "B": "General Building",
    "B2": "Residential Remodeling",
    "C2": "Insulation",
    "C5": "Framing & Rough Carpentry",
    "C6": "Cabinet & Millwork",
    "C7": "Low Voltage Systems",
    "C8": "Concrete",
    "C9": "Drywall",
    "C10": "Electrical",
    "C12": "Earthwork & Paving",
    "C13": "Fencing",
    "C15": "Flooring",
    "C16": "Fire Protection",
    "C17": "Glazing",
    "C20": "HVAC",
    "C21": "Building Moving/Demolition",
    "C22": "Asbestos Abatement",
    "C27": "Landscaping",
    "C29": "Masonry",
    "C32": "Parking & Highway Improvement",
    "C33": "Painting & Decorating",
    "C35": "Lathing & Plastering",
    "C36": "Plumbing",
    "C39": "Roofing",
    "C42": "Sanitation System",
    "C43": "Sheet Metal",
    "C45": "Sign",
    "C46": "Solar",
    "C47": "General Manufactured Housing",
    "C50": "Reinforcing Steel",
    "C51": "Structural Steel",
    "C53": "Swimming Pool",
    "C54": "Tile",
    "C55": "Water Conditioning",
    "C57": "Well Drilling",
    "C60": "Welding",
    "C61": "Limited Specialty",
    "HAZ": "Hazardous Substances Removal",
    "ASB": "Asbestos",
}


def _industry_from_classifications(classifications: list[str]) -> str | None:
    if not classifications:
        return None
    labels = []
    for code in classifications:
        labels.append(_CLASSIFICATION_LABEL.get(code, f"Contractor ({code})"))
    return " / ".join(labels)


def _describe_license(row: dict[str, Any], classifications: list[str]) -> str:
    bond = row.get("cb_amount")
    bond_str = f"${int(bond):,} bond" if bond else "no contractor bond"
    parts = [
        f"{row.get('business_type') or 'Unknown business type'}",
        f"holding {len(classifications)} classification(s)",
        bond_str,
    ]
    location = row.get("county") or row.get("city")
    if location:
        parts.append(f"in {location}, CA")
    status = row.get("primary_status")
    if status:
        parts.append(f"({status})")
    return ", ".join(parts) + "."
