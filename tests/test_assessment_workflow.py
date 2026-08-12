"""E-45. Pure helpers directly; sequencing through the workflow environment
lives in tests/test_assessment_workflow_e2e.py, following
tests/test_tidyup_workflow.py."""
from __future__ import annotations

import inspect

import pytest

from sdlc.assessment.models import (
    ASSESSED, BLOCKED, PARTIAL, PHASE_ORDER, PhaseId, PhaseResult,
    InitOutcome,
)
from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, ScanResult, ScanSignalResult, SignalSource,
    family_of,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.models import GatePolicy
from sdlc.triage.models import Readiness, RepoTriage, Verdict
from sdlc.workflows.assessment import (
    PHASE_OWNER, AssessmentInput, AssessmentWorkflow, assemble, skipped,
    unbuilt,
)


def _triage() -> RepoTriage:
    ok = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r", commit_sha="a" * 40, toolchain="python",
        readiness=Readiness(buildable=ok, runnable=ok, tests_present=ok,
                            structure_discernible=ok,
                            verdict=Verdict.READY))


def _scan_result() -> ScanResult:
    """A minimal measured ScanResult, so a measured SCAN phase satisfies the
    E-46 phase-agreement validator."""
    val = Measurement.measured(0.0)
    return ScanResult(signals=[
        ScanSignalResult(signal=s, family=family_of(s), version=1,
                         source=SignalSource.COMPUTED, collected=val,
                         categories={k: val for k in CATEGORIES[s]})
        for s in SCAN_ORDER])


def _init(ok: bool = True) -> InitOutcome:
    if not ok:
        return InitOutcome(result=PhaseResult(
            phase=PhaseId.INIT,
            collected=Measurement.not_collected("triage child failed: boom")))
    return InitOutcome(
        result=PhaseResult(phase=PhaseId.INIT,
                           collected=Measurement.measured(1.0)),
        triage=_triage())


def test_input_defaults():
    inp = AssessmentInput(repo_dir="/r")
    assert inp.commit == "HEAD"
    assert inp.build_probe is True
    assert inp.advisory_source == "none"
    assert inp.gates.default_gate_policy is GatePolicy.HARD


def test_every_unbuilt_phase_names_the_item_that_owes_it():
    """An empty assessment says WHY it is empty on the face of the
    artifact."""
    for phase, owner in PHASE_OWNER.items():
        r = unbuilt(phase)
        assert r.collected.state is CollectionState.NOT_COLLECTED
        assert owner in r.collected.reason
        assert phase.value in r.collected.reason


def test_every_post_init_phase_has_an_owner():
    # SCAN is built in E-46, so it is not in PHASE_OWNER; every other
    # post-init phase still names the item that owes its body.
    assert set(PHASE_OWNER) == set(PHASE_ORDER) - {PhaseId.INIT, PhaseId.SCAN}


def test_assemble_fills_the_whole_dag_on_a_refusal():
    a = assemble("/r", _init(), False, "verdict not_ready")
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)
    assert a.terminal_status == BLOCKED
    assert a.admission_reason == "verdict not_ready"
    for p in a.phases:
        if p.phase is PhaseId.INIT:
            continue
        assert "not admitted" in p.collected.reason


def test_assemble_keeps_the_triage_on_a_refusal():
    """E-44 D7's shape: not admitted is not empty-handed -- the caller still
    gets the readiness verdict and every hygiene finding."""
    a = assemble("/r", _init(), False, "verdict not_ready")
    assert a.triage is not None
    assert a.commit_sha == "a" * 40
    assert a.toolchain == "python"


def test_assemble_on_a_failed_child_has_no_commit_and_is_not_admitted():
    a = assemble("/r", _init(ok=False), False, "triage child failed: boom")
    assert a.triage is None
    assert a.commit_sha == ""
    assert a.admitted is False
    assert a.terminal_status == BLOCKED


def test_assemble_on_an_admitted_run_reports_partial_once_scan_lands():
    # SCAN is built in E-46 (always measured when admitted); the other five
    # phases are still stubs. terminal_status derives PARTIAL with no workflow
    # edit (D6), and the canonical phase order is preserved.
    rest = [PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(0.0))]
    rest += [unbuilt(p) for p in PHASE_ORDER
             if p not in (PhaseId.INIT, PhaseId.SCAN)]
    a = assemble("/r", _init(), True, "verdict ready", rest,
                 scan=_scan_result())
    assert a.admitted is True
    assert a.terminal_status == PARTIAL
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_assemble_reports_assessed_once_every_phase_collects():
    """The status flips by itself when E-46..E-52 land -- no workflow edit."""
    rest = [PhaseResult(phase=p, collected=Measurement.measured(1.0))
            for p in PHASE_ORDER if p is not PhaseId.INIT]
    assert assemble("/r", _init(), True, "verdict ready", rest,
                    scan=_scan_result()).terminal_status == ASSESSED


def test_assemble_orders_phases_canonically_regardless_of_arrival():
    rest = [PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(0.0))]
    rest += [unbuilt(p) for p in PHASE_ORDER
             if p not in (PhaseId.INIT, PhaseId.SCAN)]
    a = assemble("/r", _init(), True, "verdict ready",
                 list(reversed(rest)), scan=_scan_result())
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_assemble_rejects_a_partial_rest_on_an_admitted_run():
    """An admitted run has no 'unreached' phases -- run() always supplies all
    six. A missing one is a caller bug, and filling it with skipped() would
    stamp 'not admitted' onto an artifact whose admitted field is True -- a
    contradiction on the face of an FR-921 bundle (review finding 1). The
    not-admitted path still fills with skipped(), whose message is then
    truthful."""
    partial = [unbuilt(PhaseId.DISCOVER)]         # one of the unbuilt phases
    with pytest.raises(ValueError, match="admitted"):
        assemble("/r", _init(), True, "verdict ready", partial)


def test_skipped_names_the_reason_it_did_not_run():
    r = skipped(PhaseId.SCAN)
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "not admitted" in r.collected.reason


def test_the_run_body_calls_the_phases_in_dag_order():
    """FR-911 deviation (a) is the thing most likely to be 'fixed' by someone
    reordering to match the source methodology's numbering. This guards the
    run body against that, since PHASE_ORDER alone would not catch it."""
    src = inspect.getsource(AssessmentWorkflow.run)
    calls = ["self._init(", "self._scan(", "self._discover(",
             "self._assess(", "self._report(", "self._generate(",
             "self._finish("]
    positions = [src.index(c) for c in calls]
    assert positions == sorted(positions)


def test_admission_is_checked_at_tier_two_strictness():
    src = inspect.getsource(AssessmentWorkflow.run)
    assert "require_human=True" in src
