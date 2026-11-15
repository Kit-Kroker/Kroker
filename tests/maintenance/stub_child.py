"""Stubbed ``GraphWorkflow``-compatible repair child (023b T003, plan risk 3).

Registered in the test worker under the REAL child wire name
(``GraphWorkflow``), so the maintenance loop's start path needs no fork
and the wire contract is exercised verbatim. The stub is scripted by the
``IdeaBrief.title`` prefix:

====================  =====================================================
``fix:``              commit the seeded fault's fix on the integration
                      branch, then park at the merge gate
``nofix:``            commit a non-fix (an unrelated file), park at merge
``empty:``            commit nothing, park at merge (head == base)
``fail:``             fail with a retryable-looking ApplicationError
``configfail:``       fail with a NON-retryable ApplicationError
``hang:``             never park; sleep forever (non-blocking/timeout tests)
``squash:``           prefix (``squash:fix:``): on approve, publishes a
                      SQUASH commit on the default branch instead of a
                      fast-forward, so the child head is NOT an ancestor
====================  =====================================================

Everything about the merge gate is the REAL mechanics: the gate opens
through the inherited ``GateHost._gate`` and ``pending_decisions`` /
``submit_gate_decision`` are inherited verbatim — first decision for
(gate, round) wins (plan risk 3). The branch itself is cut through the
real ``setup_integration_branch`` activity. On approve the stub
publishes the integration head onto the default branch and returns
``merged-not-deployed:stub``; on reject it returns ``rejected:merge``.
``run_state()`` answers with the real ``RunState`` shape (run_id, status).

No model or harness spend happens anywhere in this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from sdlc.core.models import (
        GateConfig,
        GateOutcome,
        GatePolicy,
        GateSettings,
        RunState,
        TimeoutAction,
    )
    from sdlc.vcs.integration import IntegrationInput, setup_integration_branch
    from sdlc.workflows.gates import GateHost
    from sdlc.workflows.models import GraphRunInput

#: The stub's git side effects run as activities (never in workflow code).
STUB_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=2),
)

#: The merge gate settings the stub parks on: HARD + HOLD, i.e. exactly the
#: pipeline's merge shape (core/models.py PipelineConfig.gates default) —
#: it waits for a decision forever, visible in pending_decisions.
STUB_MERGE_GATES = GateSettings(
    gates={"merge": GateConfig(policy=GatePolicy.HARD, on_timeout=TimeoutAction.HOLD)},
    gate_timeout_hours=24,
)


@dataclass
class StubCommitInput:
    """Commit the script's change on the integration worktree."""

    worktree_path: str
    script: str  # "fix" | "nofix"


@dataclass
class StubPublishInput:
    """Publish the integration head onto the default branch (approve path)."""

    repo_path: str
    integration_head: str
    squash: bool


@activity.defn
async def stub_commit_on_integration(inp: StubCommitInput) -> str:
    """``fix:``/``nofix:`` body. Returns the integration head after the commit."""
    from pathlib import Path

    from .conftest import fix_commit, head_sha, nonfix_commit, seeded_findings

    wt = Path(inp.worktree_path)
    if inp.script == "fix":
        for finding in seeded_findings(wt):
            fix_commit(wt, finding)
    else:
        nonfix_commit(wt)
    return head_sha(wt)


@activity.defn
async def stub_publish(inp: StubPublishInput) -> str:
    """Approve path: fast-forward the default branch to the integration head,
    or (``squash:``) land a squash commit with no child ancestry. Returns the
    default branch's new head."""
    from pathlib import Path

    from .conftest import git

    repo = Path(inp.repo_path)
    if inp.squash:
        tree = git(repo, "rev-parse", f"{inp.integration_head}^{{tree}}").strip()
        parent = git(repo, "rev-parse", "HEAD").strip()
        squashed = git(
            repo,
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            f"squash of {inp.integration_head[:8]} (no ancestry)",
        ).strip()
        git(repo, "merge", "--ff-only", squashed)
        return git(repo, "rev-parse", "HEAD").strip()
    git(repo, "merge", "--ff-only", inp.integration_head)
    return git(repo, "rev-parse", "HEAD").strip()


STUB_ACTIVITIES = [stub_commit_on_integration, stub_publish]


@workflow.defn(name="GraphWorkflow")
class StubRepairChild(GateHost):
    """The repair child the 023b workflow tier runs against."""

    def __init__(self) -> None:
        super().__init__()
        self._title = ""
        self._mode = ""
        self._repo_url = ""
        self._started_at = None
        self._result = ""

    @workflow.run
    async def run(self, run_input: GraphRunInput) -> str:
        title = run_input.idea.title
        squash = title.startswith("squash:")
        if squash:
            title = title[len("squash:") :]
        script = title.split(":", 1)[0]
        self._title = run_input.idea.title
        self._mode = str(run_input.idea.mode.value)
        self._repo_url = run_input.idea.repo_url or ""
        self._started_at = workflow.now()
        run_id = workflow.info().workflow_id

        if script == "hang":
            while True:  # never parks: the loop's timeout_step is what ends it
                await workflow.sleep(timedelta(hours=1))
        if script == "configfail":
            raise ApplicationError(
                "seeded configuration failure: the graph config is invalid",
                non_retryable=True,
            )
        if script == "fail":
            raise ApplicationError("seeded failure")

        handle = await workflow.execute_activity(
            setup_integration_branch,
            IntegrationInput(
                repo_path=run_input.idea.repo_url or "",
                run_id=run_id,
                base_branch=run_input.idea.base_branch,
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        integration_head = handle.head_sha
        if script in ("fix", "nofix"):
            integration_head = await workflow.execute_activity(
                stub_commit_on_integration,
                StubCommitInput(worktree_path=handle.worktree_path, script=script),
                **STUB_ACT,
            )

        # Park at the REAL merge gate. On approve publish; on reject stop.
        decision = await self._gate("merge", STUB_MERGE_GATES)
        if decision.outcome is GateOutcome.APPROVE:
            await workflow.execute_activity(
                stub_publish,
                StubPublishInput(
                    repo_path=run_input.idea.repo_url or "",
                    integration_head=integration_head,
                    squash=squash,
                ),
                **STUB_ACT,
            )
            self._result = "merged-not-deployed:stub"
        else:
            self._result = "rejected:merge"
        return self._result

    @workflow.query
    def run_state(self) -> RunState | None:
        """The probe's query target: run_id (the child id) and status, in the
        real RunState shape."""
        return RunState(
            run_id=workflow.info().workflow_id,
            title=self._title,
            repo_url=self._repo_url or None,
            mode=self._mode,
            status=getattr(self, "_status", "starting"),
            started_at=self._started_at or workflow.now(),
        )
