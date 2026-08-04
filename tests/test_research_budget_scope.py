"""Scoped budgets: each sub-question gets its own counter so one cannot drain
the run, while a shared 'run' counter still caps the total."""
import json

import pytest

from sdlc.research.budget_store import (budget_path, charge_persisted,
                                        charge_scoped)
from sdlc.research.deps import BudgetExceeded, ResearchDeps


def _deps(run_id: str = "r1", max_fetches: int = 2) -> ResearchDeps:
    return ResearchDeps(run_id=run_id, provider="fake",
                        max_searches=2, max_fetches=max_fetches,
                        max_cost_usd=1.0)


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def test_default_scope_is_run_and_keeps_the_legacy_filename_shape():
    assert budget_path("r1").name == "budget-run.json"
    assert budget_path("r1", "sq-3").name == "budget-sq-3.json"


@pytest.mark.asyncio
async def test_separate_scopes_do_not_share_a_counter():
    await charge_persisted(_deps(), fetch=2, scope="sq-1")
    # sq-1 is now at its cap; sq-2 is untouched and must still succeed.
    await charge_persisted(_deps(), fetch=2, scope="sq-2")
    assert json.loads(budget_path("r1", "sq-1").read_text())["fetches"] == 2
    assert json.loads(budget_path("r1", "sq-2").read_text())["fetches"] == 2


@pytest.mark.asyncio
async def test_a_scope_still_enforces_its_own_cap():
    await charge_persisted(_deps(), fetch=2, scope="sq-1")
    with pytest.raises(BudgetExceeded):
        await charge_persisted(_deps(), fetch=1, scope="sq-1")


@pytest.mark.asyncio
async def test_charge_scoped_also_charges_the_run_counter():
    await charge_scoped(_deps(), fetch=1, scope="sq-1", run_max_cost_usd=4.0)
    assert json.loads(budget_path("r1", "sq-1").read_text())["fetches"] == 1
    assert json.loads(budget_path("r1", "run").read_text())["fetches"] == 1


@pytest.mark.asyncio
async def test_charge_scoped_trips_on_the_run_ceiling_even_when_the_scope_is_fine():
    # FETCH_COST_USD is 0.02, so 4 fetches = $0.08. A run ceiling of $0.05
    # trips on the third even though each sub-question scope allows more.
    for i in range(2):
        await charge_scoped(_deps(max_fetches=10), fetch=1,
                            scope=f"sq-{i}", run_max_cost_usd=0.05)
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=10), fetch=1,
                            scope="sq-2", run_max_cost_usd=0.05)


@pytest.mark.asyncio
async def test_charge_scoped_does_not_charge_the_scope_when_the_run_ceiling_trips():
    # The run check runs FIRST. A sub-question must not be billed for work
    # the run ceiling refused.
    await charge_scoped(_deps(max_fetches=10), fetch=1,
                        scope="sq-0", run_max_cost_usd=0.03)
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=10), fetch=1,
                            scope="sq-1", run_max_cost_usd=0.03)
    assert not budget_path("r1", "sq-1").exists()
