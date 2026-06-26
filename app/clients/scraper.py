from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)

ABOUT_PATTERNS = ("about", "services", "company", "who-we-are", "what-we-do")
USER_AGENT = (
    "Mozilla/5.0 (compatible; LeadGenAgent/0.1; +https://example.com/bot)"
)


@dataclass
class ScrapedPage:
    url: str
    text: str


@dataclass
class ScrapeResult:
    pages: list[ScrapedPage]

    @property
    def combined_text(self) -> str:
        return "\n\n".join(f"# {p.url}\n{p.text}" for p in self.pages)

    @property
    def total_chars(self) -> int:
        return sum(len(p.text) for p in self.pages)


class Scraper:
    def __init__(self, settings: Settings):
        self.timeout = settings.scrape_timeout_seconds
        self.max_bytes = settings.scrape_max_bytes

    async def scrape(self, url: str) -> ScrapeResult:
        if not url:
            return ScrapeResult(pages=[])
        pages: list[ScrapedPage] = []
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"user-agent": USER_AGENT},
        ) as http:
            home = await self._fetch_clean(http, url)
            if home is None:
                return ScrapeResult(pages=[])
            home_html, home_url = home
            pages.append(ScrapedPage(url=home_url, text=self._extract_text(home_html)))

            secondary = self._find_about_link(home_html, home_url)
            if secondary and secondary != home_url:
                sub = await self._fetch_clean(http, secondary)
                if sub is not None:
                    sub_html, sub_url = sub
                    pages.append(ScrapedPage(url=sub_url, text=self._extract_text(sub_html)))

        result = ScrapeResult(pages=pages)
        log.info("scraper.done", url=url, pages=len(pages), chars=result.total_chars)
        return result

    async def _fetch_clean(self, http: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
        try:
            resp = await http.get(url)
        except Exception as exc:
            log.info("scraper.fetch_failed", url=url, error=str(exc))
            return None
        if resp.status_code >= 400:
            log.info("scraper.fetch_status", url=url, status=resp.status_code)
            return None
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type.lower():
            return None
        body = resp.text[: self.max_bytes * 3]  # html is verbose; trim raw too
        return body, str(resp.url)

    def _extract_text(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return text[: self.max_bytes]

    def _find_about_link(self, html: str, base_url: str) -> str | None:
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
        base_host = urlparse(base_url).netloc
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            label = (a.get_text() or "").strip().lower()
            target = urljoin(base_url, href)
            target_host = urlparse(target).netloc
            if target_host and target_host != base_host:
                continue
            for needle in ABOUT_PATTERNS:
                if needle in href.lower() or needle in label:
                    return target
        return None
