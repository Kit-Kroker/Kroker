"""Scoped budgets: each sub-question gets its own counter so one cannot drain
the run, while a shared 'run' counter still caps the total."""

import json

import pytest

from sdlc.research.budget_store import budget_path, charge_persisted, charge_scoped
from sdlc.research.deps import BudgetExceeded, ResearchDeps


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
    from sdlc.models import ResearchBrief, SubQuestion
    from sdlc.research.stage import SubQuestionInput
    from sdlc.research.stage import _research_subquestion_impl as research_subquestion

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
