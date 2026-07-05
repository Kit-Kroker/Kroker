import pytest

from sdlc.memory.activities import (
    RecallInput, RetainInput, WatermarkInput, capture_watermark,
    recall_snapshot, retain,
)
from sdlc.models import MemoryKind, RetainItem


def test_recall_snapshot_is_a_temporal_activity():
    assert getattr(recall_snapshot, "__temporal_activity_definition",
                  None) is not None


def test_retain_is_a_temporal_activity():
    assert getattr(retain, "__temporal_activity_definition", None) is not None


@pytest.mark.asyncio
async def test_retain_then_recall_round_trips_through_fake_backend():
    await retain(RetainInput(
        item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:x",
                        text="flaky test needed a retry", metadata={}),
        backend="fake"))
    snap = await recall_snapshot(RecallInput(bank="project:x", query="q",
                                             backend="fake"))
    assert snap.items == ["flaky test needed a retry"]
    assert snap.degraded is False


@pytest.mark.asyncio
async def test_retain_scrubs_secrets_before_storing():
    await retain(RetainInput(
        item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:scrub-test",
                        text="used sk-abcdefghijklmnopqrstuvwx to auth",
                        metadata={}),
        backend="fake"))
    snap = await recall_snapshot(RecallInput(bank="project:scrub-test",
                                             query="q", backend="fake"))
    assert "sk-abcdefghijklmnopqrstuvwx" not in snap.items[0]


@pytest.mark.asyncio
async def test_recall_snapshot_degrades_on_backend_error(monkeypatch):
    import sdlc.memory.activities as act_mod

    class _Boom:
        async def recall(self, *a, **kw):
            raise ConnectionError("hindsight unreachable")

    monkeypatch.setattr(act_mod, "_backend", lambda base_url, backend: _Boom())
    snap = await recall_snapshot(RecallInput(bank="b", query="q"))
    assert snap.degraded is True
    assert snap.items == []


@pytest.mark.asyncio
async def test_capture_watermark_reflects_retains():
    before = await capture_watermark(WatermarkInput(bank="project:wm",
                                                    backend="fake"))
    await retain(RetainInput(
        item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:wm",
                        text="x", metadata={}), backend="fake"))
    after = await capture_watermark(WatermarkInput(bank="project:wm",
                                                   backend="fake"))
    assert int(after) == int(before) + 1
