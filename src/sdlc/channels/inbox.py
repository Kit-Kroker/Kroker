"""Cross-run inbox (E-8): list every pending decision across every open
FeatureWorkflow run. resolve()'s sibling -- the same query/validate path
(``transport.fetch_pending``) applied to many handles instead of one the
caller already named.
"""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ..pending import PendingDecision
from .transport import describe, fetch_pending


class RunInbox(BaseModel):
    """One open run with at least one pending decision."""
    run_id: str
    pending: list[PendingDecision] = Field(default_factory=list)


class InboxError(BaseModel):
    """An open run whose pending_decisions() query raised."""
    run_id: str
    error: str


class Inbox(BaseModel):
    """Result of fetching pending decisions across every open run.

    ``total_open_runs`` is tracked separately from ``runs`` because a run
    with nothing pending is dropped rather than listed -- without this
    count, "no runs listed" and "checked 3 runs, none had anything pending"
    would be indistinguishable.
    """
    total_open_runs: int = 0
    runs: list[RunInbox] = Field(default_factory=list)
    errors: list[InboxError] = Field(default_factory=list)


def render_inbox(inbox: Inbox) -> str:
    """ASCII-only text for the CLI. See tests/test_channel_inbox.py for the
    exact shape of every branch."""
    if inbox.total_open_runs == 0:
        return "no open runs"

    if not inbox.runs and not inbox.errors:
        noun = "run" if inbox.total_open_runs == 1 else "runs"
        return f"nothing pending across {inbox.total_open_runs} open {noun}"

    lines: list[str] = []
    for r in inbox.runs:
        lines.append(f"{r.run_id}:")
        lines += [f"  {describe(d)}" for d in r.pending]

    if inbox.errors:
        if lines:
            lines.append("")
        noun = "run" if len(inbox.errors) == 1 else "runs"
        lines.append(f"{len(inbox.errors)} {noun} could not be queried:")
        lines += [f"  {e.run_id}: {e.error}" for e in inbox.errors]

    return "\n".join(lines)


_OPEN_FEATURE_QUERY = "WorkflowType='FeatureWorkflow' AND ExecutionStatus='Running'"


async def list_open_run_ids(client) -> list[str]:
    """Every currently-running FeatureWorkflow id, via a server-side
    visibility filter -- ReflectWorkflow/BenchmarkWorkflow executions on the
    same task queue never expose pending_decisions, so they are excluded
    here rather than probed and discarded."""
    return [wf.id async for wf in client.list_workflows(_OPEN_FEATURE_QUERY)]


async def _fetch_one(client, run_id: str):
    """Never raises: an exception becomes the return value, so one run's
    failure can't take down asyncio.gather for the rest."""
    try:
        handle = client.get_workflow_handle(run_id)
        return await fetch_pending(handle)
    except Exception as e:  # noqa: BLE001 -- captured into Inbox.errors, not raised
        return e


async def fetch_inbox(client) -> Inbox:
    """Discover every open run, fetch each one's pending decisions
    concurrently, and aggregate. A run with nothing pending is dropped, not
    listed; a run whose query raised becomes an InboxError instead of
    aborting the whole fetch."""
    run_ids = await list_open_run_ids(client)
    results = await asyncio.gather(*(_fetch_one(client, rid) for rid in run_ids))

    inbox = Inbox(total_open_runs=len(run_ids))
    for run_id, outcome in zip(run_ids, results):
        if isinstance(outcome, Exception):
            inbox.errors.append(InboxError(run_id=run_id, error=str(outcome)))
        elif outcome:
            inbox.runs.append(RunInbox(run_id=run_id, pending=outcome))
    return inbox
