"""Real Hindsight (vectorize-io) HTTP client -- the integration seam noted in
ARCHITECTURE.md section 6/8.

Every path comes from hindsight_api, which is pinned against the container's
own OpenAPI schema. Callers only ever see the Memory protocol, so swapping
this module or base_url leaves workflow code untouched."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

import httpx

from ..models import RecallSnapshot, RetainItem
from .hindsight_api import BANK_PATH, RETAIN_PATH
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


# Metadata keys promoted to tags so recall can filter on them. Hindsight
# cannot filter on metadata at query time, so anything absent here is
# unfilterable -- see _filter_tags in recall. run_id/task_id/source_url stay
# out deliberately: unbounded cardinality, and URLs do not belong in a tag
# namespace.
TAG_PROMOTED_KEYS: tuple[str, ...] = ("stage", "gate")


def _tags(item: RetainItem) -> list[str]:
    tags = [f"kind:{item.kind.value}"]
    tags += [f"{k}:{item.metadata[k]}"
             for k in TAG_PROMOTED_KEYS if k in item.metadata]
    return tags


def _document_id(item: RetainItem) -> str:
    """Content-addressed, so Temporal's retries upsert rather than duplicate."""
    return hashlib.sha256(
        f"{item.bank}|{item.kind.value}|{item.text}".encode("utf-8")
    ).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        """Hindsight has no watermark, version or as-of endpoint, so the
        freeze point is a worker-clock timestamp and recall enforces it
        client-side. retain stamps the same clock, so the comparison in
        recall is like-for-like and server skew cannot leak a post-freeze
        memory into a pinned run."""
        return _now_iso()

    async def retain(self, item: RetainItem) -> None:
        await self.ensure_bank(item.bank)
        doc_id = _document_id(item)
        resp = await self._client.post(
            self._path(RETAIN_PATH, item.bank),
            json={
                "items": [{
                    "content": item.text,
                    "context": item.kind.value,
                    "tags": _tags(item),
                    "metadata": item.metadata,
                    "timestamp": _now_iso(),
                    "document_id": doc_id,
                }],
                # Retain runs LLM fact extraction; synchronously it would
                # exceed MEM_ACT's 30s ceiling. The operation_id is derived
                # from content so Temporal's five retries are idempotent.
                "async": True,
                "operation_id": str(uuid.UUID(hex=doc_id[:32])),
            })
        resp.raise_for_status()

    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot:
        raise NotImplementedError

    async def reflect(self, bank: str) -> None:
        raise NotImplementedError
