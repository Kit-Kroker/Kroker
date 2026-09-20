"""Registration contract for the replay harness (bug: notify-flake).

`GateHost._gate` fires every gate-open notification through
`workflow.execute_activity(notify, ...)` (workflows/gates.py NOTIFY_ACT:
schedule_to_start 5s, one attempt), so each replay scenario whose workflow
opens a gate or question schedules `activity:notify` in its golden command
projection. The harness activity bundles never registered `notify`: the
intended benign path (no registration -> 5s schedule-to-start expiry ->
`_notify` catches -> `_on_notified("unresolved")`) only plays out when the
pending activity task LOSES the race with the next workflow task. When it
wins, the worker hard-fails the WFT with "Activity function notify ... is
not registered on this worker" -- the nondeterministic full-file flake in
tests/replay/test_graph_golden.py (evidence matrix in the bug card).

The deterministic form of that symptom is registration-shaped: whatever a
golden history schedules, the scenario's own `activities()` must register.
These tests are deliberately FAST-tier (no Temporal server): they pin
registration against the committed golden files, not against a live run.
Fix surface: a no-op `notify` fake returning the `Results` shape from
sdlc.notify.contract, added to the harness activity bundles.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from sdlc.core.models import gate_key
from sdlc.notify.activities import notify as production_notify
from sdlc.notify.contract import NotifyInput, NotifyReason, Results
from sdlc.pending import StageGatePending
from tests.replay.harness import GOLDEN, load_golden
from tests.replay.scenarios import GOLDEN_SCENARIOS, Scenario


def _registered(scenario: Scenario) -> dict[str, Any]:
    """name -> callable, exactly as Worker(activities=...) would register:
    the @activity.defn name when present, the function name otherwise."""
    out: dict[str, Any] = {}
    for fn in scenario.activities():
        defn = getattr(fn, "__temporal_activity_definition", None)
        out[defn.name if defn is not None else fn.__name__] = fn
    return out


def _scheduled_activities(scenario: Scenario) -> set[str]:
    return {
        c.split(":", 1)[1]
        for c in load_golden(scenario.name)["commands"]
        if c.startswith("activity:")
    }


def _notify_input() -> NotifyInput:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    return NotifyInput(
        run_id="e74-registration-contract",
        pending=StageGatePending(
            key=gate_key("architecture", 1), gate="architecture", round=1, spec_summary="s"
        ),
        reason=NotifyReason.OPENED,
        opened_at=now,
        now=now,
    )


@pytest.mark.parametrize("scenario", GOLDEN_SCENARIOS, ids=[s.name for s in GOLDEN_SCENARIOS])
def test_every_scheduled_activity_is_registered(scenario: Scenario) -> None:
    """The gate: each golden scenario must register every activity its golden
    command projection schedules. RED on `notify` (12 of 15 scenarios) until
    the harness bundles register a fake; any future activity the workflows
    newly schedule is caught here before it can flake."""
    missing = _scheduled_activities(scenario) - set(_registered(scenario))
    assert not missing, (
        f"{scenario.name}: golden commands schedule {sorted(missing)} but "
        "activities() does not register them. An unregistered scheduled "
        "activity races the next workflow task and fails it with "
        '"Activity function ... is not registered on this worker" '
        "(bug: notify-flake)"
    )


def _notify_scenarios() -> list[Scenario]:
    return [s for s in GOLDEN_SCENARIOS if "activity:notify" in load_golden(s.name)["commands"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", _notify_scenarios(), ids=lambda s: s.name)
async def test_registered_notify_is_a_fake_returning_results(scenario: Scenario) -> None:
    """The notify the harness registers must be a no-op FAKE (never the
    production transport, which resolves real routes) that accepts a valid
    NotifyInput and returns the Results shape `_notify`'s success path
    iterates (gates.py: `out: Results = await ...`)."""
    registered = _registered(scenario)
    assert "notify" in registered, (
        f"{scenario.name}: golden schedules activity:notify but the scenario "
        "registers no notify; the pending task then races the next WFT"
    )
    fn = registered["notify"]
    assert fn is not production_notify, (
        "the harness must register a fake notify, not the production transport"
    )
    out = await fn(_notify_input())
    Results.model_validate(out.model_dump() if isinstance(out, Results) else out)


@pytest.mark.parametrize("scenario", GOLDEN_SCENARIOS, ids=[s.name for s in GOLDEN_SCENARIOS])
def test_core_activities_stay_registered(scenario: Scenario) -> None:
    """The fix may only ADD registrations (today: notify). Dropping any
    existing one breaks the golden runs for an unrelated reason."""
    assert {"evaluate_gate", "export_run_artifacts"} <= set(_registered(scenario)), scenario.name


# activity:notify schedulings per committed golden file (counts at the fix
# base, main 2c732e0; 34 in total). The fix registers a fake and must not
# change what the workflows schedule; the goldens are byte-frozen and may
# not be regenerated, so these counts are part of the contract.
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


def test_goldens_schedule_notify_exactly_as_pinned() -> None:
    """Guards both halves of the byte-identity constraint: the golden file
    set is unchanged, and scheduling notify stays in the projections (a
    "fix" that deschedules notify in production, or a golden regeneration,
    turns this red)."""
    files = {p.name[: -len(".json")] for p in GOLDEN.glob("*.json")}
    assert files == set(NOTIFY_SCHEDULINGS), "the golden file set changed"
    for name, count in NOTIFY_SCHEDULINGS.items():
        commands = load_golden(name)["commands"]
        assert commands.count("activity:notify") == count, name
