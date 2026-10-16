"""Age-based janitor for run worktree dirs — the backstop half of the
A-terminal teardown (vcs/worktree.py ``cleanup_run_worktrees``).

The workflow-side activity fires when a run reaches its terminal state
through its own ``run()`` body. It cannot fire when the run is killed or
crashes past it, so the worker also sweeps periodically: a run dir whose
workflow is no longer Running and that has been untouched for longer
than the grace period is torn down exactly like the activity does
(worktrees removed, branches kept). The grace period is what makes this
safe next to ``resume``: a parked run's dir is touched by its gates and
stages continuously, and a resume reuses the dir in place."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from .worktree import _worktrees_root, cleanup_run_dir

_log = logging.getLogger(__name__)


async def open_workflow_ids(client: Any) -> set[str]:
    """Every currently-Running workflow id on the namespace. Run dirs are
    named after their workflow id, so membership is the whole liveness
    check the sweep needs."""
    query = 'ExecutionStatus = "Running"'
    return {wf.id async for wf in client.list_workflows(query=query)}


async def sweep_once(
    client: Any,
    root: str | None = None,
    *,
    grace_s: float = 24 * 3600,
    now: float | None = None,
) -> list[str]:
    """One pass over the worktrees root. Returns the run dirs swept. A
    dir is swept when its workflow is not Running AND its mtime is older
    than ``grace_s``; anything else is left for a later pass."""
    root = _worktrees_root() if root is None else root
    running = await open_workflow_ids(client)
    if now is None:
        now = time.time()
    swept: list[str] = []
    try:
        entries = list(os.scandir(root))
    except OSError:
        return swept
    for entry in entries:
        if not entry.is_dir() or entry.name in running:
            continue
        try:
            age = now - entry.stat().st_mtime
        except OSError:
            continue
        if age < grace_s:
            continue
        report = cleanup_run_dir(entry.name)
        swept.append(entry.name)
        if report.errors:
            _log.warning(
                "worktree janitor: run %s swept with errors: %s",
                entry.name,
                "; ".join(report.errors),
            )
    return swept


async def worktree_janitor(
    client: Any, *, interval_s: float = 3600.0, grace_s: float = 24 * 3600
) -> None:
    """The worker-lifetime loop. Never raises: a failed pass logs and the
    next one retries — cleanup is idempotent by construction."""
    while True:
        try:
            swept = await sweep_once(client, grace_s=grace_s)
            if swept:
                _log.info("worktree janitor swept %d run dir(s)", len(swept))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _log.exception("worktree janitor pass failed")
        await asyncio.sleep(interval_s)
