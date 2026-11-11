"""021 R-6 chaos tests: the memory_recalled stage event.

RED-first: MemoryHost._recall does not emit memory_recalled and the activity
does not return snapshot_hash / ref / persist_failed yet.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import temporalio.workflow as temporal_workflow

from sdlc.core.models import MemoryConfig, PipelineConfig
from sdlc.memory.activities import RecallInput
from sdlc.workflows.memory_host import MemoryHost

SECRET_ITEM = "SECRET-ITEM-TEXT-DO-NOT-LEAK"
HASH = "a" * 64


class _Host(MemoryHost):
    def __init__(self) -> None:
        super().__init__()
        self.emitted: list[tuple] = []
        self._memory_watermark = "3"

    def _emit(self, kind, stage=None, **data):  # matches ReportHost._emit's shape
        self.emitted.append((kind, stage, data))


def _snap(**overrides):
    base = dict(
        query_hash="q",
        bank="b",
        watermark="3",
        items=[SECRET_ITEM],
        degraded=False,
        snapshot_hash=HASH,
        ref=SimpleNamespace(uri="file:///runs/run-1/recall/x.json"),
        persist_failed=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def activity_calls(monkeypatch):
    calls: list[tuple] = []

    async def fake_execute(act, inp, **kwargs):
        calls.append((act, inp))
        return fake_execute.result

    fake_execute.result = _snap()
    monkeypatch.setattr(temporal_workflow, "execute_activity", fake_execute)
    monkeypatch.setattr(temporal_workflow, "info", lambda: SimpleNamespace(workflow_id="run-1"))
    return SimpleNamespace(calls=calls, result=fake_execute)


def _cfg(enabled: bool) -> PipelineConfig:
    return PipelineConfig(memory=MemoryConfig(enabled=enabled, backend="fake"))


def _recalled(host: _Host) -> list[tuple]:
    return [e for e in host.emitted if getattr(e[0], "value", e[0]) == "memory_recalled"]


@pytest.mark.asyncio
async def test_memory_on_emits_exactly_one_memory_recalled_for_the_stage(activity_calls):
    host = _Host()
    await host._recall(_cfg(True), "b", "q", {"stage": "clarify"})

    events = _recalled(host)
    assert len(events) == 1
    assert events[0][1] == "clarify"

    (_, inp) = activity_calls.calls[0]
    assert isinstance(inp, RecallInput)
    assert inp.run_id == "run-1"


@pytest.mark.asyncio
async def test_event_carries_hash_and_uri_but_never_item_text(activity_calls):
    host = _Host()
    await host._recall(_cfg(True), "b", "q", {"stage": "clarify"})

    (_, _, data) = _recalled(host)[0]
    assert set(data) == {"snapshot_hash", "snapshot_uri", "degraded", "persist_failed"}
    assert data["snapshot_hash"] == HASH
    assert data["snapshot_uri"] == "file:///runs/run-1/recall/x.json"
    assert all(SECRET_ITEM not in str(v) for v in data.values())


@pytest.mark.asyncio
async def test_persist_failure_and_degraded_flags_are_reported_as_strings(activity_calls):
    activity_calls.result = _snap(degraded=True, persist_failed=True, ref=None, snapshot_hash=HASH)
    host = _Host()
    await host._recall(_cfg(True), "b", "q", {"stage": "clarify"})

    (_, _, data) = _recalled(host)[0]
    assert data["degraded"] == "true"
    assert data["persist_failed"] == "true"
    assert data["snapshot_uri"] == ""  # no ref means an empty uri, not "None"


@pytest.mark.asyncio
async def test_memory_off_emits_nothing_and_calls_no_activity(activity_calls):
    host = _Host()
    snap = await host._recall(_cfg(False), "b", "q", {"stage": "clarify"})

    assert host.emitted == []
    assert activity_calls.calls == []
    assert getattr(snap, "snapshot_hash", "") == ""  # FR-007 / R-4


@pytest.mark.asyncio
async def test_missing_emit_hook_does_not_break_recall(activity_calls):
    # Hosts without ReportHost have no _emit; the getattr guard must make that a no-op.
    class _Bare(MemoryHost):
        pass

    host = _Bare()
    host._memory_watermark = "3"
    snap = await host._recall(_cfg(True), "b", "q", {"stage": "clarify"})

    assert snap.snapshot_hash == HASH
