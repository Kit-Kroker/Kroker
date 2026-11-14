"""The bounded prompt, the gate context and the CLI table (023a T015, RED).

Authorship note: both QA seats are quota-blocked until 23:50; this file is
executor-written under the degradation ruling — every assertion transcribes
T015's task text, contracts/cli.md and data-model.md §pure functions.

Subject: ``sdlc.maintenance.prompt.render_repair_prompt`` and
``sdlc.maintenance.render`` (T016 implements; neither exists yet).
"""

from __future__ import annotations

from sdlc.maintenance.models import Incident, IncidentState, RepairAction, RepairPlan
from sdlc.maintenance.prompt import render_repair_prompt
from sdlc.maintenance.render import gate_context_text, incidents_table
from tests.maintenance.conftest import build_break_finding, env_file_findings

LIMIT = 16 * 1024  # the 16 KiB prompt bound


def _incident(**kw) -> Incident:
    base = dict(
        no=3,
        key="build_probe:build_failed::",
        kind="finding",
        finding=build_break_finding(),
        commit_sha="a" * 40,
        first_seen_cycle=2,
        last_seen_cycle=2,
        seen_count=1,
        state=IncidentState.AWAITING_DECISION,
        plan=None,
        plan_attempts=1,
        decision=None,
        note="",
    )
    base.update(kw)
    return Incident(**base)


def _plan(**kw) -> RepairPlan:
    base = dict(
        analysis="The build breaks because the pinned dependency resolves to a yanked wheel.",
        actions=[
            RepairAction(kind="code_fix", summary="pin the wheel", target_paths=["pyproject.toml"]),
            RepairAction(kind="ops", summary="restart the worker", ops_action="restart"),
        ],
        self_confidence=0.9,
        floor=0.6,
        effective=0.6,
        author_model="zai:glm-5.3",
    )
    base.update(kw)
    return RepairPlan(**base)


# --- the repair prompt ------------------------------------------------------ #


def test_prompt_is_within_16_kib():
    p = render_repair_prompt(_incident(plan=_plan()), triage_context="ctx")
    assert len(p.encode()) <= LIMIT


def test_prompt_stays_bounded_when_evidence_is_huge():
    from sdlc.triage.models import FixClass, TriageFinding

    loud = TriageFinding(
        signal="build_probe",
        rule="build_failed",
        severity="critical",
        detail="x" * 50_000,
        evidence="y" * 50_000,
        fix_class=FixClass.JUDGEMENT,
    )
    p = render_repair_prompt(_incident(finding=loud, plan=_plan()), triage_context="z" * 50_000)
    assert len(p.encode()) <= LIMIT


def test_prompt_carries_the_deterministic_facts():
    p = render_repair_prompt(_incident(plan=_plan()), triage_context="repo: fixture")
    assert "build_probe:build_failed::" in p  # the identity
    assert "a" * 40 in p  # the pinned commit
    assert "INC-3" in p
    assert "critical" in p  # severity
    assert "judgement" in p.lower()  # fix class


# --- the gate context text ---------------------------------------------------- #


def test_gate_context_names_incident_plan_and_the_three_confidences():
    inc = _incident(plan=_plan())
    text = gate_context_text(inc)
    assert "INC-3" in text
    assert "build_probe:build_failed::" in text
    assert "0.6" in text  # floor and effective
    assert "0.9" in text  # self


def test_gate_context_carries_the_no_execution_line():
    text = gate_context_text(_incident(plan=_plan()))
    assert "approval does NOT execute in 023a" in text


# --- the CLI incidents table (contracts/cli.md) --------------------------------- #


def test_table_header_has_the_six_contract_columns():
    out = incidents_table([])
    assert "INC-n" in out
    for col in ("state", "key", "seen", "eff.conf", "gate"):
        assert col in out


def test_table_rows_render_one_line_per_incident():
    incs = [
        _incident(no=1, state=IncidentState.AWAITING_DECISION, plan=_plan()),
        _incident(
            no=2,
            key="secrets:env_file_tracked:.gitignore:",
            finding=env_file_findings()[1],
            state=IncidentState.REJECTED,
            plan=_plan(floor=0.95, effective=0.9),
        ),
    ]
    out = incidents_table(incs)
    lines = [ln for ln in out.splitlines() if ln.startswith("INC-1")]
    assert len(lines) == 1
    row1 = lines[0]
    assert "awaiting_decision" in row1
    assert "build_probe:build_failed::" in row1
    assert "0.60" in row1 or "0.6" in row1
    assert "repair:1" in row1  # the gate column names the pending gate


def test_table_without_all_hides_terminal_incidents():
    open_inc = _incident(no=1, state=IncidentState.AWAITING_DECISION, plan=_plan())
    terminal = _incident(
        no=2,
        key="secrets:env_file_tracked:.gitignore:",
        finding=env_file_findings()[1],
        state=IncidentState.REJECTED,
    )
    default_view = incidents_table([open_inc, terminal])
    assert "INC-1" in default_view
    assert "INC-2" not in default_view
    all_view = incidents_table([open_inc, terminal], include_terminal=True)
    assert "INC-1" in all_view
    assert "INC-2" in all_view
