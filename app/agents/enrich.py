from __future__ import annotations

import json
from pathlib import Path

from app.clients.scraper import ScrapeResult, Scraper
from app.clients.web_search import TavilyClient
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.company import Company
from app.models.enrichment import EnrichedProfile, WebSearchResult

log = get_logger(__name__)


def _domain_score(url: str) -> int:
    """Lower is better — prefer business-looking domains over directories."""
    bad = (
        "yelp.com",
        "bbb.org",
        "yellowpages",
        "manta.com",
        "facebook.com",
        "linkedin.com",
        "indeed.com",
        "buzzfile",
        "glassdoor",
        "instagram.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "trustpilot",
        "angi.com",
        "homeadvisor",
        "thumbtack",
        "google.com",
        "bing.com",
    )
    for needle in bad:
        if needle in url.lower():
            return 1
    return 0


def _pick_homepage(results: list[WebSearchResult]) -> WebSearchResult | None:
    if not results:
        return None
    ranked = sorted(results, key=lambda r: (_domain_score(r.url), results.index(r)))
    return ranked[0]


class EnrichAgent:
    def __init__(
        self,
        settings: Settings,
        web: TavilyClient,
        scraper: Scraper,
        openai_client,
    ):
        self.settings = settings
        self.web = web
        self.scraper = scraper
        self.openai = openai_client
        self._extract_prompt = _load_prompt(
            settings.prompts_path / "extract.md", _DEFAULT_EXTRACT_PROMPT
        )

    async def enrich(self, company: Company) -> EnrichedProfile:
        query = _build_query(company)
        log.info("agent.search.start", company=company.name, query=query)
        results = await self.web.search(query, k=4)
        if not results:
            return EnrichedProfile(confidence="none")

        pick = _pick_homepage(results)
        if pick is None:
            return EnrichedProfile(confidence="none")

        log.info("agent.scrape.start", company=company.name, url=pick.url)
        scrape: ScrapeResult = await self.scraper.scrape(pick.url)
        if not scrape.pages:
            return EnrichedProfile(
                website=pick.url, confidence="low", scraped_chars=0
            )

        log.info(
            "agent.extract.start",
            company=company.name,
            chars=scrape.total_chars,
        )
        try:
            data = await self._extract(company, scrape.combined_text, pick)
        except Exception as exc:
            log.warning(
                "agent.extract.failed", company=company.name, error=str(exc)
            )
            return EnrichedProfile(
                website=pick.url,
                confidence="error",
                error_message=str(exc),
                scraped_chars=scrape.total_chars,
            )

        profile = EnrichedProfile(
            website=data.get("website") or pick.url,
            description=_clean_str(data.get("description")),
            services=_as_list(data.get("services")),
            estimated_employees=_as_int(data.get("estimated_employees")),
            years_in_business=_as_int(data.get("years_in_business")),
            signals=_as_list(data.get("signals")),
            contact_emails=_as_list(data.get("contact_emails")),
            confidence=_normalize_conf(data.get("confidence")),
            scraped_chars=scrape.total_chars,
        )
        log.info(
            "agent.extract.done",
            company=company.name,
            confidence=profile.confidence,
        )
        return profile

    async def _extract(
        self, company: Company, page_text: str, hit: WebSearchResult
    ) -> dict:
        user = (
            f"COMPANY (from CSLB license data):\n"
            f"  name: {company.name}\n"
            f"  city: {company.location}\n"
            f"  county: {company.county}\n"
            f"  license_classifications: {company.license_classifications}\n"
            f"  business_type: {company.business_type}\n\n"
            f"WEB SEARCH TOP RESULT:\n"
            f"  url: {hit.url}\n"
            f"  title: {hit.title}\n"
            f"  snippet: {hit.snippet}\n\n"
            f"SCRAPED PAGES:\n{page_text[:12000]}\n\n"
            "Return JSON with: website, description, services[], "
            "estimated_employees, years_in_business, signals[] "
            "(growth/hiring/expansion cues seen in text), contact_emails[], "
            'confidence ("high"|"medium"|"low"|"none").'
        )
        resp = await self.openai.chat.completions.create(
            model=self.settings.openai_extract_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._extract_prompt},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)


def _build_query(company: Company) -> str:
    parts = [company.name]
    if company.location:
        parts.append(company.location)
    if company.county:
        parts.append(f"{company.county} County")
    if company.license_classifications:
        parts.append(_class_label(company.license_classifications[0]))
    parts.append("California contractor")
    return " ".join(p for p in parts if p)


def _class_label(code: str) -> str:
    table = {
        "C10": "electrical",
        "C36": "plumbing",
        "C20": "HVAC",
        "B": "general contractor",
        "C39": "roofing",
        "C46": "solar",
        "C8": "concrete",
        "C33": "painting",
        "C27": "landscaping",
        "C57": "well drilling",
        "C6": "cabinet maker",
    }
    return table.get(code.upper().replace("-", ""), code)


def _clean_str(value) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    return s or None


def _as_list(value) -> list[str]:
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
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _normalize_conf(value) -> str:
    v = (str(value) or "").lower()
    if v in ("high", "medium", "low", "none"):
        return v
    return "low"


def _load_prompt(path: Path, default: str) -> str:
    try:
        return path.read_text()
    except Exception:
        return default


_DEFAULT_EXTRACT_PROMPT = """You extract structured facts about a small/mid \
business from scraped website text. Be conservative — if a field is not clearly \
supported by the text, omit it or set to null. Do not invent employee counts or \
founding years. Prefer facts visible on About/Services pages. Return JSON only.
"""
