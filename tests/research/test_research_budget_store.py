"""budget_store.charge_persisted: the disk-persisted counterpart to
deps.charge() (Task 8's deferred item — see deps.py's module docstring).
Each test constructs a FRESH ResearchDeps per call, mirroring what a
TemporalAgent tool-call activity actually receives (its own deserialized
copy, budget always zeroed) -- the in-memory Budget.searches/fetches on any
one of these objects proves nothing; only the on-disk count does.
"""

import asyncio
import os
import time

import pytest

from sdlc.stages.research.budget_store import budget_path, charge_persisted
from sdlc.stages.research.deps import BudgetExceeded, ResearchDeps


def _deps(run_id: str = "r1", max_fetches: int = 2) -> ResearchDeps:
    return ResearchDeps(
        run_id=run_id, provider="fake", max_searches=2, max_fetches=max_fetches, max_cost_usd=1.0
    )


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_charge_persisted_accumulates_across_separate_deps_copies():
    # Each call gets its OWN ResearchDeps instance -- exactly what happens
    # across separate Temporal activities. In-memory accumulation on a single
    # deps object (the old, broken guarantee) would never catch this.
    await charge_persisted(_deps(), fetch=1)
    await charge_persisted(_deps(), fetch=1)
    path = budget_path("r1")
    assert path.exists()
    import json

    assert json.loads(path.read_text())["fetches"] == 2


@pytest.mark.asyncio
async def test_charge_persisted_raises_when_cap_exceeded():
    await charge_persisted(_deps(), fetch=1)
    await charge_persisted(_deps(), fetch=1)  # at max_fetches=2
    with pytest.raises(BudgetExceeded):
        await charge_persisted(_deps(), fetch=1)


@pytest.mark.asyncio
async def test_charge_persisted_leaves_disk_unchanged_on_raise():
    await charge_persisted(_deps(), fetch=1)
    await charge_persisted(_deps(), fetch=1)
    with pytest.raises(BudgetExceeded):
        await charge_persisted(_deps(), fetch=1)
    import json

    assert json.loads(budget_path("r1").read_text())["fetches"] == 2


@pytest.mark.asyncio
async def test_charge_persisted_separate_run_ids_do_not_share_budget():
    await charge_persisted(_deps("run-a"), fetch=1)
    await charge_persisted(_deps("run-a"), fetch=1)
    # run-b's budget is untouched by run-a's charges.
    await charge_persisted(_deps("run-b"), fetch=1)
    import json

    assert json.loads(budget_path("run-b").read_text())["fetches"] == 1


@pytest.mark.asyncio
async def test_charge_persisted_concurrent_calls_do_not_lose_increments():
    results = await asyncio.gather(
        *[charge_persisted(_deps("run-c", max_fetches=20), fetch=1) for _ in range(10)],
        return_exceptions=True,
    )
    assert all(r is None for r in results), results
    import json

    assert json.loads(budget_path("run-c").read_text())["fetches"] == 10


@pytest.mark.asyncio
async def test_charge_persisted_steals_a_stale_lock():
    # A lock file left behind by a crashed holder must never wedge every
    # future charge for the run.
    lock = budget_path("r1").with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()
    old = time.time() - 3600
    os.utime(lock, (old, old))

    await charge_persisted(_deps(), fetch=1)

    import json

    assert json.loads(budget_path("r1").read_text())["fetches"] == 1
    assert not lock.exists()
