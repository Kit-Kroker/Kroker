# tests/test_assessment_workflow.py
"""E-45. Pure helpers directly; sequencing through the workflow environment
lives in tests/test_assessment_workflow_e2e.py, following
tests/test_tidyup_workflow.py."""

from __future__ import annotations

import inspect

import pytest

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.models import (
    ASSESSED,
    BLOCKED,
    PARTIAL,
    PHASE_ORDER,
    InitOutcome,
    PhaseId,
    PhaseResult,
)
from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    ScanResult,
    ScanSignalResult,
    SignalSource,
    family_of,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.models import GatePolicy
from sdlc.triage.models import Readiness, RepoTriage, Verdict
from sdlc.workflows.assessment import (
    PHASE_OWNER,
    AssessmentInput,
    AssessmentWorkflow,
    assemble,
    no_discover,
    skipped,
    unbuilt,
)


def _triage() -> RepoTriage:
    ok = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        toolchain="python",
        readiness=Readiness(
            buildable=ok,
            runnable=ok,
            tests_present=ok,
            structure_discernible=ok,
            verdict=Verdict.READY,
        ),
    )


def _scan_result() -> ScanResult:
    """A minimal measured ScanResult, so a measured SCAN phase satisfies the
    E-46 phase-agreement validator."""
    val = Measurement.measured(0.0)
    return ScanResult(
        signals=[
            ScanSignalResult(
                signal=s,
                family=family_of(s),
                version=1,
                source=SignalSource.COMPUTED,
                collected=val,
                categories={k: val for k in CATEGORIES[s]},
            )
            for s in SCAN_ORDER
        ]
    )


from sdlc.assessment.risk.models import UnifiedRiskMap


def _rest_after_discover(discover: PhaseResult | None = None) -> list[PhaseResult]:
    """SCAN (E-46), DISCOVER (E-48), and ASSESS (E-49) are built; the other three are stubs.

    DISCOVER and ASSESS default to not_collected so a caller that does not care about
    their pairing need not supply their maps.
    """
    out = [
        PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(0.0)),
        discover
        or PhaseResult(
            phase=PhaseId.DISCOVER, collected=Measurement.not_collected("discover not run")
        ),
        PhaseResult(phase=PhaseId.ASSESS, collected=Measurement.not_collected("assess not run")),
    ]
    out += [
        unbuilt(p)
        for p in PHASE_ORDER
        if p not in (PhaseId.INIT, PhaseId.SCAN, PhaseId.DISCOVER, PhaseId.ASSESS)
    ]
    return out


def _init(ok: bool = True) -> InitOutcome:
    if not ok:
        return InitOutcome(
            result=PhaseResult(
                phase=PhaseId.INIT, collected=Measurement.not_collected("triage child failed: boom")
            )
        )
    return InitOutcome(
        result=PhaseResult(phase=PhaseId.INIT, collected=Measurement.measured(1.0)),
        triage=_triage(),
    )


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
    # SCAN is built in E-46, DISCOVER in E-48, and ASSESS in E-49, so none is in
    # PHASE_OWNER; every other post-init phase still names the item that owes
    # its body.
    assert set(PHASE_OWNER) == set(PHASE_ORDER) - {
        PhaseId.INIT,
        PhaseId.SCAN,
        PhaseId.DISCOVER,
        PhaseId.ASSESS,
    }


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
    a = assemble("/r", _init(), True, "verdict ready", _rest_after_discover(), scan=_scan_result())
    assert a.admitted is True
    assert a.terminal_status == PARTIAL
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_assemble_reports_assessed_once_every_phase_collects():
    """The status flips by itself when E-46..E-52 land -- no workflow edit."""
    from sdlc.assessment.gates.models import RiskGateReport, RiskGateVerdict

    rest = [
        PhaseResult(phase=p, collected=Measurement.measured(1.0))
        for p in PHASE_ORDER
        if p is not PhaseId.INIT
    ]
    assert (
        assemble(
            "/r",
            _init(),
            True,
            "verdict ready",
            rest,
            scan=_scan_result(),
            discover=CapabilityMap(collected=Measurement.measured(0.0)),
            risk=UnifiedRiskMap(collected=Measurement.measured(0.0)),
            gates=RiskGateReport(verdict=RiskGateVerdict.PASS),
        ).terminal_status
        == ASSESSED
    )


def test_assemble_orders_phases_canonically_regardless_of_arrival():
    a = assemble(
        "/r",
        _init(),
        True,
        "verdict ready",
        list(reversed(_rest_after_discover())),
        scan=_scan_result(),
    )
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_assemble_rejects_a_partial_rest_on_an_admitted_run():
    """An admitted run has no 'unreached' phases -- run() always supplies all
    six. A missing one is a caller bug, and filling it with skipped() would
    stamp 'not admitted' onto an artifact whose admitted field is True -- a
    contradiction on the face of an FR-921 bundle (review finding 1). The
    not-admitted path still fills with skipped(), whose message is then
    truthful."""
    partial = [unbuilt(PhaseId.REPORT)]  # one of the unbuilt phases
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
    calls = [
        "self._init(",
        "self._scan(",
        "self._discover(",
        "self._assess(",
        "self._report(",
        "self._generate(",
        "self._finish(",
    ]
    positions = [src.index(c) for c in calls]
    assert positions == sorted(positions)


def test_admission_is_checked_at_tier_two_strictness():
    src = inspect.getsource(AssessmentWorkflow.run)
    assert "require_human=True" in src


# --- E-48 plan 2: discover is a built phase ------------------------------


def test_discover_is_no_longer_an_unbuilt_phase():
    """E-46 dropped SCAN from PHASE_OWNER when its body landed; this is the
    same move for DISCOVER, and terminal_status derives the change."""
    assert PhaseId.DISCOVER not in PHASE_OWNER


def test_the_input_carries_a_project_key():
    """Capability identity is per-project (E-47a), and a value derived from
    repo_dir would move every client-cited BC-NNN when a checkout moves.
    Named after PipelineConfig.project_key, which addresses the same SQLite."""
    assert AssessmentInput(repo_dir="/r").project_key == "default"


def test_no_discover_carries_its_reason_and_no_map():
    out = no_discover("S5 did not collect: nothing merged")
    assert out.map is None
    assert out.result.phase is PhaseId.DISCOVER
    assert out.result.collected.state is CollectionState.NOT_COLLECTED
    assert "S5" in out.result.collected.reason


def test_a_measured_discover_reaches_the_artifact():
    """The pairing Assessment._discover_agrees_with_its_phase enforces, from
    the workflow's side: assemble() must be handed the map whenever the phase
    row is measured."""
    cap_map = CapabilityMap(collected=Measurement.measured(0.0))
    rest = _rest_after_discover(PhaseResult(phase=PhaseId.DISCOVER, collected=cap_map.collected))
    a = assemble("/r", _init(), True, "verdict ready", rest, scan=_scan_result(), discover=cap_map)
    assert a.discover is not None
    assert a.terminal_status == PARTIAL


def test_the_run_body_passes_the_scan_and_triage_into_discover():
    """_discover needs the tree hash, the pinned commit and the candidate set;
    a body that still called self._discover(inp) would compile and silently
    rediscover nothing."""
    src = inspect.getsource(AssessmentWorkflow.run)
    assert "self._discover(inp, init.triage, scan_out)" in src
    assert "discover=discover_out.map" in src


# --- E-49: assess is a built phase --------------------------------------


def test_assess_is_no_longer_an_unbuilt_phase():
    """E-46 and E-48's move, for ASSESS."""
    assert PhaseId.ASSESS not in PHASE_OWNER


def test_no_assess_reports_the_reason_and_carries_no_map():
    from sdlc.workflows.assessment import no_assess

    out = no_assess("discover did not collect")
    assert out.risk is None
    assert "discover did not collect" in out.result.collected.reason


def test_the_run_body_passes_the_outputs_into_assess():
    src = inspect.getsource(AssessmentWorkflow.run)
    assert "self._assess(inp, init.triage, discover_out, scan_out)" in src
    assert "risk=assess_out.risk" in src


# --- E-49 plan 2: the judgment layer ----------------------------------


def test_assess_input_carries_a_propose_risk_knob():
    """RD7's off switch, propose_discover's shape."""
    from sdlc.workflows.assessment import AssessmentInput

    assert AssessmentInput(repo_dir="/x").propose_risk is True
    assert AssessmentInput(repo_dir="/x", propose_risk=False).propose_risk is False


def test_the_judgment_reasons_do_not_converge():
    """ "no proposer is configured" and "the proposer ran and was refused"
    are different facts and must read differently (P2-D2)."""
    import inspect

    from sdlc.workflows import assessment

    src = inspect.getsource(assessment.AssessmentWorkflow._judge)
    assert "no risk proposer ran" in src
    assert "the risk proposer ran and failed" in src


def test_a_failed_judgment_never_fails_the_phase():
    """RD7: the guard fails whatever consumed the model, and nothing else.
    _judge has no return path that is not a UnifiedRiskMap."""
    import inspect

    from sdlc.workflows import assessment

    src = inspect.getsource(assessment.AssessmentWorkflow._judge)
    assert "no_assess" not in src
    assert src.count("degraded(") >= 4


# --- E-50: workflow wiring and gate override update handler --------------
from datetime import UTC, datetime

from sdlc.assessment.gates.models import RiskGateOverride, RiskGateVerdict
from sdlc.assessment.risk.models import (
    RiskSource,
    Severity,
    StrideCategory,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.dispositions.models import Disposition, FindingDisposition


def _confirmed_vuln() -> Vulnerability:
    return Vulnerability(
        key="SS1:hardcoded-secret:src/a.py:",
        classification=VulnerabilityClass.CONFIRMED,
        severity=Severity.HIGH,
        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
        path="src/a.py",
        source=RiskSource.BASELINE,
    )


def _disposition(key="SS1:hardcoded-secret:src/a.py:") -> FindingDisposition:
    return FindingDisposition(
        kind="vulnerability",
        key=key,
        disposition=Disposition.ACCEPTED_RISK,
        approved_by="maks",
        reason="reviewed",
        decided_at=datetime.now(UTC),
    )


def _risk_map(collected: Measurement | None = None) -> UnifiedRiskMap:
    from tests.helpers_risk import capability_risk

    return UnifiedRiskMap(
        capabilities=(capability_risk(),),
        collected=collected or Measurement.measured(1.0),
    )


def _assess_dag(assess_measured: bool = True) -> list[PhaseResult]:
    out = []
    for phase in PHASE_ORDER:
        if phase is PhaseId.ASSESS and not assess_measured:
            out.append(
                PhaseResult(phase=phase, collected=Measurement.not_collected("assess not run"))
            )
        elif phase is PhaseId.DISCOVER:
            out.append(
                PhaseResult(phase=phase, collected=Measurement.not_collected("discover not run"))
            )
        else:
            out.append(PhaseResult(phase=phase, collected=Measurement.measured(1.0)))
    return out


# --- the pure evaluate step in the workflow ------------------------------


def test_assemble_threads_gates_through():
    """assemble() now accepts and populates `gates` (FR-917)."""
    from sdlc.assessment.gates.models import RiskGateReport
    from sdlc.assessment.models import PhaseId, PhaseResult
    from sdlc.workflows.assessment import assemble, unbuilt

    report = RiskGateReport(
        verdict=RiskGateVerdict.PASS,
        checks=(),
        deferred=(),
        reasons=(),
    )
    rest = [
        PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(0.0)),
        PhaseResult(
            phase=PhaseId.DISCOVER, collected=Measurement.not_collected("discover not run")
        ),
        PhaseResult(phase=PhaseId.ASSESS, collected=Measurement.measured(1.0)),
    ]
    rest += [
        unbuilt(p)
        for p in PHASE_ORDER
        if p not in (PhaseId.INIT, PhaseId.SCAN, PhaseId.DISCOVER, PhaseId.ASSESS)
    ]
    a = assemble(
        "/r",
        _init(),
        True,
        "verdict ready",
        rest,
        scan=_scan_result(),
        risk=_risk_map(),
        gates=report,
    )
    assert a.gates is not None
    assert a.gates.verdict is RiskGateVerdict.PASS


def test_evaluate_gates_pure_step_evaluates_against_dispositions():
    from sdlc.assessment.gates.checks import evaluate
    from tests.helpers_risk import capability_risk

    rmap = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_confirmed_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=Measurement.measured(1.0),
    )
    cmap = CapabilityMap(collected=Measurement.measured(1.0))
    # Without the disposition: BLOCK
    assert evaluate(rmap, cmap, ()).verdict is RiskGateVerdict.BLOCK
    # With the disposition: PASS
    assert evaluate(rmap, cmap, (_disposition(),)).verdict is RiskGateVerdict.PASS


# --- gate override update handler (GD1/GD2/FR-304) -----------------------


def test_apply_risk_gate_override_accepts_when_blocking():
    """An override submitted against a BLOCK verdict updates the artifact."""
    from sdlc.assessment.gates.models import RiskGateReport

    wf = AssessmentWorkflow()
    # Simulate a run that ended in BLOCK
    wf._assessment = assemble(
        "/r",
        _init(),
        True,
        "verdict ready",
        _assess_dag(assess_measured=True),
        scan=_scan_result(),
        risk=_risk_map(),
        gates=RiskGateReport(verdict=RiskGateVerdict.BLOCK, checks=(), deferred=(), reasons=()),
    )
    override = RiskGateOverride(
        approved_by="human",
        reviewer="maks",
        reason="production incident mitigates this differently",
        decided_at=datetime.now(UTC),
        gate_round=1,
    )
    result = wf.apply_risk_gate_override(override)
    assert result == "override applied"
    assert wf._assessment.gate_override is not None
    assert wf._assessment.gate_override.reviewer == "maks"


def test_apply_risk_gate_override_rejects_when_already_passing():
    """GD1: override on a PASS verdict is an error."""
    from sdlc.assessment.gates.models import RiskGateReport

    wf = AssessmentWorkflow()
    wf._assessment = assemble(
        "/r",
        _init(),
        True,
        "verdict ready",
        _assess_dag(assess_measured=True),
        scan=_scan_result(),
        risk=_risk_map(),
        gates=RiskGateReport(verdict=RiskGateVerdict.PASS, checks=(), deferred=(), reasons=()),
    )
    override = RiskGateOverride(
        approved_by="human",
        reviewer="maks",
        reason="redundant",
        decided_at=datetime.now(UTC),
        gate_round=1,
    )
    with pytest.raises(ValueError, match="cannot override a passing verdict"):
        wf.apply_risk_gate_override(override)
