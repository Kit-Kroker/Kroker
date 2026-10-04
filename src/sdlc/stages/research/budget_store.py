"""Disk-persisted per-run research budget (deps.py's deferred Task 8 item).

`deps.charge()` mutates `ResearchDeps.budget` in place, which accumulates
correctly for a single in-process `agent.run()` but NOT under durable execution:
each tool call is a separate activity that receives its own deserialized copy
of `deps`, so a mutation never flows back to the workflow or to the next tool
call. `charge_persisted` makes the cap in `ResearchConfig.max_searches` /
`max_fetches` / `max_cost_usd` actually hold by keeping the running count on
disk at `$SDLC_RUNS_ROOT/<run_id>/research/budget-<scope>.json` (one counter
per scope: "run" is the whole-run ceiling, "sq-<id>" is one sub-question's
allowance), guarded by a sidecar lock file so concurrent calls (e.g.
`asyncio.gather` over several `get_page` calls inside one `run_code` script)
can't race past the cap.
"""

from __future__ import annotations

import asyncio
import itertools
import os
import time
from pathlib import Path

from .deps import Budget, BudgetExceeded, ResearchDeps, charge

_LOCK_TIMEOUT_S = 10.0
_LOCK_POLL_S = 0.05
_TMP_COUNTER = itertools.count()


def budget_path(run_id: str, scope: str = "run") -> Path:
    """runs/<run_id>/research/budget-<scope>.json. Root from $SDLC_RUNS_ROOT
    (default 'runs'), mirroring verify.py's pages_dir.

    `scope` separates counters: "run" is the whole-run ceiling, "sq-<id>" is
    one sub-question's own allowance. Without separate counters a greedy
    early sub-question drains the pool and later ones get nothing -- the
    depth problem fan-out exists to fix.
    """
    root = Path(os.environ.get("SDLC_RUNS_ROOT", "runs"))
    return root / run_id / "research" / f"budget-{scope}.json"


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
                raise TimeoutError(f"research budget lock held too long: {lock_path}") from None
            await asyncio.sleep(_LOCK_POLL_S)


def _read_counter(path: Path) -> Budget:
    """A counter's current value; a missing file is an empty budget. An
    unreadable (truncated/garbage) file still raises -- the store never
    auto-resets it, that would hand the budget back."""
    if path.exists():
        return Budget.model_validate_json(path.read_text(encoding="utf-8"))
    return Budget()


def _publish_counter(path: Path, budget: Budget) -> None:
    """Publish atomically (write_page's pattern, verify.py): write_text()
    in place truncates first, and a crash between truncate and write
    leaves a file that fails Budget validation on every later charge,
    wedging that scope. The temp name carries the PID and a counter so
    concurrent writers of DIFFERENT scopes (the same directory) cannot
    collide on it. A crash before os.replace() must leave the previous
    counter intact."""
    tmp = path.with_suffix(f".{os.getpid()}.{next(_TMP_COUNTER)}.tmp")
    try:
        tmp.write_text(budget.model_dump_json(), encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


async def charge_persisted(
    deps: ResearchDeps, *, search: int = 0, fetch: int = 0, scope: str = "run"
) -> None:
    """Same contract as deps.charge(): enforces the bound BEFORE accounting
    for it, raising BudgetExceeded (and leaving the on-disk count untouched)
    if `search`/`fetch` would cross deps.max_searches/max_fetches/max_cost_usd
    for `scope`. Reads and writes that scope's file under a lock so the cap
    holds across separate activities, each of which sees its own fresh
    (zeroed) `deps.budget`."""
    path = budget_path(deps.run_id, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    await _acquire_lock(lock_path)
    try:
        scratch = deps.model_copy(update={"budget": _read_counter(path)})
        charge(scratch, search=search, fetch=fetch)
        _publish_counter(path, scratch.budget)
    finally:
        lock_path.unlink(missing_ok=True)


async def charge_scoped(
    deps: ResearchDeps, *, search: int = 0, fetch: int = 0, scope: str, run_max_cost_usd: float
) -> None:
    """Charge BOTH the sub-question scope and the shared run ceiling.

    Both counters are checked BEFORE either is written (008 D3), so a
    charge refused by either counter leaves both unchanged: the scope
    lock then the run lock are held across one read of each counter, a
    scratch-copy check of the run ceiling first (cost cap
    ``run_max_cost_usd`` only -- search/fetch counts are per-sub-question
    concerns, so the run copy's count caps are unbounded) and of the
    scope caps second, and, only if both pass, a publish of the scope
    counter then the run counter. A refusal is noted on the caller's
    deps (which counter refused, then the message) and the same
    exception is re-raised unaltered; a lock ``TimeoutError`` is not a
    refusal and is never noted; nothing ever subtracts from a counter.

    The publishes are two separate atomic writes, so a crash between
    them can leave the scope counter one charge ahead of the run
    counter: one phantom charge against this sub-question's own
    allowance, never against the shared ceiling. Work starts only after
    both writes, so the run counter never under-counts real work.

    When ``scope == "run"`` the scope IS the run ceiling (the architect path,
    which doesn't fan out, and the default scope). The two charges collapse
    onto the same ``budget-run.json`` -- so charging both would write it twice,
    double the count, and make ``max_searches``/``max_fetches`` bind at half.
    In that case charge ONCE, enforcing the count caps and the tighter of the
    two cost caps (matching the two-charge path where neither cap may be
    exceeded).
    """
    if scope == "run":
        scoped = deps.model_copy(update={"max_cost_usd": min(deps.max_cost_usd, run_max_cost_usd)})
        await charge_persisted(scoped, search=search, fetch=fetch, scope="run")
        return

    scope_path = budget_path(deps.run_id, scope)
    run_path = budget_path(deps.run_id, "run")
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    scope_lock = scope_path.with_suffix(".lock")
    run_lock = run_path.with_suffix(".lock")
    await _acquire_lock(scope_lock)
    try:
        await _acquire_lock(run_lock)
        try:
            scope_budget = _read_counter(scope_path)
            run_budget = _read_counter(run_path)
            run_scratch = deps.model_copy(
                update={
                    "budget": run_budget,
                    "max_cost_usd": run_max_cost_usd,
                    "max_searches": 10**9,
                    "max_fetches": 10**9,
                }
            )
            try:
                charge(run_scratch, search=search, fetch=fetch)
            except BudgetExceeded as exc:
                deps.note_refusal(f"run ceiling: {exc}")
                raise
            scope_scratch = deps.model_copy(update={"budget": scope_budget})
            try:
                charge(scope_scratch, search=search, fetch=fetch)
            except BudgetExceeded as exc:
                deps.note_refusal(f"{scope} allowance: {exc}")
                raise
            _publish_counter(scope_path, scope_scratch.budget)
            _publish_counter(run_path, run_scratch.budget)
        finally:
            run_lock.unlink(missing_ok=True)
    finally:
        scope_lock.unlink(missing_ok=True)
