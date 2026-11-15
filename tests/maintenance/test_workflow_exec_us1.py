"""US1 e2e: an approved, execution-authorised fix starts one child (023b T021, RED).

Subject: ``MaintenanceWorkflow`` with ``cfg.execute=True`` and the stub repair
child (``StubRepairChild``, registered under the real ``GraphWorkflow`` name).
Contracts: tasks.md T021 (authoritative cell list), workflow-wire.md,
data-model.md transitions, plan.md Phase 3.

Cells (each one a test):
- policy start: a mechanical, reproduced .env fault starts exactly one child
  (``maint-demo-<run8>-inc1-a1``), and the cycle never waits on it.
- human approval: a judgement credential at the default threshold waits for a
  human; the approval starts one child titled from ``repair_work_for``.
- mixed plan: a human-approved code_fix + ops plan starts one child, and the ops
  text is recorded as not executed.
- ops-only plan: a human-approved ops-only plan starts nothing and goes back to
  ``awaiting_decision`` round 2.
- execute off: a human-approved plan lands ``approved_not_executed`` and never
  starts a child. This cell passes at HEAD (regression pin, not RED).
- refusal: a judgement credential at threshold 0.55 is policy-approved, refused
  by the execute guard, and re-gated as ``repair:1`` round 2 with a single
  notification. Later cycles neither re-approve nor start a child.
- replay: the policy-start and refusal parent histories replay clean.

Deviation for the reviewer: the stub scripts only on a title prefix, and the
loop-built title carries none, so the e2e child parks at its merge gate rather
than hanging. That still proves the cycle never awaits the child (SC-B05).

Before T022/T023 every cell that needs the execute path fails on the
``approved`` assertion (HEAD lands ``approved_not_executed``), not on setup.
"""

from __future__ import annotations

import asyncio
import re
import time
from contextlib import asynccontextmanager

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.core.models import GateDecision, GateOutcome
from sdlc.maintenance.models import (
    MaintenanceConfig,
    MaintenanceState,
    RepairAction,
    RepairProposal,
)
from sdlc.vcs import build_verification_branch, setup_integration_branch
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import fake_agent_activities
from tests.maintenance.conftest import (
    MAINT_023B_ACTIVITIES,
    commit_env_file,
    commit_provider_credential,
    maint_worker,
)
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES
from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild
from tests.replay.harness import replayer

with workflow.unsafe.imports_passed_through():
    from sdlc.notify.contract import NotifyInput, Results

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us1-exec"
CHILD_RE = re.compile(r"^maint-demo-[0-9a-f]{8}-inc1-a1$")
OPS_TEXT = "not executed — ops proposal only"
CODE_SUMMARY = "remove the tracked credential file from the index"
OPS_SUMMARY = "restart the production worker pool"


@pytest.fixture(autouse=True)
def _worktrees(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


def _code(summary: str = CODE_SUMMARY) -> RepairAction:
    return RepairAction(kind="code_fix", summary=summary, target_paths=["config/settings.ini"])


def _ops(summary: str = OPS_SUMMARY) -> RepairAction:
    return RepairAction(kind="ops", summary=summary, ops_action="restart")


def _proposal(*actions: RepairAction) -> RepairProposal:
    return RepairProposal(
        analysis="The tracked file leaks a live credential; remove it from the index.",
        actions=list(actions),
        self_confidence=0.9,
    )


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(project="demo", repo_dir=str(repo), ack_unattended_build_probe=True)
    base.update(kw)
    return MaintenanceConfig(**base)


def _execute_cfg(repo, **kw) -> MaintenanceConfig:
    return _cfg(repo, execute=True, **kw)


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


async def _start(env, cfg: MaintenanceConfig):
    return await env.client.start_workflow(
        MaintenanceWorkflow.run,
        MaintenanceState(config=cfg),
        id="maint-demo",
        task_queue=TASK_QUEUE,
    )


async def _cycle_done(handle, cycle: int) -> None:
    async def _done() -> bool:
        s = await handle.query(MaintenanceWorkflow.maintenance_state)
        return s.cycle == cycle and not s.running_cycle

    await _until(_done, what=f"cycle {cycle} to complete")


async def _nudge(handle, cycle_after: int) -> None:
    """One nudge runs one cycle; it is done when the summary shows the next cycle."""
    await handle.signal("nudge")
    await _cycle_done(handle, cycle_after)


async def _incidents(handle):
    return await handle.query(MaintenanceWorkflow.incidents)


async def _by_rule(handle, rule: str):
    for inc in await _incidents(handle):
        if inc.finding is not None and inc.finding.rule == rule:
            return inc
    raise AssertionError(f"no incident for rule {rule!r}")


async def _pending(handle):
    return await handle.query(MaintenanceWorkflow.pending_decisions)


def _recording_notify(log: list[NotifyInput]):
    @activity.defn(name="notify")
    async def record(inp: NotifyInput) -> Results:
        log.append(inp)
        return Results(results=[])

    return record


@asynccontextmanager
async def _worker(env, proposal: RepairProposal, notifications: list[NotifyInput] | None = None):
    """The shared maint_worker, or an inline copy of its activity list when the
    test records notifications (a second ``notify`` would collide with the fake)."""
    if notifications is None:
        async with maint_worker(env, task_queue=TASK_QUEUE, proposal=proposal):
            yield
        return
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        plugins=[SdlcPydanticAIPlugin()],
        activities=[
            *TRIAGE_ACTIVITIES,
            *fake_agent_activities([("maintainer_agent", RepairProposal, proposal)]),
            _recording_notify(notifications),
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
    ):
        yield


async def _child_run_state(env, child_id: str):
    child = env.client.get_workflow_handle(child_id)
    return await child.query(StubRepairChild.run_state)


# ------------------------------------------------------------------ policy start


async def _drive_policy_start(env, repo):
    """Cycles 1-5: baseline, two incidents, reproduction, policy approval, start."""
    handle = await _start(env, _execute_cfg(repo))
    await _nudge(handle, 2)  # cycle 1: baseline
    commit_env_file(repo)
    await _nudge(handle, 3)  # cycle 2: two incidents, plans, gates

    await _nudge(handle, 4)  # cycle 3: reproduced -> policy approval
    inc1 = await _by_rule(handle, "env_file_tracked")
    assert inc1.state.value == "approved", (
        f"the mechanical reproduced fix must be approved under execute, got {inc1.state.value}"
    )

    await _nudge(handle, 5)  # cycle 4: Execute starts the child
    return handle


async def test_policy_start_runs_exactly_one_child_and_the_cycle_never_waits(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code())):
            handle = await _drive_policy_start(env, repo_dir)

            inc1 = await _by_rule(handle, "env_file_tracked")
            assert inc1.execution is not None
            assert CHILD_RE.match(inc1.execution.child_id), inc1.execution.child_id
            assert inc1.execution.base_sha == inc1.commit_sha
            assert inc1.execution.attempt == 1
            assert inc1.attempt == 1
            child_id = inc1.execution.child_id

            # The child answers its run_state query while the cycle keeps going.
            state = await _child_run_state(env, child_id)
            assert state.run_id == child_id

            # Two more nudged cycles complete while the child is parked at merge.
            await _nudge(handle, 6)
            await _nudge(handle, 7)

            inc1 = await _by_rule(handle, "env_file_tracked")
            assert inc1.attempt == 1, "a second start would be a second attempt"
            assert all(r.child_id == child_id for r in inc1.executions)
            # Executing until the child reaches its merge gate, then verifying
            # (data-model). With US2's Report landed (T027), a parked no-fix
            # child is verified, found persisted, and REJECTED — so the
            # incident may already be 'reopened' by these nudges; with T031's
            # re-plan wired, 'reopened' is transient and may already be
            # 'awaiting_decision' at the human-only round-2 gate. SC-B05's
            # proof is the completed cycles and the single record above, not
            # the state: the loop never waited on the in-flight child.
            assert inc1.state.value in {"executing", "verifying", "reopened", "awaiting_decision"}

            # The judgement half of the same plan stays human-gated (effective
            # min(0.9, floor 0.6) = 0.6 does not clear the 0.8 threshold).
            secret = await _by_rule(handle, "secret_committed")
            assert secret.state.value == "awaiting_decision"
            assert secret.execution is None


# ------------------------------------------------------------- human approval


async def test_human_approval_starts_one_child_titled_from_the_repair_work(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code())):
            handle = await _start(env, _execute_cfg(repo_dir))
            await _nudge(handle, 2)
            commit_provider_credential(repo_dir)
            await _nudge(handle, 3)  # unreproduced judgement: human gate, no auto

            async def _gate_open() -> bool:
                return any(p.gate == "repair:1" for p in await _pending(handle))

            await _until(_gate_open, what="repair:1 to open")
            inc = await _by_rule(handle, "aws_access_key_id")
            assert inc.state.value == "awaiting_decision"

            await handle.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="repair:1", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                ),
            )
            inc = await _by_rule(handle, "aws_access_key_id")
            assert inc.state.value == "approved", (
                f"a human approval must land approved under execute, got {inc.state.value}"
            )

            await _nudge(handle, 4)  # Execute starts exactly one child
            inc = await _by_rule(handle, "aws_access_key_id")
            assert inc.execution is not None
            assert CHILD_RE.match(inc.execution.child_id), inc.execution.child_id

            child = await _child_run_state(env, inc.execution.child_id)
            assert child.title == "aws_access_key_id in config/settings.ini"


# ------------------------------------------------------------------ mixed plan


async def test_mixed_plan_starts_one_child_and_records_the_ops_action_as_not_executed(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code(), _ops())):
            handle = await _start(env, _execute_cfg(repo_dir))
            await _nudge(handle, 2)
            commit_provider_credential(repo_dir)
            await _nudge(handle, 3)

            async def _gate_open() -> bool:
                return any(p.gate == "repair:1" for p in await _pending(handle))

            await _until(_gate_open, what="repair:1 to open")
            await handle.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="repair:1", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                ),
            )
            await _nudge(handle, 4)

            inc = await _by_rule(handle, "aws_access_key_id")
            assert inc.execution is not None
            assert CHILD_RE.match(inc.execution.child_id), inc.execution.child_id
            assert inc.attempt == 1
            assert OPS_TEXT in inc.model_dump_json(), "the ops action must be recorded verbatim"


# ----------------------------------------------------------------- ops-only plan


async def test_ops_only_plan_starts_nothing_and_goes_back_to_round_two(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_ops())):
            handle = await _start(env, _execute_cfg(repo_dir))
            await _nudge(handle, 2)
            commit_provider_credential(repo_dir)
            await _nudge(handle, 3)

            async def _gate_open() -> bool:
                return any(p.gate == "repair:1" for p in await _pending(handle))

            await _until(_gate_open, what="repair:1 to open")
            await handle.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="repair:1", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                ),
            )
            await _nudge(handle, 4)  # Execute refuses an ops-only plan

            inc = await _by_rule(handle, "aws_access_key_id")
            assert inc.state.value == "awaiting_decision"
            assert inc.gate_round == 2
            assert inc.execution is None
            assert inc.executions == []
            assert inc.attempt == 0
            rounds = {(p.gate, p.round) for p in await _pending(handle)}
            assert ("repair:1", 2) in rounds


# ------------------------------------------------------------------- execute off


async def test_execute_off_lands_approved_not_executed_and_starts_nothing(repo_dir):
    """Regression pin: the 023a path. Expected to PASS at HEAD."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code())):
            handle = await _start(env, _cfg(repo_dir))  # execute defaults to False
            await _nudge(handle, 2)
            commit_provider_credential(repo_dir)
            await _nudge(handle, 3)

            async def _gate_open() -> bool:
                return any(p.gate == "repair:1" for p in await _pending(handle))

            await _until(_gate_open, what="repair:1 to open")
            await handle.signal(
                "submit_gate_decision",
                GateDecision(
                    gate="repair:1", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                ),
            )
            await _nudge(handle, 4)

            inc = await _by_rule(handle, "aws_access_key_id")
            assert inc.state.value == "approved_not_executed"
            assert inc.execution is None
            assert inc.executions == []


# ----------------------------------------------------------------- refusal path


async def _drive_refusal(env, repo, notifications: list[NotifyInput]):
    """Threshold 0.55: a reproduced judgement plan is policy-approved, then
    refused by the execute guard and re-gated as repair:1 round 2."""
    handle = await _start(env, _execute_cfg(repo, threshold=0.55))
    await _nudge(handle, 2)  # cycle 1: baseline
    commit_provider_credential(repo)
    await _nudge(handle, 3)  # cycle 2: incident, plan, unreproduced
    await _nudge(handle, 4)  # cycle 3: reproduced floor 0.6 > 0.55 -> policy approve
    inc = await _by_rule(handle, "aws_access_key_id")
    assert inc.state.value == "approved", (
        f"policy must approve the reproduced judgement plan, got {inc.state.value}"
    )
    await _nudge(handle, 5)  # cycle 4: Execute refuses (judgement under policy)

    inc = await _by_rule(handle, "aws_access_key_id")
    assert inc.state.value == "awaiting_decision"
    assert inc.gate_round == 2
    assert ("repair:1", 2) in {(p.gate, p.round) for p in await _pending(handle)}
    round2 = [n for n in notifications if n.pending.gate == "repair:1" and n.pending.round == 2]
    assert len(round2) == 1, "the refusal round notifies exactly once"
    return handle


async def test_refused_judgement_is_regated_as_round_two_and_never_reapproved(repo_dir):
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code()), notifications):
            handle = await _drive_refusal(env, repo_dir, notifications)
            notified_after_refusal = len(notifications)

            # Three more cycles: no re-approval, no notification, no child.
            await _nudge(handle, 6)
            await _nudge(handle, 7)
            await _nudge(handle, 8)

            inc = await _by_rule(handle, "aws_access_key_id")
            assert inc.state.value == "awaiting_decision"
            assert inc.gate_round == 2
            assert inc.execution is None
            assert inc.executions == []
            assert len(notifications) == notified_after_refusal


# -------------------------------------------------------------------- replay


async def test_policy_start_history_replays_clean(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code())):
            handle = await _drive_policy_start(env, repo_dir)
            history = await handle.fetch_history()

    result = await replayer(MaintenanceWorkflow, TriageWorkflow).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert result is not None


async def test_refusal_history_replays_clean(repo_dir):
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code()), notifications):
            handle = await _drive_refusal(env, repo_dir, notifications)
            history = await handle.fetch_history()

    result = await replayer(MaintenanceWorkflow, TriageWorkflow).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert result is not None


# ---------------------------------------------- edge: strict threshold (regression pin)


async def test_equal_effective_and_threshold_is_refused_under_execute_and_starts_nothing(
    repo_dir,
):
    """Regression pin (R6, strict comparison), expected to PASS at HEAD. Not RED.

    At threshold 0.9 a reproduced mechanical plan has effective
    min(self_confidence 0.9, floor 0.95) == 0.9 == threshold. The comparison is
    strict (effective > threshold), so policy must not approve it, and Execute
    must not start a child on any later cycle.
    """
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, _proposal(_code())):
            handle = await _start(env, _execute_cfg(repo_dir, threshold=0.9))
            await _nudge(handle, 2)  # cycle 1: baseline
            commit_env_file(repo_dir)
            await _nudge(handle, 3)  # cycle 2: seen once
            await _nudge(handle, 4)  # cycle 3: reproduced, effective == threshold

            inc = await _by_rule(handle, "env_file_tracked")
            assert inc.state.value == "awaiting_decision", (
                f"effective == threshold must not auto-approve, got {inc.state.value}"
            )
            assert (f"repair:{inc.no}", 1) in {(p.gate, p.round) for p in await _pending(handle)}

            await _nudge(handle, 5)  # cycle 4: Execute has nothing to start
            for other in await _incidents(handle):
                assert other.execution is None, other.key
                assert other.executions == [], other.key
