from __future__ import annotations

import re
from typing import Protocol

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.company import Company, SourceName
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.icp_blocks import CSLBICPBlock, ZoomInfoICPBlock
from app.models.plan import SearchPlan
from app.models.score import ProspectSummary, ScoreBreakdown
from app.models.signal import Signal

log = get_logger(__name__)


class LLMClient(Protocol):
    async def plan_search(
        self,
        objective: str,
        icp: ICP | None,
        filters: dict,
        *,
        source: SourceName = "zoominfo",
    ) -> SearchPlan: ...

    async def summarize_prospect(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[Signal],
        breakdown: list[ScoreBreakdown],
        total_score: int,
        *,
        enriched: dict | None = None,
        relevance_reasoning: str | None = None,
    ) -> ProspectSummary: ...


class FakeLLMClient:
    """Deterministic planner + summarizer for Phase 1.

    Branches by `source`. ZoomInfo path: keyword-sniff industries/tech and
    merge with ICP/filters. CSLB path: read the ICP.cslb block + filters
    overrides, emit a `plan.cslb` populated SearchPlan.
    """

    KEYWORD_INDUSTRIES = {
        "manufactur": "Manufacturing",
        "machinery": "Industrial Machinery",
        "industrial": "Industrial Machinery",
    }
    KEYWORD_TECH = {
        "salesforce": "Salesforce",
        "netsuite": "NetSuite",
        "oracle": "Oracle",
        "sap": "SAP",
        "dynamics": "Microsoft Dynamics",
        "hubspot": "HubSpot",
    }

    CSLB_OBJECTIVE_CLASSIFICATIONS = {
        "electric": "C10",
        "c-10": "C10",
        "c10": "C10",
        "plumb": "C36",
        "hvac": "C20",
        "general building": "B",
        "general contractor": "B",
        "roofing": "C39",
        "solar": "C46",
        "concrete": "C8",
        "painting": "C33",
        "landscaping": "C27",
    }

    async def plan_search(
        self,
        objective: str,
        icp: ICP | None,
        filters: dict,
        *,
        source: SourceName = "zoominfo",
    ) -> SearchPlan:
        if source == "cslb":
            return self._plan_cslb(objective, icp, filters)
        return self._plan_zoominfo(objective, icp, filters)

    def _plan_zoominfo(
        self, objective: str, icp: ICP | None, filters: dict
    ) -> SearchPlan:
        obj_lower = (objective or "").lower()

        industries = list(filters.get("industries") or (icp.industries if icp else []))
        if not industries:
            industries = [
                label
                for kw, label in self.KEYWORD_INDUSTRIES.items()
                if kw in obj_lower
            ] or ["Manufacturing"]

        technologies = list(
            filters.get("technologies")
            or (icp.technologies_present if icp else [])
        )
        if not technologies:
            technologies = [
                label for kw, label in self.KEYWORD_TECH.items() if kw in obj_lower
            ]

        geographies = list(
            filters.get("geographies")
            or (icp.geographies if icp else [])
            or ["United States"]
        )

        employee_min = filters.get("employee_min") or (icp.employee_min if icp else None)
        employee_max = filters.get("employee_max") or (icp.employee_max if icp else None)
        revenue_min = filters.get("revenue_min") or (icp.revenue_min if icp else None)
        revenue_max = filters.get("revenue_max") or (icp.revenue_max if icp else None)

        m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*employees", obj_lower)
        if m and not (employee_min or employee_max):
            employee_min = int(m.group(1))
            employee_max = int(m.group(2))

        rationale = (
            f"Target {', '.join(industries)} companies"
            + (f" with {employee_min}-{employee_max} employees" if employee_min and employee_max else "")
            + (f" using {', '.join(technologies)}" if technologies else "")
            + (f" in {', '.join(geographies)}" if geographies else "")
            + "."
        )

        plan = SearchPlan(
            industries=industries,
            employee_min=employee_min,
            employee_max=employee_max,
            revenue_min=revenue_min,
            revenue_max=revenue_max,
            technologies=technologies,
            geographies=geographies,
            zoominfo=ZoomInfoICPBlock(
                technologies_present=technologies,
                technologies_absent=icp.technologies_absent if icp else [],
            ),
            rationale=rationale,
        )
        log.info("fake_llm.plan", source="zoominfo", rationale=plan.rationale)
        return plan

    def _plan_cslb(
        self, objective: str, icp: ICP | None, filters: dict
    ) -> SearchPlan:
        obj_lower = (objective or "").lower()
        cslb_filters = filters.get("cslb") or {}
        block_from_icp = icp.cslb if icp else None

        def pick_list(key: str) -> list[str]:
            value = cslb_filters.get(key)
            if value:
                return list(value)
            if block_from_icp and getattr(block_from_icp, key):
                return list(getattr(block_from_icp, key))
            return []

        classifications = pick_list("classifications")
        if not classifications:
            sniffed: list[str] = []
            for needle, code in self.CSLB_OBJECTIVE_CLASSIFICATIONS.items():
                if needle in obj_lower and code not in sniffed:
                    sniffed.append(code)
            classifications = sniffed

        business_types = pick_list("business_types")
        counties = pick_list("counties")
        primary_status = pick_list("primary_status") or ["CLEAR"]
        min_bond_amount = cslb_filters.get("min_bond_amount")
        if min_bond_amount is None and block_from_icp:
            min_bond_amount = block_from_icp.min_bond_amount

        cslb_block = CSLBICPBlock(
            classifications=classifications,
            business_types=business_types,
            counties=counties,
            min_bond_amount=min_bond_amount,
            primary_status=primary_status,
        )

        rationale_parts = ["Target California contractors"]
        if classifications:
            rationale_parts.append(f"holding {', '.join(classifications)}")
        if business_types:
            rationale_parts.append(f"({', '.join(business_types)})")
        if counties:
            rationale_parts.append(f"in {', '.join(counties)}")
        if min_bond_amount:
            rationale_parts.append(f"with ≥ ${min_bond_amount:,} bond")
        if primary_status:
            rationale_parts.append(f"status {', '.join(primary_status)}")
        rationale = " ".join(rationale_parts) + "."

        plan = SearchPlan(
            industries=icp.industries if icp else [],
            geographies=icp.geographies if icp else ["California"],
            cslb=cslb_block,
            rationale=rationale,
        )
        log.info("fake_llm.plan", source="cslb", rationale=plan.rationale)
        return plan

    async def summarize_prospect(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[Signal],
        breakdown: list[ScoreBreakdown],
        total_score: int,
        *,
        enriched: dict | None = None,
        relevance_reasoning: str | None = None,
    ) -> ProspectSummary:
        if company.source == "cslb":
            return self._summarize_cslb(company, contacts, signals, breakdown, total_score)
        return self._summarize_zoominfo(company, contacts, signals, breakdown, total_score)

    def _summarize_zoominfo(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[Signal],
        breakdown: list[ScoreBreakdown],
        total_score: int,
    ) -> ProspectSummary:
        signal_keys = {s.key for s in signals}
        rule_ids = {b.rule_id for b in breakdown}

        pain_points: list[str] = []
        if "uses_salesforce" in signal_keys:
            pain_points.append("Likely outgrowing Salesforce reporting for operational data.")
        if "uses_legacy_erp" in signal_keys:
            pain_points.append("Carrying legacy ERP technical debt that constrains process change.")
        if "hiring_revops" in signal_keys:
            pain_points.append("Standing up RevOps suggests inconsistent system-of-record across GTM.")
        if "hiring_erp_admin" in signal_keys:
            pain_points.append("Hiring an ERP admin signals an active modernization initiative.")
        if "multi_location" in signal_keys:
            pain_points.append("Multi-site operations multiply data reconciliation overhead.")
        if "recent_funding" in signal_keys:
            pain_points.append("Capital infusion typically pulls forward systems modernization timelines.")

        if not pain_points:
            pain_points.append("Generic operational scaling pressure inferred from headcount and growth.")

        fit_reason = (
            f"{company.name} matches the ICP on industry ({company.industry or 'unknown'}) "
            f"and headcount ({company.employee_count or 'n/a'}), "
            f"with {len(rule_ids)} scoring rules hit."
        )

        erp_relevance = (
            "Our agentic ERP unifies operations, finance, and revenue data in one platform — "
            "directly relieving the pain points above without a multi-year reimplementation."
        )

        ranked_contacts = sorted(
            contacts,
            key=lambda c: _title_priority(c.title or ""),
        )[:3]
        recommended_contacts = [f"{c.name} — {c.title or 'Contact'}" for c in ranked_contacts]

        confidence = "high" if total_score >= 70 else "medium" if total_score >= 40 else "low"

        return ProspectSummary(
            fit_reason=fit_reason,
            pain_points=pain_points,
            erp_relevance=erp_relevance,
            recommended_contacts=recommended_contacts,
            confidence=confidence,
        )

    def _summarize_cslb(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[Signal],
        breakdown: list[ScoreBreakdown],
        total_score: int,
    ) -> ProspectSummary:
        signal_keys = {s.key for s in signals}

        pain_points: list[str] = []
        if "multi_classification" in signal_keys:
            pain_points.append(
                f"{len(company.license_classifications)} active classifications imply "
                "fragmented job-cost tracking across trades."
            )
        if "large_bond" in signal_keys:
            pain_points.append(
                "Sizeable bond amount points to multi-project exposure and compliance overhead."
            )
        if "corp_or_llc" in signal_keys and (company.business_type or "").lower() == "limited liability":
            pain_points.append(
                "LLC at this scale typically lacks integrated financial reporting beyond QuickBooks."
            )
        if "has_workers_comp" in signal_keys:
            pain_points.append(
                "Workers' comp + bond renewals require document workflows that ERPs centralize natively."
            )
        if "expiring_soon" in signal_keys:
            pain_points.append(
                "Imminent license renewal is a natural trigger to revisit back-office tooling."
            )
        if "recent_reissue" in signal_keys:
            pain_points.append(
                "Recent license reissue suggests structural change — ownership, scope, or entity reorg."
            )
        if not pain_points:
            pain_points.append(
                "Active CA contractor with operations spanning multiple compliance regimes."
            )

        classifications_label = company.industry or "Contractor"
        fit_reason = (
            f"{company.name} is an active {company.business_type or 'CA'} contractor "
            f"({classifications_label}) in {company.county or 'California'} with a "
            f"{('$' + format(company.bond_amount, ',')) if company.bond_amount else 'no'} bond. "
            f"{len(breakdown)} scoring rules hit."
        )

        erp_relevance = (
            "Our agentic ERP consolidates job-cost, compliance documents, payroll, and AR/AP — "
            "removing the QuickBooks + spreadsheets + DocuSign sprawl typical of growing CA trades."
        )

        recommended_contacts = [
            f"{c.name} — {c.title or 'Contact'}" for c in contacts[:3]
        ]

        confidence = (
            "high"
            if total_score >= 70
            else "medium"
            if total_score >= 40
            else "low"
        )

        return ProspectSummary(
            fit_reason=fit_reason,
            pain_points=pain_points,
            erp_relevance=erp_relevance,
            recommended_contacts=recommended_contacts,
            confidence=confidence,
        )


_TITLE_RANK = [
    ("ceo", 0),
    ("cio", 1),
    ("cto", 2),
    ("chief information", 1),
    ("vp of operations", 3),
    ("vp of it", 4),
    ("vp of finance", 5),
    ("director of erp", 4),
    ("director of revops", 5),
    ("director of operations", 6),
    ("director of it", 6),
    ("head of operations", 6),
    ("president", 1),
]


def _title_priority(title: str) -> int:
    t = title.lower()
    for needle, rank in _TITLE_RANK:
        if needle in t:
            return rank
    return 99


class RealLLMClient:
    """OpenAI-backed planner + summarizer.

    Uses JSON-mode chat completions; responses are validated against Pydantic
    schemas. On any failure, the call falls back to FakeLLMClient logic so a
    run can still complete without an API.
    """

    def __init__(self, settings: Settings):
        from openai import AsyncOpenAI

        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._fake = FakeLLMClient()
        self._prompts_dir = settings.prompts_path

    def _load_prompt(self, name: str) -> str:
        path = self._prompts_dir / name
        try:
            return path.read_text()
        except Exception:
            return ""

    async def _json_complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
    ) -> dict:
        import json as _json

        resp = await self.client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        return _json.loads(content)

    async def plan_search(
        self,
        objective: str,
        icp: ICP | None,
        filters: dict,
        *,
        source: SourceName = "zoominfo",
    ) -> SearchPlan:
        if not self.settings.openai_api_key:
            return await self._fake.plan_search(
                objective, icp, filters, source=source
            )

        system = self._load_prompt("planner.md") or _DEFAULT_PLANNER_PROMPT
        icp_dump = icp.model_dump() if icp else None
        user = (
            f"SOURCE: {source}\n"
            f"OBJECTIVE: {objective}\n"
            f"ICP: {icp_dump}\n"
            f"FILTERS: {filters}\n\n"
            "Emit a JSON object matching the schema described in the system prompt."
        )

        try:
            data = await self._json_complete(
                model=self.settings.openai_planner_model,
                system=system,
                user=user,
            )
            plan = self._coerce_plan(data, source=source, icp=icp)
            log.info("real_llm.plan", source=source, rationale=plan.rationale)
            return plan
        except Exception as exc:
            log.warning("real_llm.plan_failed", error=str(exc))
            return await self._fake.plan_search(
                objective, icp, filters, source=source
            )

    def _coerce_plan(
        self, data: dict, *, source: SourceName, icp: ICP | None
    ) -> SearchPlan:
        rationale = str(data.get("rationale") or "").strip()
        industries = _as_list_str(data.get("industries"))
        geographies = _as_list_str(data.get("geographies")) or (
            icp.geographies if icp else []
        )
        plan = SearchPlan(
            industries=industries or (icp.industries if icp else []),
            employee_min=_as_int(data.get("employee_min")),
            employee_max=_as_int(data.get("employee_max")),
            revenue_min=_as_int(data.get("revenue_min")),
            revenue_max=_as_int(data.get("revenue_max")),
            technologies=_as_list_str(data.get("technologies")),
            geographies=geographies,
            rationale=rationale,
        )
        if source == "cslb":
            cslb_data = data.get("cslb") or {}
            plan.cslb = CSLBICPBlock(
                classifications=_as_list_str(cslb_data.get("classifications")),
                business_types=_as_list_str(cslb_data.get("business_types")),
                counties=_as_list_str(cslb_data.get("counties")),
                min_bond_amount=_as_int(cslb_data.get("min_bond_amount")),
                primary_status=_as_list_str(cslb_data.get("primary_status"))
                or ["CLEAR"],
            )
        else:
            zi = data.get("zoominfo") or {}
            plan.zoominfo = ZoomInfoICPBlock(
                technologies_present=_as_list_str(zi.get("technologies_present"))
                or plan.technologies,
                technologies_absent=_as_list_str(zi.get("technologies_absent"))
                or (icp.technologies_absent if icp else []),
            )
        return plan

    async def summarize_prospect(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[Signal],
        breakdown: list[ScoreBreakdown],
        total_score: int,
        *,
        enriched: dict | None = None,
        relevance_reasoning: str | None = None,
    ) -> ProspectSummary:
        if not self.settings.openai_api_key:
            return await self._fake.summarize_prospect(
                company, contacts, signals, breakdown, total_score
            )

        system = self._load_prompt("summary.md") or _DEFAULT_SUMMARY_PROMPT
        user = (
            f"COMPANY: {company.model_dump(exclude={'technologies'})}\n"
            f"TECHNOLOGIES: {company.technologies}\n"
            f"SIGNALS: {[s.model_dump() for s in signals]}\n"
            f"BREAKDOWN: {[b.model_dump() for b in breakdown]}\n"
            f"TOTAL_SCORE: {total_score}\n"
            f"ENRICHED_PROFILE: {enriched or {}}\n"
            f"RELEVANCE_REASONING: {relevance_reasoning or ''}\n"
            f"TOP_CONTACTS: {[c.model_dump() for c in contacts[:5]]}\n\n"
            "Emit a JSON object: {fit_reason, pain_points[], erp_relevance,"
            " recommended_contacts[], confidence in {low,medium,high}}."
        )
        try:
            data = await self._json_complete(
                model=self.settings.openai_summary_model,
                system=system,
                user=user,
            )
            confidence = data.get("confidence") or (
                "high" if total_score >= 70 else "medium" if total_score >= 40 else "low"
            )
            if confidence not in ("low", "medium", "high"):
                confidence = "low"
            return ProspectSummary(
                fit_reason=str(data.get("fit_reason") or ""),
                pain_points=_as_list_str(data.get("pain_points")),
                erp_relevance=str(data.get("erp_relevance") or ""),
                recommended_contacts=_as_list_str(data.get("recommended_contacts")),
                confidence=confidence,
            )
        except Exception as exc:
            log.warning("real_llm.summary_failed", error=str(exc), company=company.name)
            return await self._fake.summarize_prospect(
                company, contacts, signals, breakdown, total_score
            )


def _as_list_str(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    return []


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_DEFAULT_PLANNER_PROMPT = """You are a senior B2B sales-ops planner for an agentic ERP vendor. \
Given an objective, an ICP, and source ("cslb" or "zoominfo"), emit a SearchPlan as JSON.

For source="cslb", populate `cslb` with CA contractor filters: classifications (e.g. C10, C36, B), business_types, counties, min_bond_amount, primary_status (default ["CLEAR"]). Include short `rationale`.

For source="zoominfo", populate top-level industries, employee_min/max, revenue_min/max, technologies, geographies. Include short `rationale`.

Return JSON only.
"""

_DEFAULT_SUMMARY_PROMPT = """You write concise B2B prospect briefs for an agentic ERP sales team. \
Given a company, signals, breakdown, enriched_profile, and relevance reasoning, return JSON with:
- fit_reason (one sentence)
- pain_points (3-5 bullet strings, specific to this company)
- erp_relevance (one sentence on how our agentic ERP helps)
- recommended_contacts (up to 3 title strings)
- confidence ("low" | "medium" | "high")

Be specific. Avoid generic boilerplate. Return JSON only.
"""


def build_llm_client(settings: Settings) -> LLMClient:
    """Pick LLM backend. Auto-fallback to FakeLLMClient when no API key."""
    if settings.use_fake_clients or not settings.openai_api_key:
        return FakeLLMClient()
    return RealLLMClient(settings)
