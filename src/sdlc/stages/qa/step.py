"""QA stage step execution (spec A §3.3).

Executes the qa stage for a dev task: runs the deterministic test suite activity
(or uses a pre-computed QAOutput if provided), generates the clean-context QA prompt
against the frozen contract assertions and diff, executes the QA proposer agent via
ctx.run_role, and returns the resulting QAReport.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...core.context import StageContext
from ...core.models import PipelineConfig, RoleConfig, RoleUsage
from .activities import QAInput, run_test_suite
from .models import QAReport
from .prompts import qa_prompt

DEFAULT_TEST_CMD = "pytest -q --maxfail=25"
_TEST_OUTPUT_MAX = 1500

_LONG_ACT_HEARTBEAT_MINUTES = int(os.environ.get("SDLC_LONG_ACTIVITY_HEARTBEAT_MINUTES", "60"))
_LONG_ACT_TIMEOUT_HOURS = int(os.environ.get("SDLC_LONG_ACTIVITY_TIMEOUT_HOURS", "4"))
_LONG_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(hours=_LONG_ACT_TIMEOUT_HOURS),
    heartbeat_timeout=timedelta(minutes=_LONG_ACT_HEARTBEAT_MINUTES),
    retry_policy=RetryPolicy(maximum_attempts=2),
)


def _contract_shell_cmd(commands: list[str] | None, default: str) -> str:
    if not commands:
        return default
    return " && ".join(commands)


def _long_act(role_cfg: RoleConfig | None = None) -> workflow.ActivityConfig:
    """LONG_ACT, with a role's own timeout/heartbeat overrides if it has any.

    Defaults are the env-tunable 4h/60m (SDLC_LONG_ACTIVITY_*), matching
    TaskHost's helper byte-for-byte: a fallback path here with different
    defaults would silently change the test-suite timeout budget when P3
    moves the qa_raw computation into this slice.
    """
    if role_cfg is None:
        return _LONG_ACT
    hours = role_cfg.activity_timeout_hours
    minutes = role_cfg.activity_heartbeat_minutes
    if hours is None and minutes is None:
        return _LONG_ACT
    return workflow.ActivityConfig(
        start_to_close_timeout=timedelta(
            hours=hours if hours is not None else _LONG_ACT_TIMEOUT_HOURS
        ),
        heartbeat_timeout=timedelta(
            minutes=minutes if minutes is not None else _LONG_ACT_HEARTBEAT_MINUTES
        ),
        retry_policy=RetryPolicy(maximum_attempts=2),
    )


def _fix_loop_issues(qa: Any, qa_raw: Any, review: Any = None, adversary: Any = None) -> str:
    """Assemble the retry prompt's issue list from BOTH judges.

    The task gate anchors on `qa_raw.tests_passed` — the subprocess exit code
    — because an LLM opinion must never overwrite a deterministic signal. The
    retry prompt has to carry that same evidence, or the agent is asked to fix
    something it cannot see: a clean-context QA that judges the diff
    contract-compliant while pytest is red leaves the LLM-side issue list
    empty, and the fix loop then sends `Fix them:\\n- ` with nothing after the
    dash (bench-todo-api-greenfield-1785444047: 8 of 12 attempts burned
    re-confirming the stack directive while the real ModuleNotFoundError was
    never shown). Returns "" when neither judge has anything actionable —
    callers must treat that as a harness fault, not another attempt.

    `adversary` is the optional decorrelated second opinion (spec part 2).
    Its blocking findings join the primary's, because on a split the primary
    approved and contributed nothing -- without the union the retry prompt
    would carry no instruction at all."""
    deterministic: list[str] = []
    if not qa_raw.tests_passed:
        if qa_raw.issues:
            deterministic.append(
                "test command failed:\n" + "\n".join(qa_raw.issues)[-_TEST_OUTPUT_MAX:]
            )
        if qa_raw.failing_tests:
            deterministic.append("failing tests: " + ", ".join(qa_raw.failing_tests[:25]))
        if getattr(qa_raw, "stopped_early", False):
            # Without this the agent reads a truncated run as the whole
            # story and starts fixing the one test it was shown. In the P2
            # demonstration that test was unrelated to every task that
            # attacked it, and the tasks' own tests -- sorting after it --
            # never ran at all.
            deterministic.append(
                "NOTE: the test run STOPPED EARLY (-x / --maxfail), so tests "
                "ordered after the failure above did not run. This is a "
                "partial result, not a verdict on your work: the failure "
                "shown may be unrelated to your task, and your own tests may "
                "not have executed. Check whether it is yours before "
                "changing it."
            )
    review_issues = [
        f"{f.severity}: {f.assertion} — {f.detail}"
        for r in (review, adversary)
        if r is not None and getattr(r, "blocking_findings", None)
        for f in r.blocking_findings
    ]
    return "\n- ".join(list(qa.issues or qa.failing_tests) + deterministic + review_issues)


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    task: Any,
    contract: Any,
    diff: dict[str, Any],
    worktree: str,
    qa_agent: Any,
    qa_raw: QAReport | None = None,
    qa_model: str = "",
    qa_spend: RoleUsage | None = None,
) -> QAReport:
    """Execute clean-context QA analysis against the task diff and test outputs.

    Never calls a gate: QA is a clean-context validator without direct gates.
    """
    if qa_raw is None:
        test_commands = getattr(contract, "test_commands", None) if contract else None
        test_cmd = _contract_shell_cmd(test_commands, DEFAULT_TEST_CMD)
        role_cfg = cfg.roles.get(getattr(task, "role", "dev"), cfg.roles.get("dev"))
        qa_raw = await workflow.execute_activity(
            run_test_suite,
            QAInput(worktree=worktree, test_cmd=test_cmd),
            **_long_act(cfg.roles.get("test", role_cfg)),
        )

    assertions: list[str] = (
        list(contract.assertions)
        if contract and getattr(contract, "assertions", None)
        else list(getattr(task, "acceptance_criteria", []))
    )

    if not qa_model or not isinstance(qa_model, str):
        rc = cfg.roles.get("qa")
        if rc is not None and isinstance(rc.model, str) and rc.model:
            qa_model = rc.model
        elif hasattr(qa_agent, "model"):
            m = qa_agent.model
            m_name = getattr(m, "model_name", None) or getattr(m, "name", None)
            if isinstance(m_name, str):
                qa_model = m_name
            elif isinstance(m, str):
                qa_model = m
            else:
                qa_model = "unknown"
        else:
            qa_model = "unknown"

    if qa_spend is None:
        qa_spend = RoleUsage(role="qa", model=qa_model)

    prompt = qa_prompt(
        assertions,
        qa_raw.model_dump_json(),
        diff.get("stat", "") if isinstance(diff, dict) else "",
        diff.get("patch", "") if isinstance(diff, dict) else "",
    )

    role_res = await ctx.run_role(
        cfg,
        "qa",
        qa_model,
        qa_agent,
        prompt,
        into=qa_spend,
    )
    output: QAReport = getattr(role_res, "output", role_res)
    return output
