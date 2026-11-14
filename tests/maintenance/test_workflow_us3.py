"""US3 e2e: schedule, nudge, one cycle at a time, bounded (023a T028, RED).

Authorship note: both QA seats are quota-blocked again; executor-written
under the degradation ruling — every test transcribes T028's task text
(US3 AC1-5, FR-004/005/013/014/018, R2/R4/R15) and contracts/workflow-wire.md.

Subject: ``MaintenanceKickWorkflow`` and the roll-over/disable behaviour of
``MaintenanceWorkflow`` (T029 implements the kicker, the idle-boundary
continue_as_new and the disable withdrawal refinements).
"""

from __future__ import annotations

import asyncio
import inspect
import time

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.maintenance.models import MaintenanceConfig, MaintenanceState, RepairProposal
from sdlc.workflows.maintenance import MaintenanceKickWorkflow, MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import fake_agent_activities
from tests.maintenance.conftest import commit_build_break
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES
from tests.replay.harness import replayer

with workflow.unsafe.imports_passed_through():
    from sdlc.notify.contract import NotifyInput, Results

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us3"

PROPOSAL = RepairProposal(analysis="restore the return expression", actions=[], self_confidence=0.9)


def _state(repo, **kw) -> MaintenanceState:
    base = dict(project="demo", repo_dir=str(repo), ack_unattended_build_probe=True)
    base.update(kw)
    return MaintenanceState(config=MaintenanceConfig(**base))


def _acts() -> list:
    return fake_agent_activities([("maintainer_agent", RepairProposal, PROPOSAL)])


@activity.defn(name="notify")
async def fake_notify(inp: NotifyInput) -> Results:
    return Results(results=[])


async def _until(pred, timeout: float = 90.0, what: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = pred()
            if inspect.isawaitable(result):
                result = await result
            if result:
                return
        except Exception:  # noqa: BLE001 -- query before the first task lands
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


async def _await_baseline(handle) -> None:
    async def _done() -> bool:
        return (await handle.query(MaintenanceWorkflow.maintenance_state)).baseline_recorded

    await _until(_done, what="cycle 1 baseline")


def _cycle(handle):
    async def _q() -> int:
        return (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle

    return _q


# --------------------------------------------------------------------------- #
# The kicker (FR-003, workflow-wire.md)
# --------------------------------------------------------------------------- #


async def test_kicker_nudges_a_running_loop_and_a_cycle_runs(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, MaintenanceKickWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run, _state(repo_dir), id="maint-demo", task_queue=TASK_QUEUE
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            result = await env.client.execute_workflow(
                MaintenanceKickWorkflow.run,
                {"project": "demo"},
                id="kick-1",
                task_queue=TASK_QUEUE,
            )
            assert result == "nudged:demo"
            async def _kicked() -> bool:
                return (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle >= 3

            await _until(_kicked, what="the kicked cycle to run")


async def test_kicker_without_a_loop_returns_not_enabled_without_retry(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceKickWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            result = await env.client.execute_workflow(
                MaintenanceKickWorkflow.run,
                {"project": "demo"},
                id="kick-2",
                task_queue=TASK_QUEUE,
            )
            assert result == "not-enabled:demo"


# --------------------------------------------------------------------------- #
# Coalescing (SC-004): three nudges during a cycle -> exactly one follow-up
# --------------------------------------------------------------------------- #


async def test_three_nudges_during_a_cycle_coalesce_into_one_follow_up(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run, _state(repo_dir), id="maint-demo", task_queue=TASK_QUEUE
            )
            await handle.signal("nudge")
            await _await_baseline(handle)  # cycle 1 done; state.cycle == 2

            # A burst while cycle 2 is in flight: three nudges.
            for _ in range(3):
                await handle.signal("nudge")

            # Exactly one follow-up: the counter lands at 4 (cycle 2 + cycle
            # 3), never 5+ — no overlapping cycles, no queue.
            async def _at_four() -> bool:
                return (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle == 4

            await _until(_at_four, what="the single follow-up cycle")
            await asyncio.sleep(2)  # a fifth cycle would prove over-counting
            assert (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle == 4


# --------------------------------------------------------------------------- #
# Roll-over (SC-005): continue_as_new at idle only, state survives
# --------------------------------------------------------------------------- #


async def test_history_rolls_over_at_idle_carrying_incidents_and_baseline(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir, max_cycles_per_history=2),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)  # cycle 1; the history's cap is 2

            commit_build_break(repo_dir)
            await handle.signal("nudge")  # cycle 2: one incident opens

            async def _incident() -> bool:
                incs = await handle.query(MaintenanceWorkflow.incidents)
                return bool(incs) and incs[0].key == "build_probe:build_failed::"

            await _until(_incident, what="the incident")
            incs = await handle.query(MaintenanceWorkflow.incidents)
            summary = await handle.query(MaintenanceWorkflow.maintenance_state)

            # The next cycle crosses the cap -> continue_as_new at the idle
            # boundary. The SAME handle keeps resolving to the new run, and
            # open incidents + the baseline survive byte-equal.
            await handle.signal("nudge")

            async def _after_roll() -> bool:
                return (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle >= 4

            await _until(_after_roll, what="the post-roll-over cycle")
            after = await handle.query(MaintenanceWorkflow.incidents)
            summary_after = await handle.query(MaintenanceWorkflow.maintenance_state)
            assert [i.model_dump_json() for i in after] == [i.model_dump_json() for i in incs]
            assert summary_after.baseline_recorded is summary.baseline_recorded
            assert summary_after.project == summary.project


async def test_pending_gate_defers_the_roll_over(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir, max_cycles_per_history=1),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            commit_build_break(repo_dir)
            await handle.signal("nudge")  # cycle 2: incident + a PENDING gate

            async def _pending() -> bool:
                p = await handle.query(MaintenanceWorkflow.pending_decisions)
                return any(x.gate == "repair:1" for x in p)

            await _until(_pending, what="the pending repair:1 gate")

            # One more nudge: the cap says roll over, but the pending gate
            # says wait. The cycle runs; the gate stays pending on the SAME
            # history (no roll-over while a gate is open).
            await handle.signal("nudge")
            await asyncio.sleep(2)
            p = await handle.query(MaintenanceWorkflow.pending_decisions)
            assert any(x.gate == "repair:1" for x in p)  # still here, same run


# --------------------------------------------------------------------------- #
# Disable (FR-018): withdraw open gates, no synthesised decision
# --------------------------------------------------------------------------- #


async def test_disable_withdraws_an_open_gate_and_ends_the_loop(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run, _state(repo_dir), id="maint-demo", task_queue=TASK_QUEUE
            )
            await handle.signal("nudge")
            await _await_baseline(handle)
            commit_build_break(repo_dir)
            await handle.signal("nudge")

            async def _pending() -> bool:
                p = await handle.query(MaintenanceWorkflow.pending_decisions)
                return any(x.gate == "repair:1" for x in p)

            await _until(_pending, what="the pending gate")
            await handle.signal("disable")
            result = await handle.result()
            assert result == "disabled:demo"

            incs = await handle.query(MaintenanceWorkflow.incidents)
            assert incs[0].state.value == "withdrawn"
            assert incs[0].decision is None  # no decision was synthesised
            assert "disabled" in incs[0].note


async def test_re_enable_starts_fresh_with_a_new_baseline(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run, _state(repo_dir), id="maint-demo", task_queue=TASK_QUEUE
            )
            await handle.signal("nudge")
            await _await_baseline(handle)
            commit_build_break(repo_dir)
            await handle.signal("nudge")

            async def _incident() -> bool:
                incs = await handle.query(MaintenanceWorkflow.incidents)
                return bool(incs)

            await _until(_incident, what="the incident")
            await handle.signal("disable")
            assert await handle.result() == "disabled:demo"

            # Re-enable: same id, fresh state — cycle 1 again, no baseline,
            # no incidents until the new baseline cycle records.
            handle2 = await env.client.start_workflow(
                MaintenanceWorkflow.run, _state(repo_dir), id="maint-demo", task_queue=TASK_QUEUE
            )
            assert (await handle2.query(MaintenanceWorkflow.incidents)) == []
            await handle2.signal("nudge")
            await _await_baseline(handle2)
            # The break is now PART OF THE NEW BASELINE: no incident.
            assert (await handle2.query(MaintenanceWorkflow.incidents)) == []


# --------------------------------------------------------------------------- #
# Restart mid-cycle (FR-014): no duplicate incident or gate
# --------------------------------------------------------------------------- #


async def test_worker_restart_mid_cycle_duplicates_nothing(repo_dir):
    release = asyncio.Event()

    @activity.defn(name="triage_build_probe")
    async def held_probe(inp):  # noqa: ANN001, ANN202
        from sdlc.measurement import Measurement
        from sdlc.triage.models import SignalResult
        from tests.maintenance.conftest import build_break_finding

        await asyncio.to_thread(release.wait)  # held until the test releases
        findings = [build_break_finding()] if inp.commit_sha else []
        return SignalResult(
            signal="build_probe",
            version=1,
            collected=Measurement.measured(float(len(findings))),
            findings=findings,
            metrics={
                "buildable": Measurement.measured(1.0 if not findings else 0.0),
                "runnable": Measurement.measured(1.0 if not findings else 0.0),
            },
        )

    acts = [
        *[a for a in TRIAGE_ACTIVITIES if a.__temporal_activity["name"] != "triage_build_probe"],
        held_probe,
        *_acts(),
        fake_notify,
    ]
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        worker = Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=acts,
        )
        async with worker:
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run, _state(repo_dir), id="maint-demo", task_queue=TASK_QUEUE
            )
            await handle.signal("nudge")
            await _await_baseline(handle)  # cycle 1 through the held probe? no:
            # cycle 1 must COMPLETE for a baseline, so release it once.
            release.set()
            await asyncio.sleep(1)

        # Restart the worker mid-cycle 2 (a NEW hold).
        release2 = asyncio.Event()

        @activity.defn(name="triage_build_probe")
        async def held_probe2(inp):  # noqa: ANN001, ANN202
            from sdlc.measurement import Measurement
            from sdlc.triage.models import SignalResult

            await asyncio.to_thread(release2.wait)
            from pathlib import Path

            pkg = Path(inp.repo_dir) / "src" / "fixture_pkg" / "__init__.py"
            broken = pkg.exists() and "build break" in pkg.read_text()
            findings = []
            if broken:
                from tests.maintenance.conftest import build_break_finding

                findings = [build_break_finding()]
            return SignalResult(
                signal="build_probe",
                version=1,
                collected=Measurement.measured(float(len(findings))),
                findings=findings,
                metrics={
                    "buildable": Measurement.measured(1.0),
                    "runnable": Measurement.measured(1.0),
                },
            )

        acts2 = [
            *[a for a in acts if a.__temporal_activity["name"] != "triage_build_probe"],
            held_probe2,
        ]
        commit_build_break(repo_dir)
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=acts2,
        ):
            await handle.signal("nudge")  # cycle 2, held mid-probe
            await asyncio.sleep(2)
        # A third worker instance resumes the SAME run (durable state).
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=acts2,
        ):
            release2.set()

            async def _incident_once() -> bool:
                incs = await handle.query(MaintenanceWorkflow.incidents)
                return len(incs) == 1 and incs[0].key == "build_probe:build_failed::"

            await _until(_incident_once, what="exactly one incident after the restart")
            incs = await handle.query(MaintenanceWorkflow.incidents)
            assert len(incs) == 1  # no duplicate incident
            assert incs[0].no == 1  # the numbering never restarted


# --------------------------------------------------------------------------- #
# Replay across the roll-over (R13)
# --------------------------------------------------------------------------- #


async def test_replay_clean_across_the_roll_over(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir, max_cycles_per_history=1),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)
            await handle.signal("nudge")  # crosses the cap -> continue_as_new

            async def _rolled() -> bool:
                return (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle >= 3

            await _until(_rolled, what="the rolled-over cycle")
            history = await handle.fetch_history()

    result = await replayer(
        MaintenanceWorkflow, MaintenanceKickWorkflow, TriageWorkflow
    ).replay_workflow(history, raise_on_replay_failure=True)
    assert result is not None
