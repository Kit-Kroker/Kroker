"""charge_persisted publishes the budget counter atomically. Every future
charge re-reads and Budget.model_validate_json()s the count file; a torn
write (write_text() truncates then writes) leaves a file that fails
validation, nothing repairs it, and that scope stays wedged for the rest
of the run (assessment research-budget-enforcement, defect H3). The write
must therefore go through a temp file in the same directory plus
os.replace() -- write_page's pattern: a reader sees either the complete
old counter or the complete new one, never a partial or mutated file.

The chaos cases pin the crash semantics, not just the shape of the write:
a crash injected exactly at the publish boundary (os.replace armed to
raise) must leave the previous counter byte-identical, schema-valid and
chargeable -- the old count is the budget's ground truth, and losing it
zeroes or re-hands recorded spend. And a counter file that is empty or
garbage keeps failing validation loudly on every charge and is never
repaired, reset or recreated by the store: an unreadable budget stays an
operator decision, never a silent budget grant.
"""

import os
import sys

import pytest
from pydantic import ValidationError

from sdlc.stages.research import budget_store
from sdlc.stages.research.budget_store import budget_path, charge_persisted, charge_scoped
from sdlc.stages.research.deps import Budget, ResearchDeps


class _PublishCrashed(Exception):
    """Raised by the armed os.replace in the crash-injection test."""


def _deps(run_id: str = "r1") -> ResearchDeps:
    return ResearchDeps(
        run_id=run_id, provider="fake", max_searches=2, max_fetches=2, max_cost_usd=1.0
    )


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_charge_persisted_roundtrips_the_counter_through_the_schema():
    await charge_persisted(_deps(), search=1, fetch=1)
    path = budget_path("r1")
    budget = Budget.model_validate_json(path.read_text(encoding="utf-8"))
    assert budget.searches == 1
    assert budget.fetches == 1
    assert budget.cost_usd >= 0.0

    # A fresh deps copy -- what the next durable activity actually
    # receives -- reads the same file and accumulates on top of it.
    await charge_persisted(_deps(), fetch=1)
    assert Budget.model_validate_json(path.read_text(encoding="utf-8")).fetches == 2


@pytest.mark.asyncio
async def test_charge_persisted_leaves_no_temp_or_lock_files_behind():
    research_dir = budget_path("r1").parent
    await charge_persisted(_deps(), fetch=1)
    assert [p.name for p in research_dir.iterdir()] == ["budget-run.json"]

    # The dual-charge path (a sub-question scope also charges the shared
    # run ceiling) lands exactly its two counters and nothing else.
    await charge_scoped(_deps("r2"), fetch=1, scope="sq-1", run_max_cost_usd=1.0)
    assert sorted(p.name for p in budget_path("r2").parent.iterdir()) == [
        "budget-run.json",
        "budget-sq-1.json",
    ]


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="asserts POSIX replace-publishes-a-new-inode semantics; Windows "
    "opens handles without FILE_SHARE_DELETE and denies os.replace onto "
    "them (PermissionError). The delegation itself is pinned cross-platform "
    "by the crash-at-publish-boundary test.",
)
async def test_charge_persisted_publishes_atomically_not_in_place():
    # A reader that already opened the counter keeps reading the complete
    # OLD content across a later charge: os.replace() publishes a new
    # inode and never mutates the one a reader may hold. write_text() in
    # place truncates and rewrites the same inode, so this reader would
    # observe the new bytes instead.
    await charge_persisted(_deps(), fetch=1)
    path = budget_path("r1")
    old = path.read_text(encoding="utf-8")

    with path.open(encoding="utf-8") as held:
        await charge_persisted(_deps(), fetch=1)
        held.seek(0)
        assert held.read() == old, "the published counter was mutated in place"

    assert Budget.model_validate_json(path.read_text(encoding="utf-8")).fetches == 2


@pytest.mark.asyncio
async def test_crash_at_the_publish_boundary_leaves_the_old_counter_intact(monkeypatch):
    await charge_persisted(_deps(), fetch=1)
    path = budget_path("r1")
    old = path.read_text(encoding="utf-8")

    real_replace = os.replace
    armed = {"crashing": True}

    def crashing_replace(src, dst, **kwargs):
        if armed["crashing"]:
            raise _PublishCrashed("simulated crash between the tmp write and os.replace")
        return real_replace(src, dst, **kwargs)

    # Armed on the os module itself: whether the fix calls os.replace()
    # directly or Path.replace() (which routes through os.replace), the
    # simulated crash lands at the publish boundary.
    monkeypatch.setattr(budget_store.os, "replace", crashing_replace)

    crashed = False
    try:
        await charge_persisted(_deps(), fetch=1)
    except _PublishCrashed:
        crashed = True
    assert crashed, (
        "no publish boundary exists to crash at -- budget_store still writes "
        "the counter in place, so a real crash mid-write tears the file"
    )

    # The crash cost nothing: the published counter is byte-identical to
    # before and still validates, and the lock went home so the next charge
    # is not blocked behind a dead holder.
    assert path.read_text(encoding="utf-8") == old
    assert Budget.model_validate_json(path.read_text(encoding="utf-8")).fetches == 1
    assert not path.with_suffix(".lock").exists()

    # The scope is not wedged: with the crash disarmed the next charge
    # accumulates on top of the surviving count.
    armed["crashing"] = False
    await charge_persisted(_deps(), fetch=1)
    assert Budget.model_validate_json(path.read_text(encoding="utf-8")).fetches == 2


@pytest.mark.asyncio
async def test_unreadable_counter_fails_validation_loudly_and_is_never_auto_reset():
    # Contract from the assessment (defect H3, remediation note): an
    # unreadable file stays an operator problem -- the store must not
    # "helpfully" hand the budget back by recreating or resetting it.
    path = budget_path("r1")
    path.parent.mkdir(parents=True, exist_ok=True)
    for torn in (b"", b"{ this is not json"):
        path.write_bytes(torn)
        with pytest.raises(ValidationError):
            await charge_persisted(_deps(), fetch=1)
        assert path.read_bytes() == torn, "the failed charge modified the unreadable counter"
        assert not path.with_suffix(".lock").exists()
