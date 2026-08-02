"""Real Hindsight (vectorize-io) HTTP client -- the integration seam noted in
ARCHITECTURE.md section 6/8.

Every path comes from hindsight_api, which is pinned against the container's
own OpenAPI schema. Callers only ever see the Memory protocol, so swapping
this module or base_url leaves workflow code untouched."""
from __future__ import annotations

import re

import httpx

from ..models import RecallSnapshot, RetainItem
from .hindsight_api import BANK_PATH
from .protocol import Memory

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")

# Banks already ensured this process, keyed by (base_url, tenant, bank).
_ENSURED: set[tuple[str, str, str]] = set()

# _backend() builds a fresh HindsightMemory per activity invocation. One
# never-closed AsyncClient per instance leaks sockets, so connections are
# pooled per (base_url, tenant, api_key) instead.
_CLIENTS: dict[tuple[str, str, str | None], httpx.AsyncClient] = {}


def _clear_bank_cache() -> None:
    _ENSURED.clear()


def _clear_client_cache() -> None:
    _CLIENTS.clear()


def _client_for(base_url: str, tenant: str, api_key: str | None,
                timeout_s: float) -> httpx.AsyncClient:
    key = (base_url, tenant, api_key)
    client = _CLIENTS.get(key)
    if client is None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s,
                                   headers=headers)
        _CLIENTS[key] = client
    return client


def _bank_id(bank: str) -> str:
    """The factory's bank names ('project:default') contain characters a URL
    path segment should not carry. The mapping is one-way but injective for
    the names in use, since only ':' is ever replaced (Task 1 confirmed the
    container tolerates the colon anyway, so this is defensive -- but keeping
    it means bank names cannot break URL routing if Hindsight tightens up)."""
    return _UNSAFE.sub("-", bank)


class HindsightMemory(Memory):
    def __init__(self, base_url: str, tenant: str = "default",
                 api_key: str | None = None, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.tenant = tenant
        self.api_key = api_key
        self._client = _client_for(self.base_url, tenant, api_key, timeout_s)

    def _path(self, template: str, bank: str, **extra: str) -> str:
        return template.format(tenant=self.tenant, bank=_bank_id(bank),
                               **extra)

    async def ensure_bank(self, bank: str) -> None:
        """Idempotent create-or-update. Without it the first recall against a
        fresh volume 404s."""
        key = (self.base_url, self.tenant, _bank_id(bank))
        if key in _ENSURED:
            return
        resp = await self._client.put(self._path(BANK_PATH, bank), json={})
        resp.raise_for_status()
        _ENSURED.add(key)

    async def current_watermark(self, bank: str) -> str:
        raise NotImplementedError

    async def retain(self, item: RetainItem) -> None:
        raise NotImplementedError

    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot:
        raise NotImplementedError

    async def reflect(self, bank: str) -> None:
        raise NotImplementedError
