"""Contract tests for the 023b maintenance model additions (023b T004, RED).

Subject: ``sdlc.maintenance.models`` gains the execute-side fields, states and
models in data-model.md (R7, R10, R14). Authoritative contract:
``.specify/specs/023b-daper-acts-verifies/data-model.md``.

New names are imported inside each test, not at module level, so each missing
contract fails on its own test rather than breaking collection for the file.
Happy-path and schema pins only; the edge refusals live in the chaos half.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.maintenance.models import (
    Incident,
    MaintenanceConfig,
    MaintenanceState,
)

REPO_DIR = "/abs/repo"
FIXTURE = Path(__file__).parent / "fixtures" / "state_023a.json"

# Every 023b-added key, listed explicitly so a new field cannot slip in unlisted.
ADDED_CONFIG_KEYS = {
    "execute",
    "max_starts_per_cycle",
    "max_starts_per_window",
    "max_reopens",
    "child_timeout_hours",
}
ADDED_INCIDENT_KEYS = {
    "consecutive_seen",
    "attempt",
    "reopens",
    "gate_round",
    "execution",
    "executions",
    "verification",
    "retained",
}
ADDED_STATE_KEYS = {"exec_starts"}


def _cfg(**overrides) -> MaintenanceConfig:
    base = {
        "project": "demo",
        "repo_dir": REPO_DIR,
        "build_probe": False,
    }
    base.update(overrides)
    return MaintenanceConfig(**base)


def _incident(no: int, key: str, state: str, **overrides) -> Incident:
    base = {
        "no": no,
        "key": key,
        "kind": "finding",
        "commit_sha": "a" * 40,
        "first_seen_cycle": 1,
        "last_seen_cycle": 1,
        "state": state,
    }
    base.update(overrides)
    return Incident(**base)


# ---------------------------------------------------------------- config


def test_config_execute_defaults():
    cfg = _cfg()
    assert cfg.execute is False
    assert cfg.max_starts_per_cycle == 1
    assert cfg.max_starts_per_window == 3
    assert cfg.max_reopens == 2
    assert cfg.child_timeout_hours == 24


def test_config_execute_true_accepted_with_probe_and_ack():
    cfg = _cfg(execute=True, build_probe=True, ack_unattended_build_probe=True)
    assert cfg.execute is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"execute": True, "build_probe": True, "ack_unattended_build_probe": False},
        {"execute": True, "build_probe": False, "ack_unattended_build_probe": True},
    ],
)
def test_config_execute_requires_probe_and_ack(overrides):
    # Guard against a false green: the refusal must come from the probe/ack
    # rule, not from `execute` being an unknown (extra-forbidden) field.
    assert "execute" in MaintenanceConfig.model_fields
    with pytest.raises(ValidationError, match="ack_unattended_build_probe|build_probe"):
        _cfg(**overrides)


@pytest.mark.parametrize(
    ("field", "good", "bad"),
    [
        ("max_starts_per_cycle", (1, 3), (0, 4)),
        ("max_starts_per_window", (1, 10), (0, 11)),
        ("max_reopens", (0, 2), (-1, 3)),
        ("child_timeout_hours", (1, 168), (0, 169)),
    ],
)
def test_config_execute_bounds(field, good, bad):
    for value in good:
        assert getattr(_cfg(**{field: value}), field) == value
    for value in bad:
        with pytest.raises(ValidationError):
            _cfg(**{field: value})


def test_config_keeps_no_gate_policy_or_timeout_field():
    # B-FR-019: 023b adds no gate, policy or on-timeout surface.
    fields = set(MaintenanceConfig.model_fields)
    assert not ({"gates", "policy", "on_timeout"} & fields)


# ---------------------------------------------------------------- states


def test_incident_state_gains_live_and_closed_members():
    from sdlc.maintenance.models import IncidentState

    expected = {
        "approved",
        "queued",
        "executing",
        "verifying",
        "verified",
        "reopened",
        "closed",
    }
    assert expected <= {s.value for s in IncidentState}


def test_terminal_states_gain_only_closed():
    from sdlc.maintenance.models import TERMINAL_INCIDENT_STATES, IncidentState

    assert IncidentState.CLOSED in TERMINAL_INCIDENT_STATES
    for live in ("approved", "queued", "executing", "verifying", "verified", "reopened"):
        assert IncidentState(live) not in TERMINAL_INCIDENT_STATES


# ---------------------------------------------------------------- incident fields


def test_incident_023b_field_defaults():
    inc = _incident(1, "k", "open")
    assert inc.consecutive_seen == 1
    assert inc.attempt == 0
    assert inc.reopens == 0
    assert inc.gate_round == 1
    assert inc.execution is None
    assert inc.executions == []
    assert inc.verification is None
    assert inc.retained is False


# ---------------------------------------------------------------- new models


def test_execution_record_happy_path_round_trip():
    from sdlc.maintenance.models import ExecutionRecord

    rec = ExecutionRecord(
        attempt=1,
        child_id="maint-demo-abcd1234-inc1-a1",
        base_sha="b" * 40,
        started_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
        outcome="running",
        detail="started",
    )
    assert rec.integration_branch is None
    assert rec.integration_head is None
    again = ExecutionRecord.model_validate(rec.model_dump(mode="json"))
    assert again == rec


def test_execution_record_outcome_members_are_pinned():
    from typing import get_args

    from sdlc.maintenance.models import ExecutionRecord

    outcome = ExecutionRecord.model_fields["outcome"].annotation
    assert set(get_args(outcome)) == {
        "running",
        "awaiting_merge",
        "failed",
        "config_failed",
        "timed_out",
        "empty_diff",
        "rejected_by_loop",
        "completed",
    }


def test_execution_record_detail_is_bounded_at_300():
    from sdlc.maintenance.models import ExecutionRecord

    base = {
        "attempt": 1,
        "child_id": "c",
        "base_sha": "b" * 40,
        "started_at": datetime(2026, 11, 15, tzinfo=UTC),
        "outcome": "running",
    }
    ExecutionRecord(**base, detail="x" * 300)
    with pytest.raises(ValidationError):
        ExecutionRecord(**base, detail="x" * 301)


def test_verification_result_happy_path_and_verdicts():
    from typing import get_args

    from sdlc.maintenance.models import VerificationResult

    verdict = VerificationResult.model_fields["verdict"].annotation
    assert set(get_args(verdict)) == {
        "resolved",
        "persisted",
        "new",
        "unverifiable",
        "conflicted",
        "absent_at_base",
    }
    res = VerificationResult(
        child_id="maint-demo-abcd1234-inc1-a1",
        base_sha="b" * 40,
        verify_head="c" * 40,
        collected=True,
        verdict="resolved",
        delta_note="identity absent on verify",
    )
    assert VerificationResult.model_validate(res.model_dump(mode="json")) == res


def test_child_probe_phases_and_fields():
    from sdlc.maintenance.models import ChildProbe

    probe = ChildProbe(
        phase="awaiting_merge",
        pending_merge_round=1,
        integration_branch="sdlc/maint-demo-abcd1234-inc1-a1/integration",
        integration_head="d" * 40,
        result=None,
        failure=None,
        non_retryable=False,
    )
    assert probe.phase == "awaiting_merge"
    assert ChildProbe.model_validate(probe.model_dump(mode="json")) == probe
    assert {"not_found", "running", "awaiting_merge", "completed", "failed"} <= set(
        ChildProbe.model_fields["phase"].annotation.__args__
    )


# ---------------------------------------------------------------- state


def test_state_exec_starts_defaults_empty_and_holds_datetimes():
    state = MaintenanceState(config=_cfg())
    assert state.exec_starts == []
    stamp = datetime(2026, 11, 15, 9, 30, tzinfo=UTC)
    state2 = MaintenanceState(config=_cfg(), exec_starts=[stamp])
    assert state2.exec_starts == [stamp]


def test_duplicate_key_refused_among_live_execute_states():
    for live in ("approved", "queued", "executing", "verifying", "verified", "reopened"):
        with pytest.raises(ValidationError, match="duplicate incident key"):
            MaintenanceState(
                config=_cfg(),
                incidents=[
                    _incident(1, "same", live),
                    _incident(2, "same", "open"),
                ],
            )


def test_closed_incident_does_not_block_a_new_key_holder():
    state = MaintenanceState(
        config=_cfg(),
        incidents=[_incident(1, "same", "closed"), _incident(2, "same", "open")],
    )
    assert [i.no for i in state.incidents] == [1, 2]


# ---------------------------------------------------------------- 023a fixture pin (R7)


def _strip_added(dumped: dict) -> dict:
    out = {k: v for k, v in dumped.items() if k not in ADDED_STATE_KEYS}
    out["config"] = {k: v for k, v in dumped["config"].items() if k not in ADDED_CONFIG_KEYS}
    out["incidents"] = [
        {k: v for k, v in inc.items() if k not in ADDED_INCIDENT_KEYS}
        for inc in dumped["incidents"]
    ]
    return out


def test_023a_state_fixture_validates_and_round_trips_unchanged():
    # Written by the T002 capture test. Missing until T002 runs: this is RED
    # on purpose, because R7's pin cannot be proven without the fixture.
    if not FIXTURE.exists():
        pytest.fail(f"023a state fixture missing at {FIXTURE}; run T002 (capture) first")
    payload = json.loads(FIXTURE.read_text())

    # The fixture must not already carry 023b keys, or the pin is vacuous.
    assert not (ADDED_STATE_KEYS & set(payload))
    assert not (ADDED_CONFIG_KEYS & set(payload["config"]))
    for inc in payload["incidents"]:
        assert not (ADDED_INCIDENT_KEYS & set(inc))

    state = MaintenanceState.model_validate(payload)
    dumped = state.model_dump(mode="json")
    assert _strip_added(dumped) == payload


def test_023a_state_fixture_added_fields_take_their_defaults():
    if not FIXTURE.exists():
        pytest.fail(f"023a state fixture missing at {FIXTURE}; run T002 (capture) first")
    state = MaintenanceState.model_validate(json.loads(FIXTURE.read_text()))
    assert state.exec_starts == []
    assert state.config.execute is False
    for inc in state.incidents:
        assert inc.consecutive_seen == 1
        assert inc.attempt == 0
        assert inc.reopens == 0
        assert inc.gate_round == 1
        assert inc.execution is None
        assert inc.executions == []
        assert inc.verification is None
        assert inc.retained is False


# ---------------------------------------------------------- CHAOS / EDGE HALF (023b T004, RED)
#
# Refusals and edge defaults the contract half above does not reach. Each test
# first guards that the new name exists, so a model that merely has
# extra='forbid' cannot produce a false green from an unrelated refusal.


@pytest.mark.parametrize("outcome", ["bogus", "RUNNING", ""])
def test_execution_record_refuses_an_outcome_outside_the_literal(outcome):
    from sdlc.maintenance.models import ExecutionRecord

    with pytest.raises(ValidationError, match="outcome"):
        ExecutionRecord(
            attempt=1,
            child_id="maint-demo-abcd1234-inc1-a1",
            base_sha="b" * 40,
            started_at=datetime(2026, 11, 15, tzinfo=UTC),
            outcome=outcome,
            detail="",
        )


@pytest.mark.parametrize("verdict", ["green", "RESOLVED", ""])
def test_verification_result_refuses_a_verdict_outside_the_literal(verdict):
    from sdlc.maintenance.models import VerificationResult

    with pytest.raises(ValidationError, match="verdict"):
        VerificationResult(
            child_id="maint-demo-abcd1234-inc1-a1",
            base_sha="b" * 40,
            verify_head="c" * 40,
            collected=True,
            verdict=verdict,
            delta_note="",
        )


@pytest.mark.parametrize("phase", ["pending", "", "NOT_FOUND"])
def test_child_probe_refuses_an_unknown_phase_and_names_it(phase):
    from sdlc.maintenance.models import ChildProbe

    with pytest.raises(ValidationError, match="phase"):
        ChildProbe(
            phase=phase,
            pending_merge_round=None,
            integration_branch=None,
            integration_head=None,
            result=None,
            failure=None,
            non_retryable=False,
        )


def test_incident_defaults_fill_the_023b_fields_when_only_some_are_given():
    assert "attempt" in Incident.model_fields
    inc = _incident(1, "k", "open", attempt=2)
    assert inc.attempt == 2
    assert inc.consecutive_seen == 1
    assert inc.reopens == 0
    assert inc.gate_round == 1
    assert inc.execution is None
    assert inc.executions == []
    assert inc.verification is None
    assert inc.retained is False


def test_incident_executions_default_is_not_shared_between_incidents():
    assert "executions" in Incident.model_fields
    first = _incident(1, "a", "open")
    second = _incident(2, "b", "open")
    assert first.executions is not second.executions


@pytest.mark.parametrize("stamp", ["not-a-date", None, [], {"at": 1}])
def test_state_refuses_an_exec_starts_entry_that_is_not_a_datetime(stamp):
    assert "exec_starts" in MaintenanceState.model_fields
    with pytest.raises(ValidationError, match="exec_starts"):
        MaintenanceState(config=_cfg(), exec_starts=[stamp])
