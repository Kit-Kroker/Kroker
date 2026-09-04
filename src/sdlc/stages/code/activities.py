"""Code stage activities (spec A §5)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temporalio import activity

from ...artifacts.capture import capture_session
from ...core.models import HarnessKind
from ...harness.adapters import HARNESSES, HarnessRequest
from ...harness.containment import ContainmentError, load_policy
from ...harness.models import HarnessRunResult, ToolGrant
from ...observability.logfire_setup import span
from ...vcs.git import _git

if TYPE_CHECKING:
    from ...crew.activities import CrewTurnInput

_log = logging.getLogger(__name__)


@dataclass
class CodingTaskInput:
    harness: HarnessKind
    prompt: str
    worktree: str
    model: str | None = None
    session_id: str | None = None
    timeout_s: int = 3600
    task_id: str = "task"  # E-38: session artifact naming
    attempt: int = 1
    # E-15/E-16 (FR-703). Flags travel; the YAML is loaded activity-side,
    # because the workflow sandbox cannot read files — same split as the
    # agent registry.
    containment_enabled: bool = False
    containment_policy_path: str | None = None
    containment_strict: bool = False
    # E-17: human decisions about suspended tool calls. Written to a grants
    # file activity-side and read by the hook; empty on a first attempt.
    grants: list[ToolGrant] = field(default_factory=list)


def _resolve_containment(
    harness, inp: CodingTaskInput | CrewTurnInput, req: HarnessRequest | None = None
):
    """Load the policy and compile it into `req`, or fail closed.

    Returns (policy, report) — both None when containment is disabled.
    Every failure path raises: an unpoliced run that BELIEVES it is policed
    is the one outcome worse than no containment at all (ADR-17).
    """
    if not inp.containment_enabled:
        return None, None

    policy = load_policy(inp.containment_policy_path)  # raises: fail closed

    if not harness.containment:
        raise ContainmentError(
            f"containment is enabled but the {harness.kind.value} harness "
            f"cannot enforce any layer; refusing to start an unpoliced run "
            f"(ADR-17). Disable containment or choose another harness."
        )

    if req is None:  # unit-test path: compile a probe
        req = HarnessRequest(prompt=inp.prompt, cwd=inp.worktree)
    report = harness.apply_containment(policy, req, inp.grants)

    if inp.containment_strict and report.rules_unenforceable:
        raise ContainmentError(
            f"containment_strict is set and the {harness.kind.value} harness "
            f"leaves these rules unenforceable: "
            f"{', '.join(report.rules_unenforceable)}"
        )
    return policy, report


@activity.defn
async def run_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    """Execute claude -p / opencode run inside the task worktree.

    Long-running: heartbeats while the harness streams output so Temporal
    can detect a hung/dead worker and retry elsewhere.
    """
    harness = HARNESSES[inp.harness]
    req = HarnessRequest(
        prompt=inp.prompt,
        cwd=inp.worktree,
        model=inp.model,
        session_id=inp.session_id,
        timeout_s=inp.timeout_s,
    )
    _, report = _resolve_containment(harness, inp, req)
    with span("harness.run", harness=inp.harness.value, task_id=inp.task_id, attempt=inp.attempt):
        result = await harness.run(req, heartbeat=activity.heartbeat)
    result.containment = report
    try:
        result.denials = harness.normalise_denials(result._raw_stdout)
        result.deferred = harness.normalise_deferral(result._raw_stdout)
    except Exception:  # noqa: BLE001
        # Best-effort, exactly like capture_session: losing the RECORD of a
        # denial must never fail a task whose denial was already enforced.
        # A lost deferral simply means no escalation is raised — the call
        # was already suspended by the hook, not allowed.
        _log.warning("denial normalisation failed", exc_info=True)
    # E-38: capture the transcript. Raw stdout rides a PrivateAttr — it
    # exists only inside this activity and is never written unscrubbed.
    # Best-effort: a failure here (incl. running outside an activity context
    # in tests) must never break the coding task itself.
    try:
        run_id = activity.info().workflow_run_id
    except RuntimeError:
        run_id = "local"
    run_id = run_id or "local"  # temporalio types the field as Optional
    with span("session.capture", task_id=inp.task_id, stdout_bytes=len(result._raw_stdout)):
        ref, digest = capture_session(
            harness, result._raw_stdout, run_id=run_id, task_id=inp.task_id, attempt=inp.attempt
        )
        result.session_ref = ref
        result.session_digest = digest
    # Checkpoint commit — the resume point if anything downstream fails.
    add = _git(["add", "-A"], inp.worktree)
    if add.returncode != 0:
        # Surface git's actual diagnostic (e.g. "dubious ownership", a
        # locked index, a corrupt repo) instead of a bare CalledProcessError
        # that loses stderr when Temporal serializes the exception.
        detail = add.stderr.strip() or add.stdout.strip()
        hint = ""
        if "not a git repository" in detail:
            # create_worktree only returns after `git worktree add` succeeds,
            # so `.git` existed when this activity started. The coding agent
            # itself must have deleted/overwritten it (e.g. ran `git init`
            # on a "greenfield" task) — this is agent misbehavior, not a
            # worktree-setup bug.
            hint = (
                " (the worktree's .git was intact when this task started; "
                "the coding agent likely deleted or reinitialized it)"
            )
        raise RuntimeError(f"git add failed in {inp.worktree}: {detail}{hint}")
    commit = _git(
        ["commit", "-m", f"sdlc checkpoint (exit={result.exit_code})", "--allow-empty"],
        inp.worktree,
    )
    if commit.returncode == 0:
        result.commit_sha = _git(["rev-parse", "HEAD"], inp.worktree).stdout.strip()
    return result


ACTIVITIES = [run_coding_task]

__all__ = [
    "ACTIVITIES",
    "CodingTaskInput",
    "_resolve_containment",
    "run_coding_task",
]
