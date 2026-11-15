"""Happy-path contracts for the maintenance domain models (023a T004, RED).

Subject: ``sdlc.maintenance.models`` (does not exist yet; T005 implements it).
Authoritative contract: ``.specify/specs/023-daper-maintenance-loop/data-model.md``.

Edge cases (boundary refusals, extra-field refusals, duplicate incident keys)
belong to the chaos half of this file; the tests here only pin valid inputs,
defaults, enum membership, field order and round-trips.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.maintenance.models import (
    DETECT_SIGNALS,
    MAX_PREV_FINDINGS,
    Baseline,
    Incident,
    IncidentState,
    MaintenanceConfig,
    MaintenanceKickInput,
    MaintenanceState,
    RepairAction,
    RepairPlan,
    RepairProposal,
)
from tests.maintenance.conftest import env_file_findings, make_triage

# --------------------------------------------------------------------------- #
# MaintenanceConfig
# --------------------------------------------------------------------------- #


def _cfg(**kw) -> MaintenanceConfig:
    # build_probe defaults to True, which requires the explicit NFR-9 ack
    # (R14); probe-off tests pass their own ack=False. Corrected during T005:
    # the original bare helper contradicted T004's own ack-refusal rule.
    base = dict(project="demo", repo_dir="/srv/repos/demo", ack_unattended_build_probe=True)
    base.update(kw)
    return MaintenanceConfig(**base)


def test_minimal_config_is_valid_and_takes_every_default():
    cfg = _cfg()
    assert cfg.project == "demo"
    assert cfg.repo_dir == "/srv/repos/demo"
    assert cfg.default_branch == "main"
    assert cfg.build_probe is True
    assert cfg.advisory_source == "none"
    assert cfg.threshold == 0.8
    assert cfg.gate_timeout_hours == 48
    assert cfg.max_plan_attempts == 2
    assert cfg.max_new_incidents_per_cycle == 10
    assert cfg.max_cycles_per_history == 50


@pytest.mark.parametrize("project", ["demo", "a1-b", "0x", "a" * 63])
def test_project_regex_accepts_valid_slugs(project):
    assert _cfg(project=project).project == project


def test_build_probe_true_with_ack_validates():
    cfg = _cfg(build_probe=True, ack_unattended_build_probe=True)
    assert cfg.build_probe is True
    assert cfg.ack_unattended_build_probe is True


def test_build_probe_false_without_ack_validates():
    cfg = _cfg(build_probe=False, ack_unattended_build_probe=False)
    assert cfg.build_probe is False
    assert cfg.ack_unattended_build_probe is False


@pytest.mark.parametrize("threshold", [0.5, 0.8, 1.0])
def test_threshold_accepts_bounds_inclusive(threshold):
    assert _cfg(threshold=threshold).threshold == threshold


@pytest.mark.parametrize("hours", [1, 48, 168])
def test_gate_timeout_hours_accepts_bounds_inclusive(hours):
    assert _cfg(gate_timeout_hours=hours).gate_timeout_hours == hours


@pytest.mark.parametrize("source", ["none", "osv"])
def test_advisory_source_accepts_both_literals(source):
    assert _cfg(advisory_source=source).advisory_source == source


def test_config_accepts_every_tunable_at_once():
    cfg = _cfg(
        default_branch="trunk",
        build_probe=True,
        ack_unattended_build_probe=True,
        advisory_source="osv",
        threshold=0.65,
        gate_timeout_hours=12,
        max_plan_attempts=3,
        max_new_incidents_per_cycle=50,
        max_cycles_per_history=7,
    )
    assert cfg.default_branch == "trunk"
    assert cfg.advisory_source == "osv"
    assert cfg.max_plan_attempts == 3
    assert cfg.max_new_incidents_per_cycle == 50
    assert cfg.max_cycles_per_history == 7


# --------------------------------------------------------------------------- #
# MaintenanceKickInput
# --------------------------------------------------------------------------- #


def test_kick_input_carries_a_project_slug():
    assert MaintenanceKickInput(project="demo").project == "demo"


# --------------------------------------------------------------------------- #
# IncidentState
# --------------------------------------------------------------------------- #


def test_incident_state_has_exactly_the_nine_documented_members():
    # 023a pinned exactly these nine members; 023b (R7) adds the six
    # execute-side live states plus `closed`, and their values are pinned in
    # test_models_023b.py. The 023a nine keep their values verbatim.
    nine_023a = {
        "open",
        "awaiting_decision",
        "approved_not_executed",
        "rejected",
        "timed_out",
        "resolved_externally",
        "escalated",
        "withdrawn",
        "deferred",
    }
    assert nine_023a <= {member.value for member in IncidentState}
    assert len(list(IncidentState)) == 16


# --------------------------------------------------------------------------- #
# Baseline / Incident / MaintenanceState
# --------------------------------------------------------------------------- #


def test_baseline_holds_identities_versions_and_pin():
    baseline = Baseline(
        identities=frozenset({"secrets:env-file:.env"}),
        signal_versions={"secrets": 1, "build_probe": 1, "dependencies": 1},
        recorded_cycle=1,
        commit_sha="a" * 40,
    )
    assert "secrets:env-file:.env" in baseline.identities
    assert baseline.signal_versions["dependencies"] == 1
    assert baseline.recorded_cycle == 1


def test_incident_opened_from_a_finding_starts_open_with_no_plan():
    finding = env_file_findings()[0]
    incident = Incident(
        no=1,
        key="secrets:env-file:.env",
        kind="finding",
        finding=finding,
        commit_sha="b" * 40,
        first_seen_cycle=2,
        last_seen_cycle=2,
        seen_count=1,
        state=IncidentState.OPEN,
        plan=None,
        plan_attempts=0,
        decision=None,
        note="",
    )
    assert incident.state is IncidentState.OPEN
    assert incident.finding == finding
    assert incident.plan is None


def test_maintenance_state_round_trips_through_dict():
    state = MaintenanceState(
        config=_cfg(),
        cycle=3,
        baseline=Baseline(
            identities=frozenset(),
            signal_versions={"secrets": 1, "build_probe": 1, "dependencies": 1},
            recorded_cycle=1,
            commit_sha="c" * 40,
        ),
        prev=make_triage({"secrets": env_file_findings()}),
        incidents=[],
        not_collected_streak={"dependencies": 1},
        next_incident_no=4,
        nudged=False,
    )
    restored = MaintenanceState.model_validate(state.model_dump())
    assert restored == state
    assert restored.not_collected_streak == {"dependencies": 1}
    assert restored.next_incident_no == 4


def test_maintenance_state_accepts_first_cycle_with_no_baseline_or_prev():
    state = MaintenanceState(
        config=_cfg(),
        cycle=1,
        baseline=None,
        prev=None,
        incidents=[],
        not_collected_streak={},
        next_incident_no=1,
        nudged=False,
    )
    assert state.baseline is None
    assert state.prev is None
    assert state.cycle == 1


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


def test_detect_signals_are_the_three_detect_signals():
    assert DETECT_SIGNALS == {"secrets", "build_probe", "dependencies"}


def test_max_prev_findings_is_2000():
    assert MAX_PREV_FINDINGS == 2000


# --------------------------------------------------------------------------- #
# Repair proposal / plan
# --------------------------------------------------------------------------- #


def test_repair_proposal_field_order_is_evidence_first():
    assert list(RepairProposal.model_fields) == ["analysis", "actions", "self_confidence"]


def test_repair_action_code_fix_carries_target_paths():
    action = RepairAction(
        kind="code_fix",
        summary="remove the committed .env and rotate the key",
        target_paths=[".env"],
        ops_action=None,
    )
    assert action.kind == "code_fix"
    assert action.target_paths == [".env"]
    assert action.ops_action is None


def test_repair_action_ops_carries_an_ops_action():
    action = RepairAction(
        kind="ops",
        summary="roll back the last deploy",
        target_paths=[],
        ops_action="rollback",
    )
    assert action.kind == "ops"
    assert action.ops_action == "rollback"


def test_repair_proposal_builds_from_its_three_fields():
    proposal = RepairProposal(
        analysis="The .env file is tracked and holds a live token.",
        actions=[
            RepairAction(
                kind="code_fix",
                summary="untrack .env",
                target_paths=[".env"],
                ops_action=None,
            )
        ],
        self_confidence=0.9,
    )
    assert proposal.self_confidence == 0.9
    assert len(proposal.actions) == 1


def test_repair_plan_carries_floor_and_effective_alongside_the_proposal():
    plan = RepairPlan(
        analysis="The .env file is tracked and holds a live token.",
        actions=[],
        self_confidence=0.9,
        floor=0.6,
        effective=0.6,
        author_model="claude-sonnet-5-5",
    )
    assert plan.floor == 0.6
    assert plan.effective == 0.6
    assert plan.effective == min(plan.self_confidence, plan.floor)
    assert plan.author_model == "claude-sonnet-5-5"


# =========================================================================== #
# CHAOS / EDGE HALF (023a T004, RED) -- qa-chaos
#
# Every test below must FAIL until T005 lands sdlc.maintenance.models.
# Refusals assert pydantic ValidationError and that the offending field NAME
# appears in the error text.
# =========================================================================== #


def _err_text(exc_info) -> str:
    return str(exc_info.value)


def _st(value: str) -> IncidentState:
    # Lookup by spec value (data-model.md §IncidentState) to avoid guessing member names.
    return IncidentState(value)


def _incident(
    *,
    no: int,
    key: str,
    state: IncidentState = IncidentState.OPEN,
    kind: str = "finding",
    finding=None,
    **extra,
) -> Incident:
    values = dict(
        no=no,
        key=key,
        kind=kind,
        finding=finding,
        commit_sha="d" * 40,
        first_seen_cycle=1,
        last_seen_cycle=1,
        seen_count=1,
        state=state,
        plan=None,
        plan_attempts=0,
        decision=None,
        note="",
    )
    values.update(extra)
    return Incident(**values)


def _state(incidents: list[Incident]) -> MaintenanceState:
    return MaintenanceState(
        config=_cfg(),
        cycle=2,
        baseline=None,
        prev=None,
        incidents=incidents,
        not_collected_streak={},
        next_incident_no=max((i.no for i in incidents), default=0) + 1,
        nudged=False,
    )


def _plan_kwargs(**overrides) -> dict:
    values = dict(
        analysis="The .env file is tracked and holds a live token.",
        actions=[],
        self_confidence=0.9,
        floor=0.6,
        effective=0.6,
        author_model="claude-sonnet-5-5",
    )
    values.update(overrides)
    return values


# --------------------------------------------------------------------------- #
# MaintenanceConfig: project slug refusals
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "project",
    [
        "Demo",  # uppercase
        "-demo",  # leading dash
        "demo_",  # underscore
        "a" * 64,  # one over the 63-char ceiling
        "",  # empty
        "demo/x",  # slash
    ],
)
def test_project_regex_refuses_invalid_slugs_and_names_the_field(project):
    with pytest.raises(ValidationError) as exc_info:
        _cfg(project=project)
    assert "project" in _err_text(exc_info)


# --------------------------------------------------------------------------- #
# MaintenanceConfig: bounds refusals
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("threshold", [0.49, 1.01, -1.0, float("nan")])
def test_threshold_refuses_values_outside_half_to_one(threshold):
    with pytest.raises(ValidationError) as exc_info:
        _cfg(threshold=threshold)
    assert "threshold" in _err_text(exc_info)


@pytest.mark.parametrize("hours", [0, 169, -1])
def test_gate_timeout_hours_refuses_values_outside_one_to_168(hours):
    with pytest.raises(ValidationError) as exc_info:
        _cfg(gate_timeout_hours=hours)
    assert "gate_timeout_hours" in _err_text(exc_info)


def test_build_probe_true_without_ack_is_refused_and_names_the_ack_field():
    with pytest.raises(ValidationError) as exc_info:
        _cfg(build_probe=True, ack_unattended_build_probe=False)  # ack absent is the default
    assert "ack_unattended_build_probe" in _err_text(exc_info)


@pytest.mark.parametrize("source", ["github", "OSV", None])
def test_advisory_source_refuses_unknown_and_miscased_values(source):
    with pytest.raises(ValidationError) as exc_info:
        _cfg(advisory_source=source)
    assert "advisory_source" in _err_text(exc_info)


# --------------------------------------------------------------------------- #
# MaintenanceConfig: no gate surface (R9 / SC-003), extra fields named
# --------------------------------------------------------------------------- #


def test_config_refuses_a_gates_field_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        _cfg(gates={"repair:1": {"policy": "off"}})
    assert "gates" in _err_text(exc_info)


def test_config_refuses_a_policy_field_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        _cfg(policy="off")
    assert "policy" in _err_text(exc_info)


def test_config_refuses_an_on_timeout_field_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        _cfg(on_timeout="approve")
    assert "on_timeout" in _err_text(exc_info)


# --------------------------------------------------------------------------- #
# MaintenanceState: duplicate keys among non-terminal incidents
# --------------------------------------------------------------------------- #


def test_state_refuses_two_open_incidents_with_the_same_key():
    key = "build_probe:build_failed::"
    with pytest.raises(ValidationError) as exc_info:
        _state(
            [
                _incident(no=1, key=key, state=IncidentState.OPEN),
                _incident(no=2, key=key, state=IncidentState.OPEN),
            ]
        )
    assert key in _err_text(exc_info)


def test_state_refuses_an_awaiting_decision_and_an_open_with_the_same_key():
    key = "build_probe:build_failed::"
    with pytest.raises(ValidationError):
        _state(
            [
                _incident(no=1, key=key, state=_st("awaiting_decision")),
                _incident(no=2, key=key, state=IncidentState.OPEN),
            ]
        )


def test_state_accepts_a_terminal_incident_and_an_open_one_with_the_same_key():
    key = "build_probe:build_failed::"
    state = _state(
        [
            _incident(no=1, key=key, state=_st("rejected")),
            _incident(no=2, key=key, state=IncidentState.OPEN),
        ]
    )
    assert [i.no for i in state.incidents] == [1, 2]


def test_state_accepts_two_terminal_incidents_with_the_same_key():
    key = "secrets:env-file:.env"
    state = _state(
        [
            _incident(no=1, key=key, state=_st("timed_out")),
            _incident(no=2, key=key, state=_st("resolved_externally")),
        ]
    )
    assert len(state.incidents) == 2


def test_detect_escalation_key_coexists_with_a_finding_key_for_the_same_signal():
    # `<signal>:not_collected::` is unique among non-terminal incidents
    # alongside a finding incident for the same signal.
    state = _state(
        [
            _incident(
                no=1,
                key="build_probe:build_failed::",
                state=IncidentState.OPEN,
                kind="finding",
            ),
            _incident(
                no=2,
                key="build_probe:not_collected::",
                state=_st("awaiting_decision"),
                kind="detect_escalation",
                finding=None,
            ),
        ]
    )
    assert {i.key for i in state.incidents} == {
        "build_probe:build_failed::",
        "build_probe:not_collected::",
    }


# --------------------------------------------------------------------------- #
# Incident / extra='forbid' on every model
# --------------------------------------------------------------------------- #


def test_incident_refuses_an_unknown_field_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        _incident(no=1, key="secrets:env-file:.env", surprise="x")
    assert "surprise" in _err_text(exc_info)


def test_maintenance_state_refuses_an_unknown_field_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        MaintenanceState(
            config=_cfg(),
            cycle=1,
            baseline=None,
            prev=None,
            incidents=[],
            not_collected_streak={},
            next_incident_no=1,
            nudged=False,
            rogue_field=True,
        )
    assert "rogue_field" in _err_text(exc_info)


# --------------------------------------------------------------------------- #
# RepairProposal: confidence and action-count bounds
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("confidence", [1.5, -0.1])
def test_repair_proposal_refuses_self_confidence_outside_zero_to_one(confidence):
    with pytest.raises(ValidationError) as exc_info:
        RepairProposal(
            analysis="x",
            actions=[],
            self_confidence=confidence,
        )
    assert "self_confidence" in _err_text(exc_info)


def test_repair_proposal_refuses_more_than_five_actions():
    action = RepairAction(
        kind="code_fix",
        summary="s",
        target_paths=[".env"],
        ops_action=None,
    )
    with pytest.raises(ValidationError) as exc_info:
        RepairProposal(analysis="x", actions=[action] * 6, self_confidence=0.5)
    assert "actions" in _err_text(exc_info)


def test_repair_proposal_refuses_a_missing_actions_field():
    with pytest.raises(ValidationError) as exc_info:
        RepairProposal(analysis="x", self_confidence=0.5)
    assert "actions" in _err_text(exc_info)


# --------------------------------------------------------------------------- #
# RepairAction: closed enums
# --------------------------------------------------------------------------- #


def test_repair_action_refuses_an_unknown_kind_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        RepairAction(kind="magic", summary="s", target_paths=[], ops_action=None)
    assert "kind" in _err_text(exc_info)


def test_repair_action_refuses_an_unknown_ops_action_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        RepairAction(kind="ops", summary="s", target_paths=[], ops_action="nuke")
    assert "ops_action" in _err_text(exc_info)


# --------------------------------------------------------------------------- #
# RepairPlan: analysis length cap
# --------------------------------------------------------------------------- #


def test_repair_plan_refuses_analysis_over_4000_chars_and_names_it():
    with pytest.raises(ValidationError) as exc_info:
        RepairPlan(**_plan_kwargs(analysis="a" * 4001))
    assert "analysis" in _err_text(exc_info)


def test_repair_plan_accepts_analysis_at_exactly_4000_chars():
    plan = RepairPlan(**_plan_kwargs(analysis="a" * 4000))
    assert len(plan.analysis) == 4000
