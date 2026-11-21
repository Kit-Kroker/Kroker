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
    Assessment,
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
from sdlc.core.models import (
    GatePolicy,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import Readiness, RepoTriage, Verdict
from sdlc.workflows.assessment import (
    PHASE_OWNER,
    AssessmentInput,
    AssessmentWorkflow,
    AssessOutcome,
    DiscoverOutcome,
    FinishOutcome,
    RiskGateStepOutcome,
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
    """SCAN (E-46), DISCOVER (E-48), ASSESS (E-49), and FINISH (E-51) are built;
    REPORT and GENERATE remain stubs.

    DISCOVER and ASSESS default to not_collected so a caller that does not care about
    their pairing need not supply their maps. FINISH's fixture row is not_collected:
    with these producers unmeasured the phase short-circuits (FD13), so it never
    measures here.
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
        if p not in (PhaseId.INIT, PhaseId.SCAN, PhaseId.DISCOVER, PhaseId.ASSESS, PhaseId.FINISH)
    ]
    out.append(
        PhaseResult(phase=PhaseId.FINISH, collected=Measurement.not_collected("finish not run"))
    )
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
    # SCAN is built in E-46, DISCOVER in E-48, ASSESS in E-49, and FINISH in
    # E-51, so none is in PHASE_OWNER; every other post-init phase still names
    # the item that owes its body.
    assert set(PHASE_OWNER) == set(PHASE_ORDER) - {
        PhaseId.INIT,
        PhaseId.SCAN,
        PhaseId.DISCOVER,
        PhaseId.ASSESS,
        PhaseId.FINISH,
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

from sdlc.assessment.gates.models import RiskGateReport, RiskGateVerdict
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
        if p not in (PhaseId.INIT, PhaseId.SCAN, PhaseId.DISCOVER, PhaseId.ASSESS, PhaseId.FINISH)
    ]
    rest.append(
        PhaseResult(phase=PhaseId.FINISH, collected=Measurement.not_collected("finish not run"))
    )
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


# --- FR-202 (VR-3a): output-retry forwarding at the two direct calls -------
#
# The discover/risk proposers bypass the RoleHost seam (assessment.py calls
# the module-level t_<role> agents directly), so the registry's
# validated-output retry budget must be forwarded at the call sites
# themselves -- same idiom as _run_role, only when set. The posture is
# tests/durability/test_payload_guard_callsites.py's: the agent is patched
# onto the assessment module's own name, discover_context is served
# in-process, every run_or_degrade call takes its fallback, and the
# recorder raises after recording so each site's fail-closed catch is the
# thing that returns.


class _RecordingProposer:
    """Records every kwargs dict t_<role>.run received, then raises -- the
    forwarding is observable only on the calling side, and the raise rides
    the site's existing fail-closed catch so the phase still returns."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, *args: object, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise RuntimeError("recorder: kwargs captured")


def _measured_discover_context():
    from sdlc.assessment.discover.map import DiscoverContext, GraphSummary

    return DiscoverContext(
        graph=GraphSummary(
            parsed=1,
            unparsed=0,
            edges=0,
            unresolved_relative_rate=Measurement.measured(0.0),
        ),
        collected=Measurement.measured(1.0),
    )


def _scan_outcome():
    from sdlc.workflows.scanning import ScanOutcome

    return ScanOutcome(
        result=PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(1.0)),
        scan=_scan_result(),
        tree_hash="t" * 40,
    )


def _serve_discover_lead_ins(monkeypatch: pytest.MonkeyPatch) -> None:
    """discover_context answers in-process; every other activity raises, so
    each run_or_degrade call takes its fallback (memo MISS)."""
    import sdlc.workflows.assessment as assessment_module
    from sdlc.assessment.activities import discover_context

    async def _fake_activity(activity: object, arg: object, **_opts: object) -> object:
        if activity is discover_context:
            return _measured_discover_context()
        raise RuntimeError("no activity runtime in-process")

    monkeypatch.setattr(assessment_module.workflow, "execute_activity", _fake_activity)


def test_discover_forwards_configured_retries(monkeypatch):
    """VR-3a: the direct t_discover call forwards the role's configured
    budget -- registry 3 makes retries={"output": 3} reach the agent; the
    shipped registry (discover at the default 1) carries NO retries kwarg
    at all, so a default call is byte-identical to one that never knew
    about the knob. Fail-closed is untouched: the recorder's raise still
    lands in the existing catch and yields no map."""
    import asyncio

    import sdlc.workflows.assessment as assessment_module

    # Premise: the shipped registry carries discover at the default.
    assert assessment_module.OUTPUT_RETRIES.get("discover", 1) == 1

    agent = _RecordingProposer()
    monkeypatch.setattr(assessment_module, "t_discover", agent)
    _serve_discover_lead_ins(monkeypatch)
    wf = AssessmentWorkflow()
    inp = AssessmentInput(repo_dir="/r")

    # Shipped registry: no retries kwarg.
    out = asyncio.run(wf._discover(inp, _triage(), _scan_outcome()))
    assert agent.calls == [{}]
    assert out.map is None
    assert out.result.collected.reason.startswith("discover proposer failed:")

    # Configured 3: the budget reaches the agent.
    monkeypatch.setattr(assessment_module, "OUTPUT_RETRIES", {"discover": 3, "risk": 3})
    out = asyncio.run(wf._discover(inp, _triage(), _scan_outcome()))
    assert agent.calls == [{}, {"retries": {"output": 3}}]
    assert out.result.collected.reason.startswith("discover proposer failed:")


def test_risk_forwards_configured_retries(monkeypatch):
    """VR-3a's risk twin: the direct t_risk call forwards the configured
    budget (3 -> retries={"output": 3}); the shipped registry (risk at the
    default 1) carries no retries kwarg. The recorder's raise still
    degrades to the baseline with judgment NOT_COLLECTED -- RD7 untouched."""
    import asyncio

    import sdlc.workflows.assessment as assessment_module

    # Premise: the shipped registry carries risk at the default.
    assert assessment_module.OUTPUT_RETRIES.get("risk", 1) == 1

    agent = _RecordingProposer()
    monkeypatch.setattr(assessment_module, "t_risk", agent)
    wf = AssessmentWorkflow()
    cmap = CapabilityMap(collected=Measurement.measured(1.0))
    inp = AssessmentInput(repo_dir="/r")

    # Shipped registry: no retries kwarg.
    out = asyncio.run(wf._judge(inp, _triage(), cmap, _risk_map(), proposing=True))
    assert agent.calls == [{}]
    assert out.collected.state is CollectionState.MEASURED, "the composites survive"
    assert out.judgment.state is CollectionState.NOT_COLLECTED
    assert out.judgment.reason.startswith("the risk proposer ran and failed:")

    # Configured 3: the budget reaches the agent.
    monkeypatch.setattr(assessment_module, "OUTPUT_RETRIES", {"discover": 3, "risk": 3})
    out = asyncio.run(wf._judge(inp, _triage(), cmap, _risk_map(), proposing=True))
    assert agent.calls == [{}, {"retries": {"output": 3}}]
    assert out.judgment.reason.startswith("the risk proposer ran and failed:")


# --- E-51: finish is a built phase --------------------------------------


def _measured_discover_outcome() -> DiscoverOutcome:
    """A measured DISCOVER row carrying its map -- the pairing the artifact's
    discover validator demands of a measured phase."""
    return DiscoverOutcome(
        result=PhaseResult(phase=PhaseId.DISCOVER, collected=Measurement.measured(1.0)),
        map=CapabilityMap(collected=Measurement.measured(1.0)),
    )


def _measured_assess_outcome() -> AssessOutcome:
    """A measured ASSESS row carrying its map -- the ASSESS twin."""
    return AssessOutcome(
        result=PhaseResult(phase=PhaseId.ASSESS, collected=Measurement.measured(1.0)),
        risk=_risk_map(),
    )


def _drive_run(monkeypatch: pytest.MonkeyPatch, gate_out: RiskGateStepOutcome) -> Assessment:
    """run() end-to-end, in-process, over this file's fake-activity fixtures.

    The patched seams are exactly the ones Temporal owns: the child triage
    (execute_child_workflow, plus workflow.info for the child id), the scan
    fan-out (scan_tree), the two producer phases, and the gate host. run()'s
    own body, _report/_generate, _finish, and assemble all run REAL -- so the
    rest list, the finish_out binding, and the assemble kwargs are what a
    bug like an unbound finish_out on the blocked branch trips over.
    """
    import asyncio
    from types import SimpleNamespace

    import sdlc.workflows.assessment as assessment_module

    async def _fake_child(_run: object, _arg: object, **_kw: object) -> object:
        return _triage()

    async def _fake_scan_tree(*_args: object, **_kwargs: object) -> object:
        return _scan_outcome()

    async def _fake_discover(_inp: object, _triage: object, _scan_out: object) -> object:
        return _measured_discover_outcome()

    async def _fake_assess(
        _inp: object, _triage: object, _discover_out: object, _scan_out: object
    ) -> object:
        return _measured_assess_outcome()

    async def _fake_gate(_inp: object, _d: object, _a: object) -> RiskGateStepOutcome:
        return gate_out

    monkeypatch.setattr(
        assessment_module.workflow,
        "info",
        lambda: SimpleNamespace(workflow_id="test", run_id="r1", task_queue="test-queue"),
    )
    monkeypatch.setattr(assessment_module.workflow, "execute_child_workflow", _fake_child)
    monkeypatch.setattr(assessment_module, "scan_tree", _fake_scan_tree)
    wf = AssessmentWorkflow()
    monkeypatch.setattr(wf, "_discover", _fake_discover)
    monkeypatch.setattr(wf, "_assess", _fake_assess)
    monkeypatch.setattr(wf, "_risk_gate", _fake_gate)
    return asyncio.run(wf.run(AssessmentInput(repo_dir="/r")))


def test_finish_measures_on_admitted_run(monkeypatch):
    """E-51: run() on an admitted run whose three producers measured --
    _finish grades inline (FD16, the E-50 evaluate() precedent, no
    activity), the artifact carries the report, and terminal_status stays
    partial (REPORT/GENERATE are still owed to E-52)."""
    a = _drive_run(
        monkeypatch,
        gate_out=RiskGateStepOutcome(gates=RiskGateReport(verdict=RiskGateVerdict.PASS)),
    )
    finish_row = next(p for p in a.phases if p.phase is PhaseId.FINISH)
    assert finish_row.collected.state is CollectionState.MEASURED
    assert a.finish is not None
    assert a.finish.criteria, "the 14-criteria manifest grades over measured producers"
    assert a.terminal_status == PARTIAL
    # The producer pairing the artifact's validators demand, end to end.
    assert a.scan is not None
    assert a.discover is not None
    assert a.risk is not None
    assert a.gates is not None


def test_run_survives_a_blocked_gate_and_carries_no_finish(monkeypatch):
    """The blocked branch: rest carries risk_gate_skipped rows while the
    shared return still reads finish_out.report -- so finish_out must be
    bound on that branch too (an unbound one crashed every blocked run with
    an UnboundLocalError instead of producing the blocked artifact). No
    exception escapes, and the blocked artifact carries no report."""
    a = _drive_run(
        monkeypatch,
        gate_out=RiskGateStepOutcome(
            gates=RiskGateReport(verdict=RiskGateVerdict.BLOCK), blocked=True
        ),
    )
    finish_row = next(p for p in a.phases if p.phase is PhaseId.FINISH)
    assert finish_row.collected.state is CollectionState.NOT_COLLECTED
    assert "risk gate" in finish_row.collected.reason
    assert a.gates is not None
    assert a.gates.verdict is RiskGateVerdict.BLOCK
    assert a.gate_override is None
    assert a.finish is None
    assert a.terminal_status == PARTIAL


def test_phase_owner_loses_finish():
    """E-46 dropped SCAN from PHASE_OWNER when its body landed; E-48 and E-49
    did the same for DISCOVER and ASSESS. E-51's move, for FINISH: only the
    two E-52 stubs remain."""
    assert PHASE_OWNER == {PhaseId.REPORT: "E-52", PhaseId.GENERATE: "E-52"}


def test_inline_failure_degrades_to_not_collected(monkeypatch):
    """A pure-code failure inside evaluate_finish is a phase-level
    not_collected carrying the exception -- the no_discover shape, FD16's
    degraded leg -- never a crashed assessment and never a half-graded
    report on the artifact."""
    import asyncio

    import sdlc.workflows.assessment as assessment_module
    from sdlc.assessment.gates.models import RiskGateReport

    def _boom(**_kwargs: object) -> object:
        raise RuntimeError("xref exploded")

    monkeypatch.setattr(assessment_module, "evaluate_finish", _boom)
    scan_out = _scan_outcome()
    discover_out = _measured_discover_outcome()
    assess_out = _measured_assess_outcome()
    wf = AssessmentWorkflow()
    out = asyncio.run(
        wf._finish(AssessmentInput(repo_dir="/r"), scan_out, discover_out, assess_out)
    )
    assert isinstance(out, FinishOutcome), "finish returns its own outcome, not a bare row"
    assert out.report is None
    assert out.result.phase is PhaseId.FINISH
    assert out.result.collected.state is CollectionState.NOT_COLLECTED
    assert "evaluate_finish failed" in out.result.collected.reason
    assert "RuntimeError" in out.result.collected.reason

    rest = [
        scan_out.result,
        discover_out.result,
        assess_out.result,
        unbuilt(PhaseId.REPORT),
        unbuilt(PhaseId.GENERATE),
        out.result,
    ]
    a = assemble(
        "/r",
        _init(),
        True,
        "verdict ready",
        rest,
        scan=scan_out.scan,
        discover=discover_out.map,
        risk=assess_out.risk,
        gates=RiskGateReport(verdict=RiskGateVerdict.PASS),
        finish=out.report,
    )
    assert a.finish is None
