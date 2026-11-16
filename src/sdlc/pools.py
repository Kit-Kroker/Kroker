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

import asyncio
import dataclasses
import enum
import logging
import os
import re
import socket
import time
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


# ----------------------------------------------------------------- boot plan
#
# The unit-testable core of ``worker.main``'s pool selection (research R5;
# the truth table in data-model.md is normative).


@dataclasses.dataclass(frozen=True)
class PoolBootPlan:
    """Which workers a process should build, per the R5 truth table."""

    core_worker: bool
    harness_worker: bool
    janitor: bool
    cap: int | None
    queue: str | None


def pool_identity(pool: str) -> str:
    """The worker-boot G-3 identity: ``<pool>@<hostname>:<pid>``."""
    return f"{pool}@{socket.gethostname()}:{os.getpid()}"


def pool_boot_plan(
    mode: PoolMode | str,
    queue: str | None,
    cap: int | None,
) -> PoolBootPlan:
    """Validate the R5 refusals and lay out the workers to build.

    Refusals raise :class:`ValueError` naming the environment variable at
    fault and the fix, mirroring worker-boot contract G-2 (the message is
    what ``worker.main`` exits with, before connecting to Temporal).
    """
    if cap is not None and cap < 1:
        raise ValueError(
            f"KROKER_HARNESS_CAP must be an integer >= 1 (got {cap}); unset it for the SDK default"
        )
    m = PoolMode(mode)
    if m is PoolMode.ALL:
        if queue is None:
            if cap is not None:
                raise ValueError(
                    "KROKER_HARNESS_CAP is set without KROKER_HARNESS_QUEUE; "
                    "a cap only applies to the harness worker, which needs "
                    "a queue — set KROKER_HARNESS_QUEUE or unset the cap"
                )
            # Today, exactly: one worker on the core queue, janitor on.
            return PoolBootPlan(True, False, True, cap=None, queue=None)
        return PoolBootPlan(True, True, True, cap=cap, queue=queue)
    if queue is None:
        raise ValueError(
            f"KROKER_WORKER_POOL={m.value} needs KROKER_HARNESS_QUEUE to "
            "name the harness queue — set it (or use "
            f'{HARNESS_QUEUE_DEFAULT!r} via the sentinel "default")'
        )
    if m is PoolMode.CORE:
        if cap is not None:
            logging.getLogger(__name__).warning(
                "KROKER_HARNESS_CAP=%s is ignored in core mode: the cap "
                "limits the harness worker only (unset it to silence this)",
                cap,
            )
        return PoolBootPlan(True, False, False, cap=None, queue=queue)
    # PoolMode.HARNESS
    return PoolBootPlan(False, True, True, cap=cap, queue=queue)


def boot_plan_from_env(env: Mapping[str, str] | None = None) -> PoolBootPlan:
    """Read the three pool variables from ``env`` (default: ``os.environ``).

    An explicitly passed empty mapping means "no variables" and never
    falls back to the process environment. Blank values mean unset
    (``KROKER_WORKER_POOL=''`` is the default ``all``), consistent with
    the queue variable's blank handling.
    """
    source = os.environ if env is None else env
    raw_pool = source.get("KROKER_WORKER_POOL")
    if raw_pool is None or raw_pool.strip() == "":
        mode: PoolMode | str = PoolMode.ALL
    else:
        try:
            mode = PoolMode(raw_pool)
        except ValueError as exc:
            raise ValueError(
                f"KROKER_WORKER_POOL must be exactly one of all|core|harness (got {raw_pool!r})"
            ) from exc
    queue = resolve_harness_queue(source)
    raw_cap = source.get("KROKER_HARNESS_CAP")
    cap: int | None = None
    if raw_cap is not None and raw_cap.strip() != "":
        try:
            cap = int(raw_cap)
        except ValueError as exc:
            raise ValueError(
                f"KROKER_HARNESS_CAP must be an integer >= 1 (got {raw_cap!r})"
            ) from exc
    return pool_boot_plan(mode, queue, cap)


# ------------------------------------------------------------ poller check (R6)
#
# Start paths refuse to launch when routing is on and the harness queue has
# no fresh poller: a run whose harness activities queue forever is the F1
# failure the fail-fast exists to prevent.


class HarnessQueueUnpolled(RuntimeError):
    """No worker has polled the harness task queue within the freshness window."""


async def require_harness_poller(
    client: Any,
    queue: str,
    *,
    freshness_s: float = 90,
    timeout_s: float = 5,
) -> None:
    """Raise :class:`HarnessQueueUnpolled` unless a worker polled ``queue``.

    Asks the activity task queue for its pollers and requires at least one
    whose ``last_access_time`` is within ``freshness_s`` of now. The
    temporalio.api imports stay inside the function so importing this leaf
    stays cheap for workflow code (data-model: stdlib + temporalio.api).
    """
    from temporalio.api.enums.v1 import TaskQueueType
    from temporalio.api.taskqueue.v1 import TaskQueue
    from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest

    request = DescribeTaskQueueRequest(
        namespace=client.namespace,
        task_queue=TaskQueue(name=queue),
        task_queue_type=TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY,
    )
    try:
        response = await asyncio.wait_for(
            client.workflow_service.describe_task_queue(request), timeout_s
        )
    except TimeoutError as exc:
        raise HarnessQueueUnpolled(
            f"task queue {queue!r} could not be described within {timeout_s}s — "
            "start a harness worker with KROKER_WORKER_POOL=harness "
            f"(and KROKER_HARNESS_QUEUE={queue!r})"
        ) from exc
    now = time.time()
    for poller in response.pollers:
        last = poller.last_access_time
        accessed = last.seconds + last.nanos / 1e9
        if now - accessed <= freshness_s:
            return
    raise HarnessQueueUnpolled(
        f"task queue {queue!r} has no harness worker poller fresher than "
        f"{freshness_s}s — start one with KROKER_WORKER_POOL=harness "
        f"(and KROKER_HARNESS_QUEUE={queue!r})"
    )
