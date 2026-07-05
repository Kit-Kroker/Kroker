"""Real Hindsight (vectorize-io) HTTP client — the integration seam noted
in ARCHITECTURE.md §6/§8. Swap this module or `base_url` without touching
workflow code; callers only ever see the Memory protocol."""
from __future__ import annotations

import httpx

from ..models import RecallSnapshot, RetainItem
from .protocol import Memory


class HindsightMemory(Memory):
    def __init__(self, base_url: str, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url,
                                         timeout=timeout_s)

    async def current_watermark(self, bank: str) -> str:
        resp = await self._client.get(f"/v1/banks/{bank}/watermark")
        resp.raise_for_status()
        return resp.json()["watermark"]

    async def retain(self, item: RetainItem) -> None:
        resp = await self._client.post(
            f"/v1/banks/{item.bank}/retain",
            json={"kind": item.kind.value, "text": item.text,
                 "metadata": item.metadata},
        )
        resp.raise_for_status()

    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot:
        resp = await self._client.post(
            f"/v1/banks/{bank}/recall",
            json={"query": query, "filters": filters,
                 "watermark": watermark},
        )
        resp.raise_for_status()
        payload = resp.json()
        return RecallSnapshot(
            query_hash=payload["query_hash"], bank=bank,
            watermark=payload["watermark"], items=payload.get("items", []),
        )

    async def reflect(self, bank: str) -> None:
        resp = await self._client.post(f"/v1/banks/{bank}/reflect")
        resp.raise_for_status()
