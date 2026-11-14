"""US2 e2e: silence and configuration can never open the gate (023a T024).

RED discipline for this file is RUN-AND-RECORD: T018 already implemented the
workflow, so most tests VERIFY existing behaviour; any FAILING assertion
names a real gap T025 must fix. No assertion is weakened to pass.

Contract: tasks.md T024 (US2 AC1–5, FR-010/011/012, SC-003).
Scaffolding: tests/maintenance/test_workflow_us1.py (fakes, SdlcPydanticAIPlugin,
pydantic_data_converter, _until polling, fake notify, fake_triage activities
keyed off the fixture repo), tests/maintenance/test_inbox_decide.py part (b)
for the transport-level reject.

Time: a time-skipping env advances gate timers only via ``env.sleep`` —
each timeout test configures ``gate_timeout_hours=1`` and sleeps 2 virtual
hours (twice the nominal timeout), per tests/test_gate_timeout_action.py.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.channels.contract import Reply
from sdlc.channels.transport import Selector, resolve, submit
from sdlc.core.models import GateOutcome
from sdlc.maintenance.models import (
    MaintenanceConfig,
    MaintenanceState,
    RepairProposal,
)
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import fake_agent_activities
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES
from tests.replay.harness import replayer

with workflow.unsafe.imports_passed_through():
    from sdlc.notify.contract import NotifyInput, Results

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us2"

ANALYSIS = "The evidence supports this repair; restore the broken piece."


def _proposal(self_confidence: float = 0.9) -> RepairProposal:
    return RepairProposal(analysis=ANALYSIS, actions=[], self_confidence=self_confidence)


def _state(repo, **kw) -> MaintenanceState:
    base = dict(project="demo", repo_dir=str(repo), ack_unattended_build_probe=True)
    base.update(kw)
    return MaintenanceState(config=MaintenanceConfig(**base))


def _acts(proposal: RepairProposal):
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
async def fake_notify(inp: NotifyInput) -> Results:  # noqa: ANN001, ARG001
    return Results(results=[])


def _counting_notify(calls: list):
    @activity.defn(name="notify")
    async def notify(inp: NotifyInput) -> Results:  # noqa: ANN001, ARG001
        calls.append(inp)
        return Results(results=[])

    return notify


async def _await_baseline(handle) -> None:
    async def _baseline_recorded() -> bool:
        return (await handle.query(MaintenanceWorkflow.maintenance_state)).baseline_recorded

    await _until(_baseline_recorded, what="cycle 1 baseline")


async def _await_pending(handle, gate: str):
    async def _gate_pending() -> bool:
        pending = await handle.query(MaintenanceWorkflow.pending_decisions)
        return any(p.gate == gate for p in pending)

    await _until(_gate_pending, what=f"the {gate} gate")
    pending = await handle.query(MaintenanceWorkflow.pending_decisions)
    return next(p for p in pending if p.gate == gate)


def _incidents(handle):
    return handle.query(MaintenanceWorkflow.incidents)


# --------------------------------------------------------------------------- #
# AC1 / SC-003: below-threshold plan + silence past gate_timeout_hours -> timed_out
# --------------------------------------------------------------------------- #


async def test_silence_past_gate_timeout_times_out_never_approves(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(_proposal(0.9)), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir, gate_timeout_hours=1),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            from tests.maintenance.conftest import commit_build_break

            commit_build_break(repo_dir)
            await handle.signal("nudge")  # cycle 2: detect, plan, gate

            await _await_pending(handle, "repair:1")  # human-gated, not auto-approved

            await env.sleep(7200)  # 2h -- twice the nominal 1h timeout

            async def _timed_out() -> bool:
                incs = await _incidents(handle)
                return bool(incs) and incs[0].state.value == "timed_out"

            await _until(_timed_out, what="the incident to time out")
            inc = (await _incidents(handle))[0]
            # SC-003: timeout is terminal reject-shaped silence; the gate can
            # never approve itself by waiting.
            assert inc.state.value == "timed_out"
            assert inc.state.value != "approved_not_executed"
            assert inc.decision is not None
            assert inc.decision.decided_by == "timeout"
            assert inc.decision.outcome is GateOutcome.REJECT


# --------------------------------------------------------------------------- #
# AC2: JUDGEMENT at self 1.0 -> effective <= 0.6 -> human gate, never policy
# --------------------------------------------------------------------------- #


async def test_judgement_finding_at_self_1_0_is_human_gated_not_auto_approved(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(_proposal(1.0)), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            from tests.maintenance.conftest import commit_provider_credential

            commit_provider_credential(repo_dir)
            await handle.signal("nudge")  # cycle 2

            item = await _await_pending(handle, "repair:1")
            incs = await _incidents(handle)
            inc = next(i for i in incs if i.finding and i.finding.rule == "aws_access_key_id")
            # The proposer's self-rating is capped: JUDGEMENT ceiling 0.6 (and
            # -0.15 not-reproduced on the first detect), so even 1.0 cannot
            # clear the 0.8 threshold.
            assert inc.plan is not None
            assert inc.plan.self_confidence == 1.0
            assert inc.plan.effective <= 0.6
            assert inc.plan.effective < 0.8
            # The gate is open and pending a HUMAN: no policy decision landed.
            assert inc.state.value == "awaiting_decision"
            assert inc.decision is None
            assert item.gate == "repair:1"


# --------------------------------------------------------------------------- #
# AC3: MECHANICAL (.env) reproduced on two consecutive cycles -> policy approval
# --------------------------------------------------------------------------- #


async def test_mechanical_reproduced_on_two_cycles_reaches_policy_approval(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(_proposal(0.9)), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            from tests.maintenance.conftest import commit_env_file

            commit_env_file(repo_dir)
            await handle.signal("nudge")  # cycle 2: first detect

            async def _env_tracked_planned() -> bool:
                incs = await _incidents(handle)
                return any(
                    i.finding and i.finding.rule == "env_file_tracked" and i.plan is not None
                    for i in incs
                )

            await _until(_env_tracked_planned, what="the env_file_tracked plan")
            await handle.signal("nudge")  # cycle 3: reproduced

            async def _env_tracked_decided() -> bool:
                incs = await _incidents(handle)
                tracked = [i for i in incs if i.finding and i.finding.rule == "env_file_tracked"]
                return bool(tracked) and tracked[0].decision is not None

            await _until(_env_tracked_decided, what="the reproduced plan to be decided")
            inc = next(
                i
                for i in await _incidents(handle)
                if i.finding and i.finding.rule == "env_file_tracked"
            )
            # Reproduced pricing: MECHANICAL ceiling 0.95 with no penalties,
            # so effective = min(0.9, 0.95) = 0.9 clears the 0.8 threshold and
            # policy approves. NOT the 0.8 first-cycle floor.
            assert inc.plan is not None
            assert inc.plan.floor == pytest.approx(0.95)
            assert inc.plan.effective == pytest.approx(0.9)
            assert inc.state.value == "approved_not_executed"
            assert inc.decision is not None
            assert inc.decision.decided_by == "policy"
            assert inc.decision.outcome is GateOutcome.APPROVE


# --------------------------------------------------------------------------- #
# AC4: human reject with a comment -> rejected; no re-plan on that incident
# --------------------------------------------------------------------------- #


async def test_human_reject_records_actor_reason_and_never_replans(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(_proposal(0.9)), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            from tests.maintenance.conftest import commit_build_break

            commit_build_break(repo_dir)
            await handle.signal("nudge")  # cycle 2
            await _await_pending(handle, "repair:1")

            selector = Selector(reply_kind="gate", name="repair:1")
            reply = Reply(outcome=GateOutcome.REJECT, text="wrong approach, rotate first")

            pending = await resolve(handle, selector)
            await submit(handle, pending, reply)

            async def _rejected() -> bool:
                incs = await _incidents(handle)
                return bool(incs) and incs[0].state.value == "rejected"

            await _until(_rejected, what="the incident to become rejected")
            inc = (await _incidents(handle))[0]
            assert inc.decision is not None
            assert inc.decision.decided_by == "human"
            assert inc.decision.outcome is GateOutcome.REJECT
            assert inc.note == "wrong approach, rotate first"
            assert inc.plan_attempts == 0  # zero FAILED attempts; the plan landed first try

            # Another cycle must not re-plan the (now terminal) incident.
            await handle.signal("nudge")  # cycle 3

            async def _cycle_three() -> bool:
                return (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle == 3

            await _until(_cycle_three, what="cycle 3 to run")
            inc_after = (await _incidents(handle))[0]
            assert inc_after.no == inc.no
            assert inc_after.state.value == "rejected"
            assert inc_after.plan_attempts == 0
            assert inc_after.plan == inc.plan
            assert inc_after.decision == inc.decision


# --------------------------------------------------------------------------- #
# AC5: REVISE is treated as reject, guidance kept in note
# --------------------------------------------------------------------------- #


async def test_revise_is_reject_with_guidance_in_note(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(_proposal(0.9)), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            from tests.maintenance.conftest import commit_build_break

            commit_build_break(repo_dir)
            await handle.signal("nudge")
            await _await_pending(handle, "repair:1")

            selector = Selector(reply_kind="gate", name="repair:1")
            reply = Reply(outcome=GateOutcome.REVISE, text="split the fix into two steps")

            pending = await resolve(handle, selector)
            await submit(handle, pending, reply)

            async def _rejected() -> bool:
                incs = await _incidents(handle)
                return bool(incs) and incs[0].state.value == "rejected"

            await _until(_rejected, what="the REVISE to land as reject")
            inc = (await _incidents(handle))[0]
            assert inc.state.value == "rejected"
            assert inc.decision is not None
            assert inc.decision.decided_by == "human"
            assert "revise treated as reject" in inc.note
            assert "split the fix into two steps" in inc.note


# --------------------------------------------------------------------------- #
# FR-012: the gate's notify activity is called when a gate opens pending
# --------------------------------------------------------------------------- #


async def test_gate_opening_calls_the_notify_activity(repo_dir):
    calls: list = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(_proposal(0.9)), _counting_notify(calls)],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            from tests.maintenance.conftest import commit_build_break

            commit_build_break(repo_dir)
            # The notify activity's schedule_to_start is 5s (gates.py
            # NOTIFY_ACT); under auto time-skipping virtual time races past it
            # before the worker picks the activity up. Disable skipping while
            # the gate opens so the notification is observed as shipped.
            # Precedent: tests/test_gate_timeout_action.py:124,174.
            with env.auto_time_skipping_disabled():
                await handle.signal("nudge")  # cycle 2: gate opens

                await _await_pending(handle, "repair:1")
                await _until(lambda: len(calls) >= 1, what="the notify call")
            assert len(calls) >= 1
            assert (await _incidents(handle))[0].state.value == "awaiting_decision"


# --------------------------------------------------------------------------- #
# R13: a history that includes the human decision replays clean
# --------------------------------------------------------------------------- #


async def test_history_with_a_decision_replays_clean(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_acts(_proposal(0.9)), fake_notify],
        ):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")
            await _await_baseline(handle)

            from tests.maintenance.conftest import commit_build_break

            commit_build_break(repo_dir)
            await handle.signal("nudge")
            await _await_pending(handle, "repair:1")

            selector = Selector(reply_kind="gate", name="repair:1")
            reply = Reply(outcome=GateOutcome.REJECT, text="replay me")

            pending = await resolve(handle, selector)
            await submit(handle, pending, reply)

            async def _rejected() -> bool:
                incs = await _incidents(handle)
                return bool(incs) and incs[0].state.value == "rejected"

            await _until(_rejected, what="the reject to land")
            history = await handle.fetch_history()

    result = await replayer(MaintenanceWorkflow, TriageWorkflow).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert result is not None
