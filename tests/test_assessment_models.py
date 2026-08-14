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


def test_terminal_status_is_enforced_on_the_artifact():
    """D6: 'derived, never assigned' is a TYPE invariant, like the other two
    -- so a second construction path or a deserialized payload cannot silently
    set terminal_status='assessed' over six not_collected phases (review
    finding 2)."""
    from sdlc.assessment.models import terminal_status as derive

    # A status that matches the derivation is accepted:
    phases = _phases(set())
    a = Assessment(repo_dir="/r", triage=_triage(), admitted=False,
                   admission_reason="verdict not_ready", phases=phases,
                   terminal_status=derive(False, phases))
    assert a.terminal_status == BLOCKED
    # A status that disagrees with admitted+phases is rejected:
    with pytest.raises(ValidationError):
        Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="ok", phases=phases,
                   terminal_status=ASSESSED)


def test_init_outcome_defaults_to_no_triage():
    out = InitOutcome(result=PhaseResult(
        phase=PhaseId.INIT,
        collected=Measurement.not_collected("child failed")))
    assert out.triage is None


# --- E-46: the scan payload and its phase-agreement validator -------------
from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, ScanResult, ScanSignalResult, SignalSource,
    family_of,
)
from sdlc.workflows.assessment import assemble


def _scan_result() -> ScanResult:
    val = Measurement.measured(0.0)
    return ScanResult(signals=[
        ScanSignalResult(signal=s, family=family_of(s), version=1,
                         source=SignalSource.COMPUTED, collected=val,
                         categories={k: val for k in CATEGORIES[s]})
        for s in SCAN_ORDER])


def _scan_dag(scan_measured: bool) -> list[PhaseResult]:
    """The whole DAG with SCAN either measured or not (every other phase
    measured). Kept distinct from the file's existing _phases(set) helper."""
    out = []
    for phase in PHASE_ORDER:
        if phase is PhaseId.SCAN and not scan_measured:
            out.append(PhaseResult(
                phase=phase,
                collected=Measurement.not_collected("scan not run")))
        else:
            out.append(PhaseResult(phase=phase,
                                   collected=Measurement.measured(1.0)))
    return out


def _init_out() -> InitOutcome:
    return InitOutcome(
        result=PhaseResult(phase=PhaseId.INIT,
                           collected=Measurement.measured(1.0)),
        triage=_triage())


def test_a_scan_payload_requires_a_measured_scan_phase():
    """Mirrors _terminal_status_matches_derivation: the artifact cannot
    contradict its own phase row."""
    phases = _scan_dag(scan_measured=False)
    with pytest.raises(ValidationError, match="scan"):
        Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="verdict ready", phases=phases,
                   terminal_status=terminal_status(True, phases),
                   scan=_scan_result())


def test_a_measured_scan_phase_requires_a_payload():
    phases = _scan_dag(scan_measured=True)
    with pytest.raises(ValidationError, match="scan"):
        Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="verdict ready", phases=phases,
                   terminal_status=terminal_status(True, phases), scan=None)


def test_a_measured_scan_phase_with_a_payload_constructs():
    # DISCOVER is held not-measured: this test is about the SCAN pairing, and
    # a measured DISCOVER would now also require a CapabilityMap (E-48).
    phases = [
        p if p.phase is not PhaseId.DISCOVER else PhaseResult(
            phase=PhaseId.DISCOVER,
            collected=Measurement.not_collected("discover not run"))
        for p in _scan_dag(scan_measured=True)]
    a = Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="verdict ready", phases=phases,
                   terminal_status=terminal_status(True, phases),
                   scan=_scan_result())
    assert a.scan is not None
    assert len(a.scan.signals) == 13


def test_assemble_threads_the_scan_payload_through():
    from sdlc.workflows.assessment import unbuilt
    rest = [PhaseResult(phase=PhaseId.SCAN,
                        collected=Measurement.measured(0.0))]
    rest += [unbuilt(p) for p in PHASE_ORDER
             if p not in (PhaseId.INIT, PhaseId.SCAN)]
    a = assemble("/r", _init_out(), True, "verdict ready", rest,
                  scan=_scan_result())
    assert a.scan is not None
    assert a.terminal_status == PARTIAL


# --- E-48: the discover payload and its phase-agreement validator ---------
from sdlc.assessment.discover.map import CapabilityMap


def _discover_dag(discover_measured: bool) -> list[PhaseResult]:
    """The whole DAG with DISCOVER either measured or not, every other phase
    measured. _scan_dag's shape, for the other pairing."""
    out = []
    for phase in PHASE_ORDER:
        if phase is PhaseId.DISCOVER and not discover_measured:
            out.append(PhaseResult(
                phase=phase,
                collected=Measurement.not_collected("discover not run")))
        else:
            out.append(PhaseResult(phase=phase,
                                   collected=Measurement.measured(1.0)))
    return out


def test_a_measured_discover_phase_requires_a_capability_map():
    """_scan_agrees_with_its_phase, applied to DISCOVER: a measured phase
    produced an artifact by definition."""
    phases = _discover_dag(discover_measured=True)
    with pytest.raises(ValidationError, match="no CapabilityMap"):
        Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="verdict ready", phases=phases,
                   terminal_status=terminal_status(True, phases),
                   scan=_scan_result(), discover=None)


def test_a_discover_payload_requires_a_measured_discover_phase():
    """An assessment cannot claim it did not discover while shipping a map."""
    phases = _discover_dag(discover_measured=False)
    with pytest.raises(ValidationError, match="did not discover"):
        Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="verdict ready", phases=phases,
                   terminal_status=terminal_status(True, phases),
                   scan=_scan_result(),
                   discover=CapabilityMap(
                       collected=Measurement.measured(0.0)))


def test_a_measured_discover_phase_with_a_payload_constructs():
    phases = _discover_dag(discover_measured=True)
    a = Assessment(repo_dir="/r", triage=_triage(), admitted=True,
                   admission_reason="verdict ready", phases=phases,
                   terminal_status=terminal_status(True, phases),
                   scan=_scan_result(),
                   discover=CapabilityMap(
                       collected=Measurement.measured(0.0)))
    assert a.discover is not None
