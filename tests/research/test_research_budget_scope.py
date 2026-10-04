"""Scoped budgets: each sub-question gets its own counter so one cannot drain
the run, while a shared 'run' counter still caps the total."""

import asyncio
import json
import os

import pytest

from sdlc.stages.research import budget_store
from sdlc.stages.research.budget_store import budget_path, charge_persisted, charge_scoped
from sdlc.stages.research.deps import BudgetExceeded, ResearchDeps


def _deps(run_id: str = "r1", max_fetches: int = 2) -> ResearchDeps:
    return ResearchDeps(
        run_id=run_id, provider="fake", max_searches=2, max_fetches=max_fetches, max_cost_usd=1.0
    )


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
        await charge_scoped(_deps(max_fetches=10), fetch=1, scope=f"sq-{i}", run_max_cost_usd=0.05)
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=10), fetch=1, scope="sq-2", run_max_cost_usd=0.05)


@pytest.mark.asyncio
async def test_charge_scoped_does_not_charge_the_scope_when_the_run_ceiling_trips():
    # The run check runs FIRST. A sub-question must not be billed for work
    # the run ceiling refused.
    await charge_scoped(_deps(max_fetches=10), fetch=1, scope="sq-0", run_max_cost_usd=0.03)
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=10), fetch=1, scope="sq-1", run_max_cost_usd=0.03)
    assert not budget_path("r1", "sq-1").exists()


@pytest.mark.asyncio
async def test_charge_scoped_with_run_scope_charges_once_not_twice():
    """When the call's scope IS 'run' (the architect path, which doesn't fan
    out), the run ceiling and the scope collapse to the same budget-run.json.
    Charging both -- as charge_scoped does for sub-questions -- writes that
    file twice, doubles the count, and makes max_searches/max_fetches bind at
    half. The single charge must record the counter once."""
    await charge_scoped(_deps(max_fetches=2), fetch=1, scope="run", run_max_cost_usd=4.0)
    assert json.loads(budget_path("r1", "run").read_text())["fetches"] == 1


@pytest.mark.asyncio
async def test_charge_scoped_with_run_scope_enforces_count_at_full_allowance():
    """The half-allowance symptom: max_fetches=2 must permit a 2nd fetch, not
    trip on it because the first call already recorded 2."""
    await charge_scoped(_deps(max_fetches=2), fetch=1, scope="run", run_max_cost_usd=4.0)
    await charge_scoped(_deps(max_fetches=2), fetch=1, scope="run", run_max_cost_usd=4.0)
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=2), fetch=1, scope="run", run_max_cost_usd=4.0)


@pytest.mark.asyncio
async def test_research_subquestion_charges_its_own_scope():
    # The per-sub-question allowance is only real if the toolset charges the
    # sub-question's scope rather than the shared run counter.
    from sdlc.stages.research.models import (
        ResearchBrief,
        SubQuestion,
    )
    from sdlc.stages.research.stage import SubQuestionInput
    from sdlc.stages.research.stage import _research_subquestion_impl as research_subquestion

    inp = SubQuestionInput(
        sub_question=SubQuestion(id="sq-7", question="q"),
        deps=_deps(),
        model="test-model",
        max_requests=40,
        max_run_cost_usd=4.0,
    )

    captured = {}

    class _U:
        input_tokens = output_tokens = 0
        cache_read_tokens = cache_write_tokens = 0

    class _Agent:
        async def run(self, prompt, **kw):
            captured["scope"] = kw["deps"].scope
            captured["run_max"] = kw["deps"].max_run_cost_usd

            class _R:
                output = ResearchBrief(summary="s")
                usage = _U()

            return _R()

    await research_subquestion(inp, _agent=_Agent())
    assert captured["scope"] == "sq-7"
    assert captured["run_max"] == 4.0


def test_research_deps_defaults_to_the_run_scope():
    d = _deps()
    assert d.scope == "run"


# ---------------------------------------------------------------------------
# Plan-D5 scope cases 1-3 (feature 008, defect H4): a charge refused by the
# sub-question's own allowance must leave the SHARED run counter untouched
# too. Today charge_scoped commits the run charge first and only then lets
# the scope refuse, so every refused call burns the run ceiling its siblings
# share (plan D3: check both counters before writing either).


@pytest.mark.asyncio
async def test_charge_scoped_refused_by_the_scope_leaves_the_run_counter_unchanged():
    await charge_scoped(_deps(max_fetches=1), fetch=1, scope="sq-0", run_max_cost_usd=4.0)
    run_path = budget_path("r1", "run")
    before = run_path.read_bytes()
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=1), fetch=1, scope="sq-0", run_max_cost_usd=4.0)
    assert run_path.read_bytes() == before
    assert json.loads(run_path.read_text())["fetches"] == 1


@pytest.mark.asyncio
async def test_charge_scoped_concurrent_room_for_one_moves_the_run_counter_once():
    results = await asyncio.gather(
        *(
            charge_scoped(_deps(max_fetches=1), fetch=1, scope="sq-0", run_max_cost_usd=4.0)
            for _ in range(3)
        ),
        return_exceptions=True,
    )
    assert sum(r is None for r in results) == 1
    assert sum(isinstance(r, BudgetExceeded) for r in results) == 2
    assert json.loads(budget_path("r1", "run").read_text())["fetches"] == 1
    assert json.loads(budget_path("r1", "sq-0").read_text())["fetches"] == 1


@pytest.mark.asyncio
async def test_charge_scoped_refused_architect_scope_leaves_the_run_counter_unchanged():
    # spec N1: the architect's research tool charges scope="architect" through
    # this same code, so the fix must hold there too.
    await charge_scoped(_deps(max_fetches=1), fetch=1, scope="architect", run_max_cost_usd=4.0)
    run_path = budget_path("r1", "run")
    before = run_path.read_bytes()
    with pytest.raises(BudgetExceeded):
        await charge_scoped(_deps(max_fetches=1), fetch=1, scope="architect", run_max_cost_usd=4.0)
    assert run_path.read_bytes() == before
    assert json.loads(run_path.read_text())["fetches"] == 1


# ---------------------------------------------------------------------------
# Plan-D5 scope cases 4 and 5 (feature 008): the refusal NOTE the stage's
# retry-exhaustion handler will read (plan D3 -- which counter refused, then
# today's message, byte for byte), and the one possible crash leftover once
# both counters are checked before either is written (scope one ahead, never
# the shared ceiling).


@pytest.mark.asyncio
async def test_a_scope_refusal_is_noted_on_the_caller_deps():
    d = _deps(max_fetches=1)
    await charge_scoped(d, fetch=1, scope="sq-0", run_max_cost_usd=4.0)
    assert d.refusals == [], "an accepted charge notes nothing"
    with pytest.raises(BudgetExceeded) as excinfo:
        await charge_scoped(d, fetch=1, scope="sq-0", run_max_cost_usd=4.0)
    assert str(excinfo.value) == "fetch budget exhausted (1 fetches)"
    assert len(d.refusals) == 1
    assert str(excinfo.value) in d.refusals[0]
    assert d.refusals[0].startswith("sq-0 allowance: ")


@pytest.mark.asyncio
async def test_a_run_ceiling_refusal_is_noted_as_the_run_ceiling():
    # FETCH_COST_USD is 0.02, so a $0.03 run ceiling admits one fetch and
    # refuses the second.
    d = _deps(max_fetches=10)
    await charge_scoped(d, fetch=1, scope="sq-0", run_max_cost_usd=0.03)
    with pytest.raises(BudgetExceeded) as excinfo:
        await charge_scoped(d, fetch=1, scope="sq-0", run_max_cost_usd=0.03)
    assert str(excinfo.value) == "cost budget exhausted ($0.03)"
    assert len(d.refusals) == 1
    assert str(excinfo.value) in d.refusals[0]
    assert d.refusals[0].startswith("run ceiling: ")


@pytest.mark.asyncio
async def test_a_lock_timeout_propagates_and_is_never_a_refusal(monkeypatch):
    # EC4: a lock timeout is an infrastructure error, not a bound -- it must
    # reach Temporal's retry unchanged and note nothing.
    async def _always_timeout(lock_path):
        raise TimeoutError(f"research budget lock held too long: {lock_path}")

    monkeypatch.setattr(budget_store, "_acquire_lock", _always_timeout)
    d = _deps()
    with pytest.raises(TimeoutError):
        await charge_scoped(d, fetch=1, scope="sq-0", run_max_cost_usd=4.0)
    assert d.refusals == []


@pytest.mark.asyncio
async def test_a_crash_between_the_two_publishes_leaves_only_the_scope_counter(monkeypatch):
    # Case 5 (EC6): with both counters checked before either is written the
    # publishes become scope-then-run (plan D3), so the one possible crash
    # leftover is the scope counter one charge ahead. Today the run counter is
    # written first, so the crash lands with the run charged and the scope
    # missing. Precedent for the counter-armed os.replace:
    # test_research_budget_atomic_write.py::test_crash_at_the_publish_boundary.
    real_replace = os.replace
    calls = {"n": 0}

    def crashing_replace(src, dst, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated crash at the second publish")
        return real_replace(src, dst, **kwargs)

    monkeypatch.setattr(budget_store.os, "replace", crashing_replace)

    with pytest.raises(OSError):
        await charge_scoped(_deps(run_id="r-crash"), fetch=1, scope="sq-0", run_max_cost_usd=4.0)

    assert json.loads(budget_path("r-crash", "sq-0").read_text())["fetches"] == 1
    assert not budget_path("r-crash", "run").exists()
    research_dir = budget_path("r-crash").parent
    leftovers = [p.name for p in research_dir.rglob("*") if p.suffix in (".tmp", ".lock")]
    assert leftovers == []
