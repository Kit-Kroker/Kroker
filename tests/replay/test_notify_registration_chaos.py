"""Chaos/edge RED contracts for the replay-harness notify race (bug notify-flake).

The replay harness hands `Worker(activities=scenario.activities())` bundles
that do not register every activity the golden histories schedule: `notify`
in 13 goldens (34 schedulings) and -- discovered by this sweep, NOT named in
the assessment -- `plan_research` in research_greenfield. The intended benign
path (unregistered -> schedule-to-start expiry -> caught by the caller) races
the temporalio worker: a pending activity task for an unregistered type that
collides with the next workflow task hard-fails the WFT ("Activity function
... is not registered"), which is the full-file flake.

These rows pin the deterministic contract that closes the race window -- no
pending task for an unregistered type can exist -- at the edges the candidate
fix could miss:

- every scenario whose golden schedules `activity:notify` must register
  `notify`, whatever bundle SHAPE it uses: only 6 scenarios ride the shared
  `_base_activities`/`_budget_activities` helpers, the other notify-scheduling
  scenarios build inline lists, so patching just the two helpers leaves 7
  goldens red
- a general sweep (excluding notify, so it stays separable from the rows
  above under a scope ruling) catches any OTHER unregistered scheduled
  activity: today that is plan_research in research_greenfield
- the two shared bundle helpers register notify by name (the assessment's
  minimum fix surface)
- once registered, every bundle's notify fake must ACCEPT the production
  NotifyInput payload (including the optional-field boundaries deadline=None
  / project=None) and RETURN the `Results` contract from
  sdlc.notify.contract: `GateHost._notify` iterates `out.results` OUTSIDE its
  try/except (gates.py), so a garbage-returning fake kills the workflow on a
  path the "unresolved" fallback used to make unreachable -- and registering
  the production notify does not satisfy this either; the ruled fix is a
  no-op fake

Every row is assertion-RED on the pre-fix tree (verified individually; see
.specify/bugs/notify-flake/). Deterministic: pure inspection of scenario
bundles and committed goldens, no Temporal, no server, no timers.

Consolidation (2026-09-20): this file subsumes qa-happy's
test_activity_registration.py (b89e11e) -- its three unique pins are folded
in (the fake must never be the production transport; evaluate_gate /
export_run_artifacts stay registered everywhere; the golden file set and
per-file notify counts are frozen) -- and that duplicate file is retired.
Orchestrator ruling: partial_awaiting_architecture's fixture golden IS in
the sweep set.

Concurrency axis: registration completeness IS the deterministic pin for the
race (the stress reproduction is nondeterministic by the task card's own
ruling and is evidence, not a gate). No fabricated threading rows.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

import pytest

from sdlc.notify.activities import notify as production_notify
from sdlc.notify.contract import NotifyInput, NotifyReason, Results
from sdlc.pending import StageGatePending
from tests.replay.harness import GOLDEN, load_golden
from tests.replay.scenarios import SCENARIOS, _base_activities, _budget_activities

_BY_NAME = {s.name: s for s in SCENARIOS}
NOTIFY_SCHEDULERS = [
    s.name
    for s in SCENARIOS
    if any(c == "activity:notify" for c in load_golden(s.name)["commands"])
]

# activity:notify schedulings per committed golden file (counts at the bug
# base, main 2c732e0; 34 in total -- folded in from qa-happy's
# test_activity_registration.py at consolidation). The fix registers a fake
# and must not change what the workflows schedule; the goldens are
# byte-frozen and may not be regenerated, so these counts are contract.
NOTIFY_SCHEDULINGS: dict[str, int] = {
    "arch_revise_final": 5,
    "arch_timeout_reject": 4,
    "brownfield_happy": 3,
    "budget_arch_reject": 2,
    "budget_clarify_reject": 1,
    "cancel_during_code": 2,
    "context_reject": 0,
    "delta_failed": 0,
    "greenfield_happy": 3,
    "intake_reject": 0,
    "max_gate_rounds_1": 4,
    "partial_awaiting_architecture": 1,
    "plan_revise_approve": 4,
    "research_greenfield": 1,
    "seeded": 1,
    "waves": 3,
}


def _registered_names(fns: list) -> set[str]:
    """Worker-registered activity names for a bundle.

    Reads temporalio's own decoration (`__temporal_activity_definition`), the
    same metadata `Worker(activities=...)` resolves -- NOT `fn.__name__`,
    which diverges for every aliased fake (fixed_price registers as
    price_usage). An undecorated member contributes nothing: temporalio
    rejects it at Worker construction, and if its activity is scheduled the
    sweep below reports the name as missing.
    """
    names: set[str] = set()
    for fn in fns:
        defn = getattr(fn, "__temporal_activity_definition", None)
        if defn is not None:
            names.add(defn.name)
    return names


def _scheduled_activities(name: str) -> set[str]:
    cmds = load_golden(name)["commands"]
    return {c.split(":", 1)[1] for c in cmds if c.startswith("activity:")}


@pytest.mark.parametrize("name", NOTIFY_SCHEDULERS)
def test_notify_is_registered_by_every_scenario_that_schedules_it(name):
    scenario = _BY_NAME[name]
    registered = _registered_names(scenario.activities())
    assert "notify" in registered, (
        f"notify-flake race: {name} golden schedules activity:notify but its "
        f"bundle ({scenario.activities.__name__}) does not register it; a "
        "pending unregistered activity task is the WFT-collision race"
    )


@pytest.mark.parametrize("name", [s.name for s in SCENARIOS])
def test_no_activity_other_than_notify_is_left_unregistered(name):
    """The general contract, minus notify so a scope ruling on the notify rows
    cannot silently weaken it: whatever else a golden schedules must be
    registered. Today red ONLY on research_greenfield/plan_research."""
    missing = (
        _scheduled_activities(name) - _registered_names(_BY_NAME[name].activities()) - {"notify"}
    )
    assert not missing, (
        f"notify-flake sweep: {name} schedules {sorted(missing)} that its "
        "bundle does not register -- the same unregistered-activity race "
        "class as notify (worker hard-fails the WFT on collision)"
    )


def test_base_activities_registers_notify():
    assert "notify" in _registered_names(_base_activities()), (
        "notify-flake: _base_activities() omits notify (assessment's minimum fix surface)"
    )


def test_budget_activities_registers_notify():
    assert "notify" in _registered_names(_budget_activities()), (
        "notify-flake: _budget_activities() omits notify (assessment's minimum fix surface)"
    )


def _registered_map(name: str) -> dict[str, Any]:
    """name -> callable, exactly as Worker(activities=...) registers it."""
    out: dict[str, Any] = {}
    for fn in _BY_NAME[name].activities():
        defn = getattr(fn, "__temporal_activity_definition", None)
        if defn is not None:
            out[defn.name] = fn
    return out


@pytest.mark.parametrize("name", [s.name for s in SCENARIOS])
def test_no_bundle_registers_a_name_twice(name):
    """The same activity name twice in one bundle is a Worker-construction
    error -- the fix could introduce it by adding the notify fake in two
    places (e.g. inside fake_agent_activities AND the bundle). Names are
    collected from the RAW bundle into a LIST: a dict would deduplicate
    registrations on insert and this row could never fail. (qa-chaos
    landing-green guard, adopted at consolidation; list shape restored at
    reviewer finding.)"""
    names = [
        defn.name
        for fn in _BY_NAME[name].activities()
        if (defn := getattr(fn, "__temporal_activity_definition", None)) is not None
    ]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert len(names) == len(set(names)) and not dupes, (
        f"{name}: bundle registers {dupes} more than once"
    )


@pytest.mark.parametrize("name", [s.name for s in SCENARIOS])
def test_core_activities_stay_registered(name):
    """The fix may only ADD registrations (today: notify, plan_research).
    Dropping any existing one breaks the golden runs for an unrelated
    reason. (Folded from qa-happy's test_activity_registration.py.)"""
    registered = _registered_map(name)
    missing = {"evaluate_gate", "export_run_artifacts"} - set(registered)
    assert not missing, f"{name}: core activities {sorted(missing)} dropped"


def test_goldens_schedule_notify_exactly_as_pinned():
    """Guards both halves of the byte-identity constraint: the golden file
    set is unchanged (16 files), and scheduling notify stays in the
    projections (a "fix" that deschedules notify in production, or a golden
    regeneration, turns this red). (Folded from qa-happy's
    test_activity_registration.py.)"""
    files = {p.name[: -len(".json")] for p in GOLDEN.glob("*.json")}
    assert files == set(NOTIFY_SCHEDULINGS), "the golden file set changed"
    for name, count in NOTIFY_SCHEDULINGS.items():
        commands = load_golden(name)["commands"]
        assert commands.count("activity:notify") == count, name


def _notify_fake(bundle: list) -> Any:
    for fn in bundle:
        defn = getattr(fn, "__temporal_activity_definition", None)
        if defn is not None and defn.name == "notify":
            return fn
    pytest.fail(
        "notify-flake: bundle registers no notify fake -- cannot assess its "
        "return contract (the ruled fix is a no-op fake returning Results)"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", NOTIFY_SCHEDULERS)
async def test_registered_notify_fake_honours_the_results_contract(name):
    """Error path the benign fallback used to make unreachable: on success
    GateHost._notify iterates out.results outside its try/except, so the fake
    must return the Results contract -- and must tolerate the optional-field
    boundaries (deadline=None HOLD, project=None non-F4 hosts) that
    NotifyInput carries."""
    fake = _notify_fake(_BY_NAME[name].activities())
    assert fake is not production_notify, (
        "the harness must register a no-op fake notify, never the production "
        "transport (folded from qa-happy's test_activity_registration.py)"
    )
    inp = NotifyInput(
        run_id="e74-chaos-notify",
        pending=StageGatePending(
            key="architecture#1", gate="architecture", round=1, spec_summary="s"
        ),
        reason=NotifyReason.OPENED,
        opened_at=datetime.now(UTC),
        now=datetime.now(UTC),
        deadline=None,
        project=None,
    )
    out = fake(inp)
    if inspect.isawaitable(out):
        out = await out
    results = Results.model_validate(out)
    assert isinstance(results.results, list)
