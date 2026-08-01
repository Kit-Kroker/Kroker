"""Disk-persisted per-run research budget (deps.py's deferred Task 8 item).

`deps.charge()` mutates `ResearchDeps.budget` in place, which accumulates
correctly for a single in-process `agent.run()` but NOT under `TemporalAgent`:
each tool call is a separate activity that receives its own deserialized copy
of `deps`, so a mutation never flows back to the workflow or to the next tool
call. `charge_persisted` makes the cap in `ResearchConfig.max_searches` /
`max_fetches` / `max_cost_usd` actually hold by keeping the running count on
disk at `$SDLC_RUNS_ROOT/<run_id>/research/budget.json`, guarded by a sidecar
lock file so concurrent calls (e.g. `asyncio.gather` over several `get_page`
calls inside one `run_code` script) can't race past the cap.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from .deps import Budget, ResearchDeps, charge

_LOCK_TIMEOUT_S = 10.0
_LOCK_POLL_S = 0.05


def budget_path(run_id: str) -> Path:
    """runs/<run_id>/research/budget.json. Root from $SDLC_RUNS_ROOT (default
    'runs'), mirroring verify.py's pages_dir."""
    root = Path(os.environ.get("SDLC_RUNS_ROOT", "runs"))
    return root / run_id / "research" / "budget.json"


async def _acquire_lock(lock_path: Path) -> None:
    """Exclusive lock via atomic file creation (os.O_CREAT | os.O_EXCL is
    honored on Windows and POSIX alike -- no new dependency needed). Polls
    with asyncio.sleep so a contended lock never blocks the event loop, only
    the calling coroutine. A lock file older than _LOCK_TIMEOUT_S is stolen --
    a crashed holder must never wedge every future charge for the run."""
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > _LOCK_TIMEOUT_S:
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"research budget lock held too long: {lock_path}")
            await asyncio.sleep(_LOCK_POLL_S)


async def charge_persisted(deps: ResearchDeps, *,
                           search: int = 0, fetch: int = 0) -> None:
    """Same contract as deps.charge(): enforces the bound BEFORE accounting
    for it, raising BudgetExceeded (and leaving the on-disk count untouched)
    if `search`/`fetch` would cross deps.max_searches/max_fetches/max_cost_usd.
    Reads and writes the run's budget.json under a lock so the cap holds
    across separate TemporalAgent tool-call activities, each of which sees
    its own fresh (zeroed) `deps.budget`."""
    path = budget_path(deps.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    await _acquire_lock(lock_path)
    try:
        if path.exists():
            budget = Budget.model_validate_json(
                path.read_text(encoding="utf-8"))
        else:
            budget = Budget()
        scratch = deps.model_copy(update={"budget": budget})
        charge(scratch, search=search, fetch=fetch)
        path.write_text(scratch.budget.model_dump_json(), encoding="utf-8")
    finally:
        lock_path.unlink(missing_ok=True)
