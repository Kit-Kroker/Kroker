"""US6 e2e: a terminal incident is retained once, and only once (023b T042).

Contracts: tasks.md T042, US6 AC1-AC2, SC-B07, R13 (retention fires once, on terminal
entry, through the existing ``retain`` activity, wrapped in the swallow pattern; the
``retained`` flag is set in the same step; the text is ``render_retention``).

Observation channel (test-local, no conftest/stub/fake edits): the ``retain`` activity
resolves ``sdlc.memory.activities._fake_singleton`` on every call. The fixture
replaces that module global with a RECORDING backend before the worker starts, so
the activity's own backend call is what gets captured. Memory is enabled through
``SDLC_MEMORY_ENABLED`` (the env-derived path ``_default_fix_cfg().memory`` reads).

Cells and what each rides:
1. Closed -> exactly one lesson. RED on HEAD: retain_step (T043) is not landed, so
   nothing is retained.
2. Escalated -> exactly one experience. RED on HEAD for the same reason.
3. Failing memory -> the cycle survives. The incident's terminal state is the
   contract; retention is best-effort. RED on HEAD for the state-and-retained part
   (no retain_step), and the no-failure part holds.
4. Verified writes nothing. PRE-GREEN: on HEAD nothing writes anything, so this
   guards retention from writing too early.

Retained-flag reading (cell 3): on a failed retention the activity raised, so the
step records ``retained`` as False. The flag means "stored", not "attempted".
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.converter import sdlc_data_converter
from sdlc.core.models import GateDecision, GateOutcome
from sdlc.maintenance.models import (
    MaintenanceConfig,
    MaintenanceState,
    RepairAction,
    RepairProposal,
)
from sdlc.measurement import Measurement
from sdlc.memory import activities as memory_activities
from sdlc.memory.models import MemoryKind, RetainItem
from sdlc.triage.activities import TriageSignalInput
from sdlc.triage.models import FixClass, SignalResult, TriageFinding
from sdlc.vcs import build_verification_branch, setup_integration_branch
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import fake_agent_activities
from tests.maintenance.conftest import (
    MAINT_023B_ACTIVITIES,
    commit_env_file,
    fake_notify,
    git,
)
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES, fake_secrets
from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild

with workflow.unsafe.imports_passed_through():
    from sdlc.memory.activities import retain

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us6-retention"
SECRET_SCRIPT = "secret_committed"
PROPOSAL = RepairProposal(
    analysis="The tracked .env leaks a live token; untrack it and rotate the token.",
    actions=[RepairAction(kind="code_fix", summary="untrack .env", target_paths=[".env"])],
    self_confidence=0.9,
)


class RecordingBackend:
    """Stands in for the fake memory singleton. Records each retain it receives."""

    def __init__(self, *, fail: bool = False) -> None:
        self.items: list[RetainItem] = []
        self.fail = fail

    async def retain(self, item: RetainItem) -> None:
        if self.fail:
            raise RuntimeError("memory backend down (scripted)")
        self.items.append(item)


@pytest.fixture
def memory(tmp_path, monkeypatch):
    """Enable memory, point worktrees into tmp, and expose a swappable recorder."""
    monkeypatch.setenv("SDLC_MEMORY_ENABLED", "true")
    monkeypatch.setenv("SDLC_MEMORY_BACKEND", "fake")
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    backend = RecordingBackend()
    monkeypatch.setattr(memory_activities, "_fake_singleton", backend)
    return backend


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(
        project="demo",
        repo_dir=str(repo),
        ack_unattended_build_probe=True,
        execute=True,
    )
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
    """One nudge, waiting until the cycle it starts has completed."""
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


def _secrets_activity(rule: str, arm: dict):
    """The scripted triage_secrets (us4's shape): one .env finding read at the commit
    it is asked about. ``arm['on']`` reports a not-collected signal."""

    @activity.defn(name="triage_secrets")
    async def scripted_secrets(inp: TriageSignalInput) -> SignalResult:
        if arm.get("on"):
            return SignalResult(
                signal="secrets",
                version=3,
                collected=Measurement.not_collected("scripted: lost cycle"),
            )
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


@asynccontextmanager
async def _worker(env, script: str, arm: dict):
    """The inline worker: the maint_worker activity list, with the scripted
    triage_secrets and the real ``retain`` activity (the workflow calls it by name)."""
    rule = f"{script}: {SECRET_SCRIPT}"
    triage = [a for a in TRIAGE_ACTIVITIES if a is not fake_secrets]
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        plugins=[SdlcPydanticAIPlugin()],
        activities=[
            *triage,
            _secrets_activity(rule, arm),
            *fake_agent_activities([("maintainer_agent", RepairProposal, PROPOSAL)]),
            fake_notify,
            retain,
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
    ):
        yield


async def _approve_repair(handle) -> None:
    async def _gate_open() -> bool:
        return any(p.gate == "repair:1" for p in await _pending(handle))

    await _until(_gate_open, what="repair:1 to open")
    await handle.signal(
        "submit_gate_decision",
        GateDecision(gate="repair:1", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )


async def _drive_to_verified(env, repo, script: str, arm: dict):
    """us4's shared flow: baseline, incident, human repair approval, child start, the
    child parks, one verify cycle. The child's merge gate is still open."""
    handle = await _start(env, _cfg(repo))
    await _nudge(handle)  # cycle 1: baseline
    commit_env_file(repo)
    await _nudge(handle)  # cycle 2: incident, plan, repair:1 (human)
    await _approve_repair(handle)
    await _nudge(handle)  # Execute starts one child
    inc = await _only(handle)
    assert inc.execution is not None, "the approved incident must start a child"
    child_id = inc.execution.child_id

    child = env.client.get_workflow_handle(child_id)

    async def _parked() -> bool:
        return bool(await child.query(StubRepairChild.pending_decisions))

    await _until(_parked, what="the child to park at its merge gate")
    await _nudge(handle)  # Report: verified
    inc = await _only(handle)
    assert inc.state.value == "verified", f"the fix must verify first, got {inc.state.value}"
    return handle, child_id


async def _approve_child_merge(env, child_id: str) -> str:
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


# ------------------------------------------------ 1. closed -> exactly one lesson (RED)


async def test_a_closed_incident_is_retained_once_as_a_lesson(repo_dir, memory):
    """RED on HEAD: retain_step (T043) is not landed, so the backend records nothing.

    Expected: one INCIDENT_LESSON in project_bank, whose text names the rule and the
    source child (render_retention's contract), with ``retained`` True. Two more
    cycles add nothing: the retained flag makes the retention idempotent."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "fix", arm)
            assert await _approve_child_merge(env, child_id) == "merged-not-deployed:stub"
            await _nudge(handle)  # closure: the incident closes
            assert (await _only(handle)).state.value == "closed"

            assert len(memory.items) == 1, f"exactly one retention, got {len(memory.items)}"
            item = memory.items[0]
            assert item.kind is MemoryKind.INCIDENT_LESSON
            assert item.bank == "project:default"
            assert "fix: secret_committed" in item.text, "the symptom: the rule"
            assert child_id in item.text, "the source child id (R13)"
            assert (await _only(handle)).retained is True

            await _nudge(handle)
            await _nudge(handle)
            assert len(memory.items) == 1, "further cycles must not retain again"
            assert (await _only(handle)).state.value == "closed"


# ------------------------------------------------ 2. escalated -> exactly one experience (RED)


async def test_an_escalated_incident_is_retained_once_as_an_experience(repo_dir, memory):
    """RED on HEAD: retain_step (T043) is not landed.

    A non-retryable configfail child escalates at once (us3's flow). Expected: one
    INCIDENT_EXPERIENCE, with ``retained`` True."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, "configfail", arm):
            handle = await _start(env, _cfg(repo_dir))
            await _nudge(handle)
            commit_env_file(repo_dir)
            await _nudge(handle)
            await _approve_repair(handle)
            await _nudge(handle)  # starts the child
            inc = await _only(handle)
            child = env.client.get_workflow_handle(inc.execution.child_id)

            async def _failed() -> bool:
                return (await child.describe()).status == WorkflowExecutionStatus.FAILED

            await _until(_failed, what="the configfail child to fail")
            await _nudge(handle)  # the probe sees config_failed -> escalated

            inc = await _only(handle)
            assert inc.state.value == "escalated"
            assert len(memory.items) == 1, f"exactly one retention, got {len(memory.items)}"
            assert memory.items[0].kind is MemoryKind.INCIDENT_EXPERIENCE
            assert inc.retained is True


# ------------------------------------------------ 3. failing memory -> the cycle survives (RED)


async def test_a_failing_memory_backend_never_stops_the_incident_closing(repo_dir, memory):
    """RED on HEAD for the retention part: retain_step (T043) is not landed.

    The retain activity raises. Retention is best-effort: the incident still closes,
    the cycles keep advancing, and the workflow raises nothing. The retained flag is
    False: the activity raised, so nothing was stored (the reading in the module doc)."""
    memory.fail = True
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "fix", arm)
            assert await _approve_child_merge(env, child_id) == "merged-not-deployed:stub"
            await _nudge(handle)

            inc = await _only(handle)
            assert inc.state.value == "closed", "a failed retention never blocks closure"
            assert inc.retained is False
            cycle_before = (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle
            await _nudge(handle)
            assert (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle == (
                cycle_before + 1
            ), "the cycles keep advancing after a failed retention"
            assert (await handle.describe()).status == WorkflowExecutionStatus.RUNNING


# ------------------------------------------------ 4. verified writes nothing (PRE-GREEN)


async def test_a_verified_incident_writes_nothing(repo_dir, memory):
    """PRE-GREEN: on HEAD nothing writes anything, and this guards retention from
    writing too early.

    A fix that verifies but is never merged is terminal for no one: it stays
    verified, and the backend records nothing across several more cycles."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, _ = await _drive_to_verified(env, repo_dir, "fix", arm)
            await _nudge(handle)
            await _nudge(handle)

            assert (await _only(handle)).state.value == "verified"
            assert memory.items == [], "a verified incident must not be retained"


# ------------------------------------- edge: no cross-contamination, no spurious kind (RED)


async def test_a_lesson_flow_writes_only_lessons_and_each_item_is_well_formed(repo_dir, memory):
    """Edge, RED on HEAD (retain_step, T043, is not landed). The single-flow negative:
    a closed incident's flow writes one item, and every item is an INCIDENT_LESSON,
    never an experience. Two cycles after closure must add no second, differently
    kinded item. Each item's metadata is a dict of str to str.

    Scope: the two-incident extension (a second terminal incident in the same worker)
    is omitted here. It needs a second scripted rule and a second terminal flow in one
    worker, which is too heavy for one cell."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "fix", arm)
            assert await _approve_child_merge(env, child_id) == "merged-not-deployed:stub"
            await _nudge(handle)  # closure
            await _nudge(handle)
            await _nudge(handle)

            assert len(memory.items) == 1, f"one flow, one item, got {len(memory.items)}"
            assert {item.kind for item in memory.items} == {MemoryKind.INCIDENT_LESSON}
            for item in memory.items:
                assert isinstance(item.metadata, dict)
                assert all(
                    isinstance(k, str) and isinstance(v, str) for k, v in item.metadata.items()
                )
