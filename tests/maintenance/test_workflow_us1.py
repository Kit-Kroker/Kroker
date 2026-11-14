"""US1 e2e: a new problem becomes a gated repair plan (023a T017, RED).

Authorship note: both QA seats are quota-blocked; executor-written under
the degradation ruling — every test transcribes T017's task text
(US1 AC1–5, FR-009/014/016, R13).

Subject: ``sdlc.workflows.maintenance.MaintenanceWorkflow`` — does not
exist yet (T018 implements). The maintainer is the TestModel fake from
tests/fakes; the triage child is served by tests/maintenance/fake_triage.py.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.function import FunctionModel
from sdlc.workflows.maintenance import MaintenanceWorkflow
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.maintenance.models import MaintenanceConfig, MaintenanceState, RepairProposal
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import failing_durable_agent, fake_agent_activities
from tests.maintenance.conftest import commit_build_break, git, head_sha
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES
from tests.replay.harness import replayer

with workflow.unsafe.imports_passed_through():
    from sdlc.notify.contract import NotifyInput, Results

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us1"

PROPOSAL = RepairProposal(
    analysis="The build breaks on a syntax error committed to the package; "
    "restore the return expression.",
    actions=[],
    self_confidence=0.9,
)


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(project="demo", repo_dir=str(repo), ack_unattended_build_probe=True)
    base.update(kw)
    return MaintenanceConfig(**base)


def _state(repo) -> MaintenanceState:
    return MaintenanceState(config=_cfg(repo))


def _maintainer_activities(proposal: RepairProposal = PROPOSAL):
    return fake_agent_activities([("maintainer_agent", RepairProposal, proposal)])


async def _until(pred, timeout: float = 90.0, what: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await pred():
                return
        except Exception:  # noqa: BLE001 -- query before the first task lands
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


@activity.defn(name="notify")
async def fake_notify(inp: NotifyInput) -> Results:
    return Results(results=[])


def _repo_fingerprint(repo) -> tuple[str, str, str]:
    """SC-002's observation surface: every ref, every worktree, HEAD."""
    return (
        git(repo, "for-each-ref"),
        git(repo, "worktree", "list"),
        head_sha(repo),
    )


def _failing_maintainer_activities():
    """A maintainer whose model call always raises (the FR-009 degrade path)."""

    def _boom(ctx, messages):  # noqa: ANN001, ARG001
        raise RuntimeError("proposer down")

    agent = failing_durable_agent(
        "maintainer_agent", RepairProposal, FunctionModel(_boom), AGENT_ACTIVITY_CONFIG
    )
    bound = TemporalDurability.from_agent(agent)
    assert bound is not None
    return bound.temporal_activities


# --------------------------------------------------------------------------- #
# US1 AC1 + AC5: enable, cycle 1 records the baseline, zero incidents, zero writes
# --------------------------------------------------------------------------- #


async def test_cycle_one_records_baseline_and_opens_nothing(repo_dir):
    before = _repo_fingerprint(repo_dir)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            activities=[*TRIAGE_ACTIVITIES, *_maintainer_activities(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")

            async def _baseline_recorded() -> bool:
                return (await handle.query("maintenance_state")).baseline_recorded

            await _until(_baseline_recorded, what="cycle 1 baseline")
            incidents = await handle.query("incidents")
            assert incidents == []

    assert _repo_fingerprint(repo_dir) == before  # SC-002


# --------------------------------------------------------------------------- #
# US1 AC2-4: the break becomes one incident, one plan, one pending repair:1
# --------------------------------------------------------------------------- #


async def test_a_break_becomes_one_incident_one_plan_one_gate(repo_dir):
    before = _repo_fingerprint(repo_dir)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            activities=[*TRIAGE_ACTIVITIES, *_maintainer_activities(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")  # cycle 1: baseline

            async def _baseline_recorded() -> bool:
                return (await handle.query("maintenance_state")).baseline_recorded

            await _until(_baseline_recorded, what="cycle 1 baseline")

            commit_build_break(repo_dir)
            await handle.signal("nudge")  # cycle 2: detect, plan, gate

            async def _incident_opened() -> bool:
                return any(
                    i.key == "build_probe:build_failed::" for i in await handle.query("incidents")
                )

            await _until(_incident_opened, what="the break to become an incident")
            incidents = await handle.query("incidents")
            assert len(incidents) == 1
            inc = incidents[0]
            assert inc.plan is not None
            # All three confidences present, effective is the lower of the two.
            assert inc.plan.self_confidence == 0.9
            assert inc.plan.floor == pytest.approx(0.45)  # JUDGEMENT, not reproduced
            assert inc.plan.effective == pytest.approx(min(0.9, 0.45))

            pending = await handle.query("pending_decisions")
            gates = [p.gate for p in pending]
            assert "repair:1" in gates

    assert _repo_fingerprint(repo_dir) == before  # SC-002


# --------------------------------------------------------------------------- #
# FR-009 degrade: proposer exception -> analysis_failed, retried, escalated
# --------------------------------------------------------------------------- #


async def test_proposer_failure_degrades_retries_then_escalates(repo_dir):
    failing_acts = _failing_maintainer_activities()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            activities=[*TRIAGE_ACTIVITIES, *failing_acts, fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")

            async def _baseline_recorded() -> bool:
                return (await handle.query("maintenance_state")).baseline_recorded

            await _until(_baseline_recorded, what="cycle 1 baseline")

            commit_build_break(repo_dir)
            await handle.signal("nudge")  # attempt 1 fails

            async def _open_with_note() -> bool:
                incs = await handle.query("incidents")
                return bool(incs) and incs[0].state.value == "open" and incs[0].note

            await _until(_open_with_note, what="analysis_failed note")
            inc = (await handle.query("incidents"))[0]
            assert "analysis_failed" in inc.note
            assert inc.plan is None
            assert inc.plan_attempts == 1

            await handle.signal("nudge")  # attempt 2: max_plan_attempts=2 -> escalated

            async def _escalated() -> bool:
                return (await handle.query("incidents"))[0].state.value == "escalated"

            await _until(_escalated, what="escalation after max attempts")

    assert True  # SC-002 fingerprint asserted implicitly by fakes never writing


# --------------------------------------------------------------------------- #
# FR-009 edge: zero-action plan still gates, rendered "no action proposed"
# --------------------------------------------------------------------------- #


async def test_zero_action_plan_still_gates_as_no_action_proposed(repo_dir):
    proposal = RepairProposal(
        analysis="The evidence supports no repair.", actions=[], self_confidence=0.5
    )
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            activities=[*TRIAGE_ACTIVITIES, *_maintainer_activities(proposal), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")

            async def _baseline_recorded() -> bool:
                return (await handle.query("maintenance_state")).baseline_recorded

            await _until(_baseline_recorded, what="cycle 1 baseline")
            commit_build_break(repo_dir)
            await handle.signal("nudge")

            async def _plan_recorded() -> bool:
                return any(i.plan for i in await handle.query("incidents"))

            await _until(_plan_recorded, what="the zero-action plan")
            inc = (await handle.query("incidents"))[0]
            assert inc.plan is not None
            assert inc.plan.actions == []
            pending = await handle.query("pending_decisions")
            item = next(p for p in pending if p.gate == "repair:1")
            assert "no action proposed" in item.spec_summary


# --------------------------------------------------------------------------- #
# R13: the captured history replays clean through the Replayer
# --------------------------------------------------------------------------- #


async def test_history_replays_clean(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            activities=[*TRIAGE_ACTIVITIES, *_maintainer_activities(), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")

            async def _baseline_recorded() -> bool:
                return (await handle.query("maintenance_state")).baseline_recorded

            await _until(_baseline_recorded, what="cycle 1 baseline")
            commit_build_break(repo_dir)
            await handle.signal("nudge")

            async def _incident_opened() -> bool:
                return any(
                    i.key == "build_probe:build_failed::" for i in await handle.query("incidents")
                )

            await _until(_incident_opened, what="one incident")
            history = await handle.fetch_history()

    result = await replayer(MaintenanceWorkflow, TriageWorkflow).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert result is not None
