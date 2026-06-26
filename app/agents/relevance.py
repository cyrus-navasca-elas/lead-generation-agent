from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.company import Company
from app.models.enrichment import EnrichedProfile, RelevanceScore
from app.models.icp import ICP

log = get_logger(__name__)


class RelevanceAgent:
    def __init__(self, settings: Settings, openai_client):
        self.settings = settings
        self.openai = openai_client
        self._prompt = _load_prompt(
            settings.prompts_path / "relevance.md", _DEFAULT_RELEVANCE_PROMPT
        )

    async def score(
        self,
        company: Company,
        profile: EnrichedProfile,
        *,
        objective: str,
        icp: ICP | None,
    ) -> RelevanceScore:
        icp_dump = icp.model_dump() if icp else None
        user = (
            f"OBJECTIVE: {objective}\n"
            f"ICP: {icp_dump}\n\n"
            f"COMPANY:\n"
            f"  name: {company.name}\n"
            f"  city: {company.location}\n"
            f"  county: {company.county}\n"
            f"  business_type: {company.business_type}\n"
            f"  license_classifications: {company.license_classifications}\n"
            f"  bond_amount: {company.bond_amount}\n"
            f"  license_status: {company.license_status}\n\n"
            f"ENRICHED:\n"
            f"  website: {profile.website}\n"
            f"  description: {profile.description}\n"
            f"  services: {profile.services}\n"
            f"  estimated_employees: {profile.estimated_employees}\n"
            f"  years_in_business: {profile.years_in_business}\n"
            f"  signals: {profile.signals}\n"
            f"  contact_emails: {profile.contact_emails}\n"
            f"  confidence: {profile.confidence}\n\n"
            "Score this prospect for an agentic ERP outreach campaign. "
            "Return JSON: {score (0-100 int), reasoning (1-2 sentences), "
            'pain_points (3 short strings), outreach_priority ("high"|"medium"|"low")}.'
        )
        try:
            resp = await self.openai.chat.completions.create(
                model=self.settings.openai_relevance_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._prompt},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as exc:
            log.warning("agent.relevance.failed", company=company.name, error=str(exc))
            return RelevanceScore(score=0, reasoning=f"error: {exc}", outreach_priority="low")

        score = _clamp(int(data.get("score") or 0), 0, 100)
        priority = data.get("outreach_priority") or _priority_for(score)
        if priority not in ("high", "medium", "low"):
            priority = _priority_for(score)
        return RelevanceScore(
            score=score,
            reasoning=str(data.get("reasoning") or "").strip(),
            pain_points=[str(p).strip() for p in (data.get("pain_points") or []) if p],
            outreach_priority=priority,
        )


def _priority_for(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _load_prompt(path: Path, default: str) -> str:
    try:
        return path.read_text()
    except Exception:
        return default


_DEFAULT_RELEVANCE_PROMPT = """You score B2B prospects for an agentic ERP \
vendor. The product unifies operations, finance, payroll, AR/AP, job-cost, and \
compliance workflows in one platform — strongest fit when a business has \
fragmented tools (QuickBooks + spreadsheets + DocuSign), multi-site or \
multi-trade ops, growth signals, or compliance-heavy operations.

Score 0-100:
- 80-100: Clear ICP match, evidence of growth/multi-site/multi-trade, modern web presence, sized for a real ERP buy.
- 50-79: Plausible fit, some positive signals, but missing evidence or borderline size.
- 20-49: Weak fit — solo operator, niche service, no growth signal, or off-ICP.
- 0-19: Bad fit, defunct, or no info.

Be decisive. Reasoning must reference specific facts. Return JSON only.
"""
