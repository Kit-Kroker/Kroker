"""Contract tests for ``start_repair_child`` (023b T009, RED).

Subject: ``sdlc.workflows.pipeline_child.start_repair_child(*, child_id, idea,
cfg, seeded, task_queue) -> Literal["started", "attached"]``, which sits
beside ``execute_pipeline_child`` (unchanged). Contracts: R1 (non-blocking
start, ABANDON, REJECT_DUPLICATE, no patch marker) and R3 (the child is cut
from the incident's commit).

The temporal tier imports ``start_repair_child`` only inside the throwaway
parent's ``run`` (deferred, passed through), so before T010 each temporal test
fails with a clean ``ImportError`` rather than a collection failure. The fast
tier runs without the function under test and records its own status.
"""

from __future__ import annotations

import asyncio
import subprocess

import pytest
import temporalio.workflow as _workflow
from pydantic import BaseModel
from temporalio import workflow
from temporalio.api.enums.v1 import EventType, ParentClosePolicy
from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment

from sdlc.converter import sdlc_data_converter

with _workflow.unsafe.imports_passed_through():
    # Mark THIS module pass-through so the workflow sandbox reuses the real
    # model classes instead of re-importing them (a sandbox-local IdeaBrief
    # fails pydantic's model_type check against the real GraphRunInput --
    # the same reason every src workflow module wraps its imports).
    from sdlc.core.models import IdeaBrief, PipelineConfig
    from sdlc.maintenance.models import RepairProposal
    from sdlc.tidyup.backlog import seeded_work_for
    from sdlc.vcs.integration import IntegrationInput, setup_integration_branch
    from sdlc.workflows.graph_catalog import build_run_input
    from sdlc.workflows.models import GraphRunInput
    from sdlc.workflows.tidyup import _default_fix_cfg
    from tests.maintenance.conftest import commit_env_file, env_file_findings, maint_worker

TASK_QUEUE = "t009-repair-child"
PARENT_ID = "t009-parent"
CHILD_ID = "maint-demo-abcd1234-inc1-a1"
IDENTITY = "secrets:env_file_tracked:.gitignore"
PATCH_ID = "e74-graph-child"


class RepairParentInput(BaseModel):
    idea: IdeaBrief
    cfg: PipelineConfig
    child_id: str
    task_queue: str


@workflow.defn(name="ThrowawayRepairParent")
class ThrowawayRepairParent:
    """Calls ``start_repair_child`` twice with the same id and returns
    ``"<first>/<second>"``. The import is deferred and passed through, so a
    missing function surfaces as an ImportError on the run, not at load."""

    @workflow.run
    async def run(self, inp: RepairParentInput) -> str:
        with workflow.unsafe.imports_passed_through():
            from sdlc.workflows.pipeline_child import start_repair_child

        first = await start_repair_child(
            child_id=inp.child_id,
            idea=inp.idea,
            cfg=inp.cfg,
            seeded=None,
            task_queue=inp.task_queue,
        )
        second = await start_repair_child(
            child_id=inp.child_id,
            idea=inp.idea,
            cfg=inp.cfg,
            seeded=None,
            task_queue=inp.task_queue,
        )
        return f"{first}/{second}"


def _idea(base: str, repo_url: str) -> IdeaBrief:
    return IdeaBrief(
        title="hang: never parks",
        description="the 023b repair child contract test",
        mode="brownfield",
        repo_url=repo_url,
        base_branch=base,
    )


async def _run_parent(env: WorkflowEnvironment, repo_dir) -> tuple[str, object]:
    """Run the throwaway parent to completion; return its result string and
    its handle (for history). The child is left running (ABANDON)."""
    base = commit_env_file(repo_dir)
    inp = RepairParentInput(
        idea=_idea(base, str(repo_dir)),
        cfg=_default_fix_cfg(),
        child_id=CHILD_ID,
        task_queue=TASK_QUEUE,
    )
    async with maint_worker(
        env,
        task_queue=TASK_QUEUE,
        proposal=RepairProposal(analysis="x", actions=[], self_confidence=0.9),
        extra_workflows=[ThrowawayRepairParent],
    ):
        handle = await env.client.start_workflow(
            ThrowawayRepairParent.run,
            inp,
            id=PARENT_ID,
            task_queue=TASK_QUEUE,
        )
        result = await asyncio.wait_for(handle.result(), timeout=60)
    return result, handle


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_start_returns_without_awaiting_the_child(repo_dir):
    """R1: the first start returns 'started' while the child is still RUNNING."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        result, _ = await _run_parent(env, repo_dir)
        first, _, _ = result.partition("/")
        assert first == "started"

        child = env.client.get_workflow_handle(CHILD_ID)
        desc = await child.describe()
        assert desc.status == WorkflowExecutionStatus.RUNNING, (
            f"start_repair_child awaited the child: status is {desc.status}"
        )


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_second_start_with_same_id_returns_attached(repo_dir):
    """R1: a second start of the same child id is 'attached', not an error."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        result, _ = await _run_parent(env, repo_dir)
        _, _, second = result.partition("/")
        assert second == "attached"


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_child_start_is_recorded_with_abandon(repo_dir):
    """R1: the child start in the parent's history uses ParentClosePolicy.ABANDON."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        _, handle = await _run_parent(env, repo_dir)
        history = await handle.fetch_history()
        starts = [
            ev
            for ev in history.events
            if ev.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED
        ]
        assert starts, "the parent recorded no child start"
        policies = {
            ev.start_child_workflow_execution_initiated_event_attributes.parent_close_policy
            for ev in starts
        }
        assert policies == {ParentClosePolicy.PARENT_CLOSE_POLICY_ABANDON}


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_no_deprecate_patch_marker_in_parent_history(repo_dir):
    """R1: start_repair_child adds no deprecate_patch marker (the e74 patch id
    must not appear in any recorded event of the parent's history)."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        _, handle = await _run_parent(env, repo_dir)
        history = await handle.fetch_history()
        markers = [
            ev for ev in history.events if ev.event_type == EventType.EVENT_TYPE_MARKER_RECORDED
        ]
        offenders = [ev.event_id for ev in markers if PATCH_ID.encode() in ev.SerializeToString()]
        assert offenders == [], f"patch marker {PATCH_ID!r} recorded in events {offenders}"


# ---------------------------------------------------------------- fast tier


def test_brownfield_run_input_accepts_a_sha_base_branch(repo_dir):
    """R3: a 40-hex sha base_branch builds a valid brownfield run input.

    This is expected to PASS at HEAD: intake does not reject a sha (no
    pure intake validator exists to refuse it)."""
    base = commit_env_file(repo_dir)
    assert len(base) == 40
    seeded = seeded_work_for(IDENTITY, env_file_findings()[1], 1)
    run_input = build_run_input(
        _idea(base, str(repo_dir)),
        _default_fix_cfg(),
        seeded,
    )
    assert isinstance(run_input, GraphRunInput)


@pytest.mark.asyncio
async def test_integration_branch_is_cut_from_the_sha(repo_dir, tmp_path, monkeypatch):
    """R3 fallback check: setup_integration_branch cuts sdlc/<run>/integration
    from the given sha, so the worktree HEAD is that sha.

    Expected to PASS at HEAD (this is the named R3 fallback's evidence)."""
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    base = commit_env_file(repo_dir)
    handle = await setup_integration_branch(
        IntegrationInput(
            repo_path=str(repo_dir),
            run_id=CHILD_ID,
            base_branch=base,
        )
    )
    assert handle.head_sha == base
    head = subprocess.run(
        ["git", "-C", handle.worktree_path, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == base


# ---------------------------------------------------------------- EDGE (023b T009, RED) -- qa-chaos
#
# Edge cases the happy half above does not reach. Each test imports
# ``start_repair_child`` inside the throwaway parent's run (deferred), so a
# missing function fails that test alone with an ImportError.

EDGE_TASK_QUEUE = "t009-repair-child-edge"
EDGE_CHILD_ID = "maint-demo-abcd1234-inc2-a1"
VERBATIM_CHILD_ID = "maint-demo-0badf00d-inc42-a7"


async def _edge_until(pred, timeout: float = 90.0, what: str = "condition") -> None:
    """Poll ``pred`` until true; local copy so the edge half owns its helpers."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await pred():
                return
        except Exception:  # noqa: BLE001 -- queries before the first task
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


@workflow.defn(name="ThrowawayEdgeStartOnceParent")
class EdgeStartOnceParent:
    """Calls ``start_repair_child`` once and returns its literal result."""

    @workflow.run
    async def run(self, inp: RepairParentInput) -> str:
        with workflow.unsafe.imports_passed_through():
            from sdlc.workflows.pipeline_child import start_repair_child

        return await start_repair_child(
            child_id=inp.child_id,
            idea=inp.idea,
            cfg=inp.cfg,
            seeded=None,
            task_queue=inp.task_queue,
        )


def _edge_idea(base: str, repo_url: str, title: str) -> IdeaBrief:
    return IdeaBrief(
        title=title,
        description="the 023b repair child edge test",
        mode="brownfield",
        repo_url=repo_url,
        base_branch=base,
    )


async def _run_edge_parent(env, repo_dir, *, base, child_id, title, parent_id):
    inp = RepairParentInput(
        idea=_edge_idea(base, str(repo_dir), title),
        cfg=_default_fix_cfg(),
        child_id=child_id,
        task_queue=EDGE_TASK_QUEUE,
    )
    handle = await env.client.start_workflow(
        EdgeStartOnceParent.run,
        inp,
        id=parent_id,
        task_queue=EDGE_TASK_QUEUE,
    )
    result = await asyncio.wait_for(handle.result(), timeout=60)
    return result, handle


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_start_with_the_id_of_a_completed_child_returns_attached_not_restart(
    repo_dir, monkeypatch, tmp_path
):
    """R1 edge: REJECT_DUPLICATE refuses a re-run of a COMPLETED child id. The
    mapped result is 'attached', and the completed run is not restarted."""
    from sdlc.core.models import GateDecision, GateOutcome
    from tests.maintenance.stub_child import StubRepairChild

    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with maint_worker(
            env,
            task_queue=EDGE_TASK_QUEUE,
            proposal=RepairProposal(analysis="x", actions=[], self_confidence=0.9),
            extra_workflows=[EdgeStartOnceParent],
        ):
            base = commit_env_file(repo_dir)
            first, _ = await _run_edge_parent(
                env,
                repo_dir,
                base=base,
                child_id=EDGE_CHILD_ID,
                title="nofix: completes once approved",
                parent_id="t009-edge-a-parent-1",
            )
            assert first == "started"

            child = env.client.get_workflow_handle(EDGE_CHILD_ID)

            async def _at_merge_gate():
                # pending_gate returns the status verbatim ("awaiting:<gate>").
                return await child.query(StubRepairChild.pending_gate) == "awaiting:merge"

            await _edge_until(_at_merge_gate, what="the merge gate to open")
            await child.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="merge",
                    round=1,
                    outcome=GateOutcome.APPROVE,
                    decided_by="human",
                ),
            )
            done = await asyncio.wait_for(child.result(), timeout=60)
            assert done == "merged-not-deployed:stub"
            run_before = (await child.describe()).run_id

            second, _ = await _run_edge_parent(
                env,
                repo_dir,
                base=base,
                child_id=EDGE_CHILD_ID,
                title="nofix: completes once approved",
                parent_id="t009-edge-a-parent-2",
            )
            assert second == "attached", (
                f"a completed child id must map to 'attached', got {second!r}"
            )
            assert (await child.describe()).run_id == run_before, (
                "the completed child was restarted under the same id"
            )


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_sha_base_branch_reaches_the_child_run_input_unchanged(repo_dir):
    """R3 edge: a 40-hex sha base_branch is passed through build_run_input
    without normalisation; the child's recorded start input carries it verbatim."""
    import json

    from sdlc.workflows.models import GraphRunInput

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with maint_worker(
            env,
            task_queue=EDGE_TASK_QUEUE,
            proposal=RepairProposal(analysis="x", actions=[], self_confidence=0.9),
            extra_workflows=[EdgeStartOnceParent],
        ):
            base = commit_env_file(repo_dir)
            assert len(base) == 40
            started, _ = await _run_edge_parent(
                env,
                repo_dir,
                base=base,
                child_id=EDGE_CHILD_ID,
                title="hang: never parks",
                parent_id="t009-edge-b-parent",
            )
            assert started == "started"

            history = await env.client.get_workflow_handle(EDGE_CHILD_ID).fetch_history()
            begun = next(
                ev
                for ev in history.events
                if ev.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED
            )
            payload = begun.workflow_execution_started_event_attributes.input.payloads[0]
            run_input = GraphRunInput.model_validate(json.loads(payload.data))
            assert run_input.idea.base_branch == base, (
                f"sha base_branch was normalised: {run_input.idea.base_branch!r}"
            )


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_child_id_is_used_verbatim_for_the_started_workflow(repo_dir):
    """R1 edge: the id passed to start_repair_child is the started child's
    workflow id, with no rewriting or prefixing."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with maint_worker(
            env,
            task_queue=EDGE_TASK_QUEUE,
            proposal=RepairProposal(analysis="x", actions=[], self_confidence=0.9),
            extra_workflows=[EdgeStartOnceParent],
        ):
            base = commit_env_file(repo_dir)
            started, parent = await _run_edge_parent(
                env,
                repo_dir,
                base=base,
                child_id=VERBATIM_CHILD_ID,
                title="hang: never parks",
                parent_id="t009-edge-c-parent",
            )
            assert started == "started"

            desc = await env.client.get_workflow_handle(VERBATIM_CHILD_ID).describe()
            assert desc.id == VERBATIM_CHILD_ID

            history = await parent.fetch_history()
            child_ids = [
                ev.start_child_workflow_execution_initiated_event_attributes.workflow_id
                for ev in history.events
                if ev.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED
            ]
            assert child_ids == [VERBATIM_CHILD_ID]
