"""Offline SearchProvider over a canned corpus dir. CI uses this; no test may
require TAVILY_API_KEY. The corpus is a directory with an index.json:

    {"searches": {"<query substring>": ["<url>", ...]},
     "pages":    {"<url>": "<relative filename>.txt"}}

`search` returns hits whose key is a case-insensitive substring of the query."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .protocol import FetchedPage, SearchHit, SearchProvider


def _corpus_dir() -> Path:
    root = os.environ.get("SDLC_RESEARCH_FAKE_CORPUS")
    if not root:
        raise RuntimeError(
            "FakeProvider needs $SDLC_RESEARCH_FAKE_CORPUS pointing at a "
            "corpus directory (index.json + page files)"
        )
    return Path(root)


class FakeProvider(SearchProvider):
    def _index(self) -> dict:
        return json.loads((_corpus_dir() / "index.json").read_text(encoding="utf-8"))

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        idx = self._index()
        q = query.lower()
        hits: list[SearchHit] = []
        for key, urls in idx.get("searches", {}).items():
            if key.lower() in q:
                hits.extend(SearchHit(url=u, title=u, snippet=key) for u in urls)
        return hits[:max_results]

    async def fetch(self, url: str) -> FetchedPage:
        idx = self._index()
        rel = idx.get("pages", {}).get(url)
        if rel is None:
            raise FileNotFoundError(f"no canned page for {url}")
        text = (_corpus_dir() / rel).read_text(encoding="utf-8")
        return FetchedPage(url=url, text=text)
