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

Concurrency axis: registration completeness IS the deterministic pin for the
race (the stress reproduction is nondeterministic by the task card's own
ruling and is evidence, not a gate). No fabricated threading rows.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

import pytest

from sdlc.notify.contract import NotifyInput, NotifyReason, Results
from sdlc.pending import StageGatePending
from tests.replay.harness import load_golden
from tests.replay.scenarios import SCENARIOS, _base_activities, _budget_activities

_BY_NAME = {s.name: s for s in SCENARIOS}
NOTIFY_SCHEDULERS = [
    s.name
    for s in SCENARIOS
    if any(c == "activity:notify" for c in load_golden(s.name)["commands"])
]


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
