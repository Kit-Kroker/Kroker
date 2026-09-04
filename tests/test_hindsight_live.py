"""The test that proves the integration is real.

Skipped by default: it needs a running Hindsight container and spends LLM
tokens through HINDSIGHT_API_LLM_API_KEY on every retain (fact extraction).

Run with:
  docker compose up -d hindsight
  SDLC_LIVE_TESTS=1 python -m pytest tests/test_hindsight_live.py -v -m live
"""

from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from sdlc.memory.hindsight_client import HindsightMemory
from sdlc.memory.models import (
    MemoryKind,
    RetainItem,
)

BASE_URL = os.environ.get("SDLC_MEMORY_BASE_URL_LIVE", "http://localhost:8888")


def _reachable() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/openapi.json", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("SDLC_LIVE_TESTS") != "1", reason="set SDLC_LIVE_TESTS=1 to spend tokens"
    ),
    pytest.mark.skipif(not _reachable(), reason=f"no Hindsight answering on {BASE_URL}"),
]


@pytest.fixture(autouse=True)
def _clear_caches():
    """pytest-asyncio gives each test its own event loop; the module-level
    client cache would hand test N an AsyncClient bound to test N-1's closed
    loop. Clearing between tests is the fix."""
    from sdlc.memory import hindsight_client as hc

    hc._clear_bank_cache()
    hc._clear_client_cache()
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


@pytest.fixture
def memory() -> HindsightMemory:
    return HindsightMemory(
        base_url=BASE_URL,
        tenant=os.environ.get("SDLC_MEMORY_TENANT", "default"),
        api_key=os.environ.get("SDLC_MEMORY_API_KEY") or None,
        timeout_s=120.0,
    )


@pytest.fixture
def bank() -> str:
    return f"livetest-{uuid.uuid4().hex[:8]}"


async def _settle(memory: HindsightMemory, bank: str) -> None:
    """Retain is async on Hindsight's side (LLM fact extraction runs in the
    background); consolidation makes what was retained recallable. The sleep
    BEFORE reflect gives fact extraction time to land -- without it, reflect
    processes an empty bank. The sleep AFTER lets the recall index settle."""
    await asyncio.sleep(15)
    await memory.reflect(bank)
    await asyncio.sleep(2)


@pytest.mark.asyncio
async def test_a_retained_memory_comes_back_from_recall(memory, bank):
    await memory.retain(
        RetainItem(
            kind=MemoryKind.GOTCHA,
            bank=bank,
            text="The staging deploy fails when PGBOUNCER_MAX_CLIENT_CONN is unset.",
            metadata={"stage": "qa"},
        )
    )
    await _settle(memory, bank)

    snap = await memory.recall(bank, "why does the staging deploy fail?", {}, None)
    assert snap.items, "nothing recalled -- retain or consolidation did not land"
    assert any("PGBOUNCER" in item.upper() for item in snap.items)
    assert snap.degraded is False


@pytest.mark.asyncio
async def test_stage_filters_actually_exclude_other_stages(memory, bank):
    await memory.retain(
        RetainItem(
            kind=MemoryKind.STAGE_SUMMARY,
            bank=bank,
            text="Clarify settled that the export format is CSV, not XLSX.",
            metadata={"stage": "clarify"},
        )
    )
    await memory.retain(
        RetainItem(
            kind=MemoryKind.STAGE_SUMMARY,
            bank=bank,
            text="Architecture chose a read-through Redis cache for the catalogue.",
            metadata={"stage": "architect"},
        )
    )
    await _settle(memory, bank)

    snap = await memory.recall(bank, "what was decided?", {"stage": "clarify"}, None)
    joined = " ".join(snap.items).upper()
    assert "CSV" in joined or "XLSX" in joined, (
        "the clarify memory did not come back; filter may be over-strict"
    )
    assert "REDIS" not in joined, (
        "the architect memory leaked through a stage:clarify filter -- "
        "this is the defect the tag mapping exists to fix"
    )


@pytest.mark.asyncio
async def test_the_watermark_excludes_memories_retained_after_it(memory, bank):
    await memory.retain(
        RetainItem(
            kind=MemoryKind.GOTCHA,
            bank=bank,
            text="Postgres 14 rejects the CONCURRENTLY index build in a txn.",
            metadata={"stage": "qa"},
        )
    )
    await _settle(memory, bank)

    watermark = await memory.current_watermark(bank)
    await asyncio.sleep(2)

    await memory.retain(
        RetainItem(
            kind=MemoryKind.GOTCHA,
            bank=bank,
            text="Redis 7 changed the default eviction policy to noeviction.",
            metadata={"stage": "qa"},
        )
    )
    await _settle(memory, bank)

    pinned = await memory.recall(bank, "what should I watch out for?", {}, watermark)
    joined = " ".join(pinned.items).upper()
    assert "REDIS" not in joined, "a memory retained after the freeze point entered a pinned recall"

    unpinned = await memory.recall(bank, "what should I watch out for?", {}, None)
    assert "REDIS" in " ".join(unpinned.items).upper(), (
        "the second memory never landed at all -- the pinned assertion above would then be vacuous"
    )
