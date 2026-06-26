from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enrichment import WebSearchResult

log = get_logger(__name__)


class TavilyClient:
    """Async Tavily search client.

    Tavily API docs: https://docs.tavily.com/docs/rest-api/api-reference
    """

    def __init__(self, settings: Settings):
        self.api_key = settings.tavily_api_key
        self.base_url = settings.tavily_base_url.rstrip("/")

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, k: int = 3) -> list[WebSearchResult]:
        if not self.api_key:
            log.warning("tavily.missing_key")
            return []
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": k,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.post(f"{self.base_url}/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            log.warning("tavily.search_failed", query=query, error=str(exc))
            return []
        results = []
        for item in data.get("results", [])[:k]:
            results.append(
                WebSearchResult(
                    url=item.get("url", ""),
                    title=item.get("title", "") or "",
                    snippet=item.get("content", "") or "",
                )
            )
        log.info("tavily.search", query=query, hits=len(results))
        return results
