"""Durability and disable (023b T044): crash, roll-over, disable, re-enable.

Contracts: tasks.md T044, B-FR-014/015, R1 (ABANDON, REJECT_DUPLICATE), R15, SC-B08,
SC-B11. Idioms copied from test_workflow_us3.py (the held-activity crash window,
max_cached_workflows=0, the fresh-start re-enable) and test_workflow_exec_us4.py.

Test-local fakes (no conftest/stub/fake edits):
- A scripted triage_secrets emits .env (rule ``fix: secret_committed``, so its child
  parks and can be approved), config/settings.ini (rule ``hang: aws_access_key_id``,
  so its child never parks), and config/extra.ini (also ``hang:``). Every finding is
  JUDGEMENT, so each gate is human-approved.
- ``verify_held``: the verify probe can be armed to block mid-flight (cell 1).
- ``not_collect_verify``: a verify triage at a commit other than HEAD reports
  not-collected, so an incident parks in VERIFYING (cells 2 and 3).
- A recording memory backend (cell 1 counts one retention).

Cells and status on HEAD (declared in each docstring):
1. Mid-probe worker crash. Pre-green (T043 landed, retain_step wired): one child,
   one record, one gate round, and exactly one retention after the restart.
2. Roll-over carry. Pre-green: the carried incidents match the new run's input, and
   the parked child re-attaches to verified after the roll-over.
3. Disable. RED on HEAD: the run withdraws only awaiting_decision, so the verifying
   incident stays un-withdrawn (T045 lands the executing/verifying branch).
4. Re-enable freshness. Pre-green: the new child id carries a different run8.

Window choice (cell 1), documented: the brief's first-activity hold on the stub child
cannot reach a closed end state. The stub runs setup_integration_branch with
maximum_attempts=1, so a killed first attempt fails the child. The window used is the
parent's verify PROBE (probe_repair_child: 60s timeout, 2 attempts). The crash is a
cancelled worker run, a restart with max_cached_workflows=0, and a virtual sleep past
the probe timeout.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import suppress
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.converter import sdlc_data_converter
from sdlc.core.models import GateDecision, GateOutcome
from sdlc.maintenance.activities import probe_repair_child
from sdlc.maintenance.models import (
    MaintenanceConfig,
    MaintenanceState,
    RepairAction,
    RepairProposal,
)
from sdlc.measurement import Measurement
from sdlc.memory import activities as memory_activities
from sdlc.memory.models import RetainItem
from sdlc.triage.activities import TriageSignalInput
from sdlc.triage.models import FixClass, SignalResult, TriageFinding
from sdlc.vcs import build_verification_branch, setup_integration_branch
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import failing_durable_agent
from tests.maintenance.conftest import (
    MAINT_023B_ACTIVITIES,
    commit_env_file,
    commit_provider_credential,
    fake_notify,
    git,
    head_sha,
)
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES, fake_secrets
from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild

with workflow.unsafe.imports_passed_through():
    from sdlc.memory.activities import retain

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-durability"
FIX_RULE = "fix: secret_committed"
HANG_RULE = "hang: aws_access_key_id"
PROPOSAL = RepairProposal(
    analysis="The tracked file leaks a live credential; remove it from the index.",
    actions=[RepairAction(kind="code_fix", summary="untrack the file", target_paths=[".env"])],
    self_confidence=0.9,
)


class RecordingBackend:
    def __init__(self) -> None:
        self.items: list[RetainItem] = []

    async def retain(self, item: RetainItem) -> None:
        self.items.append(item)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    monkeypatch.setenv("SDLC_MEMORY_ENABLED", "true")
    monkeypatch.setenv("SDLC_MEMORY_BACKEND", "fake")


@pytest.fixture
def memory(monkeypatch):
    backend = RecordingBackend()
    monkeypatch.setattr(memory_activities, "_fake_singleton", backend)
    return backend


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(
        project="demo",
        repo_dir=str(repo),
        ack_unattended_build_probe=True,
        execute=True,
        child_timeout_hours=168,
    )
    base.update(kw)
    return MaintenanceConfig(**base)


def _proposer(messages, info):  # noqa: ANN001, ARG001
    """The maintainer's proposal, with the incident's own path as the target."""
    text = " ".join(str(getattr(p, "content", "")) for m in messages for p in m.parts)
    path = ".env"
    for candidate in ("config/settings.ini", "config/extra.ini"):
        if candidate in text:
            path = candidate
            break
    proposal = RepairProposal(
        analysis=f"The tracked {path} leaks a credential.",
        actions=[RepairAction(kind="code_fix", summary=f"untrack {path}", target_paths=[path])],
        self_confidence=0.9,
    )
    return ModelResponse(
        parts=[
            ToolCallPart(tool_name=info.output_tools[0].name, args=proposal.model_dump(mode="json"))
        ]
    )


def _maintainer_activities():
    agent = failing_durable_agent(
        "maintainer_agent", RepairProposal, FunctionModel(_proposer), AGENT_ACTIVITY_CONFIG
    )
    bound = TemporalDurability.from_agent(agent)
    assert bound is not None
    return bound.temporal_activities


def _secrets_activity(state: dict):
    """Emit the three scripted findings, read at the commit asked about. While
    ``state['not_collect_verify']`` is set, a commit other than HEAD is not collected."""

    @activity.defn(name="triage_secrets")
    async def scripted_secrets(inp: TriageSignalInput) -> SignalResult:
        repo = Path(inp.repo_dir)
        if state.get("not_collect_verify") and inp.commit_sha != head_sha(repo):
            return SignalResult(
                signal="secrets",
                version=3,
                collected=Measurement.not_collected("scripted: verify tree not collected"),
            )
        tracked = set(git(repo, "ls-tree", "-r", "--name-only", inp.commit_sha).split())
        wanted = [
            (".env", FIX_RULE),
            ("config/settings.ini", HANG_RULE),
            ("config/extra.ini", HANG_RULE),
        ]
        findings = [
            TriageFinding(
                signal="secrets",
                rule=rule,
                severity="critical",
                detail=f"scripted: {path} is tracked",
                path=path,
                fix_class=FixClass.JUDGEMENT,
            )
            for path, rule in wanted
            if path in tracked
        ]
        return SignalResult(
            signal="secrets",
            version=3,
            collected=Measurement.measured(float(len(findings))),
            findings=findings,
        )

    return scripted_secrets


def _held_probe(hold: dict):
    """probe_repair_child, with the FIRST armed call blocked until ``hold['event']``
    is set. The crash cell kills the worker while that call is blocked."""

    @activity.defn(name="probe_repair_child")
    async def held(child_id: str):
        if hold.get("armed") and not hold.get("held"):
            hold["held"] = True
            await asyncio.to_thread(hold["event"].wait)
        return await probe_repair_child(child_id)

    return held


def _activities(state: dict, hold: dict | None = None):
    triage = [a for a in TRIAGE_ACTIVITIES if a is not fake_secrets]
    other = [a for a in MAINT_023B_ACTIVITIES if a is not probe_repair_child]
    probe = _held_probe(hold) if hold is not None else probe_repair_child
    return [
        *triage,
        _secrets_activity(state),
        *_maintainer_activities(),
        fake_notify,
        retain,
        setup_integration_branch,
        build_verification_branch,
        *STUB_ACTIVITIES,
        *other,
        probe,
    ]


def _worker(env, state: dict, hold: dict | None = None, *, max_cached: int | None = None):
    kwargs = {} if max_cached is None else {"max_cached_workflows": max_cached}
    return Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        plugins=[SdlcPydanticAIPlugin()],
        activities=_activities(state, hold),
        **kwargs,
    )


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
    before = (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle
    await handle.signal("nudge")

    async def _done() -> bool:
        s = await handle.query(MaintenanceWorkflow.maintenance_state)
        return s.cycle == before + 1 and not s.running_cycle

    await _until(_done, what=f"cycle {before + 1} to complete")


async def _incidents(handle):
    return await handle.query(MaintenanceWorkflow.incidents)


async def _by_path(handle, path: str):
    for inc in await _incidents(handle):
        if inc.finding is not None and inc.finding.path == path:
            return inc
    raise AssertionError(f"no incident for {path}")


async def _gate_open(handle, no: int) -> bool:
    return any(
        p.gate == f"repair:{no}" for p in await handle.query(MaintenanceWorkflow.pending_decisions)
    )


async def _approve(handle, no: int) -> None:
    await _until(lambda: _gate_open(handle, no), what=f"repair:{no} to open")
    await handle.signal(
        "submit_gate_decision",
        GateDecision(gate=f"repair:{no}", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )


async def _wait_parked(env, child_id: str) -> None:
    child = env.client.get_workflow_handle(child_id)

    async def _parked() -> bool:
        return bool(await child.query(StubRepairChild.pending_decisions))

    await _until(_parked, what=f"{child_id} to park at its merge gate")


def _child_ids(inc) -> set[str]:
    records = list(inc.executions) + ([inc.execution] if inc.execution is not None else [])
    return {r.child_id for r in records}


async def _drive_env_child_parked(env, handle, repo):
    """Baseline, the .env incident, its human approval, the child start, and the child
    parked at its merge gate. Returns the child id."""
    await _nudge(handle)  # cycle 1: baseline
    commit_env_file(repo)
    await _nudge(handle)  # cycle 2: incident + plan + repair:1
    inc = await _by_path(handle, ".env")
    await _approve(handle, inc.no)
    await _nudge(handle)  # Execute starts the child
    inc = await _by_path(handle, ".env")
    assert inc.execution is not None, "the approved incident must start a child"
    child_id = inc.execution.child_id
    await _wait_parked(env, child_id)
    return child_id


# ------------------------------------------------------------------ 1. restart (SC-B08)


async def test_a_worker_crash_mid_verify_leaves_one_child_one_record_one_retention(
    repo_dir, memory
):
    """Pre-green (T043 landed, retain_step wired): the crash window is the verify probe.

    The probe call is armed and blocks mid-flight, then the worker is cancelled. A
    restart replays the cycle with max_cached_workflows=0. A virtual sleep past the
    probe's 60s timeout makes the server retry it, and the retry completes the verify.
    The end state is one child, one ExecutionRecord, one gate round, and exactly one
    retention.
    """
    state = {"not_collect_verify": False}
    hold = {"armed": False, "held": False, "event": threading.Event()}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        worker_b = _worker(env, state, hold, max_cached=0)
        run_b = asyncio.create_task(worker_b.run())
        handle = await _start(env, _cfg(repo_dir, max_cycles_per_history=50))
        try:
            child_id = await _drive_env_child_parked(env, handle, repo_dir)

            hold["armed"] = True
            await handle.signal("nudge")  # the verify cycle: its probe is held mid-flight

            async def _held_now() -> bool:
                return bool(hold["held"])

            await _until(_held_now, what="the verify probe to be held mid-flight")
            run_b.cancel()
            with suppress(asyncio.CancelledError):
                await run_b

            worker_c = _worker(env, state, hold, max_cached=0)
            async with worker_c:
                await env.sleep(timedelta(seconds=90))  # the held probe times out and retries

                async def _verified() -> bool:
                    return (await _by_path(handle, ".env")).state.value == "verified"

                await _until(_verified, what="the verify to finish after the restart")
                await child_result(env, child_id)
                await _nudge(handle)  # closure

                inc = await _by_path(handle, ".env")
                assert inc.state.value == "closed"
                assert _child_ids(inc) == {child_id}, "exactly one child id"
                assert len(inc.executions) == 1, "one ExecutionRecord"
                assert inc.gate_round == 1, "one repair gate round"
                assert len(memory.items) == 1, f"one retention, got {len(memory.items)}"
        finally:
            hold["event"].set()
            run_b.cancel()
            with suppress(BaseException):
                await run_b


async def child_result(env, child_id: str) -> str:
    """Approve the child's merge gate, then return its result."""
    child = env.client.get_workflow_handle(child_id)
    (pending,) = await child.query(StubRepairChild.pending_decisions)
    await child.signal(
        "submit_gate_decision",
        GateDecision(
            gate=pending.gate,
            round=pending.round,
            outcome=GateOutcome.APPROVE,
            decided_by="human",
        ),
    )
    return await asyncio.wait_for(child.result(), timeout=60)


# ---------------------------------------------------------------- 2. roll-over (SC-B11)


async def test_a_parked_child_re_attaches_after_a_roll_over_with_the_state_carried(repo_dir):
    """Pre-green (T039 carriage landed): the carried state matches, and the parked
    child re-attaches to verified after the roll-over. Roll-overs are counted from the
    park on, and the carried state is compared with the run it was carried into.

    The verify is held in VERIFYING by the not-collected arm until the roll-over,
    so the re-attach happens in the NEW history. The carried incidents are compared
    byte-for-byte with the input the new run started from."""
    state = {"not_collect_verify": True}
    hold = {"armed": False, "held": False, "event": threading.Event()}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, state, hold):
            handle = await _start(env, _cfg(repo_dir, max_cycles_per_history=2))
            child_id = await _drive_env_child_parked(env, handle, repo_dir)
            run_before = (await handle.describe()).run_id  # roll-overs count from the park on

            for _ in range(6):  # force at least one roll-over while the child is parked
                await _nudge(handle)
                if (await handle.describe()).run_id != run_before:
                    break
            run_after = (await handle.describe()).run_id
            assert run_after != run_before, "the roll-over must have happened"

            new_run = env.client.get_workflow_handle("maint-demo", run_id=run_after)
            carried = [
                i.model_dump(mode="json")
                for i in await new_run.query(MaintenanceWorkflow.incidents)
            ]
            history = await new_run.fetch_history()
            begun = next(
                ev
                for ev in history.events
                if ev.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED
            )
            payload = begun.workflow_execution_started_event_attributes.input.payloads[0]
            started_from = MaintenanceState.model_validate(json.loads(payload.data))
            carried_again = [i.model_dump(mode="json") for i in started_from.incidents]
            diffs = [
                (n, k, a.get(k), b.get(k))
                for n, (a, b) in enumerate(zip(carried, carried_again, strict=True))
                for k in sorted(set(a) | set(b))
                if a.get(k) != b.get(k)
            ]
            assert len(carried_again) == len(carried) and not diffs, (
                f"the carried incidents must be byte-equal across the roll-over: {diffs[:3]}"
            )

            child = env.client.get_workflow_handle(child_id)
            assert (await child.describe()).status == WorkflowExecutionStatus.RUNNING
            assert bool(await child.query(StubRepairChild.pending_decisions))

            state["not_collect_verify"] = False  # the verify can now collect
            await _nudge(handle)  # the NEW history's probe sees awaiting_merge and verifies
            assert (await _by_path(handle, ".env")).state.value == "verified"


# ---------------------------------------------------------------------- 3. disable


async def _disable_scenario(env, repo, state: dict, hold: dict):
    """A .env child parked and VERIFYING (not collected), plus a credential incident
    still awaiting its human gate. Returns (handle, child_id)."""
    handle = await _start(env, _cfg(repo))
    await _nudge(handle)  # cycle 1: baseline
    commit_env_file(repo)
    commit_provider_credential(repo)
    await _nudge(handle)  # cycle 2: two incidents, two repair gates
    env_inc = await _by_path(handle, ".env")
    await _approve(handle, env_inc.no)
    await _nudge(handle)  # starts the .env child
    env_inc = await _by_path(handle, ".env")
    child_id = env_inc.execution.child_id
    await _wait_parked(env, child_id)
    state["not_collect_verify"] = True
    await _nudge(handle)  # verify is not collected: the .env incident stays verifying
    assert (await _by_path(handle, ".env")).state.value == "verifying"
    assert (await _by_path(handle, "config/settings.ini")).state.value == "awaiting_decision"
    return handle, child_id


async def test_disable_withdraws_verifying_and_awaiting_incidents_and_leaves_the_child(repo_dir):
    """RED on HEAD: the run withdraws only awaiting_decision, so the verifying incident
    stays un-withdrawn (T045 lands the executing/verifying branch).

    Expected: both incidents withdrawn, the parked child is NOT cancelled (its merge
    gate is still pending and its status is RUNNING), and the loop's own gates are
    unwound."""
    state = {"not_collect_verify": False}
    hold = {"armed": False, "held": False, "event": threading.Event()}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, state, hold):
            handle, child_id = await _disable_scenario(env, repo_dir, state, hold)

            await handle.signal("disable")
            result = await asyncio.wait_for(handle.result(), timeout=90)
            assert result == "disabled:demo"

            assert (await _by_path(handle, ".env")).state.value == "withdrawn"
            assert (await _by_path(handle, "config/settings.ini")).state.value == "withdrawn"

            child = env.client.get_workflow_handle(child_id)
            assert (await child.describe()).status == WorkflowExecutionStatus.RUNNING, (
                "disable must not cancel the ABANDONed child"
            )
            assert bool(await child.query(StubRepairChild.pending_decisions)), (
                "the child's merge gate must still be pending"
            )
            assert await handle.query(MaintenanceWorkflow.pending_decisions) == []


# ---------------------------------------------------------------- 4. re-enable freshness


async def test_a_re_enabled_loop_starts_a_child_with_a_fresh_run8(repo_dir):
    """Pre-green: R1's freshness proof. After a disable, a fresh loop (same id) starts a
    child whose run8 differs from the old loop's, so REJECT_DUPLICATE cannot collide
    with the ABANDONed child, which stays running."""
    state = {"not_collect_verify": False}
    hold = {"armed": False, "held": False, "event": threading.Event()}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, state, hold):
            handle, old_child = await _disable_scenario(env, repo_dir, state, hold)
            await handle.signal("disable")
            assert await asyncio.wait_for(handle.result(), timeout=90) == "disabled:demo"

            # Re-enable: the same id, a fresh state, a new baseline.
            state["not_collect_verify"] = False
            handle2 = await _start(env, _cfg(repo_dir))
            await _nudge(handle2)  # the fresh baseline records what is already committed
            (repo_dir / "config").mkdir(exist_ok=True)
            (repo_dir / "config" / "extra.ini").write_text("[x]\nkey = 1\n", encoding="utf-8")
            git(repo_dir, "add", "config/extra.ini")
            git(repo_dir, "commit", "-m", "a new credential file")
            await _nudge(handle2)  # the new incident
            await _approve(handle2, (await _by_path(handle2, "config/extra.ini")).no)
            await _nudge(handle2)  # the new loop starts its child

            new_child = (await _by_path(handle2, "config/extra.ini")).execution.child_id
            assert new_child.split("-")[2] != old_child.split("-")[2], (
                "the new loop's child must carry a fresh run8"
            )
            old = env.client.get_workflow_handle(old_child)
            assert (await old.describe()).status == WorkflowExecutionStatus.RUNNING


# ------------------------------------------------- EDGE (023b T044) -- qa-chaos


async def test_a_second_disable_after_the_loop_ended_is_refused_and_the_child_survives(repo_dir):
    """Edge, mixed status on HEAD. Pre-green: the loop's result stays ``disabled:demo``
    and the ABANDONed child is still RUNNING with its merge gate pending. The re-signal
    is observed, not assumed: a signal to a completed workflow is refused by the server
    (RPCError NOT_FOUND), so disable is not repeatable and nothing is re-run.
    RED on HEAD, from the withdrawn asserts only (the same root as the disable cell:
    the verifying .env incident is not withdrawn). Those asserts run last, so the
    pre-green asserts above them have already passed when the test fails."""
    from temporalio.service import RPCError, RPCStatusCode

    state = {"not_collect_verify": False}
    hold = {"armed": False, "held": False, "event": threading.Event()}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, state, hold):
            handle, child_id = await _disable_scenario(env, repo_dir, state, hold)
            await handle.signal("disable")
            assert await asyncio.wait_for(handle.result(), timeout=90) == "disabled:demo"

            with pytest.raises(RPCError) as refused:
                await handle.signal("disable")
            assert refused.value.status == RPCStatusCode.NOT_FOUND, "a finished loop refuses"
            assert await handle.result() == "disabled:demo", "the result is stable"

            child = env.client.get_workflow_handle(child_id)
            assert (await child.describe()).status == WorkflowExecutionStatus.RUNNING, (
                "the second disable must not cancel the ABANDONed child"
            )
            assert bool(await child.query(StubRepairChild.pending_decisions)), (
                "the child's merge gate must still be pending"
            )

            assert (await _by_path(handle, ".env")).state.value == "withdrawn"
            assert (await _by_path(handle, "config/settings.ini")).state.value == "withdrawn"
