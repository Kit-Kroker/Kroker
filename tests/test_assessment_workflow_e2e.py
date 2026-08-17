"""E-45 end to end. Two workflows, no fan-out -- materially lighter than the
TidyUpWorkflow e2e P5 deferred for host contention.

Scenario (a) is the load-bearing one: it is the FUTURE-CONSUMER TRAP
workflows/tidyup.py:87-97 documents, executed end to end.
"""
from __future__ import annotations

import subprocess
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.assessment.activities import (
    AssessmentTree, AssessmentTreeInput,
    assess_risk,
    discover_context, discover_finalize, discover_lock, discover_memo_load,
    discover_memo_store, load_blueprint,
    risk_memo_load, risk_memo_store,
    scan_ci, scan_config_infra, scan_coverage, scan_entrypoints, scan_frontend,
    scan_packages, scan_schema, scan_security_static, scan_sensitivity,
    scan_testability, scan_tests_inventory, verify_discover_refs,
    verify_risk_refs,
)
from sdlc.assessment.models import (
    BLOCKED, PARTIAL, PHASE_ORDER, PhaseId,
)
from sdlc.assessment.scan.models import SCAN_ORDER, ScanSignalId, SignalSource
from sdlc.capability.store import BoardIdentityStore
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
              fake_resolve_tree, *SCAN_ACTS,
              discover_context, discover_lock, discover_finalize,
              discover_memo_load, discover_memo_store]
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


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)


@pytest.fixture
def assessed_repo(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"next": "14.0.0"}}\n')
    (tmp_path / "app" / "payments").mkdir(parents=True)
    (tmp_path / "app" / "payments" / "page.tsx").write_text(
        "export default function PaymentsPage() { return null; }\n")
    (tmp_path / "payments").mkdir()
    (tmp_path / "payments" / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "from payments.models import Order\n"
        "app = FastAPI()\n"
        "@app.post('/api/payments')\ndef charge(): pass\n")
    (tmp_path / "payments" / "models.py").write_text(
        "class Order(Base):\n    __tablename__ = 'payments'\n"
        "    id = Column(Integer)\n")
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                         capture_output=True, text=True,
                         stdin=subprocess.DEVNULL).stdout.strip()
    return str(tmp_path), sha


# --- E-48 plan 2 & 3: discover runs end to end inside the assessment --------


async def test_discover_goes_measured_and_the_map_reaches_the_artifact(
        assessed_repo, tmp_path, monkeypatch):
    """The happy-path assessment with a real git tree: triage is still faked
    (NFR-9: no build executed), but scan and discover run their REAL
    activities over the real repo.

    DD4's deterministic spine executes end-to-end:
      scan (S1-S4 real blobs, S5 merges S3-payments)
        -> discover_context (refgraph built and discarded)
        -> discover_memo_load (miss)
        -> stamp(context, None) -> apply (C-01 locked)
        -> discover_lock (allocates BC-001 in SQLite)
        -> load_blueprint + discover_finalize (attribute + decompose + assign)
        -> build_map -> discover_memo_store
        -> Assessment carries the CapabilityMap
    """
    repo_dir, sha = assessed_repo
    db = str(tmp_path / "board.sqlite3")
    monkeypatch.setenv("SDLC_BOARD_DB", db)

    # Pin to the real commit so the scan blob-readers find it.
    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    # Real tree resolver: the repo exists, so git rev-parse HEAD^{tree} works.
    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme",
                                propose_discover=False),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await handle.result()

    assert result.terminal_status == PARTIAL
    assert result.phases[1].phase is PhaseId.SCAN
    assert result.phases[1].collected.state is CollectionState.MEASURED
    assert result.phases[2].phase is PhaseId.DISCOVER
    assert result.phases[2].collected.state is CollectionState.MEASURED

    cap_map = result.discover
    assert cap_map is not None
    assert [c.bc_id for c in cap_map.capabilities] == ["BC-001"]
    assert cap_map.capabilities[0].name == "payment"
    assert cap_map.attribution.coverage.state is CollectionState.MEASURED
    assert cap_map.decomposition.collected.state is CollectionState.MEASURED
    assert cap_map.decomposition.by_capability["BC-001"] == 2
    assert cap_map.ownership.collected.state is CollectionState.MEASURED
    assert next(e for e in cap_map.ownership.entities
                if e.entity == "payment").owner == "BC-001"
    assert cap_map.blueprint is not None
    assert cap_map.blueprint.collected.state is CollectionState.MEASURED
    assert cap_map.domain_model is not None
    assert cap_map.domain_model.collected.state is CollectionState.MEASURED
    assert next(e for e in cap_map.domain_model.entities
                if e.entity == "payment").owner == "BC-001"


async def test_a_second_assessment_of_the_same_tree_hits_the_memo(
        assessed_repo, tmp_path, monkeypatch):
    """DD10 end-to-end: run 1 populates the discover memo; run 2 loads it
    without re-running disposition, lock or finalize.

    Proved by asserting the SQLite registry version did not increment --
    discover_lock was never called.
    """
    repo_dir, sha = assessed_repo
    db = str(tmp_path / "board.sqlite3")
    monkeypatch.setenv("SDLC_BOARD_DB", db)

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts):
            # Run 1: cold cache.
            h1 = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme",
                                propose_discover=False),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            r1 = await h1.result()
            assert r1.discover is not None

            store = BoardIdentityStore()
            try:
                v1 = store.registry_version("acme")
            finally:
                store.close()
            assert v1 == 1

            # Run 2: hits discover_memo_store's entry.
            h2 = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme",
                                propose_discover=False),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            r2 = await h2.result()
            assert r2.discover is not None

            # Byte-identical payload served from the memo.
            assert (r2.discover.model_dump_json()
                    == r1.discover.model_dump_json())

            store = BoardIdentityStore()
            try:
                v2 = store.registry_version("acme")
            finally:
                store.close()
            # No lock run: SQLite registry version is untouched.
            assert v2 == v1


async def test_discover_proposer_judgment_and_verification(
        assessed_repo, tmp_path, monkeypatch):
    """When t_discover is active, proposer's proposal runs through verify_discover_refs
    and shapes the map."""
    repo_dir, sha = assessed_repo
    db = str(tmp_path / "board.sqlite3")
    monkeypatch.setenv("SDLC_BOARD_DB", db)

    from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
    from temporalio.contrib.pydantic import pydantic_data_converter
    from tests.fakes.fake_agents import fake_agent_activities
    from sdlc.assessment.discover.map import (
        DiscoverAction, DiscoverProposal, ProposedDisposition,
    )

    from sdlc.assessment.scan.models import EvidenceRef

    canned = DiscoverProposal(
        dispositions=(
            ProposedDisposition(
                candidate_id="C-01",
                action=DiscoverAction.CONFIRM,
                rationale="Core payment processing domain logic",
                evidence=(EvidenceRef(path="payments/api.py", lines="5"),),
                quote="def charge(): pass",
            ),
        ),
    )

    agent_acts = fake_agent_activities([
        ("discover_agent", DiscoverProposal, canned),
    ])

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs, *agent_acts,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts,
                          plugins=[PydanticAIPlugin()]):
            h = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme"),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            res = await h.result()

    assert res.discover is not None
    assert res.discover.total_references == 2
    assert res.discover.capabilities[0].disposition.rationale == "Core payment processing domain logic"
    assert res.discover.capabilities[0].disposition.evidence == (EvidenceRef(path="payments/api.py", lines="5"),)


async def test_discover_proposer_trips_guard_fails_closed(
        assessed_repo, tmp_path, monkeypatch):
    """When the proposer cites non-existent files or wrong quotes exceeding threshold,
    the citation guard trips and the discover phase reports not_collected."""
    repo_dir, sha = assessed_repo
    db = str(tmp_path / "board.sqlite3")
    monkeypatch.setenv("SDLC_BOARD_DB", db)

    from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
    from temporalio.contrib.pydantic import pydantic_data_converter
    from tests.fakes.fake_agents import fake_agent_activities
    from sdlc.assessment.scan.models import EvidenceRef
    from sdlc.assessment.discover.map import (
        DiscoverAction, DiscoverProposal, ProposedDisposition,
    )

    canned = DiscoverProposal(
        dispositions=(
            ProposedDisposition(
                candidate_id="C-01",
                action=DiscoverAction.CONFIRM,
                rationale="Core payment processing domain logic",
                evidence=(EvidenceRef(path="nonexistent.py", lines="10"),),
                quote="def fake(): pass",
            ),
        ),
    )

    agent_acts = fake_agent_activities([
        ("discover_agent", DiscoverProposal, canned),
    ])

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs, *agent_acts,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts,
                          plugins=[PydanticAIPlugin()]):
            h = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme"),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            res = await h.result()

    assert res.discover is None
    discover_phase = next(p for p in res.phases if p.phase is PhaseId.DISCOVER)
    assert discover_phase.collected.state is CollectionState.NOT_COLLECTED
    assert "fabrication rate" in discover_phase.collected.reason


async def test_discover_proposer_exception_fails_closed(
        assessed_repo, tmp_path, monkeypatch):
    """When the discover proposer agent raises an error, the phase fails closed
    (not_collected) rather than quietly laundering into baseline or caching."""
    repo_dir, sha = assessed_repo
    db = str(tmp_path / "board.sqlite3")
    monkeypatch.setenv("SDLC_BOARD_DB", db)

    from datetime import timedelta
    from pydantic_ai import Agent
    from pydantic_ai.durable_exec.temporal import PydanticAIPlugin, TemporalAgent
    from pydantic_ai.models.function import FunctionModel
    from temporalio.common import RetryPolicy
    from temporalio.contrib.pydantic import pydantic_data_converter
    from temporalio.exceptions import ApplicationError
    from temporalio.workflow import ActivityConfig
    from sdlc.assessment.discover.map import DiscoverProposal

    async def _failing_model(messages, info):
        raise ApplicationError("LLM service unavailable", non_retryable=True)

    agent = Agent(
        FunctionModel(_failing_model),
        name="discover_agent",
        output_type=DiscoverProposal,
    )
    ta = TemporalAgent(
        agent,
        activity_config=ActivityConfig(
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        ),
    )
    agent_acts = ta.temporal_activities

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs, *agent_acts,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts,
                          plugins=[PydanticAIPlugin()]):
            h = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme"),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            res = await h.result()

    assert res.discover is None
    discover_phase = next(p for p in res.phases if p.phase is PhaseId.DISCOVER)
    assert discover_phase.collected.state is CollectionState.NOT_COLLECTED
    assert "discover proposer failed" in discover_phase.collected.reason


async def test_assess_phase_measures_with_no_model_registered(
        assessed_repo, tmp_path, monkeypatch):
    """E-49 plan 1: the deterministic score is a live phase, not a stub.

    No risk proposer exists yet, and the phase must still measure -- that is
    what makes plan 1 a defensible increment on its own.
    """
    repo_dir, sha = assessed_repo
    db = str(tmp_path / "board.sqlite3")
    monkeypatch.setenv("SDLC_BOARD_DB", db)

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts):
            h = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme",
                                propose_discover=False),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await h.result()

    row = next(p for p in result.phases if p.phase is PhaseId.ASSESS)
    assert row.collected.state is CollectionState.MEASURED
    assert result.risk is not None
    assert result.terminal_status == PARTIAL

    # RD3's headline consequence, asserted end to end rather than only in
    # the unit tests: with defect density and change velocity unsourced, the
    # unified composite is partial on every run.
    for cap in result.risk.capabilities:
        assert cap.qa.is_partial is True
        assert cap.unified.value.state is CollectionState.NOT_COLLECTED


async def test_risk_proposer_judgment_reaches_the_map(
        assessed_repo, tmp_path, monkeypatch):
    """RD1 end to end: the proposer dispositions rows code produced, and the
    composites it never touched come through unchanged."""
    repo_dir, sha = assessed_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))

    from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
    from temporalio.contrib.pydantic import pydantic_data_converter
    from tests.fakes.fake_agents import fake_agent_activities
    from sdlc.assessment.risk.models import (
        ProposedThreat, RiskProposal, RiskSource, StrideCategory,
    )
    from sdlc.assessment.activities import (
        risk_memo_load, risk_memo_store, verify_risk_refs,
    )
    from sdlc.assessment.discover.map import (
        DiscoverAction, DiscoverProposal, ProposedDisposition,
    )
    from sdlc.assessment.scan.models import EvidenceRef
    from sdlc.measurement import CollectionState

    discover_canned = DiscoverProposal(dispositions=(
        ProposedDisposition(
            candidate_id="C-01", action=DiscoverAction.CONFIRM,
            rationale="Core payment processing domain logic",
            evidence=(EvidenceRef(path="payments/api.py", lines="5"),),
            quote="def charge(): pass"),))

    # No evidence: an unevidenced row is accepted (it fabricates nothing),
    # which keeps this case about JUDGMENT rather than about citations.
    risk_canned = RiskProposal(threats=[
        ProposedThreat(bc_id="BC-001", category=StrideCategory.SPOOFING,
                       applicable=True,
                       rationale="the charge route has no session check")])

    agent_acts = fake_agent_activities([
        ("discover_agent", DiscoverProposal, discover_canned),
        ("risk_agent", RiskProposal, risk_canned),
    ])

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs, *agent_acts,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts,
                          plugins=[PydanticAIPlugin()]):
            h = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme"),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            res = await h.result()

    row = next(p for p in res.phases if p.phase is PhaseId.ASSESS)
    assert row.collected.state is CollectionState.MEASURED
    assert res.risk is not None
    assert res.risk.judgment.state is CollectionState.MEASURED
    cap = next(c for c in res.risk.capabilities if c.bc_id == "BC-001")
    spoofing = next(t for t in cap.threats
                    if t.category is StrideCategory.SPOOFING)
    assert spoofing.applicable is True
    assert spoofing.source is RiskSource.PROPOSER
    # RD7: the other five categories were never judged and say so.
    assert sum(1 for t in cap.threats if t.source is RiskSource.BASELINE) == 5


async def test_the_phase_is_measured_with_no_risk_proposer(
        assessed_repo, tmp_path, monkeypatch):
    """RD7: no folder, no model call, and a phase that is still MEASURED --
    with the judgment layer reporting not_collected rather than absent."""
    repo_dir, sha = assessed_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))

    from temporalio.contrib.pydantic import pydantic_data_converter
    from sdlc.assessment.activities import (
        risk_memo_load, risk_memo_store, verify_risk_refs,
    )
    from sdlc.measurement import CollectionState

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts):
            h = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme",
                                propose_discover=False, propose_risk=False),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            res = await h.result()

    row = next(p for p in res.phases if p.phase is PhaseId.ASSESS)
    assert row.collected.state is CollectionState.MEASURED
    assert res.risk is not None
    assert res.risk.judgment.state is CollectionState.NOT_COLLECTED
    assert "no risk proposer ran" in res.risk.judgment.reason


async def test_the_system_view_measures_with_no_model_registered(
        assessed_repo, tmp_path, monkeypatch):
    """E-49 plan 3: the two computed families and the two candidate lists are
    deterministic, so the system view is live with no proposer at all.

    A family that could not be computed reports not_collected with a reason;
    none of the four may be silently absent.
    """
    repo_dir, sha = assessed_repo
    db = str(tmp_path / "board.sqlite3")
    monkeypatch.setenv("SDLC_BOARD_DB", db)

    from sdlc.assessment.risk.models import SYSTEM_FAMILIES

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    from sdlc.assessment.activities import assessment_resolve_tree

    acts = [real_pin, fake_baseline, fake_scaffold, fake_probe,
            fake_secrets, fake_misconfig, fake_outliers, fake_deps,
            assessment_resolve_tree, *SCAN_ACTS,
            discover_context, discover_lock, discover_finalize,
            discover_memo_load, discover_memo_store,
            load_blueprint, verify_discover_refs,
            assess_risk, risk_memo_load, risk_memo_store, verify_risk_refs]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=WORKFLOWS, activities=acts):
            h = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir=repo_dir, project_key="acme",
                                propose_discover=False, propose_risk=False),
                id=f"assess-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await h.result()

    row = next(p for p in result.phases if p.phase is PhaseId.ASSESS)
    assert row.collected.state is CollectionState.MEASURED
    assert result.risk is not None

    system = result.risk.system
    for family in SYSTEM_FAMILIES:
        state = system.collected_of(family)
        assert state.state in (CollectionState.MEASURED,
                               CollectionState.NOT_COLLECTED), family
        if state.state is CollectionState.NOT_COLLECTED:
            assert state.reason.strip(), (
                f"{family} did not collect and gave no reason")
        else:
            # A MEASURED family's rows are the artifact's; an uncollected one
            # carries none (SystemRisk._unmeasured_carries_no_payload).
            assert isinstance(system.rows_of(family), tuple)

    # RD7 unchanged by plan 3: no proposer means no judgment, and the
    # deterministic families still measured.
    assert result.risk.judgment.state is CollectionState.NOT_COLLECTED





