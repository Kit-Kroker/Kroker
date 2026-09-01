"""Real Hindsight (vectorize-io) HTTP client -- the integration seam noted in
ARCHITECTURE.md section 6/8.

Every path comes from hindsight_api, which is pinned against the container's
own OpenAPI schema. Callers only ever see the Memory protocol, so swapping
this module or base_url leaves workflow code untouched."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import uuid
from datetime import UTC, datetime

import httpx

from ..models import RecallSnapshot, RetainItem
from .hindsight_api import (
    BANK_PATH,
    CONSOLIDATE_PATH,
    OPERATION_PATH,
    RECALL_LIMIT_FIELD,
    RECALL_PATH,
    RETAIN_PATH,
)
from .protocol import Memory
from .query_hash import recall_query_hash

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


def _client_for(
    base_url: str, tenant: str, api_key: str | None, timeout_s: float
) -> httpx.AsyncClient:
    key = (base_url, tenant, api_key)
    client = _CLIENTS.get(key)
    if client is None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s, headers=headers)
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
    tags += [f"{k}:{item.metadata[k]}" for k in TAG_PROMOTED_KEYS if k in item.metadata]
    return tags


def _document_id(item: RetainItem) -> str:
    """Content-addressed, so Temporal's retries upsert rather than duplicate."""
    return hashlib.sha256(f"{item.bank}|{item.kind.value}|{item.text}".encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# Filter keys recall can honour -- the promoted tags plus the always-written
# kind tag.
_FILTERABLE = frozenset(TAG_PROMOTED_KEYS) | {"kind"}

RECALL_KEEP = 10  # matches FakeMemory's slice size
OVER_FETCH = 3  # advisory: recall asks for ~3x what it keeps
# RECALL_LIMIT_FIELD is max_tokens (Task 1 Step 4), not a result count, so
# over-fetching means requesting a generous token budget rather than
# RECALL_KEEP * OVER_FETCH. 4096 is the schema default; enough headroom that
# the watermark cutoff can discard without starving the snapshot.
RECALL_TOKEN_BUDGET = 4096


def _filter_tags(filters: dict[str, str]) -> list[str]:
    """Raises rather than silently returning unfiltered results. Hindsight
    cannot filter on metadata at query time, so a key with no promoted tag
    would otherwise produce a filtered-looking call that matched everything."""
    unfilterable = sorted(set(filters) - _FILTERABLE)
    if unfilterable:
        raise ValueError(
            f"recall filter keys {unfilterable} are not promoted to Hindsight "
            f"tags, and Hindsight cannot filter on metadata; add them to "
            f"TAG_PROMOTED_KEYS (filterable today: {sorted(_FILTERABLE)})"
        )
    return [f"{k}:{v}" for k, v in sorted(filters.items())]


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _within_watermark(result: dict, watermark: str | None) -> bool:
    if watermark is None:
        return True
    stamp = result.get("mentioned_at")
    if not stamp:
        # Cannot prove it predates the freeze, so it does not enter a pinned
        # run. Keeps the NFR-6 guarantee honest at the cost of a rare drop.
        return False
    try:
        return _parse_iso(stamp) <= _parse_iso(watermark)
    except ValueError:
        return False


# ReflectWorkflow's REFLECT_ACT allows 10 minutes; give up just inside it so
# the client raises something diagnosable instead of Temporal killing the
# activity on a timeout that says nothing about consolidation. Both values are
# unmeasured -- tune against a real bank.
POLL_INTERVAL_S = 5.0
POLL_DEADLINE_S = 540.0

_TERMINAL_OK = {"completed", "complete", "succeeded", "success"}
_TERMINAL_BAD = {"failed", "cancelled", "canceled", "error"}


class ConsolidationFailed(RuntimeError):
    pass


class HindsightMemory(Memory):
    def __init__(
        self,
        base_url: str,
        tenant: str = "default",
        api_key: str | None = None,
        timeout_s: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.tenant = tenant
        self.api_key = api_key
        self._client = _client_for(self.base_url, tenant, api_key, timeout_s)

    def _path(self, template: str, bank: str, **extra: str) -> str:
        return template.format(tenant=self.tenant, bank=_bank_id(bank), **extra)

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
                "items": [
                    {
                        "content": item.text,
                        "context": item.kind.value,
                        "tags": _tags(item),
                        "metadata": item.metadata,
                        "timestamp": _now_iso(),
                        "document_id": doc_id,
                    }
                ],
                # Retain runs LLM fact extraction; synchronously it would
                # exceed MEM_ACT's 30s ceiling. The operation_id is derived
                # from content so Temporal's five retries are idempotent.
                "async": True,
                "operation_id": str(uuid.UUID(hex=doc_id[:32])),
            },
        )
        resp.raise_for_status()

    async def recall(
        self, bank: str, query: str, filters: dict[str, str], watermark: str | None
    ) -> RecallSnapshot:
        await self.ensure_bank(bank)
        payload: dict[str, object] = {
            "query": query,
            RECALL_LIMIT_FIELD: RECALL_TOKEN_BUDGET,
        }
        tags = _filter_tags(filters)
        if tags:
            # all_strict: every tag must match AND untagged memories are
            # excluded. The permissive default would match everything, which
            # is the filter-shaped no-op this client exists to remove.
            payload["tags"] = tags
            payload["tags_match"] = "all_strict"

        resp = await self._client.post(self._path(RECALL_PATH, bank), json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        kept = [r["text"] for r in results if _within_watermark(r, watermark)][:RECALL_KEEP]
        return RecallSnapshot(
            query_hash=recall_query_hash(bank, query, filters, watermark),
            bank=bank,
            watermark=watermark or _now_iso(),
            items=kept,
        )

    async def reflect(self, bank: str) -> None:
        """Consolidation, not the /reflect question-answering endpoint --
        that runs an agent loop and returns prose the nightly job discards.
        Polls to a terminal state: without it ReflectWorkflow reports success
        for a consolidation that failed, the silent no-op its own docstring
        names as the failure mode it exists to prevent."""
        await self.ensure_bank(bank)
        resp = await self._client.post(self._path(CONSOLIDATE_PATH, bank))
        resp.raise_for_status()
        operation_id = (resp.json() or {}).get("operation_id")
        if not operation_id:
            return  # consolidation ran synchronously
        await self._await_operation(bank, operation_id)

    async def _await_operation(self, bank: str, operation_id: str) -> None:
        deadline = time.monotonic() + POLL_DEADLINE_S
        status = "unknown"
        while True:
            resp = await self._client.get(
                self._path(OPERATION_PATH, bank, operation_id=operation_id)
            )
            resp.raise_for_status()
            body = resp.json() or {}
            status = str(body.get("status", "unknown")).lower()
            if status in _TERMINAL_OK:
                return
            if status in _TERMINAL_BAD:
                raise ConsolidationFailed(
                    f"consolidation of {bank} ended {status}: "
                    f"{body.get('error_message') or 'no detail'}"
                )
            if time.monotonic() >= deadline:
                raise ConsolidationFailed(
                    f"consolidation of {bank} did not finish within "
                    f"{POLL_DEADLINE_S:.0f}s (last status {status})"
                )
            await asyncio.sleep(POLL_INTERVAL_S)
