"""The ABANDON proof (023b T008, plan D1, risk 1) — PROOF, not RED-first.

The whole 023b design rests on one Temporal behaviour: a child started
with ``ParentClosePolicy.ABANDON`` keeps running across the parent's
``continue_as_new``, stays signalable from the NEW parent run, survives
the parent's termination, and its id stays occupied under
``WorkflowIDReusePolicy.REJECT_DUPLICATE`` (R1, SC-B11).

**If any assertion here fails, STOP: report to the orchestrator before
any task after T009.** Do not work around it (plan risk 1).

The parent workflow is throwaway, defined here; the child is the real
stub repair child (``hang:`` — it parks nowhere and sleeps forever).
No model or harness spend happens anywhere in this file.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import pytest
import temporalio.workflow as _workflow
from pydantic import BaseModel
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.testing import WorkflowEnvironment

from sdlc.converter import sdlc_data_converter
from sdlc.core.models import GateDecision, GateOutcome, IdeaBrief
from sdlc.maintenance.models import RepairProposal
from sdlc.workflows.graph_catalog import build_run_input
from sdlc.workflows.models import GraphRunInput
from sdlc.workflows.tidyup import _default_fix_cfg
from tests.maintenance.conftest import maint_worker
from tests.maintenance.stub_child import StubRepairChild

with _workflow.unsafe.imports_passed_through():
    from temporalio import workflow
    from temporalio.client import WorkflowExecutionStatus

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "t008-proof"
PARENT_ID = "proof-parent"
CHILD_ID = "maint-proof-abcd1234-inc1-a1"


class ProofParentInput(BaseModel):
    """The throwaway parent's scripted phases (see run)."""

    run_input: GraphRunInput
    child_id: str
    task_queue: str
    phase: Literal["start", "probe", "hold"] = "start"
    signal_ok: bool = False
    second_start: str = ""


@workflow.defn(name="ThrowawayAbandonParent")
class ThrowawayAbandonParent:
    """History 1 (start): start the child ABANDON + REJECT_DUPLICATE,
    then continue_as_new. History 2 (probe): signal the child through
    get_external_workflow_handle(id), try the SAME id again, record the
    outcome, then continue_as_new. History 3 (hold): park until
    terminated."""

    def __init__(self) -> None:
        self._report = ""

    @workflow.query
    def report(self) -> str:
        return self._report

    @workflow.run
    async def run(self, inp: ProofParentInput) -> str:
        if inp.phase == "start":
            await workflow.start_child_workflow(
                StubRepairChild.run,
                inp.run_input,
                id=inp.child_id,
                task_queue=inp.task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
            await workflow.continue_as_new(inp.model_copy(update={"phase": "probe"}))
            raise AssertionError("unreachable: continue_as_new never returns")

        if inp.phase == "probe":
            ext = workflow.get_external_workflow_handle(inp.child_id)
            await ext.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="merge",
                    round=1,
                    outcome=GateOutcome.REJECT,
                    decided_by="policy",
                    comments="abandon proof signal",
                ),
            )
            second = "started"
            try:
                await workflow.start_child_workflow(
                    StubRepairChild.run,
                    inp.run_input,
                    id=inp.child_id,
                    task_queue=inp.task_queue,
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                )
            except WorkflowAlreadyStartedError:
                second = "already-started"
            await workflow.continue_as_new(
                inp.model_copy(update={"phase": "hold", "signal_ok": True, "second_start": second})
            )
            raise AssertionError("unreachable: continue_as_new never returns")

        # hold: park until the test terminates this parent.
        self._report = f"signal-ok second={inp.second_start}"
        await workflow.wait_condition(lambda: False)
        return "unreachable"


async def _until(pred, timeout: float = 90.0, what: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await pred():
                return
        except Exception:  # noqa: BLE001 -- queries before the first task
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


async def test_child_survives_continue_as_new_signal_and_parent_termination(repo_dir):
    from tests.maintenance.conftest import commit_env_file

    base = commit_env_file(repo_dir)
    run_input = build_run_input(
        IdeaBrief(
            title="hang: never parks",
            description="the ABANDON proof child",
            mode="brownfield",
            repo_url=str(repo_dir),
            base_branch=base,
        ),
        _default_fix_cfg(),
        None,
    )
    inp = ProofParentInput(run_input=run_input, child_id=CHILD_ID, task_queue=TASK_QUEUE)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with maint_worker(
            env,
            task_queue=TASK_QUEUE,
            proposal=RepairProposal(analysis="x", actions=[], self_confidence=0.9),
            extra_workflows=[ThrowawayAbandonParent],
        ):
            parent = await env.client.start_workflow(
                ThrowawayAbandonParent.run,
                inp,
                id=PARENT_ID,
                task_queue=TASK_QUEUE,
            )

            # history 3's report proves: the signal through the NEW run's
            # external handle was delivered, and the second start of the
            # same id raised WorkflowAlreadyStartedError.
            async def _probe_report():
                return "signal-ok second=already-started" in await parent.query(
                    ThrowawayAbandonParent.report
                )

            await _until(_probe_report, what="the probe report")

            child = env.client.get_workflow_handle(CHILD_ID)
            desc = await child.describe()
            assert desc.status == WorkflowExecutionStatus.RUNNING, (
                f"ABANDON FAILED across continue_as_new: child is {desc.status}"
            )

            # Terminating the parent must leave the child running (ABANDON).
            await env.client.get_workflow_handle(PARENT_ID).terminate()
            await asyncio.sleep(0.2)
            desc = await child.describe()
            assert desc.status == WorkflowExecutionStatus.RUNNING, (
                f"ABANDON FAILED on parent termination: child is {desc.status}"
            )

            # The id stays occupied for a THIRD party too: a fresh start of
            # the same id with REJECT_DUPLICATE is refused — the client
            # itself raises WorkflowAlreadyStartedError at start time.
            try:
                third = await env.client.start_workflow(
                    StubRepairChild.run,
                    run_input,
                    id=CHILD_ID,
                    task_queue=TASK_QUEUE,
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                )
                await asyncio.wait_for(third.result(), timeout=10)
                raise AssertionError("duplicate start was accepted: REJECT_DUPLICATE failed")
            except WorkflowAlreadyStartedError:
                pass
            desc = await child.describe()
            assert desc.status == WorkflowExecutionStatus.RUNNING
