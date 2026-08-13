"""E-45 end to end. Two workflows, no fan-out -- materially lighter than the
TidyUpWorkflow e2e P5 deferred for host contention.

Scenario (a) is the load-bearing one: it is the FUTURE-CONSUMER TRAP
workflows/tidyup.py:87-97 documents, executed end to end.
"""
from __future__ import annotations

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.assessment.activities import (
    AssessmentTree, AssessmentTreeInput,
    scan_ci, scan_config_infra, scan_coverage, scan_entrypoints, scan_frontend,
    scan_packages, scan_schema, scan_security_static, scan_sensitivity,
    scan_testability, scan_tests_inventory,
)
from sdlc.assessment.models import (
    BLOCKED, PARTIAL, PHASE_ORDER, PhaseId,
)
from sdlc.assessment.scan.models import SCAN_ORDER, ScanSignalId, SignalSource
from sdlc.measurement import CollectionState, Measurement
from sdlc.models import (
    GateDecision, GateOutcome, GatePolicy, GateSettings,
)
from sdlc.triage.activities import (
    TriageDependencyInput, TriagePin, TriagePinInput, TriageProbeInput,
    TriageSignalInput,
)
from sdlc.triage.models import SignalResult, Verdict
from sdlc.workflows.assessment import AssessmentInput, AssessmentWorkflow
from sdlc.workflows.triage import TriageWorkflow

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "assess-test"


def _ok(signal: str, version: int, metrics=None) -> SignalResult:
    return SignalResult(signal=signal, version=version,
                        collected=Measurement.measured(0.0),
                        metrics=metrics or {})


@activity.defn(name="triage_resolve_commit")
async def fake_pin(inp: TriagePinInput) -> TriagePin:
    return TriagePin(commit_sha="a" * 40, toolchain="python")


@activity.defn(name="triage_baseline")
async def fake_baseline(inp: TriageSignalInput) -> SignalResult:
    return _ok("baseline", 2, {"tests_present": Measurement.measured(3.0)})


@activity.defn(name="triage_scaffold")
async def fake_scaffold(inp: TriageSignalInput) -> SignalResult:
    return _ok("scaffold", 1,
               {"structure_discernible": Measurement.measured(1.0)})


@activity.defn(name="triage_build_probe")
async def fake_probe(inp: TriageProbeInput) -> SignalResult:
    return _ok("build_probe", 1, {"buildable": Measurement.measured(1.0),
                                  "runnable": Measurement.measured(1.0)})


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
async def fake_deps(inp: TriageDependencyInput) -> SignalResult:
    return _ok("dependencies", 1)


@activity.defn(name="assessment_resolve_tree")
async def fake_resolve_tree(inp: AssessmentTreeInput) -> AssessmentTree:
    # repo_dir="/r" is not a real git repo, so the real activity would fail.
    # The scan memo keys on this tree_hash; any stable 40-hex string stands in.
    return AssessmentTree(tree_hash="t" * 40)


# The eleven scan activities are the real stubs (no I/O -- each returns a
# not_collected row naming its plan), so they are registered as-is.
SCAN_ACTS = [scan_packages, scan_schema, scan_entrypoints, scan_frontend,
             scan_security_static, scan_config_infra, scan_sensitivity,
             scan_tests_inventory, scan_coverage, scan_testability, scan_ci]

ACTIVITIES = [fake_pin, fake_baseline, fake_scaffold, fake_probe,
              fake_secrets, fake_misconfig, fake_outliers, fake_deps,
              fake_resolve_tree, *SCAN_ACTS]
WORKFLOWS = [AssessmentWorkflow, TriageWorkflow]


async def _await_child_gate(env, child_id):
    """Poll the child until its readiness gate is pending. The child may not
    have started yet, so a query failure is a retry, not an error."""
    while True:
        try:
            items = await env.client.get_workflow_handle(child_id).query(
                TriageWorkflow.pending_decisions)
            if items:
                return items
        except Exception:                       # noqa: BLE001 -- not started
            pass
        await env.sleep(1)


async def test_a_policy_approved_tree_is_refused():
    """Scenario (a). --no-build-probe forces INDETERMINATE by construction,
    and gates OFF makes the child auto-approve its own readiness gate with
    decided_by='policy'. E-42's rule would admit this; Tier 2 must not."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir="/r", build_probe=False,
                    gates=GateSettings(default_gate_policy=GatePolicy.OFF)),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await handle.result()

    assert result.admitted is False
    assert result.terminal_status == BLOCKED
    assert result.triage.readiness.verdict is Verdict.INDETERMINATE
    assert result.triage.override is not None
    assert result.triage.override.approved_by == "policy"
    assert "policy" in result.admission_reason
    # Not admitted is not empty-handed (E-44 D7): the caller still gets the
    # verdict and every hygiene finding.
    assert result.commit_sha == "a" * 40
    assert [p.phase for p in result.phases] == list(PHASE_ORDER)
    for p in result.phases:
        if p.phase is PhaseId.INIT:
            continue
        assert p.collected.state is CollectionState.NOT_COLLECTED
        assert "not admitted" in p.collected.reason


async def test_a_human_override_admits_the_same_tree():
    """Scenario (b). Identical tree, decided by a human on the CHILD's gate."""
    wf_id = f"assess-{uuid.uuid4()}"
    child_id = f"{wf_id}-triage"        # _init derives it exactly this way
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r", build_probe=False),
                id=wf_id, task_queue=TASK_QUEUE)

            items = await _await_child_gate(env, child_id)
            assert items[0].gate == "readiness"

            await env.client.get_workflow_handle(child_id).signal(
                TriageWorkflow.submit_gate_decision,
                GateDecision(gate="readiness", round=1,
                             outcome=GateOutcome.APPROVE,
                             decided_by="human", reviewer="alice",
                             comments="scope understood"))
            result = await handle.result()

    assert result.admitted is True
    assert result.triage.override.approved_by == "human"
    assert result.terminal_status == PARTIAL
    assert [p.phase for p in result.phases] == list(PHASE_ORDER)
    # SCAN is built in E-46: its phase row is now measured, not an unbuilt
    # stub naming its owner.
    assert result.phases[1].phase is PhaseId.SCAN
    assert result.phases[1].collected.state is CollectionState.MEASURED


async def test_a_ready_repo_is_admitted_with_no_gate():
    """The happy path: the build probe reports a buildable repo, the child
    opens no gate at all, and the shell runs the whole DAG."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r"),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await handle.result()

    assert result.triage.readiness.verdict is Verdict.READY
    assert result.triage.override is None
    assert result.admitted is True
    assert result.admission_reason == "verdict ready"
    assert result.terminal_status == PARTIAL
    assert result.toolchain == "python"


async def test_the_assessment_query_serves_the_artifact():
    """FR-911: phase state lives in workflow history -- the result plus this
    query ARE the record, and no workflow.json is written."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r"),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            await handle.result()
            served = await handle.query(AssessmentWorkflow.assessment)
            status = await handle.query(AssessmentWorkflow.status)

    assert served is not None
    assert served.commit_sha == "a" * 40
    assert status == PARTIAL


async def test_scan_phase_flips_terminal_status_to_partial():
    """E-45 D6's claim, now testable end to end: terminal_status is DERIVED,
    so E-46 landing flips it with no edit to E-45's derivation. The happy-path
    worker (fake triage + fake tree resolver + real scan stubs) drives a READY
    repo through to an assessed:partial artifact whose SS1 row carries its
    inherited producer (D7)."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r"),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await handle.result()

    assert result.terminal_status == PARTIAL
    assert result.scan is not None
    assert [s.signal for s in result.scan.signals] == list(SCAN_ORDER)
    ss1 = next(s for s in result.scan.signals
               if s.signal is ScanSignalId.SS1)
    assert ss1.source is SignalSource.EXTENDED
    assert ss1.producer is not None
    # SS2 is purely inherited (D12 cut its computed half): fake_deps reported
    # measured, so its row reads INHERITED + collected -- not a skipped stub
    # (FR-915, review finding 1).
    ss2 = next(s for s in result.scan.signals
               if s.signal is ScanSignalId.SS2)
    assert ss2.source is SignalSource.INHERITED
    assert ss2.collected.state is CollectionState.MEASURED
    # S5's merge is real as of plan 2. This worker points the activities at a
    # repo_dir that does not exist, so S1-S4 degrade and S5 correctly reports
    # a GAP naming them -- not a measured zero, and not a plan.
    s5 = next(s for s in result.scan.signals if s.signal is ScanSignalId.S5)
    assert s5.collected.state is CollectionState.NOT_COLLECTED
    assert "plan" not in s5.collected.reason.lower()
    assert "S1" in s5.collected.reason
    assert result.scan.candidates == []
    # Plan 3: every body has landed, so no row may name a plan. The fake
    # worker's repo_dir does not exist, so the tree-reading signals report
    # a FAILURE -- which is a different sentence from "not implemented", and
    # the two must not converge (failed_signal vs unbuilt_signal).
    assert len(result.scan.signals) == 13
    for row in result.scan.signals:
        assert "not implemented" not in (row.collected.reason or "")
        assert "plan" not in (row.collected.reason or "").lower()
