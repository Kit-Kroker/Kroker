"""US3 e2e: the reopen bound and the escalation (023b T030).

Contracts: tasks.md T030, US3 AC1-AC2, SC-B01, data-model transitions (the dirty
and escalate rows), research.md R11.

Helper shape and scripting channel copied from ``test_workflow_exec_us2.py``. The
inline worker's ``triage_secrets`` emits one JUDGEMENT ``.env`` finding whose
rule carries the stub script prefix. A recording ``notify`` counts escalation
notifications.

Cells and status on HEAD:
1. three nofix: attempts then escalated. RED: the re-plan after a reopen (T031) is
   not wired yet, so the second round never opens.
2. configfail: escalates after a1. PRE-GREEN regression pin. Passes on the
   landed T027/T029 machinery.
3. per-cycle PERSISTED while executing never moves reopens. PRE-GREEN regression
   pin on the execute-gated Detect (R7/R9).

Human-only rounds: the scripted finding is JUDGEMENT, so its effective confidence
is at most 0.6 and no automatic decision can clear the 0.8 threshold. The
human-only property is therefore pinned as "the round-N gate is pending and no
child starts until a human approves it".
"""

from __future__ import annotations

import asyncio
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
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
from sdlc.measurement import Measurement
from sdlc.notify.contract import NotifyInput, Results
from sdlc.triage.activities import TriageSignalInput
from sdlc.triage.models import FixClass, SignalResult, TriageFinding
from sdlc.vcs import build_verification_branch, setup_integration_branch
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import fake_agent_activities
from tests.maintenance.conftest import MAINT_023B_ACTIVITIES, commit_env_file, git
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES, fake_secrets
from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us3-bounds"
SECRET_SCRIPT = "secret_committed"
PROPOSAL = RepairProposal(
    analysis="The tracked .env leaks a live token; untrack it and rotate the token.",
    actions=[RepairAction(kind="code_fix", summary="untrack .env", target_paths=[".env"])],
    self_confidence=0.9,
)


@pytest.fixture(autouse=True)
def _worktrees(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(project="demo", repo_dir=str(repo), ack_unattended_build_probe=True, execute=True)
    base.update(kw)
    return MaintenanceConfig(**base)


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


async def _nudge(handle) -> None:
    """One nudge, waiting until the cycle that it starts has completed."""
    before = (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle
    await handle.signal("nudge")

    async def _done() -> bool:
        s = await handle.query(MaintenanceWorkflow.maintenance_state)
        return s.cycle == before + 1 and not s.running_cycle

    await _until(_done, what=f"cycle {before + 1} to complete")


async def _only(handle):
    incs = await handle.query(MaintenanceWorkflow.incidents)
    assert len(incs) == 1, f"expected one incident, got {len(incs)}"
    return incs[0]


async def _pending(handle):
    return await handle.query(MaintenanceWorkflow.pending_decisions)


def _child_ids(inc) -> set[str]:
    records = list(inc.executions) + ([inc.execution] if inc.execution is not None else [])
    return {r.child_id for r in records}


def _secrets_activity(rule: str):
    """The scripted triage_secrets: one .env finding, read at the given commit."""

    @activity.defn(name="triage_secrets")
    async def scripted_secrets(inp: TriageSignalInput) -> SignalResult:
        repo = Path(inp.repo_dir)
        tracked = set(git(repo, "ls-tree", "-r", "--name-only", inp.commit_sha).split())
        findings: list[TriageFinding] = []
        if ".env" in tracked:
            findings.append(
                TriageFinding(
                    signal="secrets",
                    rule=rule,
                    severity="critical",
                    detail="scripted: a committed .env holds a live token",
                    path=".env",
                    fix_class=FixClass.JUDGEMENT,
                )
            )
        return SignalResult(
            signal="secrets",
            version=3,
            collected=Measurement.measured(float(len(findings))),
            findings=findings,
        )

    return scripted_secrets


def _recording_notify(log: list[NotifyInput]):
    @activity.defn(name="notify")
    async def record(inp: NotifyInput) -> Results:
        log.append(inp)
        return Results(results=[])

    return record


@asynccontextmanager
async def _worker(env, script: str, notifications: list[NotifyInput]):
    rule = f"{script}: {SECRET_SCRIPT}"
    triage = [a for a in TRIAGE_ACTIVITIES if a is not fake_secrets]
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        plugins=[SdlcPydanticAIPlugin()],
        activities=[
            *triage,
            _secrets_activity(rule),
            *fake_agent_activities([("maintainer_agent", RepairProposal, PROPOSAL)]),
            _recording_notify(notifications),
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
    ):
        yield


async def _approve_round_and_start(handle, round_no: int, attempt: int) -> str:
    """Human-approve repair:1 at ``round_no``, start the next child, and return
    its id. Asserts the gate is pending and the approval is the only trigger."""

    async def _gate_open() -> bool:
        return any(p.gate == "repair:1" and p.round == round_no for p in await _pending(handle))

    await _until(_gate_open, what=f"repair:1 round {round_no} to open")
    await handle.signal(
        "submit_gate_decision",
        GateDecision(
            gate="repair:1",
            round=round_no,
            outcome=GateOutcome.APPROVE,
            decided_by="human",
        ),
    )
    await _nudge(handle)  # Execute starts exactly one child for this round
    inc = await _only(handle)
    assert inc.execution is not None, f"round {round_no} must start attempt a{attempt}"
    child_id = inc.execution.child_id
    assert re.match(rf"^maint-demo-[0-9a-f]{{8}}-inc1-a{attempt}$", child_id), child_id
    return child_id


async def _wait_parked(env, child_id: str) -> None:
    child = env.client.get_workflow_handle(child_id)

    async def _parked() -> bool:
        return bool(await child.query(StubRepairChild.pending_decisions))

    await _until(_parked, what=f"{child_id} to park at its merge gate")


async def _baseline_and_incident(handle, repo) -> None:
    await _nudge(handle)  # cycle 1: baseline
    commit_env_file(repo)
    await _nudge(handle)  # cycle 2: incident, plan, repair:1 round 1 (human)


# ------------------------------------------------ 1. three nofix: attempts, escalated


async def test_three_nofix_attempts_then_escalated_with_one_notification(repo_dir):
    """RED on HEAD until T031: the re-plan after each reopen (a new gate_round,
    human-only) is not wired yet, so attempt a2 never starts. The full contract
    is written here, and T031 makes it green.

    Expected: a1, a2, a3 each start after a human approval of its round, and each
    child gets exactly one REJECT. The third dirty verdict reaches the bound
    (reopens == max_reopens == 2) and escalates, with one escalation notification.
    """
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "nofix", notifications):
            handle = await _start(env, _cfg(repo_dir))
            await _baseline_and_incident(handle, repo_dir)

            # Attempt 1: approve round 1, child parks, dirty -> reopened.
            child_a1 = await _approve_round_and_start(handle, round_no=1, attempt=1)
            await _wait_parked(env, child_a1)
            await _nudge(handle)  # verify: dirty -> reopened (reopens 1)
            inc = await _only(handle)
            assert inc.state.value == "reopened"
            assert inc.reopens == 1

            # Re-plan: the reopened incident opens repair:1 round 2, human-only.
            await _nudge(handle)
            inc = await _only(handle)
            assert inc.state.value == "awaiting_decision"
            assert inc.gate_round == 2
            assert inc.plan is not None
            assert any(p.gate == "repair:1" and p.round == 2 for p in await _pending(handle))
            assert len(_child_ids(inc)) == 1, "no child may start before a human decides round 2"

            # Attempt 2: approve round 2, child parks, dirty -> reopened (reopens 2).
            child_a2 = await _approve_round_and_start(handle, round_no=2, attempt=2)
            await _wait_parked(env, child_a2)
            await _nudge(handle)
            inc = await _only(handle)
            assert inc.state.value == "reopened"
            assert inc.reopens == 2

            # Re-plan: round 3 is human-only too.
            await _nudge(handle)
            inc = await _only(handle)
            assert inc.state.value == "awaiting_decision"
            assert inc.gate_round == 3

            # Attempt 3: approve round 3, child parks, dirty -> escalated.
            child_a3 = await _approve_round_and_start(handle, round_no=3, attempt=3)
            await _wait_parked(env, child_a3)
            before_escalation = len(notifications)
            await _nudge(handle)  # verify: dirty at the bound -> escalated

            inc = await _only(handle)
            assert inc.state.value == "escalated"
            assert inc.reopens == 2, "no reopen past the bound"
            assert inc.attempt == 3
            assert len(_child_ids(inc)) == 3
            assert {child_a1, child_a2, child_a3} == _child_ids(inc)
            assert len(notifications) - before_escalation == 1, (
                "the escalation notifies the operator exactly once"
            )

            # One REJECT to each child, never an approval.
            for child_id in (child_a1, child_a2, child_a3):
                child = env.client.get_workflow_handle(child_id)
                result = await asyncio.wait_for(child.result(), timeout=60)
                assert result == "rejected:merge", f"{child_id} got {result!r}"


# ----------------------------------------------------- 2. configfail: escalates at once


async def test_configfail_escalates_after_attempt_one_without_a_reopen(repo_dir):
    """PRE-GREEN regression pin (T027/T029 machinery). Expected to PASS on HEAD.

    A non-retryable child failure is a configuration fault, not a bad fix. It
    escalates at once, with no reopen and no second child."""
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "configfail", notifications):
            handle = await _start(env, _cfg(repo_dir))
            await _baseline_and_incident(handle, repo_dir)
            child_a1 = await _approve_round_and_start(handle, round_no=1, attempt=1)

            child = env.client.get_workflow_handle(child_a1)
            with pytest.raises(WorkflowFailureError):
                await asyncio.wait_for(child.result(), timeout=60)

            await _nudge(handle)  # the probe sees the non-retryable failure

            inc = await _only(handle)
            assert inc.state.value == "escalated"
            assert inc.attempt == 1
            assert inc.reopens == 0
            assert _child_ids(inc) == {child_a1}, "no second child id may ever appear"
            assert inc.execution is not None
            assert inc.execution.outcome == "config_failed"


# --------------------------------------------- 3. per-cycle PERSISTED never reopens


async def test_persisted_detects_while_executing_never_move_reopens(repo_dir):
    """PRE-GREEN regression pin (execute-gated Detect, R7/R9). Expected to PASS on HEAD.

    A child that never parks keeps the incident executing. Every cycle's
    PERSISTED bumps seen_count and consecutive_seen but never reopens."""
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "hang", notifications):
            handle = await _start(env, _cfg(repo_dir))
            await _baseline_and_incident(handle, repo_dir)
            await _approve_round_and_start(handle, round_no=1, attempt=1)

            inc = await _only(handle)
            assert inc.state.value == "executing"
            seen0, consecutive0 = inc.seen_count, inc.consecutive_seen

            for _ in range(3):
                await _nudge(handle)

            inc = await _only(handle)
            assert inc.state.value == "executing"
            assert inc.reopens == 0
            assert inc.seen_count == seen0 + 3
            assert inc.consecutive_seen == consecutive0 + 3


# ------------------------------------------------ edge: escalation is terminal (pre-green)


async def test_escalation_is_terminal_with_no_residue_on_the_execute_path(repo_dir):
    """Edge, PRE-GREEN pin (escalation is terminal for the execute path). Expected
    to PASS on HEAD. Not RED.

    After a configfail escalation, further cycles still complete. The incident
    stays escalated with attempt 1 and no reopen. Exactly one exec_starts stamp
    exists, and no child id beyond the first one is ever created, so nothing is
    probed, verified or retried against the escalated incident."""
    from temporalio.service import RPCError

    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "configfail", notifications):
            handle = await _start(env, _cfg(repo_dir))
            await _baseline_and_incident(handle, repo_dir)
            child_a1 = await _approve_round_and_start(handle, round_no=1, attempt=1)

            with pytest.raises(WorkflowFailureError):
                await asyncio.wait_for(
                    env.client.get_workflow_handle(child_a1).result(), timeout=60
                )
            await _nudge(handle)  # the probe sees the non-retryable failure
            assert (await _only(handle)).state.value == "escalated"

            before = await handle.query(MaintenanceWorkflow.maintenance_state)
            for _ in range(3):
                await _nudge(handle)

            after = await handle.query(MaintenanceWorkflow.maintenance_state)
            assert after.cycle == before.cycle + 3, "cycles must keep completing"
            assert not after.running_cycle

            inc = await _only(handle)
            assert inc.state.value == "escalated"
            assert inc.attempt == 1
            assert inc.reopens == 0
            assert _child_ids(inc) == {child_a1}
            # The query exposes the windowed count, not the raw exec_starts list.
            assert after.starts_in_window == 1, "no further start may be stamped"

            prefix = child_a1.rsplit("-a1", 1)[0]
            with pytest.raises(RPCError):
                await env.client.get_workflow_handle(f"{prefix}-a2").describe()
