"""E-45: the assessment artifact and its derived status."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.models import (
    ASSESSED, BLOCKED, NO_PHASES, PARTIAL, PHASE_ORDER, Assessment,
    InitOutcome, PhaseId, PhaseResult, terminal_status,
)
from sdlc.measurement import Measurement
from sdlc.triage.models import Readiness, RepoTriage, Verdict


def _triage() -> RepoTriage:
    ok = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r", commit_sha="a" * 40, toolchain="python",
        readiness=Readiness(buildable=ok, runnable=ok, tests_present=ok,
                            structure_discernible=ok,
                            verdict=Verdict.READY))


def _phases(collected: set[PhaseId]) -> list[PhaseResult]:
    return [PhaseResult(
        phase=p,
        collected=(Measurement.measured(1.0) if p in collected
                   else Measurement.not_collected("stub")))
        for p in PHASE_ORDER]


def test_report_runs_after_assess_and_before_generate():
    """FR-911 deviation (a): the methodology numbers report 4th and assess
    5th, but reports render risk scores only assess produces."""
    order = list(PHASE_ORDER)
    assert order.index(PhaseId.ASSESS) < order.index(PhaseId.REPORT)
    assert order.index(PhaseId.REPORT) < order.index(PhaseId.GENERATE)


def test_phase_order_is_the_whole_dag_once():
    """Spelled out rather than compared against tuple(PhaseId), which would
    be tautological: this is the assertion that catches a reordering."""
    assert [p.value for p in PHASE_ORDER] == [
        "init", "scan", "discover", "assess", "report", "generate", "finish"]
    assert len(set(PHASE_ORDER)) == len(PhaseId) == 7


def test_a_phase_that_did_not_run_carries_no_value():
    """FR-915: never Measurement.measured(0.0)."""
    with pytest.raises(ValidationError):
        PhaseResult(phase=PhaseId.SCAN,
                    collected=Measurement(state="not_collected", value=0.0))


@pytest.mark.parametrize("admitted,collected,expected", [
    (False, set(), BLOCKED),
    (False, set(PHASE_ORDER), BLOCKED),
    (True, {PhaseId.INIT}, NO_PHASES),
    (True, {PhaseId.INIT, PhaseId.SCAN}, PARTIAL),
    (True, set(PHASE_ORDER), ASSESSED),
])
def test_terminal_status_is_derived(admitted, collected, expected):
    """D6: E-46 landing flips the status with no workflow edit."""
    assert terminal_status(admitted, _phases(collected)) == expected


def test_admitted_without_a_triage_is_unrepresentable():
    """Admission is a function of a RepoTriage (FR-903), so this state is a
    contradiction rather than an edge case."""
    with pytest.raises(ValidationError):
        Assessment(repo_dir="/r", triage=None, admitted=True,
                   admission_reason="", phases=_phases(set()),
                   terminal_status=BLOCKED)


def test_phases_must_be_the_whole_dag_in_order():
    """Anything rendering the DAG relies on this, so the type enforces it."""
    with pytest.raises(ValidationError):
        Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="ok",
                   phases=_phases(set())[:3], terminal_status=NO_PHASES)
    with pytest.raises(ValidationError):
        Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="ok",
                   phases=list(reversed(_phases(set()))),
                   terminal_status=NO_PHASES)


def test_a_refused_assessment_still_carries_the_triage():
    """E-44 D7's shape: not admitted is not empty-handed."""
    a = Assessment(repo_dir="/r", commit_sha="a" * 40, triage=_triage(),
                   admitted=False, admission_reason="verdict not_ready",
                   phases=_phases(set()), terminal_status=BLOCKED)
    assert a.triage is not None
    assert a.triage.commit_sha == "a" * 40


def test_init_outcome_defaults_to_no_triage():
    out = InitOutcome(result=PhaseResult(
        phase=PhaseId.INIT,
        collected=Measurement.not_collected("child failed")))
    assert out.triage is None
