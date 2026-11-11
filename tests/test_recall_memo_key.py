"""021 FR-004 / FR-006 / FR-007 / FR-010 chaos tests for the memo key's recall slot.

RED-first: RoleHost._cached_stage does not accept `recall_ref` yet.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

import sdlc.workflows.role_host as role_host
from sdlc.core.models import PipelineConfig
from sdlc.workflows.role_host import RoleHost


class _Out(BaseModel):
    x: str = "out"


class _Host(RoleHost):
    pass


@pytest.fixture
def keys(monkeypatch):
    """Record every content_key call's arguments; cache always misses."""
    seen: list[tuple] = []
    real = role_host.content_key

    def recording(*args):
        seen.append(args)
        return real(*args)

    async def fake_execute(act, inp, **kwargs):
        return None  # cache_get misses; cache_put is a no-op

    monkeypatch.setattr(role_host, "content_key", recording)
    monkeypatch.setattr(role_host.workflow, "execute_activity", fake_execute)
    return seen


def _cfg() -> PipelineConfig:
    cfg = PipelineConfig()
    cfg.memoization_enabled = True
    return cfg


async def _recorded_last_arg(keys, host, **kwargs) -> str:
    async def run():
        return _Out()

    await host._cached_stage(_cfg(), "clarify", "{}", _Out, run, **kwargs)
    assert keys, "memoization must compute a key"
    return keys[-1][-1]


@pytest.mark.asyncio
async def test_empty_recall_ref_keeps_the_pre_021_watermark_slot(keys):
    host = _Host()
    host._memory_watermark = "5"
    assert await _recorded_last_arg(keys, host, recall_ref="") == "5"


@pytest.mark.asyncio
async def test_empty_recall_ref_with_no_watermark_keeps_none_slot(keys):
    host = _Host()  # FR-007: memory-off key stays byte-identical
    assert await _recorded_last_arg(keys, host, recall_ref="") == "none"


@pytest.mark.asyncio
async def test_disabled_snapshot_hash_feeds_the_exact_pre_021_slot(keys):
    # T027 / FR-007: the memory-disabled snapshot MemoryHost._recall returns has no hash,
    # and feeding that hash as recall_ref must leave the pre-021 slot untouched.
    from sdlc.memory.models import RecallSnapshot

    snap = RecallSnapshot(query_hash="", bank="b", watermark="unknown")
    assert snap.snapshot_hash == ""
    host = _Host()  # no watermark: the pre-021 slot is "none"
    assert await _recorded_last_arg(keys, host, recall_ref=snap.snapshot_hash) == "none"


@pytest.mark.asyncio
async def test_non_empty_recall_ref_extends_the_watermark_slot(keys):
    host = _Host()
    host._memory_watermark = "5"
    assert await _recorded_last_arg(keys, host, recall_ref="abc123") == "5|abc123"


@pytest.mark.asyncio
async def test_absent_watermark_with_a_ref_still_gets_a_none_prefix(keys):
    host = _Host()
    assert await _recorded_last_arg(keys, host, recall_ref="abc123") == "none|abc123"


@pytest.mark.asyncio
async def test_degraded_and_healthy_snapshots_never_share_a_key(keys):
    # FR-006: same watermark, same (empty) items, degraded flag differs -> different key.
    from sdlc.memory.query_hash import recall_snapshot_hash

    healthy = recall_snapshot_hash(
        bank="b", watermark="5", query_hash="q", items=[], degraded=False
    )
    degraded = recall_snapshot_hash(
        bank="b", watermark="5", query_hash="q", items=[], degraded=True
    )
    host = _Host()
    host._memory_watermark = "5"
    k_healthy = await _recorded_last_arg(keys, host, recall_ref=healthy)
    k_degraded = await _recorded_last_arg(keys, host, recall_ref=degraded)
    assert k_healthy != k_degraded


@pytest.mark.asyncio
async def test_same_items_give_same_key_and_different_items_give_different_key(keys):
    from sdlc.memory.query_hash import recall_snapshot_hash

    a = recall_snapshot_hash(bank="b", watermark="5", query_hash="q", items=["x"], degraded=False)
    a_again = recall_snapshot_hash(
        bank="b", watermark="5", query_hash="q", items=["x"], degraded=False
    )
    b = recall_snapshot_hash(bank="b", watermark="5", query_hash="q", items=["y"], degraded=False)
    host = _Host()
    host._memory_watermark = "5"
    k_a = await _recorded_last_arg(keys, host, recall_ref=a)
    k_a2 = await _recorded_last_arg(keys, host, recall_ref=a_again)
    k_b = await _recorded_last_arg(keys, host, recall_ref=b)
    assert k_a == k_a2
    assert k_a != k_b


@pytest.mark.asyncio
async def test_watermark_containing_the_separator_cannot_forge_another_key(keys):
    # Edge: a backend watermark is a free-form string. "5|x" + ref "y" and
    # "5" + ref "x|y" must not produce the same memo-slot text.
    host = _Host()
    host._memory_watermark = "5|x"
    k1 = await _recorded_last_arg(keys, host, recall_ref="y")
    host._memory_watermark = "5"
    k2 = await _recorded_last_arg(keys, host, recall_ref="x|y")
    assert k1 != k2
