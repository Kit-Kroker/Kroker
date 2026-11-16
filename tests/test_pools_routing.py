"""R4 dynamic layer / SC-002: harness activities land on the harness queue (024 T032a-b).

Two ``Worker``s share one ``start_local`` server (not time-skipping: the
round's platform finding): the core worker (``ai-sdlc-test``, identity
``core@test``) hosts the workflows plus the core activities, the harness worker
(``pools-q``, identity ``harness@test``) hosts the activities in
``sdlc.pools.HARNESS_ACTIVITIES``. A test-only interceptor on the core worker
records ``(activity, task_queue)`` at every ``start_activity``.

Driven here (T032a/T032b, this sitting):

- (a) a greenfield ``GraphWorkflow`` through code with a CREW dev task (so the
  ``CrewTaskWorkflow`` child runs) and a deploy (``DeploymentWorkflow`` child);
- (b) a one-cell ``BenchmarkWorkflow``.

Asserts, routing on: every recorded harness name has ``task_queue == "pools-q"``
and every core name has ``None``; from each workflow's (and child's) history,
every harness ``ActivityTaskStarted`` has identity ``harness@test`` and every
other ``core@test``. Routing off, the same two drivers re-run: every recorded
``task_queue`` is ``None``.

Sub-scenario not driven on fakes: the benchmark's graph child is a stub that
shadows ``GraphWorkflow`` by name (the 012 sequence-test pattern), because the
real child needs the full agent bundle and gate driving. The stub records the
``cfg.harness_queue`` it is handed, which pins the parent -> child inheritance
(W-2); the child-side activity sites themselves are covered by (a) and by the
AST layer, ``tests/test_pools_call_sites.py``.

Driven in T032b (routing on, same rig; the task re-runs only (a)/(b) off):

- (c) ``TriageWorkflow``, ``AssessmentWorkflow`` and ``TidyUpWorkflow`` on the
  ``tests/maintenance/conftest.py`` fixture repo (assessment: the replay
  scenario's staged repo and bundle);
- (d) a ``MaintenanceWorkflow`` execute path via 023b's stub child
  (``tests/maintenance/stub_child.py::StubRepairChild``);
- (e) ``ReflectWorkflow``: the negative space. Every activity is core and no
  harness queue appears anywhere in the run (R2's "Reflect all-core").
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowHandle
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import (
    Interceptor,
    StartActivityInput,
    UnsandboxedWorkflowRunner,
    Worker,
    WorkflowInboundInterceptor,
    WorkflowInterceptorClassInput,
    WorkflowOutboundInterceptor,
)

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.benchmarks.axis import AxisInput
from sdlc.benchmarks.cell import CellProgress
from sdlc.benchmarks.models import AxisBag, BenchmarkRecord, CaseSpec
from sdlc.benchmarks.oracle import OracleGrade
from sdlc.benchmarks.provenance import Provenance
from sdlc.core.models import GateConfig, GatePolicy, HarnessKind, RoleConfig
from sdlc.crew.activities import (
    CheckpointInput,
    CrewTurnInput,
    CrewTurnOutput,
    PrepareCrewInput,
    ReadRoundInput,
    RoundReading,
    load_crew,
)
from sdlc.crew.models import TurnRecord
from sdlc.harness.models import HarnessRunResult
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from sdlc.pools import HARNESS_ACTIVITIES
from sdlc.stages.merge.activities import evaluate_gate
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import git_fakes_except
from tests.fakes.fake_agents import fake_agent_activities
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

CORE_Q = "ai-sdlc-test"
HARNESS_Q = "pools-q"
CORE_ID = "core@test"
HARNESS_ID = "harness@test"

Recorded = list[tuple[str, str | None]]


# ------------------------------------------------------------------- the rig


class _Recorder(Interceptor):
    """Records (activity, task_queue) at every workflow-side start_activity."""

    def __init__(self, sink: Recorded, skip_types: frozenset[str] = frozenset()) -> None:
        self._sink = sink
        self._skip = skip_types

    def workflow_interceptor_class(
        self, input: WorkflowInterceptorClassInput
    ) -> type[WorkflowInboundInterceptor]:
        sink = self._sink
        skip = self._skip

        class _Outbound(WorkflowOutboundInterceptor):
            def start_activity(self, input: StartActivityInput) -> Any:
                if workflow.info().workflow_type not in skip:
                    sink.append((input.activity, input.task_queue))
                return super().start_activity(input)

        class _Inbound(WorkflowInboundInterceptor):
            def init(self, outbound: WorkflowOutboundInterceptor) -> None:
                super().init(_Outbound(outbound))

        return _Inbound


def _name(fn: Any) -> str:
    return str(fn.__temporal_activity_definition.name)


def _split(bundle: list[Any]) -> tuple[list[Any], list[Any]]:
    core = [a for a in bundle if _name(a) not in HARNESS_ACTIVITIES]
    harness = [a for a in bundle if _name(a) in HARNESS_ACTIVITIES]
    return core, harness


@contextlib.asynccontextmanager
async def _rig(
    *,
    workflows: list[type],
    bundle: list[Any],
    routed: bool,
    sink: Recorded,
    skip_types: frozenset[str] = frozenset(),
    core_extra: list[Any] | None = None,
) -> AsyncIterator[Client]:
    """Routed: core + harness workers. Unrouted: the core worker hosts everything."""
    core_acts, harness_acts = _split(bundle)
    async with await WorkflowEnvironment.start_local(data_converter=pydantic_data_converter) as env:
        client = env.client
        core = Worker(
            client,
            task_queue=CORE_Q,
            identity=CORE_ID,
            workflows=workflows,
            activities=[*core_acts, *(core_extra or [])] if routed else bundle,
            plugins=[SdlcPydanticAIPlugin()],
            interceptors=[_Recorder(sink, skip_types)],
            workflow_runner=UnsandboxedWorkflowRunner(),
        )
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(core)
            if routed and harness_acts:  # (e) reflect has none: negative space
                await stack.enter_async_context(
                    Worker(
                        client,
                        task_queue=HARNESS_Q,
                        identity=HARNESS_ID,
                        workflows=[],  # explicit: the harness worker never hosts a workflow
                        activities=harness_acts,
                        workflow_runner=UnsandboxedWorkflowRunner(),
                    )
                )
            yield client


async def _histories(
    client: Client, handle: WorkflowHandle, skip_types: frozenset[str] = frozenset()
) -> list[Any]:
    """The workflow's history plus every child's, recursively (minus ``skip_types``)."""
    out: list[Any] = []
    pending = [handle]
    while pending:
        h = pending.pop()
        hist = await h.fetch_history()
        first = hist.events[0].workflow_execution_started_event_attributes
        if first.workflow_type.name in skip_types:
            continue
        out.append(hist)
        for ev in hist.events:
            if ev.event_type == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_STARTED:
                attrs = ev.child_workflow_execution_started_event_attributes
                pending.append(client.get_workflow_handle(attrs.workflow_execution.workflow_id))
    return out


def _started_identities(histories: list[Any]) -> list[tuple[str, str]]:
    """(activity name, worker identity) for every ActivityTaskStarted."""
    pairs: list[tuple[str, str]] = []
    for hist in histories:
        scheduled: dict[int, str] = {}
        for ev in hist.events:
            if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                scheduled[ev.event_id] = (
                    ev.activity_task_scheduled_event_attributes.activity_type.name
                )
            elif ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
                attrs = ev.activity_task_started_event_attributes
                pairs.append((scheduled[attrs.scheduled_event_id], attrs.identity))
    return pairs


def _assert_routed(recorded: Recorded, histories: list[Any]) -> None:
    harness_seen = {n for n, _ in recorded if n in HARNESS_ACTIVITIES}
    core_seen = {n for n, _ in recorded if n not in HARNESS_ACTIVITIES}
    assert harness_seen, "the run scheduled no harness activity: the driver is vacuous"
    assert core_seen, "the run scheduled no core activity: the driver is vacuous"
    for name, queue in recorded:
        expected = HARNESS_Q if name in HARNESS_ACTIVITIES else None
        assert queue == expected, f"{name}: task_queue {queue!r}, expected {expected!r}"
    started = _started_identities(histories)
    assert started, "no ActivityTaskStarted in any history"
    for name, identity in started:
        expected_id = HARNESS_ID if name in HARNESS_ACTIVITIES else CORE_ID
        assert identity == expected_id, f"{name} ran on {identity!r}, expected {expected_id!r}"


def _assert_unrouted(recorded: Recorded) -> None:
    assert recorded, "the run scheduled no activity: the driver is vacuous"
    assert any(n in HARNESS_ACTIVITIES for n, _ in recorded), "no harness activity scheduled"
    assert all(q is None for _, q in recorded), [(n, q) for n, q in recorded if q is not None]


# ------------------------------------------------ chaos: pins the rig cannot drift from


def _assert_children_and_workflow_tasks_on_core(
    histories: list[Any], *, expect_children: bool
) -> None:
    """W-2 from history: routing on never moves a workflow, child or parent, off the core pool.

    Children are pinned to the core queue (they inherit the parent's), and every
    WorkflowTaskStarted ran on ``core@test``, so no workflow ever executes on the
    harness worker.
    """
    initiated = [
        ev.start_child_workflow_execution_initiated_event_attributes
        for hist in histories
        for ev in hist.events
        if ev.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED
    ]
    if expect_children:
        assert initiated, "no child workflow was started: the W-2 pin is vacuous"
    for attrs in initiated:
        assert attrs.task_queue.name != HARNESS_Q, f"child {attrs.workflow_type.name} on harness"
        assert attrs.task_queue.name == CORE_Q, (
            f"child {attrs.workflow_type.name} on {attrs.task_queue.name!r}, expected {CORE_Q!r}"
        )

    identities = [
        ev.workflow_task_started_event_attributes.identity
        for hist in histories
        for ev in hist.events
        if ev.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_STARTED
    ]
    assert identities, "no WorkflowTaskStarted in any history"
    assert set(identities) == {CORE_ID}, f"workflow tasks ran on {set(identities) - {CORE_ID}}"


def _assert_both_call_forms_recorded(recorded: Recorded) -> None:
    """The recorder sees workflow.execute_activity AND workflow.start_activity.

    Both forms reach the outbound interceptor's ``start_activity``, so the sink
    cannot tell them apart. The only ``workflow.start_activity`` call in src is
    the crew lead turn (``run_crew_turn``); every other site uses
    ``execute_activity``. So seeing a routed ``run_crew_turn`` proves the
    start_activity form is recorded, and a core name proves the execute form.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src" / "sdlc"
    users = {
        p.relative_to(src).as_posix(): p.read_text(encoding="utf-8").count(
            "workflow.start_activity("
        )
        for p in src.rglob("*.py")
        if "workflow.start_activity(" in p.read_text(encoding="utf-8")
    }
    assert users == {"workflows/crew.py": 1}, (
        f"start_activity sites changed ({users}); extend this test to cover the new site"
    )
    assert ("run_crew_turn", HARNESS_Q) in recorded, "start_activity form not recorded"
    assert ("evaluate_gate", None) in recorded, "execute_activity form not recorded"


async def test_split_puts_every_bundle_member_on_exactly_one_side() -> None:
    for bundle in (_graph_bundle(), _bench_bundle()):
        core, harness = _split(bundle)
        core_names, harness_names = [_name(a) for a in core], [_name(a) for a in harness]
        all_names = [_name(a) for a in bundle]

        assert len(all_names) == len(set(all_names)), "duplicate activity registration in the rig"
        assert len(core) + len(harness) == len(bundle)
        assert not set(core_names) & set(harness_names)
        assert set(core_names) | set(harness_names) == set(all_names)
        assert not set(core_names) & HARNESS_ACTIVITIES
        assert set(harness_names) <= HARNESS_ACTIVITIES


# ---------------------------------------------------- (a) graph, crew + deploy


@activity.defn(name="prepare_crew")
async def _fake_prepare(inp: PrepareCrewInput) -> str:
    return "/w/.workspace/orchestration/code"


@activity.defn(name="run_crew_turn")
async def _fake_turn(inp: CrewTurnInput) -> CrewTurnOutput:
    run = HarnessRunResult(
        harness=inp.harness,
        exit_code=0,
        summary="ok",
        session_id="s-1",
        cost_usd=0.5,
        input_tokens=100,
        output_tokens=20,
    )
    return CrewTurnOutput(
        run=run,
        record=TurnRecord(
            role=inp.role,
            round=inp.round,
            attempt=inp.attempt,
            harness=inp.harness,
            model=inp.model,
            session_id="s-1",
            cost_usd=0.5,
            input_tokens=100,
            output_tokens=20,
            exit_code=0,
        ),
    )


@activity.defn(name="read_round")
async def _fake_read(inp: ReadRoundInput) -> RoundReading:
    return RoundReading(
        deliverable_path="/w/round-1/notes.md", note_summary="added greet()", missing=False
    )


@activity.defn(name="checkpoint_round")
async def _fake_checkpoint(inp: CheckpointInput) -> str | None:
    return "a" * 40


@activity.defn(name="notify")
async def _fake_notify(inp: NotifyInput) -> Results:
    return Results(results=[])


def _graph_bundle() -> list[Any]:
    return [
        evaluate_gate,
        export_run_artifacts,
        _fake_notify,
        load_crew,  # the real one: reads the shipped crew/ tree (core: reads no run state)
        _fake_prepare,
        _fake_turn,
        _fake_read,
        _fake_checkpoint,
        # run_coding_task is deliberately absent: the CREW dev role must not use it.
        *git_fakes_except("run_coding_task"),
        *DEPLOY_FAKES,
        *fake_agent_activities(AGENT_SPECS),
    ]


def _graph_cfg(queue: str | None) -> Any:
    cfg = e2e_config()
    cfg.gates = {
        name: GateConfig(policy=GatePolicy.OFF)
        for name in ("clarify", "architecture", "plan", "merge", "deploy")
    }
    cfg.default_gate_policy = GatePolicy.OFF
    cfg.roles["dev"] = RoleConfig(
        harness=HarnessKind.CREW, layout="code", model="zai-coding-plan/glm-5.3"
    )
    cfg.deploy.enabled = True
    cfg.harness_queue = queue
    return cfg


async def _drive_graph(
    queue: str | None, routed: bool, tmp_path: Any, mp: Any
) -> tuple[Recorded, list[Any]]:
    from sdlc.workflows.crew import CrewTaskWorkflow
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow
    from sdlc.workflows.graph_catalog import build_run_input

    mp.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    mp.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    reset_deploy()
    sink: Recorded = []
    async with _rig(
        workflows=[GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow],
        bundle=_graph_bundle(),
        routed=routed,
        sink=sink,
    ) as client:
        handle = await client.start_workflow(
            GraphWorkflow.run,
            build_run_input(greenfield_idea(), _graph_cfg(queue), None),
            id=f"pools-graph-{uuid.uuid4()}",
            task_queue=CORE_Q,
        )
        for qid in QUESTION_IDS:
            await handle.signal("answer_question", args=[qid, "yes"])
        result = await asyncio.wait_for(handle.result(), timeout=180)
        assert not str(result).startswith("failed"), result
        return sink, await _histories(client, handle)


async def test_graph_routing_on(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded, histories = await _drive_graph(HARNESS_Q, True, tmp_path, monkeypatch)
    names = {n for n, _ in recorded}
    # the crew child and the deploy child both ran their harness activities
    assert {"run_crew_turn", "prepare_crew", "deploy_apply"} <= names
    _assert_routed(recorded, histories)
    _assert_children_and_workflow_tasks_on_core(histories, expect_children=True)
    _assert_both_call_forms_recorded(recorded)


async def test_graph_routing_off(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded, _ = await _drive_graph(None, False, tmp_path, monkeypatch)
    _assert_unrouted(recorded)


# --------------------------------------------------- (b) one-cell benchmark run

CHILD_QUEUES: list[Any] = []


@workflow.defn(name="GraphWorkflow")
class _StubGraphChild:
    """Shadows GraphWorkflow by name (012 sequence-test pattern); records the
    cfg.harness_queue the parent hands its child (W-2)."""

    @workflow.run
    async def run(self, run_input: Any) -> str:
        CHILD_QUEUES.append(run_input["cfg"].get("harness_queue"))
        return "stub child ok"


@activity.defn(name="load_case_assets")
async def _load_case_assets(case_id: str, files: Any) -> dict[str, Any]:
    return {}


@activity.defn(name="record_benchmark")
async def _record_benchmark(record: BenchmarkRecord) -> None:
    return None


@activity.defn(name="summarize_cell")
async def _summarize_cell(
    bench_run_id: str, cell_id: str, final_stage: str | None = None
) -> CellProgress:
    return CellProgress(last_stage="code", code_finished=True)


@activity.defn(name="measure_code_axis")
async def _measure_code_axis(inp: AxisInput) -> AxisBag:
    return AxisBag(reason="language not python")


@activity.defn(name="grade_oracle")
async def _grade_oracle(inp: Any) -> OracleGrade:
    raise AssertionError("language=None must skip the oracle")


@activity.defn(name="resolve_provenance")
async def _resolve_provenance() -> Provenance:
    return Provenance(kroker_commit="abc123", tree_dirty=False)


@activity.defn(name="finalize_benchmark_report")
async def _finalize(bench_run_id: str) -> str:
    return "report.md"


def _bench_bundle() -> list[Any]:
    return [
        _load_case_assets,
        _record_benchmark,
        _summarize_cell,
        _measure_code_axis,
        _grade_oracle,
        _resolve_provenance,
        _finalize,
    ]


def _bench_spec(queue: str | None) -> str:
    return CaseSpec(
        case_id="pools-case",
        idea_summary="routing probe",
        mode="greenfield",
        harnesses=["opencode"],
        models=["openai/gpt-5.2"],
        judge_model="google:gemini-3.5-flash",
        language=None,
        harness_queue=queue,
    ).model_dump_json()


async def _drive_bench(queue: str | None, routed: bool) -> tuple[Recorded, list[Any]]:
    from sdlc.benchmarks.workflow import BenchmarkWorkflow

    CHILD_QUEUES.clear()
    sink: Recorded = []
    async with _rig(
        workflows=[BenchmarkWorkflow, _StubGraphChild],
        bundle=_bench_bundle(),
        routed=routed,
        sink=sink,
    ) as client:
        handle = await client.start_workflow(
            BenchmarkWorkflow.run,
            _bench_spec(queue),
            id=f"pools-bench-{uuid.uuid4()}",
            task_queue=CORE_Q,
        )
        await asyncio.wait_for(handle.result(), timeout=120)
        return sink, await _histories(client, handle)


async def test_benchmark_routing_on() -> None:
    recorded, histories = await _drive_bench(HARNESS_Q, True)
    assert "measure_code_axis" in {n for n, _ in recorded}
    assert CHILD_QUEUES == [HARNESS_Q], "the child did not inherit the harness queue"
    _assert_routed(recorded, histories)
    _assert_children_and_workflow_tasks_on_core(histories, expect_children=True)


async def test_benchmark_routing_off() -> None:
    recorded, _ = await _drive_bench(None, False)
    assert CHILD_QUEUES == [None]
    _assert_unrouted(recorded)


# ------------------------------------------------ T032b: (c) (d) (e), routing on


async def _run_routed(
    workflows: list[type],
    bundle: list[Any],
    start: Callable[[Client], Awaitable[WorkflowHandle]],
    *,
    timeout: float = 120,
) -> tuple[Recorded, list[Any], Any]:
    sink: Recorded = []
    async with _rig(workflows=workflows, bundle=bundle, routed=True, sink=sink) as client:
        handle = await start(client)
        result = await asyncio.wait_for(handle.result(), timeout=timeout)
        return sink, await _histories(client, handle), result


def _wf_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


async def test_triage_routing_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.workflows.triage import TriageInput, TriageWorkflow
    from tests.maintenance.conftest import make_repo
    from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES

    repo = make_repo(tmp_path)

    async def start(client: Client) -> WorkflowHandle:
        return await client.start_workflow(
            TriageWorkflow.run,
            TriageInput(
                repo_dir=str(repo),
                commit="HEAD",
                build_probe=True,
                advisory_source="none",
                harness_queue=HARNESS_Q,
            ),
            id=_wf_id("pools-triage"),
            task_queue=CORE_Q,
        )

    recorded, histories, _ = await _run_routed([TriageWorkflow], [*TRIAGE_ACTIVITIES], start)
    assert "triage_build_probe" in {n for n, _ in recorded}
    _assert_routed(recorded, histories)


async def test_assessment_routing_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.workflows.assessment import AssessmentWorkflow
    from sdlc.workflows.triage import TriageWorkflow
    from tests.replay import scenarios

    # the scenario stages its repo and sets two machine-global env vars; restore them.
    for key in ("SDLC_MEMOIZATION_CACHE_ROOT", "SDLC_BOARD_DB"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    scenario = scenarios.ASSESSMENT_SCENARIOS[0]
    scenario.before()
    inp = scenario.extra["assessment_input"].model_copy(update={"harness_queue": HARNESS_Q})

    async def start(client: Client) -> WorkflowHandle:
        return await client.start_workflow(
            AssessmentWorkflow.run, inp, id=_wf_id("pools-assess"), task_queue=CORE_Q
        )

    recorded, histories, _ = await _run_routed(
        [AssessmentWorkflow, TriageWorkflow], scenario.activities(), start
    )
    # the triage child inherited the queue (T028) and ran its build probe on pools-q
    assert "triage_build_probe" in {n for n, _ in recorded}
    _assert_routed(recorded, histories)


# StubRepairChild is test code registered as "GraphWorkflow": it schedules its own vcs
# activities with no routing, so it is outside what this test measures. The production
# graph/crew/deploy children are driven by (a); the AST layer covers the rest.
STUB_CHILD = frozenset({"GraphWorkflow"})


async def _until(pred: Callable[[], Awaitable[bool]], what: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(Exception):  # queries before the first workflow task
            if await pred():
                return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


async def test_maintenance_execute_routing_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(d) cribs tests/maintenance/test_workflow_exec_us1.py::_drive_policy_start."""
    from sdlc.maintenance.models import (
        MaintenanceConfig,
        MaintenanceState,
        RepairAction,
        RepairProposal,
    )
    from sdlc.vcs import build_verification_branch, setup_integration_branch
    from sdlc.workflows.maintenance import MaintenanceWorkflow
    from sdlc.workflows.triage import TriageWorkflow
    from tests.maintenance.conftest import (
        MAINT_023B_ACTIVITIES,
        commit_env_file,
        fake_notify,
        make_repo,
    )
    from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES
    from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild

    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    repo = make_repo(tmp_path)
    proposal = RepairProposal(
        analysis="The tracked file leaks a live credential; remove it from the index.",
        actions=[
            RepairAction(
                kind="code_fix",
                summary="remove the tracked credential file from the index",
                target_paths=["config/settings.ini"],
            )
        ],
        self_confidence=0.9,
    )
    cfg = MaintenanceConfig(
        project="demo",
        repo_dir=str(repo),
        ack_unattended_build_probe=True,
        execute=True,
        harness_queue=HARNESS_Q,
    )
    bundle = [
        *TRIAGE_ACTIVITIES,
        *fake_agent_activities([("maintainer_agent", RepairProposal, proposal)]),
        fake_notify,
        setup_integration_branch,
        build_verification_branch,
        *STUB_ACTIVITIES,
        *MAINT_023B_ACTIVITIES,
    ]
    sink: Recorded = []
    async with _rig(
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        bundle=bundle,
        routed=True,
        sink=sink,
        skip_types=STUB_CHILD,
        # the unrouted stub child calls setup_integration_branch directly; serve it on core
        core_extra=[setup_integration_branch],
    ) as client:
        handle = await client.start_workflow(
            MaintenanceWorkflow.run,
            MaintenanceState(config=cfg),
            id="maint-demo",
            task_queue=CORE_Q,
        )

        async def nudge(cycle_after: int) -> None:
            await handle.signal("nudge")

            async def done() -> bool:
                s = await handle.query(MaintenanceWorkflow.maintenance_state)
                return s.cycle == cycle_after and not s.running_cycle

            await _until(done, f"cycle {cycle_after}")

        await nudge(2)  # cycle 1: baseline
        commit_env_file(repo)
        await nudge(3)  # cycle 2: incidents, plans, gates
        await nudge(4)  # cycle 3: reproduced -> policy approval
        await nudge(5)  # cycle 4: Execute starts the repair child
        await nudge(6)  # cycle 5+: the loop observes the child and verifies
        await nudge(7)

        incidents = await handle.query(MaintenanceWorkflow.incidents)
        assert any(i.execution is not None for i in incidents), "no repair child was started"
        histories = await _histories(client, handle, STUB_CHILD)
        await handle.terminate("T032b done")

    names = {n for n, _ in sink}
    # the triage child (inherited queue) and the loop's own verification calls
    assert {"triage_build_probe", "build_verification_branch", "remove_verification_tree"} <= names
    _assert_routed(sink, histories)
    _assert_repair_child_input_carries_queue(histories)


def _assert_repair_child_input_carries_queue(histories: list[Any]) -> None:
    """Wire-level W-2, independent of the activity sink: the repair child's start
    command (``StartChildWorkflowExecutionInitiated`` in the parent's history) carries
    ``cfg.harness_queue == HARNESS_Q`` in its decoded input, so ``start_repair_child``'s
    ``model_copy`` reached the wire. (Form landed: decoded child input, not the
    child's ActivityTaskScheduled events: the stub child is skipped by design.)
    """
    from pydantic import BaseModel

    inputs: list[Any] = []
    for hist in histories:
        for ev in hist.events:
            if ev.event_type != EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED:
                continue
            attrs = ev.start_child_workflow_execution_initiated_event_attributes
            if attrs.workflow_type.name != "GraphWorkflow":
                continue
            [decoded] = pydantic_data_converter.payload_converter.from_payloads(
                list(attrs.input.payloads), [dict]
            )
            inputs.append(decoded)
    assert inputs, "no GraphWorkflow child start in the parent's history: the pin is vacuous"
    for decoded in inputs:
        cfg = decoded["cfg"]
        assert not isinstance(cfg, BaseModel)
        assert cfg.get("harness_queue") == HARNESS_Q, cfg.get("harness_queue")


async def test_reflect_has_no_harness_queue_anywhere(tmp_path: Path) -> None:
    """(e) The negative space: reflect is core; no harness queue in the run."""
    from sdlc.memory.activities import reflect
    from sdlc.workflows.reflect import ReflectScheduleInput, ReflectWorkflow

    async def start(client: Client) -> WorkflowHandle:
        return await client.start_workflow(
            ReflectWorkflow.run,
            ReflectScheduleInput(banks=["banks/one"], backend="fake"),
            id=_wf_id("pools-reflect"),
            task_queue=CORE_Q,
        )

    recorded, histories, result = await _run_routed([ReflectWorkflow], [reflect], start)
    assert result == 1
    assert [n for n, _ in recorded] == ["reflect"]
    assert all(q is None for _, q in recorded)
    assert {i for _, i in _started_identities(histories)} == {CORE_ID}


async def test_tidyup_routing_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.core.models import GateOutcome, GateSettings
    from sdlc.vcs import build_verification_branch, setup_integration_branch
    from sdlc.workflows.tidyup import TidyUpInput, TidyUpWorkflow
    from sdlc.workflows.triage import TriageWorkflow
    from tests.maintenance.conftest import MAINT_023B_ACTIVITIES, commit_env_file, make_repo
    from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES
    from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild
    from tests.replay.scenarios import decide

    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    repo = make_repo(tmp_path)
    commit_env_file(repo)  # a mechanical finding, so tidy-up has a backlog

    async def start(client: Client) -> WorkflowHandle:
        return await client.start_workflow(
            TidyUpWorkflow.run,
            TidyUpInput(
                repo_dir=str(repo),
                commit="HEAD",
                build_probe=True,
                advisory_source="none",
                max_fix_runs=1,
                gates=GateSettings(default_gate_policy=GatePolicy.OFF),
                harness_queue=HARNESS_Q,
            ),
            id=_wf_id("pools-tidyup"),
            task_queue=CORE_Q,
        )

    sink: Recorded = []
    async with _rig(
        workflows=[TidyUpWorkflow, TriageWorkflow, StubRepairChild],
        bundle=[
            *TRIAGE_ACTIVITIES,
            _fake_notify,
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
        routed=True,
        sink=sink,
        skip_types=STUB_CHILD,
        core_extra=[setup_integration_branch],
    ) as client:
        handle = await start(client)

        # The fix-run child is the stub, parked at its real HARD merge gate: approve it.
        async def child_id() -> str | None:
            for ev in (await handle.fetch_history()).events:
                if ev.event_type == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_STARTED:
                    attrs = ev.child_workflow_execution_started_event_attributes
                    if attrs.workflow_type.name == "GraphWorkflow":
                        return str(attrs.workflow_execution.workflow_id)
            return None

        async def child_parked() -> bool:
            cid = await child_id()
            if cid is None:
                return False
            pending = await client.get_workflow_handle(cid).query("pending_decisions")
            return bool(pending)

        await _until(child_parked, "the fix-run child to park at its merge gate")
        cid = await child_id()
        assert cid is not None
        await decide(client.get_workflow_handle(cid), "merge", 1, GateOutcome.APPROVE)
        await asyncio.wait_for(handle.result(), timeout=120)
        histories = await _histories(client, handle, STUB_CHILD)

    # the triage child (inherited queue) and TidyUp's own verification call
    assert {"triage_build_probe", "build_verification_branch"} <= {n for n, _ in sink}
    _assert_routed(sink, histories)


# ------------------------------------------- chaos: skip_types can only silence the stub


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    return f.id if isinstance(f, ast.Name) else None


def _skip_violations(tree: ast.AST) -> list[str]:
    """Every way a workflow type other than the stub child could be silenced."""
    bad: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = _call_name(n)
        for kw in n.keywords:
            if kw.arg == "skip_types" and not (
                isinstance(kw.value, ast.Name) and kw.value.id == "STUB_CHILD"
            ):
                bad.append(f"{n.lineno}: skip_types is not STUB_CHILD")
        if name == "_histories" and len(n.args) > 2:
            a = n.args[2]
            if not (isinstance(a, ast.Name) and a.id == "STUB_CHILD"):
                bad.append(f"{n.lineno}: _histories skip arg is not STUB_CHILD")
        if name == "_Recorder" and len(n.args) > 1:
            a = n.args[1]
            if not (isinstance(a, ast.Name) and a.id == "skip_types"):
                bad.append(f"{n.lineno}: _Recorder skip arg is not the rig's skip_types")
        if name == "_rig":
            kws = {kw.arg: kw.value for kw in n.keywords}
            wfs = kws.get("workflows")
            names = (
                {e.id for e in wfs.elts if isinstance(e, ast.Name)}
                if isinstance(wfs, ast.List)
                else set()
            )
            skips = "skip_types" in kws
            if "StubRepairChild" in names and not skips:
                bad.append(f"{n.lineno}: _rig registers StubRepairChild without skip_types")
            if skips and ("StubRepairChild" not in names or "GraphWorkflow" in names):
                bad.append(f"{n.lineno}: _rig skips types but not for the stub alone")
    return bad


async def test_skip_types_can_only_silence_the_stub_child() -> None:
    from tests.maintenance.stub_child import StubRepairChild

    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    stub_name = str(getattr(StubRepairChild, "__temporal_workflow_definition").name)  # noqa: B009
    assert stub_name
    assert STUB_CHILD == frozenset({stub_name}), "STUB_CHILD drifted from the stub's wire name"
    assert _skip_violations(tree) == []
    # non-vacuous: the file really does pass the skip somewhere
    assert any(
        kw.arg == "skip_types"
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        for kw in n.keywords
    )


@pytest.mark.parametrize(
    "src",
    [
        "_rig(workflows=[StubRepairChild], skip_types=frozenset({'X'}))",
        "_rig(workflows=[GraphWorkflow, StubRepairChild], skip_types=STUB_CHILD)",
        "_rig(workflows=[TriageWorkflow], skip_types=STUB_CHILD)",
        "_rig(workflows=[StubRepairChild])",
        "_histories(client, handle, frozenset({'TriageWorkflow'}))",
        "_Recorder(sink, frozenset({'GraphWorkflow'}))",
    ],
)
async def test_skip_detector_catches_silencing_of_real_workflows(src: str) -> None:
    assert _skip_violations(ast.parse(src)), src
