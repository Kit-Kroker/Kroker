"""Same-named fakes for every git/subprocess activity the FeatureWorkflow
calls. Registered on the e2e worker INSTEAD of the production activities, so
the run touches no real git, subprocess, or network. Names must match the
production activity names for Temporal dispatch."""
from __future__ import annotations

from temporalio import activity

from sdlc.activities import (
    CodingTaskInput, CoverageInput, DeployInput, DiffInput, IntegrationChecks,
    IntegrationChecksInput, IntegrationHandle,
    IntegrationInput, LintInput, MergeInput, MergeResult, PROpenInput,
    QAInput, SecurityScanInput, WorktreeHandle, WorktreeInput,
)
from sdlc.models import (
    CoverageReport, HarnessRunResult, QAReport, SecurityReport,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.pricing import price_usage


@activity.defn(name="setup_integration_branch")
async def fake_setup_integration_branch(
        inp: IntegrationInput) -> IntegrationHandle:
    return IntegrationHandle(head_sha="deadbeef", worktree_path="/fake/integ")


@activity.defn(name="create_worktree")
async def fake_create_worktree(inp: WorktreeInput) -> WorktreeHandle:
    return WorktreeHandle(path=f"/fake/wt/{inp.task_id}",
                          branch=f"sdlc/{inp.run_id}/{inp.task_id}",
                          branch_point="deadbeef")


@activity.defn(name="run_coding_task")
async def fake_run_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    return HarnessRunResult(
        harness=inp.harness, session_id="s1", exit_code=0,
        summary="implemented", commit_sha="cafe1234",
        input_tokens=1000, output_tokens=200, context_window=200000)


@activity.defn(name="get_task_diff")
async def fake_get_task_diff(inp: DiffInput) -> dict:
    return {"stat": " app/main.py | 3 +++",
            "patch": "diff --git a/app/main.py b/app/main.py\n+ok\n",
            "files": ["app/main.py"]}


@activity.defn(name="run_test_suite")
async def fake_run_test_suite(inp: QAInput) -> QAReport:
    return QAReport(tests_passed=True)


@activity.defn(name="run_lint")
async def fake_run_lint(inp: LintInput) -> tuple[bool, str]:
    return True, "clean"


@activity.defn(name="merge_into_integration")
async def fake_merge_into_integration(inp: MergeInput) -> MergeResult:
    return MergeResult(merged=True, conflict=False, integration_head="feed0001")


@activity.defn(name="open_pull_request")
async def fake_open_pull_request(inp: PROpenInput) -> str:
    return "https://example.test/pr/1"


@activity.defn(name="deploy")
async def fake_deploy(inp: DeployInput) -> str:
    return "deploy ok"


@activity.defn(name="security_scan")
async def fake_security_scan(inp: SecurityScanInput) -> SecurityReport:
    return SecurityReport(critical=0, findings=[],
                          state=CollectionState.MEASURED)


@activity.defn(name="measure_coverage")
async def fake_measure_coverage(inp: CoverageInput) -> CoverageReport:
    # No coverage artifact in this offline run -> not collected, check passes.
    return CoverageReport(coverage=Measurement.not_collected("fake: unmeasured"))


@activity.defn(name="run_integration_checks")
async def fake_run_integration_checks(
        inp: IntegrationChecksInput) -> IntegrationChecks:
    # Offline orchestration proof: no real toolchain is detected in the fake
    # worktree, so the workflow takes the no-adapter fallback (per-task
    # aggregate green + fake run_lint) — identical to the pre-E-30 path the
    # e2e suite was built around. Never touches a real subprocess.
    return IntegrationChecks(
        toolchain=None,
        qa=QAReport(tests_passed=False, issues=["fake: no adapter"]),
        lint_clean=True, lint_detail="fake: no adapter (not linted)")


GIT_FAKES = [
    fake_setup_integration_branch, fake_create_worktree, fake_run_coding_task,
    fake_get_task_diff, fake_run_test_suite, fake_run_lint,
    fake_merge_into_integration, fake_open_pull_request, fake_deploy,
    fake_security_scan, fake_measure_coverage, fake_run_integration_checks,
    price_usage,   # E-33: real activity — pure local table lookup, no network
]
