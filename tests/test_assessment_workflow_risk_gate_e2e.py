# tests/test_assessment_workflow_risk_gate_e2e.py
"""E-50 end to end: the risk gate opens on BLOCK, mirrors the readiness
gate's mechanics, and REJECT vs APPROVE diverge exactly as GD2 states."""

from __future__ import annotations

import subprocess
import time
import uuid
from datetime import UTC, datetime

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.assessment.activities import (
    assessment_resolve_tree,
    discover_context,
    load_dispositions,
    scan_ci,
    scan_config_infra,
    scan_coverage,
    scan_entrypoints,
    scan_frontend,
    scan_packages,
    scan_schema,
    scan_security_static,
    scan_sensitivity,
    scan_testability,
    scan_tests_inventory,
)
from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.gates.models import RiskGateVerdict
from sdlc.assessment.models import PARTIAL, PhaseId
from sdlc.assessment.risk.models import (
    Composite,
    Criticality,
    CriticalityRating,
    Factor,
    RiskSource,
    Severity,
    StrideCategory,
    UnifiedRiskMap,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.assessment.scan.models import TestabilityFinding, testability_identity
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
)
from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.dispositions.store import BoardFindingDispositionStore
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.activities import TriagePin, TriagePinInput, TriageProbeInput, TriageSignalInput
from sdlc.triage.models import SignalResult
from sdlc.workflows.assessment import AssessmentInput, AssessmentWorkflow, risk_gate_skipped
from sdlc.workflows.triage import TriageWorkflow
from tests.helpers_risk import capability, capability_map, capability_risk

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "risk-gate-test"


def _ok(signal, version, metrics=None):
    return SignalResult(
        signal=signal, version=version, collected=Measurement.measured(0.0), metrics=metrics or {}
    )


@activity.defn(name="triage_baseline")
async def fake_baseline(inp: TriageSignalInput) -> SignalResult:
    return _ok("baseline", 2, {"tests_present": Measurement.measured(3.0)})


@activity.defn(name="triage_scaffold")
async def fake_scaffold(inp: TriageSignalInput) -> SignalResult:
    return _ok("scaffold", 1, {"structure_discernible": Measurement.measured(1.0)})


@activity.defn(name="triage_build_probe")
async def fake_probe(inp: TriageProbeInput) -> SignalResult:
    return _ok(
        "build_probe",
        1,
        {"buildable": Measurement.measured(1.0), "runnable": Measurement.measured(1.0)},
    )


@activity.defn(name="triage_secrets")
async def fake_secrets(inp: TriageSignalInput) -> SignalResult:
    return _ok("secrets", 2)


@activity.defn(name="triage_misconfig")
async def fake_misconfig(inp: TriageSignalInput) -> SignalResult:
    return _ok("misconfig", 1)


@activity.defn(name="triage_outliers")
async def fake_outliers(inp: TriageSignalInput) -> SignalResult:
    return _ok("outliers", 1)


@activity.defn(name="triage_dependencies")
async def fake_deps(inp) -> SignalResult:
    return _ok("dependencies", 1)


SCAN_ACTS = [
    scan_packages,
    scan_schema,
    scan_entrypoints,
    scan_frontend,
    scan_security_static,
    scan_config_infra,
    scan_sensitivity,
    scan_tests_inventory,
    scan_coverage,
    scan_testability,
    scan_ci,
]
WORKFLOWS = [AssessmentWorkflow, TriageWorkflow]


def _blocker() -> TestabilityFinding:
    return TestabilityFinding(
        severity="blocks",
        pattern="singleton-access",
        detail="reaches a global instance",
        recommended_seam="pass the collaborator in",
        path="payments/api.py",
        line=3,
        evidence="Singleton.getInstance()",
    )


def _blocking_capability_map() -> CapabilityMap:
    # capability_map() (tests/helpers_risk.py) derives by_action -- a raw
    # CapabilityMap(capabilities=(...)) with no by_action trips
    # _counts_are_derived's "unlisted" branch (discover/map.py) the instant
    # a capability carries a disposition action absent from that dict.
    return capability_map(capability(bc_id="BC-001", testability=(_blocker(),)))


def _clean_capability_map() -> CapabilityMap:
    return capability_map(capability(bc_id="BC-001"))


def _high_risk_map() -> UnifiedRiskMap:
    cap = capability_risk(
        bc_id="BC-001",
        criticality=CriticalityRating(level=Criticality.HIGH, collected=Measurement.measured(1.0)),
    )
    return UnifiedRiskMap(capabilities=(cap,), collected=Measurement.measured(1.0))


def _git(args, cwd):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


@pytest.fixture
def gate_repo(tmp_path):
    # Exact content of test_assessment_workflow_e2e.py's `assessed_repo`
    # fixture, proven to carry S5/discover_context all the way to MEASURED
    # (test_assess_phase_measures_with_no_model_registered). This test does
    # not need THAT content specifically -- discover_memo_load and
    # risk_memo_load are faked below, so nothing here needs to resolve to
    # any particular capability or finding -- it only needs SCAN and
    # discover_context to succeed for real before the memo fakes take over.
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}\n')
    (tmp_path / "app" / "payments").mkdir(parents=True)
    (tmp_path / "app" / "payments" / "page.tsx").write_text(
        "export default function PaymentsPage() { return null; }\n"
    )
    (tmp_path / "payments").mkdir()
    (tmp_path / "payments" / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "from payments.models import Order\n"
        "app = FastAPI()\n"
        "@app.post('/api/payments')\ndef charge(): pass\n"
    )
    (tmp_path / "payments" / "models.py").write_text(
        "class Order(Base):\n    __tablename__ = 'payments'\n    id = Column(Integer)\n"
    )
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()
    return str(tmp_path), sha


async def _await_gate(env, wf_id, gate_name, *, timeout_seconds: float = 60.0):
    """Bounded on purpose, by a wall-clock DEADLINE rather than a poll
    count: before Task 9's implementation exists, `run()` never opens a
    "risk" gate at all, so an unbounded version of this helper would hang
    forever (the workflow completes normally in the background while
    polling keeps returning an empty list) rather than failing the test
    cleanly. A poll count sized for the common case would flake instead --
    this e2e drives the real triage child plus all thirteen scan signals
    plus discover_context before the gate can even open, which itself
    takes genuine wall-clock time (env.sleep only skips virtual time while
    the workflow is otherwise idle, not while real activities are still
    running), and a loaded CI host makes that worse. 60s is generous
    against that pipeline, not against the gate wait itself."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            items = await env.client.get_workflow_handle(wf_id).query(
                AssessmentWorkflow.pending_decisions
            )
            if items and items[0].gate == gate_name:
                return items
        except Exception:  # noqa: BLE001 -- not started
            pass
        await env.sleep(1)
    raise AssertionError(f"no {gate_name!r} gate became pending within {timeout_seconds}s")


def _acts(sha, discover_hit, risk_hit):
    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    @activity.defn(name="discover_memo_load")
    async def fake_discover_hit(inp) -> CapabilityMap:
        return discover_hit

    @activity.defn(name="risk_memo_load")
    async def fake_risk_hit(inp) -> UnifiedRiskMap:
        return risk_hit

    return [
        real_pin,
        fake_baseline,
        fake_scaffold,
        fake_probe,
        fake_secrets,
        fake_misconfig,
        fake_outliers,
        fake_deps,
        assessment_resolve_tree,
        *SCAN_ACTS,
        discover_context,
        fake_discover_hit,
        fake_risk_hit,
        load_dispositions,
    ]


async def test_a_rejected_block_leaves_report_generate_finish_skipped(
    gate_repo, tmp_path, monkeypatch
):
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            items = await _await_gate(env, wf_id, "risk")
            assert items[0].gate == "risk"

            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(
                    gate="risk",
                    round=1,
                    outcome=GateOutcome.REJECT,
                    decided_by="human",
                    reviewer="alice",
                    comments="not overriding",
                ),
            )
            result = await handle.result()

    assert result.gates is not None
    assert result.gates.verdict == RiskGateVerdict.BLOCK
    assert result.gate_override is None
    assert result.terminal_status == PARTIAL
    for phase_id in (PhaseId.REPORT, PhaseId.GENERATE, PhaseId.FINISH):
        row = next(p for p in result.phases if p.phase is phase_id)
        assert row.collected.state is CollectionState.NOT_COLLECTED
        assert "risk gate" in row.collected.reason


async def test_an_approved_block_stamps_an_override_and_continues(gate_repo, tmp_path, monkeypatch):
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, wf_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(
                    gate="risk",
                    round=1,
                    outcome=GateOutcome.APPROVE,
                    decided_by="human",
                    reviewer="alice",
                    comments="known issue, ticket filed",
                ),
            )
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.BLOCK
    assert result.gate_override is not None
    assert result.gate_override.approved_by == "human"
    assert result.terminal_status == PARTIAL  # E-51/E-52 still unbuilt
    for phase_id in (PhaseId.REPORT, PhaseId.GENERATE, PhaseId.FINISH):
        row = next(p for p in result.phases if p.phase is phase_id)
        # Distinguishable from the rejected case's reason (GD2's whole
        # point) -- compared against risk_gate_skipped() itself, not a
        # hardcoded "not implemented" substring, so this stays true once
        # E-51/E-52 land and REPORT/GENERATE/FINISH stop being unbuilt
        # stubs (their MEASURED reason, whatever it becomes, will still
        # differ from risk_gate_skipped()'s).
        assert row.collected.reason != risk_gate_skipped(phase_id).collected.reason


async def test_a_revised_block_is_treated_as_rejected(gate_repo, tmp_path, monkeypatch):
    """GD2's amendment, pinned: REVISE has no round concept for this gate,
    so it leaves REPORT/GENERATE/FINISH unreached exactly like REJECT."""
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, wf_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(
                    gate="risk",
                    round=1,
                    outcome=GateOutcome.REVISE,
                    decided_by="human",
                    comments="try again?",
                ),
            )
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.BLOCK
    assert result.gate_override is None
    for phase_id in (PhaseId.REPORT, PhaseId.GENERATE, PhaseId.FINISH):
        row = next(p for p in result.phases if p.phase is phase_id)
        assert row.collected.reason == risk_gate_skipped(phase_id).collected.reason


async def test_load_dispositions_failing_falls_back_to_zero_not_a_crash(
    gate_repo, tmp_path, monkeypatch
):
    """Failure-modes row: 'load_dispositions activity fails -> treated as
    zero dispositions loaded for this run.' A real disposition sits in the
    board, but the activity always raises, so run_or_degrade's fallback
    must still let BLOCK fire -- proving the fallback is conservative
    (nothing is treated as accepted that couldn't be confirmed), not a
    silent 'assume everything is dispositioned.'"""
    repo_dir, sha = gate_repo
    db = tmp_path / "board.sqlite3"
    monkeypatch.setenv("SDLC_BOARD_DB", str(db))
    key = testability_identity(_blocker())

    store = BoardFindingDispositionStore(db=db)
    store.apply(
        "acme",
        FindingDisposition(
            kind="testability",
            key=key,
            disposition=Disposition.ACCEPTED_RISK,
            approved_by="maks",
            reason="pre-seeded, should be unreachable",
            decided_at=datetime.now(UTC),
        ),
        expected_version=0,
        actor="maks",
    )
    store.close()

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    @activity.defn(name="discover_memo_load")
    async def fake_discover_hit(inp) -> CapabilityMap:
        return _blocking_capability_map()

    @activity.defn(name="risk_memo_load")
    async def fake_risk_hit(inp) -> UnifiedRiskMap:
        return _high_risk_map()

    @activity.defn(name="load_dispositions")
    async def failing_load_dispositions(inp):
        raise RuntimeError("board unavailable")

    acts = [
        real_pin,
        fake_baseline,
        fake_scaffold,
        fake_probe,
        fake_secrets,
        fake_misconfig,
        fake_outliers,
        fake_deps,
        assessment_resolve_tree,
        *SCAN_ACTS,
        discover_context,
        fake_discover_hit,
        fake_risk_hit,
        failing_load_dispositions,
    ]
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            # The pre-seeded disposition would clear this BLOCK if it were
            # read; the gate must still open, proving it was not.
            items = await _await_gate(env, wf_id, "risk")
            assert items[0].gate == "risk"
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(gate="risk", round=1, outcome=GateOutcome.REJECT, decided_by="human"),
            )
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.BLOCK


def _warn_risk_map() -> UnifiedRiskMap:
    cap = capability_risk(
        bc_id="BC-001",
        unified=Composite(
            value=Measurement.measured(0.65),
            factors=(Factor(key="x", value=Measurement.measured(0.65)),),
        ),
    )
    return UnifiedRiskMap(capabilities=(cap,), collected=Measurement.measured(1.0))


async def test_a_warn_verdict_opens_no_gate_and_phases_proceed(gate_repo, tmp_path, monkeypatch):
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _clean_capability_map(), _warn_risk_map())

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            # No signal is sent: a WARN must never leave the workflow waiting.
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.WARN
    assert result.gate_override is None
    row = next(p for p in result.phases if p.phase is PhaseId.REPORT)
    # Stable across E-51/E-52 landing, unlike a hardcoded "not implemented"
    # substring (finding 13's fix, applied here too): phases ran normally,
    # not risk-gate-skipped.
    assert row.collected.reason != risk_gate_skipped(PhaseId.REPORT).collected.reason


async def test_a_testability_disposition_clears_the_block_on_rerun(
    gate_repo, tmp_path, monkeypatch
):
    """FR-917's persistence promise, end to end: the SAME finding BLOCKs the
    first run and does not even open a gate on the second, once dispositioned."""
    repo_dir, sha = gate_repo
    db = tmp_path / "board.sqlite3"
    monkeypatch.setenv("SDLC_BOARD_DB", str(db))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    key = testability_identity(_blocker())

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            first_id = f"assess-{uuid.uuid4()}"
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=first_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, first_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(gate="risk", round=1, outcome=GateOutcome.REJECT, decided_by="human"),
            )
            first_result = await handle.result()
            assert first_result.gates.verdict == RiskGateVerdict.BLOCK

            store = BoardFindingDispositionStore(db=db)
            store.apply(
                "acme",
                FindingDisposition(
                    kind="testability",
                    key=key,
                    disposition=Disposition.ACCEPTED_RISK,
                    approved_by="maks",
                    reason="known pattern, ticket filed",
                    decided_at=datetime.now(UTC),
                ),
                expected_version=0,
                actor="maks",
            )
            store.close()

            second_id = f"assess-{uuid.uuid4()}"
            handle2 = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=second_id,
                task_queue=TASK_QUEUE,
            )
            second_result = await handle2.result()

    assert second_result.gates.verdict == RiskGateVerdict.PASS
    assert second_result.gate_override is None


def _confirmed_vuln_risk_map(bc_id="BC-001") -> UnifiedRiskMap:
    vuln = Vulnerability(
        key="SS1:hardcoded-secret:payments/api.py:",
        classification=VulnerabilityClass.CONFIRMED,
        severity=Severity.HIGH,
        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
        path="payments/api.py",
        source=RiskSource.BASELINE,
    )
    cap = capability_risk(bc_id=bc_id, vulnerabilities=(vuln,))
    # judgment MEASURED: CONFIRMED is only reachable through the judgment
    # layer (GD3) -- unlike the testability fixtures above, this map must
    # carry it directly since faking risk_memo_load bypasses _judge() (the
    # method that would otherwise stamp it) entirely.
    return UnifiedRiskMap(
        capabilities=(cap,),
        collected=Measurement.measured(1.0),
        judgment=Measurement.measured(1.0),
    )


async def test_a_vulnerability_disposition_clears_the_block_on_rerun(
    gate_repo, tmp_path, monkeypatch
):
    """The spec's own first e2e case: a confirmed vulnerability opens the
    gate, and `sdlc risk dispose --kind vulnerability` clears it on
    re-run -- mirrors the testability version above but for the OTHER live
    clause, which the testability case alone does not exercise."""
    repo_dir, sha = gate_repo
    db = tmp_path / "board.sqlite3"
    monkeypatch.setenv("SDLC_BOARD_DB", str(db))
    acts = _acts(sha, _clean_capability_map(), _confirmed_vuln_risk_map())
    key = "SS1:hardcoded-secret:payments/api.py:"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            first_id = f"assess-{uuid.uuid4()}"
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=first_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, first_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(gate="risk", round=1, outcome=GateOutcome.REJECT, decided_by="human"),
            )
            first_result = await handle.result()
            assert first_result.gates.verdict == RiskGateVerdict.BLOCK

            store = BoardFindingDispositionStore(db=db)
            store.apply(
                "acme",
                FindingDisposition(
                    kind="vulnerability",
                    key=key,
                    disposition=Disposition.ACCEPTED_RISK,
                    approved_by="maks",
                    reason="known issue, ticket filed",
                    decided_at=datetime.now(UTC),
                ),
                expected_version=0,
                actor="maks",
            )
            store.close()

            second_id = f"assess-{uuid.uuid4()}"
            handle2 = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=second_id,
                task_queue=TASK_QUEUE,
            )
            second_result = await handle2.result()

    assert second_result.gates.verdict == RiskGateVerdict.PASS
    assert second_result.gate_override is None
