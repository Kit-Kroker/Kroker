"""Temporal activities wrapping the Memory backend. All memory I/O funnels
through here — workflow code never touches a backend directly
(ARCHITECTURE.md §2, 'memory is I/O')."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from temporalio import activity

from ..models import RecallSnapshot, RetainItem
from .fake import FakeMemory
from .protocol import Memory
from .query_hash import recall_query_hash
from .scrub import scrub

logger = logging.getLogger(__name__)

_fake_singleton = FakeMemory()


def _backend(base_url: str, backend: str) -> Memory:
    """Tenant and API key come from the environment, never from the activity
    input -- RecallInput/RetainInput are serialized into Temporal history."""
    if backend == "hindsight":
        from .hindsight_client import HindsightMemory

        return HindsightMemory(
            base_url=base_url,
            tenant=os.environ.get("SDLC_MEMORY_TENANT", "default"),
            api_key=os.environ.get("SDLC_MEMORY_API_KEY") or None,
        )
    return _fake_singleton


@dataclass
class RecallInput:
    bank: str
    query: str
    filters: dict[str, str] = field(default_factory=dict)
    watermark: str | None = None
    backend: str = "fake"
    base_url: str = "http://localhost:8888"


@activity.defn
async def recall_snapshot(inp: RecallInput) -> RecallSnapshot:
    """Never raises: an unreachable backend degrades to an empty snapshot
    (logged) rather than blocking the pipeline on memory."""
    try:
        memory = _backend(inp.base_url, inp.backend)
        return await memory.recall(inp.bank, inp.query, inp.filters, inp.watermark)
    except Exception:
        logger.warning("recall degraded to empty snapshot", exc_info=True)
        query_hash = recall_query_hash(inp.bank, inp.query, inp.filters, inp.watermark)
        return RecallSnapshot(
            query_hash=query_hash,
            bank=inp.bank,
            watermark=inp.watermark or "unknown",
            items=[],
            degraded=True,
        )


@dataclass
class RetainInput:
    item: RetainItem
    backend: str = "fake"
    base_url: str = "http://localhost:8888"


@activity.defn
async def retain(inp: RetainInput) -> None:
    """Raises on backend failure (unlike recall) so Temporal's own
    RetryPolicy retries in the background, per ARCHITECTURE.md §12."""
    memory = _backend(inp.base_url, inp.backend)
    scrubbed = inp.item.model_copy(update={"text": scrub(inp.item.text)})
    await memory.retain(scrubbed)


@dataclass
class WatermarkInput:
    bank: str
    backend: str = "fake"
    base_url: str = "http://localhost:8888"


@activity.defn
async def capture_watermark(inp: WatermarkInput) -> str:
    memory = _backend(inp.base_url, inp.backend)
    return await memory.current_watermark(inp.bank)


@dataclass
class ReflectInput:
    bank: str
    backend: str = "fake"
    base_url: str = "http://localhost:8888"


@activity.defn
async def reflect(inp: ReflectInput) -> None:
    memory = _backend(inp.base_url, inp.backend)
    await memory.reflect(inp.bank)
