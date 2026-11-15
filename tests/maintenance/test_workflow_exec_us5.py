"""US5 e2e: the caps queue, they never block, and the window survives a roll-over (023b T038).

Contracts: tasks.md T038, US5 AC1-AC2, SC-B06, R10 (the gate order: path overlap,
per-cycle cap, window cap, then may_execute; QUEUED is admitted-but-held; the
operator is notified once per cycle, not once per incident).

Test-local fakes (no conftest edits):
- The scripted triage_secrets emits one MECHANICAL finding per path in a mutable
  ``faults`` list, rule ``hang: env_file_tracked``. The ``hang:`` script keeps
  every child running, so nothing parks and nothing verifies.
- The maintainer is a FunctionModel that reads the ``Identity:`` line of its prompt
  and returns a proposal whose ``target_paths`` is THAT incident's path. Three
  incidents therefore get path-disjoint plans, and only the caps can queue them.
  A single fixed proposal would make every incident overlap by path.

Route to approval: a MECHANICAL finding with a single code_fix plan (effective 0.9)
is policy-approved once it is reproduced (seen 2, floor 0.95). That is cheaper than
a human round per incident, and it is the path R10 names.

Child timeout: ``child_timeout_hours`` is 168 in every cell, so no child times out
during the test's cycles.

Cells and what each rides:
1. Three approved, one start per cycle. The classification is landed (T037), so the
   cell is PRE-GREEN. It pins that the held incidents never re-gate.
2. Window cap: three starts fill the 3-window, a fourth stays queued. RED: the
   once-per-cycle window notification is T039 (not landed).
3. Window survives a forced roll-over. RED: exec_starts carriage through
   continue_as_new is T039 (not landed).
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import pytest
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.maintenance.models import (
    MaintenanceConfig,
    MaintenanceState,
    RepairAction,
    RepairProposal,
)
from sdlc.measurement import Measurement
from sdlc.triage.activities import TriageSignalInput
from sdlc.triage.models import FixClass, SignalResult, TriageFinding
from sdlc.vcs import build_verification_branch, setup_integration_branch
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import failing_durable_agent
from tests.maintenance.conftest import MAINT_023B_ACTIVITIES
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES, fake_secrets
from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild

with workflow.unsafe.imports_passed_through():
    from sdlc.notify.contract import NotifyInput, Results

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us5-caps"
PATHS = ["config/a.ini", "config/b.ini", "config/c.ini", "config/d.ini"]
RULE = "hang: env_file_tracked"
CHILD_TIMEOUT_HOURS = 168  # nothing times out within a cell's cycles (see module doc)


def _proposer(messages, info):  # noqa: ANN001, ARG001
    """Return a proposal whose target path is the incident's own path."""
    identity = next(
        line
        for m in messages
        for part in m.parts
        for line in str(getattr(part, "content", "")).splitlines()
        if line.startswith("Identity:")
    )
    path = next(p for p in PATHS if p in identity)
    proposal = RepairProposal(
        analysis=f"The tracked {path} must be untracked.",
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


@pytest.fixture(autouse=True)
def _worktrees(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(
        project="demo",
        repo_dir=str(repo),
        ack_unattended_build_probe=True,
        execute=True,
        child_timeout_hours=CHILD_TIMEOUT_HOURS,
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


async def _incidents(handle):
    return await handle.query(MaintenanceWorkflow.incidents)


async def _pending_gates(handle) -> set[str]:
    return {p.gate for p in await handle.query(MaintenanceWorkflow.pending_decisions)}


def _by_path(incs, path: str):
    for inc in incs:
        if inc.finding is not None and inc.finding.path == path:
            return inc
    raise AssertionError(f"no incident for {path}")


def _secrets_activity(faults: dict):
    """The scripted triage_secrets: one MECHANICAL finding per path in
    ``faults['paths']``, read from the mutable cell."""

    @activity.defn(name="triage_secrets")
    async def scripted_secrets(inp: TriageSignalInput) -> SignalResult:
        findings = [
            TriageFinding(
                signal="secrets",
                rule=RULE,
                severity="high",
                detail=f"scripted: {p} is tracked",
                path=p,
                fix_class=FixClass.MECHANICAL,
            )
            for p in faults["paths"]
        ]
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
async def _worker(env, faults: dict, notifications: list[NotifyInput]):
    triage = [a for a in TRIAGE_ACTIVITIES if a is not fake_secrets]
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        plugins=[SdlcPydanticAIPlugin()],
        activities=[
            *triage,
            _secrets_activity(faults),
            *_maintainer_activities(),
            _recording_notify(notifications),
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
    ):
        yield


async def _reproduce_and_start_first(handle, faults: dict, paths: list[str]) -> None:
    """Baseline, add the faults, reproduce them (policy-approves), then start the
    lowest-numbered approved incident."""
    await _nudge(handle)  # cycle 1: baseline (no faults yet)
    faults["paths"] = list(paths)
    await _nudge(handle)  # cycle 2: incidents, plans, repair gates (unreproduced)
    await _nudge(handle)  # cycle 3: reproduced -> policy approves all of them
    await _nudge(handle)  # cycle 4: Execute starts one, the rest are held


# ------------------------------------------------------------------ 1. one start per cycle


async def test_three_approved_incidents_start_one_per_cycle_and_never_re_gate(repo_dir):
    """PRE-GREEN (the classification is landed, T037). Expected to PASS on HEAD.

    Three path-disjoint approved incidents with max_starts_per_cycle=1: each cycle
    starts exactly one, in number order. The held incidents stay QUEUED, and no
    repair:<n> gate ever pends for them again, so their approval is kept (unlike
    023a's DEFERRED, which re-gated)."""
    faults = {"paths": []}
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, faults, notifications):
            handle = await _start(env, _cfg(repo_dir, max_starts_per_cycle=1))
            await _reproduce_and_start_first(handle, faults, PATHS[:3])

            incs = await _incidents(handle)
            started = [i for i in incs if i.execution is not None]
            queued = [i for i in incs if i.state.value == "queued"]
            assert len(started) == 1
            assert len(queued) == 2
            first = min(i.no for i in incs)
            assert started[0].no == first, "the lowest-numbered incident starts first"

            held_nos = {i.no for i in queued}
            for _ in range(2):  # cycle 5 starts the next, cycle 6 the last
                await _nudge(handle)
                pending = await _pending_gates(handle)
                for no in held_nos:
                    assert f"repair:{no}" not in pending, "a held approval must not re-gate"

            incs = await _incidents(handle)
            assert all(i.execution is not None for i in incs), "each cycle starts the next one"
            child_ids = {i.execution.child_id for i in incs}
            assert len(child_ids) == 3, "three incidents, three distinct child ids"


# ----------------------------------------------------------- 2. window cap, one notice


async def _by_path_state(handle, path: str) -> str:
    return _by_path(await _incidents(handle), path).state.value


async def test_a_fourth_incident_stays_queued_with_one_window_notice_per_cycle(repo_dir):
    """RED on HEAD: the once-per-cycle window notification is T039.

    Three starts fill the window of 3. A fourth, path-distinct incident is approved
    and then held by the window. Across the cycles it stays held, each cycle emits
    exactly one window notification, not one per incident."""
    faults = {"paths": []}
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, faults, notifications):
            handle = await _start(env, _cfg(repo_dir, max_starts_per_cycle=3))
            await _reproduce_and_start_first(handle, faults, PATHS[:3])  # cycle 4 starts all three
            await _nudge(handle)
            assert sum(1 for i in await _incidents(handle) if i.execution) == 3

            faults["paths"] = PATHS[:4]  # the fourth fault appears
            await _nudge(handle)  # NEW
            await _nudge(handle)  # reproduced -> approved
            await _nudge(handle)  # Execute: the window is full -> queued
            fourth = _by_path(await _incidents(handle), PATHS[3])
            assert fourth.state.value == "queued"

            for _ in range(2):
                before = len(notifications)
                await _nudge(handle)
                assert (await _by_path_state(handle, PATHS[3])) == "queued"
                assert len(notifications) - before == 1, (
                    "one window notice per cycle while an incident is held"
                )


# ------------------------------------------------ 3. the window survives a roll-over


async def test_the_window_survives_a_forced_roll_over(repo_dir):
    """PRE-GREEN (executor re-declaration; qa predicted RED): exec_starts
    rides the MaintenanceState model, so continue_as_new already carries it
    — the roll-over provably happens (run_id changes, asserted) and the
    window survives it. T039's 'carry exec_starts through continue_as_new'
    is confirmed by this pin rather than implemented; the cell stays as the
    regression pin that the carriage must not regress.

    max_cycles_per_history=2 forces roll-overs. After the three starts and at least
    one roll-over, the fourth incident must still be held by the window, not
    started. If the window resets at roll-over, the fourth starts."""
    faults = {"paths": []}
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, faults, notifications):
            handle = await _start(
                env, _cfg(repo_dir, max_starts_per_cycle=3, max_cycles_per_history=2)
            )
            run_before = (await handle.describe()).run_id
            await _reproduce_and_start_first(handle, faults, PATHS[:3])
            await _nudge(handle)
            assert sum(1 for i in await _incidents(handle) if i.execution) == 3

            faults["paths"] = PATHS[:4]
            for _ in range(4):  # enough cycles to roll the history over
                await _nudge(handle)

            assert (await handle.describe()).run_id != run_before, (
                "the history must have rolled over for this cell to mean anything"
            )
            assert await _by_path_state(handle, PATHS[3]) == "queued", (
                "the window must survive the roll-over: the fourth incident stays held"
            )


# ------------------------------------------------ edge: the overlap gate (R10 gate 1)

# Incident b's plan targets incident a's path, so a and b overlap; c is disjoint.
OVERLAP_TARGET = {
    "config/a.ini": "config/a.ini",
    "config/b.ini": "config/a.ini",
    "config/c.ini": "config/c.ini",
}


def _overlap_proposer(messages, info):  # noqa: ANN001, ARG001
    """Like ``_proposer``, but the target path comes from ``OVERLAP_TARGET``."""
    identity = next(
        line
        for m in messages
        for part in m.parts
        for line in str(getattr(part, "content", "")).splitlines()
        if line.startswith("Identity:")
    )
    path = next(p for p in OVERLAP_TARGET if p in identity)
    target = OVERLAP_TARGET[path]
    proposal = RepairProposal(
        analysis=f"The tracked {path} must be untracked.",
        actions=[RepairAction(kind="code_fix", summary=f"untrack {target}", target_paths=[target])],
        self_confidence=0.9,
    )
    return ModelResponse(
        parts=[
            ToolCallPart(tool_name=info.output_tools[0].name, args=proposal.model_dump(mode="json"))
        ]
    )


@asynccontextmanager
async def _overlap_worker(env, faults: dict, notifications: list[NotifyInput]):
    """The ``_worker`` activity list, with the overlap-targeting maintainer."""
    agent = failing_durable_agent(
        "maintainer_agent", RepairProposal, FunctionModel(_overlap_proposer), AGENT_ACTIVITY_CONFIG
    )
    bound = TemporalDurability.from_agent(agent)
    assert bound is not None
    triage = [a for a in TRIAGE_ACTIVITIES if a is not fake_secrets]
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        plugins=[SdlcPydanticAIPlugin()],
        activities=[
            *triage,
            _secrets_activity(faults),
            *bound.temporal_activities,
            _recording_notify(notifications),
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
    ):
        yield


async def test_an_overlapping_incident_queues_without_holding_the_cycle_or_starting(repo_dir):
    """Edge, the R10 gate-1 path overlap at the e2e tier.

    Incidents a, b and c. b's plan targets a's path, and c is disjoint. With
    max_starts_per_cycle=2, cycle 4 starts a and c in that same cycle. b is QUEUED,
    not started, even though the cap has room, because a's hang: child keeps its
    path live. The overlap holds b without holding the cycle. In later cycles b
    stays queued, and no overlap-based start ever happens.

    Status: the overlap classification is T037. On HEAD the interim choose_starts
    has no overlap gate, so this is expected to be RED at the queued assertion
    until T037 lands.
    """
    faults = {"paths": []}
    notifications: list[NotifyInput] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _overlap_worker(env, faults, notifications):
            handle = await _start(env, _cfg(repo_dir, max_starts_per_cycle=2))
            await _nudge(handle)  # cycle 1: baseline, no faults yet
            faults["paths"] = list(OVERLAP_TARGET)
            await _nudge(handle)  # cycle 2: incidents, plans, repair gates
            await _nudge(handle)  # cycle 3: reproduced -> policy approves
            await _nudge(handle)  # cycle 4: Execute starts a and c; b overlaps a

            a = _by_path(await _incidents(handle), "config/a.ini")
            b = _by_path(await _incidents(handle), "config/b.ini")
            c = _by_path(await _incidents(handle), "config/c.ini")
            assert a.execution is not None
            assert a.state.value == "executing"
            assert c.execution is not None, "the disjoint incident starts in the same cycle"
            assert c.state.value == "executing"
            assert b.execution is None, "an overlapping incident must not start"
            assert b.state.value == "queued"

            for _ in range(2):
                await _nudge(handle)
                incs = await _incidents(handle)
                b = _by_path(incs, "config/b.ini")
                assert b.state.value == "queued", "a's live child keeps b held"
                assert b.execution is None and b.executions == []
                assert _by_path(incs, "config/a.ini").state.value == "executing"

            children = {i.execution.child_id for i in await _incidents(handle) if i.execution}
            assert len(children) == 2, "only the disjoint starts ever happen"
