"""The per-task escalation gate must honour REVISE, not collapse it to
quarantine.

Found by the first real brownfield run (P2's exit criterion, 2026-08-19). A
task exhausted its fix loop, escalated, and the operator answered REVISE with
specific guidance; `_dev_task` recorded the guidance in `TaskResult.notes` and
quarantined the task anyway, which fails the whole run
(`failed:quarantined-tasks`). So APPROVE was the only outcome a run could
survive -- a gate documented as "accept, retry, or quarantine" offering, in
practice, "accept or kill the run".

Nothing under tests/ drove this path before this module, which is why the gap
survived: `GateDecision.approved` is False for both REJECT and REVISE, and the
call site branched on that boolean instead of on `outcome` -- exactly what the
property's own docstring warns callers not to do.

The stage gates already do this correctly via `_revisable_stage`; these tests
pin the same contract at the task gate.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.activities import (
    CodingTaskInput,
    HarnessRunResult,
    QAInput,
    evaluate_gate,
)
from sdlc.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    QAReport,
)
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import git_fakes_except

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_GATE = "task:t1"


@dataclass
class TaskScript:
    """Module-level state so a test can script the coding/QA pair without
    threading config through FeatureWorkflow's whole call chain (the
    fake_deploy.DeployScript pattern).

    `qa_failures` is consumed one entry per run_test_suite call, so a REVISE
    retry can succeed where the bounded fix loop failed.
    """

    qa_failures: int = 0
    coding_calls: int = 0
    prompts: list[str] = field(default_factory=list)


SCRIPT = TaskScript()


def reset(**over) -> TaskScript:
    global SCRIPT
    SCRIPT = TaskScript(**over)
    return SCRIPT


@activity.defn(name="run_coding_task")
async def scripted_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    SCRIPT.coding_calls += 1
    SCRIPT.prompts.append(inp.prompt)
    return HarnessRunResult(
        harness=inp.harness,
        session_id="s1",
        exit_code=0,
        summary="implemented",
        commit_sha="cafe1234",
        input_tokens=1000,
        output_tokens=200,
        context_window=200000,
    )


@activity.defn(name="run_test_suite")
async def scripted_test_suite(inp: QAInput) -> QAReport:
    if SCRIPT.qa_failures > 0:
        SCRIPT.qa_failures -= 1
        return QAReport(
            tests_passed=False, failing_tests=["test_hello"], issues=["assert 500 == 200"]
        )
    return QAReport(tests_passed=True)


@activity.defn(name="notify")
async def _noop_notify(inp: NotifyInput) -> Results:
    # Escalating a gate delivers a notification. Registering a no-op keeps a
    # missing activity from surfacing as a confusing NotFoundError instead of
    # the assertion the test is actually about (the hazard
    # test_board_workflow.py records).
    return Results(results=[])


def _scripted_fakes():
    """GIT_FAKES with the coding/QA pair swapped for the scripted ones."""
    return [
        *git_fakes_except("run_coding_task", "run_test_suite"),
        scripted_coding_task,
        scripted_test_suite,
    ]


def _cfg(max_fix_attempts: int = 1, max_gate_rounds: int = 2):
    """Only the task gate is HARD: the run must reach the escalation without
    the driver having to service every other gate."""
    cfg = e2e_config()
    cfg.gates = {
        name: GateConfig(policy=GatePolicy.OFF)
        for name in ("clarify", "architecture", "plan", "merge", "deploy")
    }
    cfg.gates[TASK_GATE] = GateConfig(policy=GatePolicy.HARD)
    cfg.default_gate_policy = GatePolicy.OFF
    cfg.max_fix_attempts = max_fix_attempts
    cfg.max_gate_rounds = max_gate_rounds
    return cfg


async def _wait_for_status(handle, target: str, timeout_s: float = 20.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"timed out waiting for {target!r}; "
        f"last seen {await handle.query(FeatureWorkflow.pending_gate)!r}"
    )


async def _run(cfg, tmp_path, monkeypatch, tag, driver):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=tag,
            workflows=[FeatureWorkflow, DeploymentWorkflow],
            activities=[
                evaluate_gate,
                export_run_artifacts,
                _noop_notify,
                *_scripted_fakes(),
                *fake_agent_activities(AGENT_SPECS),
            ],
            plugins=[PydanticAIPlugin()],
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[greenfield_idea(), cfg, None],
                id=f"{tag}-{uuid.uuid4()}",
                task_queue=tag,
            )
            with env.auto_time_skipping_disabled():
                await driver(handle)
            return await handle.result()


async def _answer_clarify(handle):
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])


async def test_task_gate_revise_retries_with_the_operator_guidance(tmp_path, monkeypatch):
    """REVISE runs another coding attempt carrying the guidance, and the run
    survives. This is the defect the P2 demonstration run hit."""
    # 2 failures = attempt 1 and its one permitted fix, so the loop is spent
    # and the gate fires. The third call passes, so a granted retry succeeds.
    reset(qa_failures=2)

    async def driver(handle):
        await _answer_clarify(handle)
        await _wait_for_status(handle, f"awaiting:{TASK_GATE}")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(
                gate=TASK_GATE,
                round=1,
                outcome=GateOutcome.REVISE,
                decided_by="human",
                guidance="revert the shared fixture edits",
            ),
        )

    result = await _run(_cfg(), tmp_path, monkeypatch, "tgr1", driver)

    assert result != "failed:quarantined-tasks", (
        "REVISE at a task gate must not quarantine the task: the operator "
        "asked for a retry, not for the run to die"
    )
    assert SCRIPT.coding_calls == 3, (
        f"expected a third coding attempt after REVISE, got {SCRIPT.coding_calls}"
    )
    assert any("revert the shared fixture edits" in p for p in SCRIPT.prompts), (
        "the operator's guidance must reach the retry prompt; otherwise the "
        "agent re-rolls the same dice that already failed twice"
    )


async def test_task_gate_reject_still_quarantines(tmp_path, monkeypatch):
    """Regression guard: only REVISE changes meaning. REJECT stays terminal."""
    reset(qa_failures=2)

    async def driver(handle):
        await _answer_clarify(handle)
        await _wait_for_status(handle, f"awaiting:{TASK_GATE}")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=TASK_GATE, round=1, outcome=GateOutcome.REJECT, decided_by="human"),
        )

    result = await _run(_cfg(), tmp_path, monkeypatch, "tgr2", driver)
    assert result == "failed:quarantined-tasks", result


async def test_task_gate_revise_is_bounded_by_max_gate_rounds(tmp_path, monkeypatch):
    """Revise cannot loop forever: after max_gate_rounds the run stops asking
    and the task is quarantined. Mirrors _revisable_stage's bound."""
    # Never satisfiable -- every QA call fails, so every granted retry fails.
    reset(qa_failures=99)

    async def driver(handle):
        await _answer_clarify(handle)
        for round in (1, 2):
            await _wait_for_status(handle, f"awaiting:{TASK_GATE}")
            await handle.signal(
                FeatureWorkflow.submit_gate_decision,
                GateDecision(
                    gate=TASK_GATE,
                    round=round,
                    outcome=GateOutcome.REVISE,
                    decided_by="human",
                    guidance=f"try again ({round})",
                ),
            )
        # Round 3 is the bound's final gate: the run must ask once more
        # rather than looping, and a REJECT there ends it.
        await _wait_for_status(handle, f"awaiting:{TASK_GATE}")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=TASK_GATE, round=3, outcome=GateOutcome.REJECT, decided_by="human"),
        )

    result = await _run(_cfg(max_gate_rounds=2), tmp_path, monkeypatch, "tgr3", driver)
    assert result == "failed:quarantined-tasks", result
