"""Worker pools: the harness activity class and its routing helpers (024, E-91).

ADR-9 splits work between two capability pools. The core pool (``ai-sdlc``)
runs workflows and everything cheap and pure; the harness pool
(``KROKER_HARNESS_QUEUE``) runs the activities that touch a harness or a
run's git state. The class authority is this module and nowhere else.

An activity is harness-class when it (rule A.1, as amended by round 024's
research R2):

(a) spawns a coding-harness CLI (``run_coding_task``, ``run_crew_turn``);
(b) executes repository code, or uses the repository remote (tests, lint,
    security scans, coverage, integration checks, pull requests, deploys);
(c) creates, mutates, removes **or reads** a run's worktree, integration
    branch or verification branch — the R2 amendment extends the original
    write-only rule to reads of run state; reads of the canonical checkout
    and by-sha blob reads of repositories the run does not write stay core.

When unsure, route to harness: a misplaced read costs one harness slot,
while a misplaced write breaks the split (advisor D2). This module is a
leaf — it imports only the standard library, so workflow code may import
it freely (it must never import ``sdlc.worker`` or any stage).
"""

from __future__ import annotations

import enum
import os
import re
from collections.abc import Mapping
from typing import Any

HARNESS_QUEUE_DEFAULT = "ai-sdlc-harness"
"""The documented default harness queue name.

Used only when an operator sets ``KROKER_HARNESS_QUEUE`` to the
empty-but-on sentinel ``"default"``.
"""

HARNESS_ACTIVITIES: frozenset[str] = frozenset(
    {
        # (a) spawn a coding harness CLI
        "run_coding_task",
        "run_crew_turn",
        # (c) create/mutate/remove a run's worktree or branches
        "create_worktree",
        "merge_into_integration",
        "setup_integration_branch",
        "build_verification_branch",
        "prepare_base_worktree",
        "remove_verification_tree",
        "cleanup_run_worktrees",
        "prepare_crew",
        "checkpoint_round",
        "check_test_drift",
        "measure_code_axis",
        # (c, amended) read a run's worktree or branch state
        "read_round",
        "get_task_diff",
        "read_committed_bytes",
        "is_ancestor",
        # (b) execute repo code, or use the repo remote
        "grade_oracle",
        "triage_build_probe",
        "run_test_suite",
        "run_lint",
        "scoped_security_scan",
        "measure_coverage",
        "run_integration_checks",
        "open_pull_request",
        "deploy_apply",
        "deploy_rollback",
        "smoke_check",
    }
)
"""The 28 activity names in the harness class (research R2's rows)."""

_QUEUE_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,200}")


class PoolMode(enum.StrEnum):
    """Which pool(s) a worker process hosts (research R5)."""

    ALL = "all"
    CORE = "core"
    HARNESS = "harness"


def on_harness(opts: Mapping[str, Any], queue: str | None) -> dict[str, Any]:
    """Copy ``opts`` for an activity call, routed to ``queue`` when set.

    Returns ``dict(opts)`` unchanged when ``queue`` is falsy, so with
    routing off no ``task_queue`` key reaches the SDK and the command is
    byte-identical to today's. With routing on, splat the result into the
    call: ``workflow.execute_activity(fn, **on_harness(opts, q))``.
    """
    if not queue:
        return dict(opts)
    return {**opts, "task_queue": queue}


def resolve_harness_queue(
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve ``KROKER_HARNESS_QUEUE`` from ``env`` (default: ``os.environ``).

    Unset or blank means single pool, routing off (``None``). The exact
    value ``"default"`` maps to :data:`HARNESS_QUEUE_DEFAULT`. Any other
    value must match ``^[A-Za-z0-9._-]{1,200}$`` (no trimming), else
    :class:`ValueError`.
    """
    raw = (os.environ if env is None else env).get("KROKER_HARNESS_QUEUE")
    if raw is None or raw.strip() == "":
        return None
    if raw == "default":
        return HARNESS_QUEUE_DEFAULT
    if _QUEUE_NAME_RE.fullmatch(raw) is None:
        raise ValueError(
            "KROKER_HARNESS_QUEUE must match ^[A-Za-z0-9._-]{1,200}$ "
            f"(got {raw!r}); unset it for single-pool routing-off, or use a "
            'valid queue name (the sentinel "default" means '
            f"{HARNESS_QUEUE_DEFAULT!r})"
        )
    return raw
