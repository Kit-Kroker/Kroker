"""SC-003 / SC-004: five concurrent benchmark runs share one harness pool (024 T033).

One ``start_local`` server (not time-skipping: the round's platform finding),
two workers as in ``tests/test_pools_routing.py``: core (``ai-sdlc-test``,
``core@test``) with the workflows and the core side of the demo bundle;
harness (``pools-q``, ``harness@test``, ``max_concurrent_activities=2``) with
the harness side. Each benchmark's graph child is the REAL ``GraphWorkflow``
running over ``sdlc.demo.fakes`` (no stub).

``run_coding_task`` is a barrier fake registered on the harness worker only. It
counts in-flight calls, records the peak, and waits on an event the test
releases after the harness slots have been held for >= 1.0 s. A solo,
uncontended run goes first (barrier already open) to fix the expected set of
benchmark record keys.

Asserted for the five runs (three on case ``pools-fleet-a``, two on
``pools-fleet-b``, one cell each, all started within a second):

1. all five complete;
2. peak in-flight ``run_coding_task`` <= 2 (the barrier fake measures itself);
3. some harness activity waited >= 0.5 s from scheduled to started (it queued);
4. core activities stay prompt: p95 schedule-to-start < 1.0 s, with the harness
   slots held by the barrier;
5. each run's benchmark record key set equals the solo run's.

Not driven here: the fleet's id uniqueness (R8) is covered by
``bench_workflow_id``'s own unit test, and which call sites are routed at all is
covered by the AST layer, ``tests/test_pools_call_sites.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

import pytest
from temporalio import activity
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.benchmarks.cli import bench_workflow_id
from sdlc.benchmarks.models import BenchmarkRecord, CaseSpec
from sdlc.calibration.activities import VerdictInput
from sdlc.calibration.models import INSUFFICIENT, CalibrationVerdict
from sdlc.converter import sdlc_data_converter
from sdlc.core.models import GateDecision, GateOutcome
from sdlc.demo.fakes import demo_activities
from sdlc.harness.models import HarnessRunResult
from sdlc.pools import HARNESS_ACTIVITIES
from sdlc.stages.code.activities import CodingTaskInput
from tests.fakes.canned import AGENT_SPECS
from tests.test_pools_routing import (
    CORE_ID,
    CORE_Q,
    HARNESS_ID,
    HARNESS_Q,
    _finalize,
    _grade_oracle,
    _histories,
    _load_case_assets,
    _measure_code_axis,
    _name,
    _resolve_provenance,
    _split,
    _started_identities,
    _summarize_cell,
)

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

HOLD_S = 1.0
FLEET = ("pools-fleet-a", "pools-fleet-a", "pools-fleet-a", "pools-fleet-b", "pools-fleet-b")

# ------------------------------------------------------------- the barrier fake


class _Barrier:
    def __init__(self) -> None:
        self.inflight = 0
        self.peak = 0
        self.gate = asyncio.Event()

    def reset(self, *, open_: bool) -> None:
        self.inflight = 0
        self.peak = 0
        self.gate = asyncio.Event()
        if open_:
            self.gate.set()


BARRIER = _Barrier()
RECORDS: list[BenchmarkRecord] = []


@activity.defn(name="run_coding_task")
async def _barrier_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    BARRIER.inflight += 1
    BARRIER.peak = max(BARRIER.peak, BARRIER.inflight)
    try:
        await BARRIER.gate.wait()
    finally:
        BARRIER.inflight -= 1
    # the sdlc.demo.fakes.run_coding_task result shape
    return HarnessRunResult(
        harness=inp.harness,
        session_id="demo-session",
        exit_code=0,
        summary="implemented (scripted: no coding CLI was run)",
        commit_sha="cafe1234",
        input_tokens=1000,
        output_tokens=200,
        context_window=200000,
    )


@activity.defn(name="record_benchmark")
async def _collect_record(record: BenchmarkRecord) -> None:
    RECORDS.append(record)


@activity.defn(name="calibration_verdict")
async def _calibration_verdict(inp: VerdictInput) -> CalibrationVerdict:
    # a benchmark child consults the calibration ledger at each gate; no ledger here
    return INSUFFICIENT


def _bundle() -> list[Any]:
    demo = [a for a in demo_activities(AGENT_SPECS) if _name(a) != "run_coding_task"]
    return [
        *demo,
        _barrier_coding_task,
        _collect_record,
        _calibration_verdict,
        _load_case_assets,
        _summarize_cell,
        _measure_code_axis,
        _grade_oracle,
        _resolve_provenance,
        _finalize,
    ]


# ------------------------------------------------------------------------ rig


@contextlib.asynccontextmanager
async def _fleet_rig() -> AsyncIterator[Client]:
    from sdlc.benchmarks.workflow import BenchmarkWorkflow
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow

    core_acts, harness_acts = _split(_bundle())
    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        async with (
            Worker(
                env.client,
                task_queue=CORE_Q,
                identity=CORE_ID,
                workflows=[BenchmarkWorkflow, GraphWorkflow, DeploymentWorkflow],
                activities=core_acts,
                plugins=[SdlcPydanticAIPlugin()],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=HARNESS_Q,
                identity=HARNESS_ID,
                activities=harness_acts,
                max_concurrent_activities=2,
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
        ):
            yield env.client


def _spec(case_id: str) -> str:
    return CaseSpec(
        case_id=case_id,
        idea_summary="fleet probe",
        mode="greenfield",
        harnesses=["opencode"],
        models=["openai/gpt-5.2"],
        judge_model="google:gemini-3.5-flash",
        language=None,
        harness_queue=HARNESS_Q,
    ).model_dump_json()


async def _start(client: Client, case_id: str) -> WorkflowHandle:
    from sdlc.benchmarks.workflow import BenchmarkWorkflow

    return await client.start_workflow(
        BenchmarkWorkflow.run,
        _spec(case_id),
        id=bench_workflow_id(case_id),
        task_queue=CORE_Q,
    )


async def _drive_child(client: Client, parent: WorkflowHandle, done: asyncio.Event) -> None:
    """Answer the benchmark child like the demo's operator loop: its clarify
    question and every stage gate (SOFT gates only auto-approve with calibration
    evidence, which a fresh ledger lacks)."""
    child: WorkflowHandle | None = None
    answered: set[str] = set()
    deadline = time.monotonic() + 150
    while not done.is_set() and time.monotonic() < deadline:
        if child is None:
            for ev in (await parent.fetch_history()).events:
                if ev.event_type == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_STARTED:
                    attrs = ev.child_workflow_execution_started_event_attributes
                    child = client.get_workflow_handle(attrs.workflow_execution.workflow_id)
        else:
            with contextlib.suppress(Exception):  # a query racing the child's close
                for pending in await child.query("pending_decisions"):
                    if pending["key"] in answered:
                        continue
                    answered.add(pending["key"])
                    if pending["kind"] == "clarify":
                        await child.signal("answer_question", args=[pending["key"], "yes"])
                    else:
                        decision = GateDecision(
                            gate=pending["gate"],
                            round=pending["round"],
                            outcome=GateOutcome.APPROVE,
                            decided_by="human",
                        )
                        await child.signal("submit_gate_decision", decision)
        await asyncio.sleep(0.1)


def _record_keys(bench_run_id: str) -> set[tuple[Any, ...]]:
    return {
        (r.scope.value, r.stage, r.task_id, r.attempt, r.role)
        for r in RECORDS
        if r.bench_run_id == bench_run_id
    }


def _ts(ev: Any) -> float:
    return float(ev.event_time.seconds) + ev.event_time.nanos / 1e9


def _schedule_to_start(histories: list[Any]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for hist in histories:
        scheduled: dict[int, tuple[str, float]] = {}
        for ev in hist.events:
            if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                name = ev.activity_task_scheduled_event_attributes.activity_type.name
                scheduled[ev.event_id] = (name, _ts(ev))
            elif ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
                sid = ev.activity_task_started_event_attributes.scheduled_event_id
                name, t0 = scheduled[sid]
                out.append((name, _ts(ev) - t0))
    return out


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


# ----------------------------------------------------------------------- test


async def test_five_runs_share_two_harness_slots(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    RECORDS.clear()

    async with _fleet_rig() as client:
        # ---- solo, uncontended: the barrier is already open
        BARRIER.reset(open_=True)
        solo = await _start(client, "pools-fleet-a")
        solo_done = asyncio.Event()
        solo_driver = asyncio.create_task(_drive_child(client, solo, solo_done))
        await asyncio.wait_for(solo.result(), timeout=120)
        solo_done.set()
        await solo_driver
        solo_keys = _record_keys(solo.id)
        assert solo_keys, "the solo run wrote no benchmark records"
        RECORDS.clear()

        # ---- the fleet: five starts within one second, the barrier closed
        BARRIER.reset(open_=False)
        t0 = time.monotonic()
        handles = [await _start(client, case) for case in FLEET]
        assert time.monotonic() - t0 < 1.0, "the five starts must land within one second"
        fleet_done = asyncio.Event()
        drivers = [asyncio.create_task(_drive_child(client, h, fleet_done)) for h in handles]

        # hold both harness slots for >= HOLD_S, then release
        deadline = time.monotonic() + 60
        while BARRIER.inflight < 2 and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert BARRIER.inflight == 2, "the fleet never filled both harness slots"
        held_at = time.monotonic()
        await asyncio.sleep(HOLD_S)
        held_for = time.monotonic() - held_at
        inflight_before_open = BARRIER.inflight  # still full right before the gate opens
        BARRIER.gate.set()

        # 1. all five complete
        results = await asyncio.gather(
            *(asyncio.wait_for(h.result(), timeout=180) for h in handles)
        )
        assert len(results) == 5
        fleet_done.set()
        await asyncio.gather(*drivers)
        histories: list[Any] = []
        for h in handles:
            histories.extend(await _histories(client, h))

    # 2. the concurrency cap holds
    assert BARRIER.peak <= 2, f"peak in-flight run_coding_task was {BARRIER.peak}"

    waits = _schedule_to_start(histories)
    harness_waits = [w for n, w in waits if n in HARNESS_ACTIVITIES]
    core_waits = [w for n, w in waits if n not in HARNESS_ACTIVITIES]
    assert harness_waits and core_waits

    # 2b. the barrier really held: both slots full until the gate opened, and a queued
    # harness task waited out essentially the whole hold
    assert held_for >= HOLD_S - 0.05, f"hold lasted only {held_for:.2f}s"
    assert inflight_before_open == 2, f"inflight was {inflight_before_open} when the gate opened"
    assert max(harness_waits) >= HOLD_S - 0.1, (
        f"max harness wait {max(harness_waits):.2f}s: the queued task did not wait out the hold"
    )

    # 2c. the cap was enforced BY the harness worker: every harness activity started on
    # harness@test, every core activity on core@test (read back from history)
    started = _started_identities(histories)
    harness_started = [i for n, i in started if n in HARNESS_ACTIVITIES]
    core_started = [i for n, i in started if n not in HARNESS_ACTIVITIES]
    assert harness_started and core_started
    assert set(harness_started) == {HARNESS_ID}, set(harness_started)
    assert set(core_started) == {CORE_ID}, set(core_started)

    # 3. the pool queued: some harness activity waited for a slot
    assert max(harness_waits) >= 0.5, f"max harness wait {max(harness_waits):.2f}s"

    # 4. core activities were not starved while the harness slots were held
    p95 = _p95(core_waits)
    assert p95 < 1.0, f"core p95 schedule-to-start {p95:.3f}s"

    # 5. contention changes timing, not the shape of what is recorded
    by_run: dict[str, set[tuple[Any, ...]]] = defaultdict(set)
    for r in RECORDS:
        by_run[r.bench_run_id].add((r.scope.value, r.stage, r.task_id, r.attempt, r.role))
    assert set(by_run) == {h.id for h in handles}
    # the solo run's records never leaked into the fleet comparison
    assert solo.id not in {h.id for h in handles}
    assert solo.id not in {r.bench_run_id for r in RECORDS}, "a solo record leaked into the fleet"
    for run_id, keys in by_run.items():
        assert keys == solo_keys, f"{run_id}: record keys differ from the solo run's"

    print(  # noqa: T201 -- the measured values, for the T033 report
        f"fleet: peak={BARRIER.peak} max_harness_wait={max(harness_waits):.2f}s "
        f"core_p95={p95:.6f}s core_max={max(core_waits):.6f}s "
        f"core_n={len(core_waits)} harness_n={len(harness_waits)} "
        f"identities: harness={len(harness_started)}@{HARNESS_ID} "
        f"core={len(core_started)}@{CORE_ID}"
    )
