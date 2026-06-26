from __future__ import annotations

from datetime import date, timedelta

from app.models.company import Company
from app.models.signal import Signal

LEGACY_ERP_VENDORS = {"netsuite", "oracle", "sap", "microsoft dynamics", "infor"}
TARGET_TECH_SIGNALS = {
    "salesforce": ("uses_salesforce", "Uses Salesforce"),
    "hubspot": ("uses_hubspot", "Uses HubSpot"),
    "netsuite": ("uses_netsuite", "Uses NetSuite"),
    "oracle": ("uses_oracle", "Uses Oracle"),
    "sap": ("uses_sap", "Uses SAP"),
    "microsoft dynamics": ("uses_dynamics", "Uses Microsoft Dynamics"),
}

HIRING_KEYWORDS = {
    "revops": ("hiring_revops", "Hiring RevOps"),
    "revenue operations": ("hiring_revops", "Hiring RevOps"),
    "erp administrator": ("hiring_erp_admin", "Hiring ERP Administrator"),
    "erp admin": ("hiring_erp_admin", "Hiring ERP Administrator"),
    "director of erp": ("hiring_erp_admin", "Hiring Director of ERP"),
    "cio": ("hiring_cio", "Hiring CIO"),
    "vp of it": ("hiring_vp_it", "Hiring VP of IT"),
}

CORP_LLC_BUSINESS_TYPES = {"corporation", "limited liability"}


def extract_signals(company: Company, *, large_bond_threshold: int = 25000) -> list[Signal]:
    """Deterministic signal extraction.

    Branches on `company.source` — ZoomInfo and CSLB have disjoint signal sets,
    but both flow into the same scoring engine.
    """
    if company.source == "cslb":
        return _extract_cslb(company, large_bond_threshold=large_bond_threshold)
    return _extract_zoominfo(company)


def _extract_zoominfo(company: Company) -> list[Signal]:
    signals: dict[str, Signal] = {}

    def add(key: str, label: str, source: str, confidence: float = 1.0) -> None:
        if key not in signals:
            signals[key] = Signal(
                key=key, label=label, source=source, confidence=confidence
            )

    tech_lower = {t.lower() for t in company.technologies}
    for vendor, (key, label) in TARGET_TECH_SIGNALS.items():
        if vendor in tech_lower:
            add(key, label, source="zoominfo.tech")

    if tech_lower & LEGACY_ERP_VENDORS:
        add("uses_legacy_erp", "Uses legacy ERP", source="zoominfo.tech")

    if (company.location_count or 0) >= 2:
        add("multi_location", "Multiple locations", source="zoominfo.firmographic")

    if (company.growth_rate or 0) >= 0.20:
        add(
            "high_growth",
            f"Growth {(company.growth_rate or 0) * 100:.0f}% YoY",
            source="zoominfo.firmographic",
        )

    for scoop in company.scoops:
        text = f"{scoop.title} {scoop.detail or ''}".lower()
        if scoop.category == "funding":
            add("recent_funding", scoop.title, source="zoominfo.scoops", confidence=0.95)
        if scoop.category == "expansion":
            add("expansion", scoop.title, source="zoominfo.scoops", confidence=0.9)
        if scoop.category == "hiring":
            for needle, (key, label) in HIRING_KEYWORDS.items():
                if needle in text:
                    add(key, label, source="zoominfo.scoops", confidence=0.9)

    return list(signals.values())


def _extract_cslb(company: Company, *, large_bond_threshold: int) -> list[Signal]:
    signals: dict[str, Signal] = {}

    def add(key: str, label: str, source: str, confidence: float = 1.0) -> None:
        if key not in signals:
            signals[key] = Signal(
                key=key, label=label, source=source, confidence=confidence
            )

    if (company.license_status or "").upper() == "CLEAR":
        add("clear_status", "License status CLEAR", source="cslb.license")

    if company.has_workers_comp:
        add("has_workers_comp", "Active workers' comp policy", source="cslb.wc")

    if company.bond_amount:
        add("has_contractor_bond", "Active contractor bond", source="cslb.bond")
        if company.bond_amount >= large_bond_threshold:
            add(
                "large_bond",
                f"Bond ${company.bond_amount:,}",
                source="cslb.bond",
            )

    if len(company.license_classifications) >= 2:
        add(
            "multi_classification",
            f"{len(company.license_classifications)} classifications",
            source="cslb.classifications",
        )

    if (company.business_type or "").lower() in CORP_LLC_BUSINESS_TYPES:
        add(
            "corp_or_llc",
            f"Entity: {company.business_type}",
            source="cslb.entity",
        )

    today = date.today()
    if company.license_reissue_date and company.license_reissue_date >= today - timedelta(days=730):
        add(
            "recent_reissue",
            f"License reissued {company.license_reissue_date.isoformat()}",
            source="cslb.license",
        )

    if (
        company.license_expiration_date
        and company.license_expiration_date <= today + timedelta(days=180)
    ):
        add(
            "expiring_soon",
            f"License expires {company.license_expiration_date.isoformat()}",
            source="cslb.license",
        )

    return list(signals.values())
