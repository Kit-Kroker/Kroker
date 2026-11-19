import pathlib

import pytest

from sdlc.memory.activities import (
    PromoteInput,
    RecallInput,
    RetainInput,
    _fake_singleton,
    promote_org_learnings,
    recall_snapshot,
    retain,
)
from sdlc.memory.models import MemoryKind, RetainItem
from sdlc.memory.promote import GOTCHA_QUERY, promotions


def test_same_gotcha_in_two_banks_promotes_once():
    items = promotions(
        {"project:a": ["uv run pytest, not pytest"], "project:b": ["uv run pytest, not pytest"]},
        org_bank="org",
    )
    assert len(items) == 1
    assert items[0].bank == "org"
    assert items[0].kind is MemoryKind.GOTCHA
    assert items[0].metadata == {"promoted_from": "project:a,project:b"}


def test_one_bank_twice_does_not_promote():
    assert promotions({"project:a": ["x", "x"]}, org_bank="org") == []


def test_normalization_groups_case_and_punctuation_variants():
    items = promotions(
        {"project:a": ["UV run pytest!"], "project:b": ["uv run pytest"]}, org_bank="org"
    )
    assert len(items) == 1
    assert items[0].text == "UV run pytest!"  # lexicographically smallest RAW text


def test_single_project_never_promotes():
    assert promotions({"project:a": ["x"], "project:b": []}, org_bank="org") == []


def test_min_projects_three_requires_three_banks():
    two = {"project:a": ["x"], "project:b": ["x"]}
    assert promotions(two, org_bank="org", min_projects=3) == []


def test_identical_input_yields_identical_output():
    src = {"project:b": ["zeta", "alpha"], "project:a": ["alpha", "zeta"]}
    assert promotions(src, org_bank="org") == promotions(src, org_bank="org")


def test_result_is_sorted_by_text():
    items = promotions(
        {"project:a": ["b-item", "a-item"], "project:b": ["a-item", "b-item"]}, org_bank="org"
    )
    assert [i.text for i in items] == ["a-item", "b-item"]


def test_gotcha_query_is_pinned():
    assert GOTCHA_QUERY == "recurring cross-project gotchas and stack knowledge"


def test_promote_is_a_temporal_activity():
    assert getattr(promote_org_learnings, "__temporal_activity_definition", None) is not None


def test_promote_is_registered_on_the_worker():
    # test_triage_registry.py's source-grep convention: the original FR-404
    # bug was a registered-looking activity nobody called or served.
    src = pathlib.Path("src/sdlc/worker.py").read_text(encoding="utf-8")
    assert "promote_org_learnings" in src, "not registered in worker.py"


@pytest.mark.asyncio
async def test_promote_end_to_end_on_fake_backend():
    await retain(
        RetainInput(
            item=RetainItem(
                kind=MemoryKind.GOTCHA,
                bank="project:e2e-a",
                text="uv run pytest",
                metadata={},
            )
        )
    )
    await retain(
        RetainInput(
            item=RetainItem(
                kind=MemoryKind.GOTCHA,
                bank="project:e2e-b",
                text="uv run pytest",
                metadata={},
            )
        )
    )
    n = await promote_org_learnings(
        PromoteInput(project_banks=["project:e2e-a", "project:e2e-b"], org_bank="org:e2e")
    )
    assert n == 1
    snap = await recall_snapshot(RecallInput(bank="org:e2e", query="q", backend="fake"))
    assert snap.items == ["uv run pytest"]


@pytest.mark.asyncio
async def test_promote_scrubs_before_retain():
    # Seed the fake singleton directly, bypassing the retain activity's own
    # scrub, so the scrub under test is the one at the promote boundary.
    # The org bank is read the same way: recall_snapshot scrubs
    # item-by-item on read (FR-012), so verifying through it would pass
    # even if the promote boundary forgot to scrub -- the stored bytes
    # would be raw and the read would mask them.
    raw_key = "sk-" + "a" * 40
    for bank in ("project:promote-scrub-a", "project:promote-scrub-b"):
        await _fake_singleton.retain(
            RetainItem(kind=MemoryKind.GOTCHA, bank=bank, text=f"key {raw_key} fix", metadata={})
        )
    n = await promote_org_learnings(
        PromoteInput(
            project_banks=["project:promote-scrub-a", "project:promote-scrub-b"],
            org_bank="org:promote-scrub",
        )
    )
    assert n == 1
    snap = await _fake_singleton.recall("org:promote-scrub", "q", {}, None)
    assert snap.items == ["key [REDACTED_API_KEY] fix"]
    assert raw_key not in snap.items[0]


@pytest.mark.asyncio
async def test_promote_raises_when_backend_recall_raises(monkeypatch):
    # Fail-visible by design: an empty recall here would read as "no
    # gotchas recurred" and the org bank would silently go stale. Pins
    # that nobody wraps the activity's recall in a recall_snapshot-style
    # silent degrade.

    async def unreachable(*args, **kwargs):
        raise RuntimeError("backend unreachable")

    monkeypatch.setattr(_fake_singleton, "recall", unreachable)
    with pytest.raises(RuntimeError, match="backend unreachable"):
        await promote_org_learnings(
            PromoteInput(project_banks=["project:raise"], org_bank="org:raise")
        )


@pytest.mark.asyncio
async def test_promote_with_no_recurrence_returns_zero():
    await retain(
        RetainInput(
            item=RetainItem(
                kind=MemoryKind.GOTCHA,
                bank="project:promote-solo",
                text="only ever seen in one project",
                metadata={},
            )
        )
    )
    n = await promote_org_learnings(
        PromoteInput(project_banks=["project:promote-solo"], org_bank="org:promote-solo-empty")
    )
    assert n == 0
    snap = await recall_snapshot(
        RecallInput(bank="org:promote-solo-empty", query="q", backend="fake")
    )
    assert snap.items == []
