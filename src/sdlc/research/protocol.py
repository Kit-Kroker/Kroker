"""Search backend abstraction — mirrors memory/protocol.py's protocol + real +
fake shape. Providers are constructed and called INSIDE tool functions (which
run activity-side), never in workflow code."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel


class SearchHit(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""


class FetchedPage(BaseModel):
    url: str
    text: str


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchHit]: ...

    @abstractmethod
    async def fetch(self, url: str) -> FetchedPage: ...


def make_provider(name: Literal["tavily", "fake"]) -> SearchProvider:
    if name == "tavily":
        from .tavily import TavilyProvider

        return TavilyProvider()
    if name == "fake":
        from .fake import FakeProvider

        return FakeProvider()
    raise ValueError(f"unknown research provider {name!r}; known: tavily, fake")
