"""e2e-proposer-hang chaos edges: every way a proposer await can lose its
bound, and the stale state that masks the loss.

Two mechanisms interact in the reported hang (2026-09-20), and both are
load-bearing for these tests:

1. THE UNBOUNDED AWAIT. t_discover/t_risk run under AGENT_ACTIVITY_CONFIG,
   which sets no retry policy, so Temporal's default UNLIMITED retries apply.
   An activity no worker serves (the reported scenario) or one that fails
   retryably can never exhaust, so the workflow-side await never resolves and
   the assessment never completes. roles.py's E-85 comment names this exact
   class for the clarify fan-out; the proposers never got the bound.

2. THE MACHINE-GLOBAL MEMO. memoization/cache.py roots at
   %TEMP%/sdlc/memo_cache unless SDLC_MEMOIZATION_CACHE_ROOT is set, and the
   risk memo key is pure content (project|tree|map_digest|rules|prompt|model).
   The e2e harness builds a byte-identical repo for every test, so ANY
   earlier run of the risk-proposer scenario on the machine -- including from
   the primary checkout, hours ago -- leaves a judged map under the very key
   this test computes. _assess then HITS the memo and never awaits the risk
   proposer at all: workflow history shows no agent__risk_agent__* activity,
   no assess_risk, and a judgment=MEASURED that no run of this test made.
   The hang is therefore COLD-CACHE-ONLY (tier position #102: before the
   warming test ever runs), and a warm cache launders it into a pass.

Every test here isolates SDLC_MEMOIZATION_CACHE_ROOT to a per-test directory,
so the scenarios are deterministic on any machine, cold or warm. A test that
hangs is not a RED, so each result await is bounded with asyncio.wait_for;
today the bound fires and the test fails naming the await -- once the await
is bounded in production (finite retries or a schedule-to-close timeout, the
E-85 precedent), the failures exhaust into the fail-closed / degrade paths
these tests assert.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid

import pytest
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin, TemporalAgent
from pydantic_ai.models.function import FunctionModel
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.assessment.activities import (
    AssessmentTree,
    AssessmentTreeInput,
    assess_risk,
    discover_context,
    discover_finalize,
    discover_lock,
    discover_memo_load,
    discover_memo_store,
    load_blueprint,
    risk_memo_load,
    risk_memo_store,
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
    verify_discover_refs,
    verify_risk_refs,
)
from sdlc.assessment.discover.map import (
    DiscoverAction,
    DiscoverProposal,
    ProposedDisposition,
)
from sdlc.assessment.models import PHASE_ORDER, PhaseId
from sdlc.assessment.risk.models import (
    ProposedThreat,
    RiskProposal,
    StrideCategory,
)
from sdlc.assessment.scan.models import EvidenceRef
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.activities import (
    TriageDependencyInput,
    TriagePin,
    TriagePinInput,
    TriageProbeInput,
    TriageSignalInput,
)
from sdlc.triage.models import SignalResult
from sdlc.workflows.assessment import AssessmentInput, AssessmentWorkflow
from sdlc.workflows.triage import TriageWorkflow

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio, pytest.mark.timeout(300)]

TASK_QUEUE = "assess-chaos-test"

# Green runs of these scenarios complete in 16-36s each; a wedged await never
# moves, so 120s separates them with headroom without stalling the tier.
RESULT_BUDGET_S = 120.0

WORKFLOWS = [AssessmentWorkflow, TriageWorkflow]

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


def _ok(signal: str, version: int, metrics=None) -> SignalResult:
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
    # buildable=1.0 -> READY -> no readiness gate -> the shell self-completes.
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
async def fake_deps(inp: TriageDependencyInput) -> SignalResult:
    return _ok("dependencies", 1)


@activity.defn(name="assessment_resolve_tree")
async def fake_resolve_tree(inp: AssessmentTreeInput) -> AssessmentTree:
    # Overridden per test by the real resolver; unused activities are harmless.
    return AssessmentTree(tree_hash="t" * 40)


def _canned_discover_proposal() -> DiscoverProposal:
    """The same valid proposal the reported test feeds its fake proposer."""
    return DiscoverProposal(
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


def _canned_risk_proposal() -> RiskProposal:
    """The unevidenced row test_risk_proposer_judgment_reaches_the_map uses:
    accepted without citations, so the guard stays out of the way."""
    return RiskProposal(
        threats=[
            ProposedThreat(
                bc_id="BC-001",
                category=StrideCategory.SPOOFING,
                applicable=True,
                rationale="the charge route has no session check",
            )
        ]
    )


def _flaky_agent_activities(name: str, output_type: type) -> list:
    """A proposer whose model call raises RETRYABLY, under the PRODUCTION
    activity config -- AGENT_ACTIVITY_CONFIG verbatim, the very config whose
    missing retry bound is the defect under test. The sibling
    test_discover_proposer_exception_fails_closed opts OUT of this defect
    (its own ActivityConfig with maximum_attempts=1 and non_retryable=True);
    this fake opts IN, which is what makes the exhaustion contract testable.
    """

    async def _transient(messages, info):
        raise ApplicationError(f"{name} model transiently unavailable")

    ta = TemporalAgent(
        Agent(FunctionModel(_transient), name=name, output_type=output_type),
        activity_config=AGENT_ACTIVITY_CONFIG,
    )
    return ta.temporal_activities


def _acts(repo_sha: str, *extra: object) -> list:
    """The reported test's worker registration: fake triage, real
    scan/discover/risk deterministic activities, plus whatever proposer
    activities the scenario serves."""
    from sdlc.assessment.activities import assessment_resolve_tree

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=repo_sha, toolchain="python")

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
        discover_lock,
        discover_finalize,
        discover_memo_load,
        discover_memo_store,
        load_blueprint,
        verify_discover_refs,
        *extra,
        assess_risk,
        risk_memo_load,
        risk_memo_store,
        verify_risk_refs,
    ]


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
def assessed_repo(tmp_path, monkeypatch):
    """The e2e harness's deterministic repo, PLUS the isolation the harness
    lacks: a per-test memo cache root. Without it every run on the machine
    shares %TEMP%/sdlc/memo_cache and the scenarios below flip between wedge
    and memo-laundered pass depending on what ran earlier (see the module
    docstring, mechanism 2)."""
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
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "memo-cache"))
    return str(tmp_path), sha


async def _run(env, repo_dir: str) -> object:
    h = await env.client.start_workflow(
        AssessmentWorkflow.run,
        AssessmentInput(repo_dir=repo_dir, project_key="acme"),
        id=f"assess-{uuid.uuid4()}",
        task_queue=TASK_QUEUE,
    )
    # The bound is the point: a wedged proposer await must surface as THIS
    # test's bounded failure, never as a process-wide hang.
    return await asyncio.wait_for(h.result(), timeout=RESULT_BUDGET_S)


def _discover_row(res) -> object:
    return next(p for p in res.phases if p.phase is PhaseId.DISCOVER)


def _assess_row(res) -> object:
    return next(p for p in res.phases if p.phase is PhaseId.ASSESS)


async def test_a_degraded_run_leaves_no_memo_poison_for_a_healthy_rerun(
    assessed_repo, tmp_path, monkeypatch
):
    """Stale state across the failure: run 1 cannot reach the risk proposer
    (its activity is served by no worker -- the reported scenario), degrades
    fail-closed, and must NOT cache that judgment-free map under the
    proposer's memo key (P2-D3); run 2, whose worker DOES serve the proposer,
    must re-judge rather than inherit run 1's degradation.

    Today run 1 never completes (the unbounded await), so the bound fails
    this test at the first result. After the await is bounded: run 1
    exhausts into RD7's degrade, P2-D3 refuses the store, and run 2 judges.
    """
    repo_dir, sha = assessed_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))

    from tests.fakes.fake_agents import fake_agent_activities

    discover_acts = fake_agent_activities(
        [("discover_agent", DiscoverProposal, _canned_discover_proposal())]
    )
    healthy_acts = fake_agent_activities(
        [
            ("discover_agent", DiscoverProposal, _canned_discover_proposal()),
            ("risk_agent", RiskProposal, _canned_risk_proposal()),
        ]
    )

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        # Run 1: discover served, risk proposer served by NO worker.
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=_acts(sha, *discover_acts),
            plugins=[PydanticAIPlugin()],
        ):
            res1 = await _run(env, repo_dir)

        assert res1.discover is not None
        assert res1.discover.total_references == 2
        assert _assess_row(res1).collected.state is CollectionState.MEASURED
        assert res1.risk is not None
        assert res1.risk.judgment.state is CollectionState.NOT_COLLECTED
        assert "risk proposer" in res1.risk.judgment.reason
        assert "ran and failed" in res1.risk.judgment.reason

        # Run 2: identical inputs, proposer now served. A hit here would be
        # run 1's degradation cached under the proposer key -- P2-D3's exact
        # refusal -- surfacing as a stale NOT_COLLECTED judgment.
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=_acts(sha, *healthy_acts),
            plugins=[PydanticAIPlugin()],
        ):
            res2 = await _run(env, repo_dir)

    assert res2.discover is not None
    assert _assess_row(res2).collected.state is CollectionState.MEASURED
    assert res2.risk is not None
    assert res2.risk.judgment.state is CollectionState.MEASURED, (
        "run 2 inherited run 1's degraded judgment from the memo"
    )


@pytest.mark.timeout(420)
async def test_a_retryable_risk_proposer_failure_exhausts_and_degrades(
    assessed_repo, tmp_path, monkeypatch
):
    """Error path + reason boundary: a SERVED proposer whose model call fails
    RETRYABLY (the default classification -- the sibling exception test opts
    out with non_retryable=True) under the production activity config must
    exhaust its attempts and degrade with the 'ran and failed' sentence, NOT
    converge with the 'no risk proposer ran' sentence of the never-invoked
    path (unbuilt_signal vs failed_signal).

    Today AGENT_ACTIVITY_CONFIG sets no retry bound, so the failure retries
    forever and the bound fails this test. The E-85 precedent (finite
    maximum_attempts) turns it into the bounded exhaustion asserted here.
    """
    repo_dir, sha = assessed_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))

    from tests.fakes.fake_agents import fake_agent_activities

    agent_acts = fake_agent_activities(
        [("discover_agent", DiscoverProposal, _canned_discover_proposal())]
    )
    flaky_risk = _flaky_agent_activities("risk_agent", RiskProposal)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=_acts(sha, *agent_acts, *flaky_risk),
            plugins=[PydanticAIPlugin()],
        ):
            res = await _run(env, repo_dir)

    assert res.discover is not None
    assert res.discover.total_references == 2
    assert [p.phase for p in res.phases] == list(PHASE_ORDER)
    assert _assess_row(res).collected.state is CollectionState.MEASURED
    assert res.risk is not None
    assert res.risk.judgment.state is CollectionState.NOT_COLLECTED
    assert "ran and failed" in res.risk.judgment.reason
    assert "no risk proposer ran" not in res.risk.judgment.reason


async def test_a_retryable_discover_proposer_failure_fails_the_phase_closed(
    assessed_repo, tmp_path, monkeypatch
):
    """The discover-side twin, where failure semantics differ on purpose
    (RD7): dispositions ARE the map's content, so an exhausted discover
    proposer fails the PHASE closed instead of degrading a layer -- and the
    rest of the DAG still runs to a complete artifact.

    Today the unbounded retry wedges _discover's await; the bound fails this
    test. Bounded, it lands in the existing 'discover proposer failed' path.
    """
    repo_dir, sha = assessed_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))

    from tests.fakes.fake_agents import fake_agent_activities

    # The risk proposer is served and healthy: the wedge under test is
    # discover's await alone, and post-fix the risk phase is unreachable
    # (no map) rather than degraded.
    agent_acts = fake_agent_activities([("risk_agent", RiskProposal, _canned_risk_proposal())])
    flaky_discover = _flaky_agent_activities("discover_agent", DiscoverProposal)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=_acts(sha, *agent_acts, *flaky_discover),
            plugins=[PydanticAIPlugin()],
        ):
            res = await _run(env, repo_dir)

    assert res.discover is None
    discover_row = _discover_row(res)
    assert discover_row.collected.state is CollectionState.NOT_COLLECTED
    assert "discover proposer failed" in discover_row.collected.reason
    assert [p.phase for p in res.phases] == list(PHASE_ORDER)
    # No map means nothing to assess: the phase degrades with its own
    # sentence, and no risk artifact is conjured.
    assert _assess_row(res).collected.state is CollectionState.NOT_COLLECTED
    assert res.risk is None
