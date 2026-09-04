"""Real SearchProvider over the Tavily HTTP API. Constructed only when a
kind=research role declares provider: tavily; validate_registry fails closed at
boot if TAVILY_API_KEY is unreachable, so this never runs without a key."""

from __future__ import annotations

import os

import httpx

from .protocol import FetchedPage, SearchHit, SearchProvider

_SEARCH_URL = "https://api.tavily.com/search"
_EXTRACT_URL = "https://api.tavily.com/extract"


class TavilyProvider(SearchProvider):
    def __init__(self, api_key: str | None = None, timeout_s: float = 30.0) -> None:
        self._key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self._timeout = timeout_s

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                _SEARCH_URL, json={"api_key": self._key, "query": query, "max_results": max_results}
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchHit(url=r.get("url", ""), title=r.get("title", ""), snippet=r.get("content", ""))
            for r in data.get("results", [])
            if r.get("url")
        ]

    async def fetch(self, url: str) -> FetchedPage:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(_EXTRACT_URL, json={"api_key": self._key, "urls": [url]})
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results") or []
        text = results[0].get("raw_content", "") if results else ""
        return FetchedPage(url=url, text=text)
