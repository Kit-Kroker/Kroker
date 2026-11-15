"""Contract tests for ``probe_repair_child`` (023b T013, RED).

Subject: ``sdlc.maintenance.activities.probe_repair_child(child_id) -> ChildProbe``
(NEW module; R2, data-model.md ``ChildProbe``). The probe is a client-side
activity: it describes the child and queries ``pending_decisions`` /
``run_state`` through ``activity.client()``, and it reads the integration head
read-only.

The probe is driven as a REAL activity from a throwaway parent workflow. The
activity import is deferred inside the parent's ``run`` (passed through), so
before T014 each test fails with an ImportError on the parent, not at
collection. Each test uses its own child id and a stub child (``StubRepairChild``
registered under the real ``GraphWorkflow`` wire name).

T014 must register ``probe_repair_child`` in ``MAINT_023B_ACTIVITIES`` in
``tests/maintenance/conftest.py``; until then this file cannot go green.

No model or harness spend happens here.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import timedelta

import pytest
from pydantic import BaseModel
from temporalio import workflow
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from sdlc.core.models import GateDecision, GateOutcome, IdeaBrief
from sdlc.maintenance.models import RepairProposal
from sdlc.workflows.graph_catalog import build_run_input
from sdlc.workflows.models import GraphRunInput
from sdlc.workflows.tidyup import _default_fix_cfg
from tests.maintenance.conftest import commit_env_file, maint_worker
from tests.maintenance.stub_child import StubRepairChild

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "t013-probe"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ProbeParentInput(BaseModel):
    child_id: str


@workflow.defn(name="ThrowawayProbeParent")
class ProbeParent:
    """Runs ``probe_repair_child`` as an activity and returns its result as a
    plain dict (so this module need not import ``ChildProbe`` at load time)."""

    @workflow.run
    async def run(self, inp: ProbeParentInput) -> dict:
        with workflow.unsafe.imports_passed_through():
            from sdlc.maintenance.activities import probe_repair_child

        probe = await workflow.execute_activity(
            probe_repair_child,
            inp.child_id,
            start_to_close_timeout=timedelta(seconds=60),
        )
        return probe.model_dump(mode="json")


def _idea(title: str, base: str, repo_url: str) -> IdeaBrief:
    return IdeaBrief(
        title=title,
        description="the 023b probe contract test",
        mode="brownfield",
        repo_url=repo_url,
        base_branch=base,
    )


def _run_input(title: str, base: str, repo_url: str) -> GraphRunInput:
    return build_run_input(_idea(title, base, repo_url), _default_fix_cfg(), None)


async def _until(pred, timeout: float = 60.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await pred():
                return
        except Exception:  # noqa: BLE001 -- queries before the first task
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


async def _probe(env: WorkflowEnvironment, child_id: str, label: str) -> dict:
    handle = await env.client.start_workflow(
        ProbeParent.run,
        ProbeParentInput(child_id=child_id),
        id=f"t013-probe-parent-{label}",
        task_queue=TASK_QUEUE,
    )
    return await asyncio.wait_for(handle.result(), timeout=60)


async def _start_child(env: WorkflowEnvironment, child_id: str, run_input: GraphRunInput):
    return await env.client.start_workflow(
        StubRepairChild.run,
        run_input,
        id=child_id,
        task_queue=TASK_QUEUE,
    )


@pytest.fixture
def worktrees(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    return tmp_path / "wts"


def _worker(env, proposal=None):
    return maint_worker(
        env,
        task_queue=TASK_QUEUE,
        proposal=proposal or RepairProposal(analysis="x", actions=[], self_confidence=0.9),
        extra_workflows=[ProbeParent],
    )


# ---------------------------------------------------------------- phase mapping


async def test_running_child_probes_as_running(repo_dir, worktrees):
    """A child that is still running (``hang:``) maps to phase 'running'."""
    base = commit_env_file(repo_dir)
    child_id = "maint-demo-abcd1234-inc1-a1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            await _start_child(env, child_id, _run_input("hang: never parks", base, str(repo_dir)))
            probe = await _probe(env, child_id, "running")
            assert probe["phase"] == "running"


async def test_child_parked_at_merge_probes_as_awaiting_merge(repo_dir, worktrees):
    """A ``nofix:`` child parked at its merge gate maps to 'awaiting_merge',
    with the integration branch and a real integration head."""
    base = commit_env_file(repo_dir)
    child_id = "maint-demo-abcd1234-inc2-a1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            child = await _start_child(
                env, child_id, _run_input("nofix: a parked change", base, str(repo_dir))
            )

            async def _parked():
                return bool(await child.query(StubRepairChild.pending_decisions))

            await _until(_parked, what="the merge gate to open")
            probe = await _probe(env, child_id, "awaiting")

            assert probe["phase"] == "awaiting_merge"
            assert probe["pending_merge_round"] == 1
            assert probe["integration_branch"] == f"sdlc/{child_id}/integration"
            assert probe["integration_head"] is not None
            assert SHA40.match(probe["integration_head"])
            assert probe["integration_head"] != base


async def test_approved_child_probes_as_completed_with_its_result(repo_dir, worktrees):
    """A ``fix:`` child approved through its merge gate maps to 'completed'
    with the child's result string."""
    base = commit_env_file(repo_dir)
    child_id = "maint-demo-abcd1234-inc3-a1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            child = await _start_child(
                env, child_id, _run_input("fix: the seeded fault", base, str(repo_dir))
            )

            async def _parked():
                return bool(await child.query(StubRepairChild.pending_decisions))

            await _until(_parked, what="the merge gate to open")
            await child.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="merge",
                    round=1,
                    outcome=GateOutcome.APPROVE,
                    decided_by="human",
                ),
            )
            assert await asyncio.wait_for(child.result(), timeout=60) == (
                "merged-not-deployed:stub"
            )

            probe = await _probe(env, child_id, "completed")
            assert probe["phase"] == "completed"
            assert probe["result"] == "merged-not-deployed:stub"


async def test_configfail_child_probes_as_failed_and_non_retryable(repo_dir, worktrees):
    """A ``configfail:`` child fails non-retryably: phase 'failed', failure set,
    non_retryable True."""
    base = commit_env_file(repo_dir)
    child_id = "maint-demo-abcd1234-inc4-a1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            child = await _start_child(
                env, child_id, _run_input("configfail: bad graph", base, str(repo_dir))
            )
            with pytest.raises(WorkflowFailureError):
                await asyncio.wait_for(child.result(), timeout=60)

            probe = await _probe(env, child_id, "configfail")
            assert probe["phase"] == "failed"
            assert probe["failure"]
            assert probe["non_retryable"] is True


async def test_retryable_failure_probes_as_failed_and_not_non_retryable(repo_dir, worktrees):
    """A ``fail:`` child fails retryably: phase 'failed', non_retryable False."""
    base = commit_env_file(repo_dir)
    child_id = "maint-demo-abcd1234-inc5-a1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            child = await _start_child(
                env, child_id, _run_input("fail: transient", base, str(repo_dir))
            )
            with pytest.raises(WorkflowFailureError):
                await asyncio.wait_for(child.result(), timeout=60)

            probe = await _probe(env, child_id, "fail")
            assert probe["phase"] == "failed"
            assert probe["non_retryable"] is False


async def test_unknown_child_id_probes_as_not_found(repo_dir, worktrees):
    """An id that was never started maps to phase 'not_found'."""
    commit_env_file(repo_dir)
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            probe = await _probe(env, "maint-demo-abcd1234-inc99-a9", "unknown")
            assert probe["phase"] == "not_found"


# ---------------------------------------------------------------- EDGE (023b T013, RED) -- qa-chaos


async def test_rejected_child_probes_as_completed_with_the_verbatim_rejection(repo_dir, worktrees):
    """Edge: a child that completed through a REJECT maps to 'completed', and
    the probe reports its result string verbatim, whatever it is."""
    base = commit_env_file(repo_dir)
    child_id = "maint-demo-abcd1234-inc6-a1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            child = await _start_child(
                env, child_id, _run_input("nofix: rejected at merge", base, str(repo_dir))
            )

            async def _parked():
                return bool(await child.query(StubRepairChild.pending_decisions))

            await _until(_parked, what="the merge gate to open")
            await child.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="merge",
                    round=1,
                    outcome=GateOutcome.REJECT,
                    decided_by="human",
                ),
            )
            assert await asyncio.wait_for(child.result(), timeout=60) == "rejected:merge"

            probe = await _probe(env, child_id, "rejected")
            assert probe["phase"] == "completed"
            assert probe["result"] == "rejected:merge"


async def test_probing_a_child_twice_is_stable_and_read_only(repo_dir, worktrees):
    """Edge: two probes of the same child return the same result, and a
    COMPLETED child's history is unchanged by probing.

    Read-only-ness is measured against a completed child because a live one
    never stands still in a time-skipping environment: a hang: loop re-arms
    its own sleep timer every cycle and a parked gate re-fires its notify
    schedule as the clock skips, so "history unchanged" would be
    unmeasurable noise. A completed child's history is frozen; queries
    themselves never append events."""
    base = commit_env_file(repo_dir)
    child_id = "maint-demo-abcd1234-inc7-a1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env):
            await _start_child(
                env, child_id, _run_input("nofix: completes on reject", base, str(repo_dir))
            )
            handle = env.client.get_workflow_handle(child_id)

            async def _gate_open():
                return await handle.query(StubRepairChild.pending_gate) == "awaiting:merge"

            await _until(_gate_open, what="the merge gate to open")
            await handle.signal(
                "submit_gate_decision",
                GateDecision(gate="merge", round=1, outcome=GateOutcome.REJECT, decided_by="human"),
            )
            await asyncio.wait_for(handle.result(), timeout=60)
            events_before = len((await handle.fetch_history()).events)

            first = await _probe(env, child_id, "stable-a")
            second = await _probe(env, child_id, "stable-b")

            assert first["phase"] == "completed"
            assert second["phase"] == first["phase"]
            assert first["result"] == second["result"] == "rejected:merge"
            assert len((await handle.fetch_history()).events) == events_before, (
                "probing changed the child's history"
            )
