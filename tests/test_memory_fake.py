import pytest

from sdlc.memory.fake import FakeMemory
from sdlc.memory.models import (
    MemoryKind,
    RetainItem,
)


@pytest.mark.asyncio
async def test_recall_empty_bank_returns_no_items():
    mem = FakeMemory()
    snap = await mem.recall("project:x", "query", {}, None)
    assert snap.items == []
    assert snap.degraded is False


@pytest.mark.asyncio
async def test_retain_then_recall_returns_it():
    mem = FakeMemory()
    await mem.retain(
        RetainItem(kind=MemoryKind.GOTCHA, bank="project:x", text="fixed a flaky test", metadata={})
    )
    snap = await mem.recall("project:x", "query", {}, None)
    assert snap.items == ["fixed a flaky test"]


@pytest.mark.asyncio
async def test_recall_filters_by_metadata():
    mem = FakeMemory()
    await mem.retain(
        RetainItem(
            kind=MemoryKind.STAGE_SUMMARY,
            bank="b",
            text="clarify done",
            metadata={"stage": "clarify"},
        )
    )
    await mem.retain(
        RetainItem(
            kind=MemoryKind.STAGE_SUMMARY,
            bank="b",
            text="architect done",
            metadata={"stage": "architect"},
        )
    )
    snap = await mem.recall("b", "q", {"stage": "architect"}, None)
    assert snap.items == ["architect done"]


@pytest.mark.asyncio
async def test_watermark_freezes_recall_against_later_retains():
    mem = FakeMemory()
    await mem.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="b", text="first", metadata={}))
    watermark = await mem.current_watermark("b")
    await mem.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="b", text="second", metadata={}))
    frozen = await mem.recall("b", "q", {}, watermark)
    live = await mem.recall("b", "q", {}, None)
    assert frozen.items == ["first"]
    assert live.items == ["first", "second"]


@pytest.mark.asyncio
async def test_reflect_is_a_noop_that_does_not_raise():
    mem = FakeMemory()
    await mem.reflect("b")


@pytest.mark.asyncio
async def test_recall_filters_by_kind():
    mem = FakeMemory()
    await mem.retain(
        RetainItem(
            kind=MemoryKind.GOTCHA,
            bank="bank:kind-filter",
            text="uv runs tests via uv run pytest",
            metadata={},
        )
    )
    await mem.retain(
        RetainItem(
            kind=MemoryKind.STAGE_SUMMARY,
            bank="bank:kind-filter",
            text="clarify done",
            metadata={},
        )
    )
    snap = await mem.recall("bank:kind-filter", "query", {"kind": "gotcha"}, None)
    assert snap.items == ["uv runs tests via uv run pytest"]


@pytest.mark.asyncio
async def test_recall_without_kind_filter_returns_all_kinds():
    mem = FakeMemory()
    await mem.retain(
        RetainItem(
            kind=MemoryKind.GOTCHA,
            bank="bank:all-kinds",
            text="uv runs tests via uv run pytest",
            metadata={},
        )
    )
    await mem.retain(
        RetainItem(
            kind=MemoryKind.STAGE_SUMMARY,
            bank="bank:all-kinds",
            text="clarify done",
            metadata={},
        )
    )
    snap = await mem.recall("bank:all-kinds", "query", {}, None)
    assert len(snap.items) == 2
