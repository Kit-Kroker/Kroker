"""Scripted stand-ins for everything the dry run must not really do.

Each fake carries the PRODUCTION activity name, so Temporal dispatches the
workflow's call to it when only these are registered on the demo worker.
None of them opens a file, spawns a process or reaches the network.

tests/fakes/ holds the test suite's own copies of the same seams; those are
scripted per test (failures, recorders, staggering) and stay there. This
module is the one fixed happy path the shipped command runs.
tests/test_demo.py pins that every name below is one the production worker
registers, so a renamed activity fails a fast test rather than a demo.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from temporalio import activity

from ..agents.roles import AGENT_ACTIVITY_CONFIG
from ..artifacts.retention import RetentionInput
from ..board.activities import (
    AttachEvidenceInput,
    PublishArtifactInput,
    PublishArtifactResult,
    SetTaskStatusInput,
    SyncPlanTasksInput,
)
from ..context.delta import DELTA_CHECK
from ..context.models import RepoObservation
from ..core.models import ArtifactRef
from ..deploy.activities import (
    ApplyResult,
    CurrentVersionResult,
    DeployActivityInput,
    RollbackInput,
    SmokeCheckInput,
    SmokeCheckOutput,
)
from ..gate import CheckClass, CheckResult, build_check
from ..harness.models import HarnessRunResult
from ..measurement import CollectionState, Measurement
from ..notify.contract import NotifyInput, Results
from ..observability.activities import export_run_artifacts
from ..pricing import price_usage
from ..stages.code.activities import CodingTaskInput
from ..stages.context.activities import DeltaCheckInput, RepoProbeInput
from ..stages.deploy.models import SmokeCheckResult, SmokeState
from ..stages.merge.activities import (
    CoverageInput,
    IntegrationChecks,
    IntegrationChecksInput,
    PROpenInput,
    evaluate_gate,
)
from ..stages.merge.models import CoverageReport
from ..stages.qa.activities import LintInput, QAInput, ScopedSecurityScanInput
from ..stages.qa.models import QAReport, ScopedSecurityReport
from ..vcs import (
    BaseWorktree,
    BaseWorktreeInput,
    DiffInput,
    IntegrationHandle,
    IntegrationInput,
    MergeInput,
    MergeResult,
    WorktreeHandle,
    WorktreeInput,
)

# ---- proposer agents -----------------------------------------------------------


def scripted_agent(name: str, output_type: type, value: BaseModel) -> Agent:
    """A durable agent whose model always answers `value`.

    The ResolveModelId is what keeps the run off the network: the
    workflow-side agent is the real registry agent, whose model is a
    provider string that crosses the wire and would be rebuilt into a real
    provider client inside the activity. The resolver answers every arriving
    model id with the TestModel instead. `call_tools=[]` stops TestModel
    from auto-calling tools the real agent advertises and this one lacks.
    """
    payload = value.model_dump(mode="json")

    def _resolve(ctx: Any, model_id: str | None) -> TestModel:
        return TestModel(custom_output_args=payload, call_tools=[], model_name=model_id or "test")

    return Agent(
        TestModel(custom_output_args=payload, call_tools=[]),
        name=name,
        output_type=output_type,
        capabilities=[
            TemporalDurability(
                activity_config=AGENT_ACTIVITY_CONFIG,
                model_activity_config={"heartbeat_timeout": None},
            ),
            ResolveModelId(_resolve),
        ],
    )


def scripted_agent_activities(specs: list[tuple[str, type, BaseModel]]) -> list[Callable[..., Any]]:
    activities: list[Callable[..., Any]] = []
    for name, output_type, value in specs:
        bound = TemporalDurability.from_agent(scripted_agent(name, output_type, value))
        assert bound is not None, name  # attached in scripted_agent
        activities.extend(bound.temporal_activities)
    return activities


# ---- git, harness, QA ----------------------------------------------------------


@activity.defn(name="classify_repo")
async def classify_repo(inp: RepoProbeInput) -> RepoObservation:
    return RepoObservation(
        is_git_repo=True, base_branch_resolves=True, commit_sha="deadbeef" * 5, source_file_count=10
    )


@activity.defn(name="check_brownfield_delta")
async def check_brownfield_delta(inp: DeltaCheckInput) -> CheckResult:
    return build_check(DELTA_CHECK, True, CheckClass.ABSOLUTE, "all resolve (demo)")


@activity.defn(name="setup_integration_branch")
async def setup_integration_branch(inp: IntegrationInput) -> IntegrationHandle:
    return IntegrationHandle(head_sha="deadbeef", worktree_path="/demo/integration")


@activity.defn(name="prepare_base_worktree")
async def prepare_base_worktree(inp: BaseWorktreeInput) -> BaseWorktree:
    return BaseWorktree(path="/demo/base")


@activity.defn(name="create_worktree")
async def create_worktree(inp: WorktreeInput) -> WorktreeHandle:
    return WorktreeHandle(
        path=f"/demo/worktrees/{inp.task_id}",
        branch=f"sdlc/{inp.run_id}/{inp.task_id}",
        branch_point="deadbeef",
    )


@activity.defn(name="run_coding_task")
async def run_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    return HarnessRunResult(
        harness=inp.harness,
        session_id="demo-session",
        exit_code=0,
        summary="implemented (scripted: no coding CLI was run)",
        commit_sha="cafe1234",
        input_tokens=1000,
        output_tokens=200,
        context_window=200000,
    )


@activity.defn(name="get_task_diff")
async def get_task_diff(inp: DiffInput) -> dict:
    return {
        "stat": " app/health.py | 6 ++++++",
        "patch": "diff --git a/app/health.py b/app/health.py\n+ok\n",
        "files": ["app/health.py"],
        "renames": [],
    }


@activity.defn(name="run_test_suite")
async def run_test_suite(inp: QAInput) -> QAReport:
    return QAReport(tests_passed=True)


@activity.defn(name="run_lint")
async def run_lint(inp: LintInput) -> tuple[bool, str]:
    return True, "clean"


@activity.defn(name="scoped_security_scan")
async def scoped_security_scan(inp: ScopedSecurityScanInput) -> ScopedSecurityReport:
    return ScopedSecurityReport(state=CollectionState.MEASURED)


@activity.defn(name="merge_into_integration")
async def merge_into_integration(inp: MergeInput) -> MergeResult:
    return MergeResult(merged=True, conflict=False, integration_head="feed0001")


@activity.defn(name="measure_coverage")
async def measure_coverage(inp: CoverageInput) -> CoverageReport:
    return CoverageReport(coverage=Measurement.not_collected("demo: unmeasured"))


@activity.defn(name="run_integration_checks")
async def run_integration_checks(inp: IntegrationChecksInput) -> IntegrationChecks:
    # No toolchain: the workflow takes its no-adapter fallback (per-task
    # aggregate + run_lint), which never needs a real working tree.
    return IntegrationChecks(toolchain=None)


@activity.defn(name="open_pull_request")
async def open_pull_request(inp: PROpenInput) -> str:
    return "https://example.invalid/demo/pull/1"


@activity.defn(name="apply_session_retention")
async def apply_session_retention(inp: RetentionInput) -> str:
    return "kept:0"


# ---- board ---------------------------------------------------------------------
# Scripted rather than real: the real ones would add a demo project to the
# operator's board database.


@activity.defn(name="publish_artifact_version")
async def publish_artifact_version(inp: PublishArtifactInput) -> PublishArtifactResult:
    # version_id must be a non-None int or the task loop skips its board writes.
    return PublishArtifactResult(
        ref=ArtifactRef(kind="board_artifact", uri="file:///demo/board", sha256="0" * 64),
        version_id=1,
    )


@activity.defn(name="sync_plan_tasks")
async def sync_plan_tasks(inp: SyncPlanTasksInput) -> int:
    return len(inp.tasks)


@activity.defn(name="set_task_authoritative")
async def set_task_authoritative(inp: SetTaskStatusInput) -> None:
    return None


@activity.defn(name="attach_task_evidence")
async def attach_task_evidence(inp: AttachEvidenceInput) -> ArtifactRef:
    return ArtifactRef(kind="board_evidence", uri="file:///demo/evidence", sha256="0" * 64)


# ---- notify, deploy ------------------------------------------------------------


@activity.defn(name="notify")
async def notify(inp: NotifyInput) -> Results:
    # The real one delivers to the routes in policy/notifications.yaml; a
    # dry run must not page anyone.
    return Results()


@activity.defn(name="deploy_current_version")
async def deploy_current_version(inp: DeployActivityInput) -> CurrentVersionResult:
    return CurrentVersionResult(version="v0")


@activity.defn(name="deploy_apply")
async def deploy_apply(inp: DeployActivityInput) -> ApplyResult:
    return ApplyResult(endpoint="http://demo.invalid")


@activity.defn(name="smoke_check")
async def smoke_check(inp: SmokeCheckInput) -> SmokeCheckOutput:
    return SmokeCheckOutput(
        results=[SmokeCheckResult(name="liveness", state=SmokeState.PASSED, detail="")]
    )


@activity.defn(name="deploy_rollback")
async def deploy_rollback(inp: RollbackInput) -> None:
    return None


SCRIPTED: list[Callable[..., Any]] = [
    classify_repo,
    check_brownfield_delta,
    setup_integration_branch,
    prepare_base_worktree,
    create_worktree,
    run_coding_task,
    get_task_diff,
    run_test_suite,
    run_lint,
    scoped_security_scan,
    merge_into_integration,
    measure_coverage,
    run_integration_checks,
    open_pull_request,
    apply_session_retention,
    publish_artifact_version,
    sync_plan_tasks,
    set_task_authoritative,
    attach_task_evidence,
    notify,
    deploy_current_version,
    deploy_apply,
    smoke_check,
    deploy_rollback,
]

# Production activities the dry run keeps: pure code, or a write under the
# export root that is the point of the run.
REAL: list[Callable[..., Any]] = [evaluate_gate, price_usage, export_run_artifacts]


def demo_activities(specs: list[tuple[str, type, BaseModel]]) -> list[Callable[..., Any]]:
    return [*REAL, *SCRIPTED, *scripted_agent_activities(specs)]
