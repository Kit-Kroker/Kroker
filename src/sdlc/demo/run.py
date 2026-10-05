"""Drive one dry run: start the workflow, answer its gates, report.

The gates are answered through sdlc.channels.transport -- the same
query/match/signal path `sdlc.cli answer` and `approve` use -- so the run
exercises the human surface rather than reaching past it.

All output is ASCII: the Windows console cannot print anything else.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from ..agents.runner import SdlcPydanticAIPlugin
from ..channels.contract import Reply
from ..channels.transport import describe, fetch_pending, submit
from ..core.models import GateOutcome, RunSummary
from ..graph.start import start_graph_run
from ..pending import ClarifyPending, PendingDecision
from ..workflows.deployment import DeploymentWorkflow
from ..workflows.graph import GraphWorkflow
from ..workflows.graph_catalog import build_run_input
from .canned import AGENT_SPECS, demo_config, demo_idea
from .fakes import demo_activities

Emit = Callable[[str], None]

_POLL_S = 0.1


@dataclass(frozen=True)
class DemoResult:
    run_id: str
    outcome: str
    summary: RunSummary | None
    report_dir: Path

    @property
    def ok(self) -> bool:
        return self.outcome.startswith("deployed:")


def demo_run_id(now: datetime | None = None) -> str:
    """Distinct per run: Temporal refuses an id that is already RUNNING, and
    a dry run interrupted mid-gate must not block the next one."""
    return f"demo-{(now or datetime.now(UTC)).strftime('%Y%m%dT%H%M%SZ')}"


def _reply_for(pending: PendingDecision) -> tuple[Reply, str]:
    """The reply a consenting operator would give, and the command a real
    run would take it from."""
    if isinstance(pending, ClarifyPending):
        text = pending.suggested_answer or "yes"
        return Reply(text=text), f'answer --q {pending.key} --text "{text}"'
    return Reply(outcome=GateOutcome.APPROVE), f"approve --gate {pending.gate}"


async def _drive(handle: Any, emit: Emit, done: asyncio.Event) -> None:
    """Print each status the run passes through and answer every pending
    decision, until `done` is set.

    Stopped by a flag rather than by cancellation: cancelling mid-query
    leaves the worker answering a query nobody is waiting for, which the
    SDK logs as a warning on an otherwise clean run.
    """
    last_status = None
    answered: set[str] = set()
    while not done.is_set():
        status = await handle.query("status")
        if status != last_status:
            emit(f"[{status}]")
            last_status = status
        for pending in await fetch_pending(handle):
            if pending.key in answered:
                continue
            reply, command = _reply_for(pending)
            emit(f"  waiting on a human: {describe(pending)}")
            emit(f"    a real run takes: python -m sdlc.cli {command} --id {handle.id}")
            result = await submit(handle, pending, reply)
            # An unconfirmed reply is retried on the next poll: the signal
            # is idempotent per (gate, round) and per question id.
            if result.confirmed:
                answered.add(pending.key)
                emit(f"    demo: {result.message}")
        await asyncio.sleep(_POLL_S)


def export_root() -> Path:
    # The same resolution export_run_artifacts performs inside the activity.
    return Path(os.environ.get("SDLC_EXPORT_ROOT", "./runs"))


async def run_demo(
    client: Client,
    *,
    emit: Emit = print,
    timeout_s: float = 120.0,
    run_id: str | None = None,
) -> DemoResult:
    """Run the scripted pipeline to completion on `client`'s Temporal.

    The worker lives inside this call, on a task queue of its own, so a
    running production worker never sees the run and a previous dry run's
    leftovers are never picked up.
    """
    wf_id = run_id or demo_run_id()
    task_queue = f"kroker-demo-{uuid.uuid4().hex[:8]}"
    idea = demo_idea()
    run_input = build_run_input(idea, demo_config())

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[GraphWorkflow, DeploymentWorkflow],
        activities=demo_activities(AGENT_SPECS),
        plugins=[SdlcPydanticAIPlugin()],
    ):
        handle = await start_graph_run(
            client, GraphWorkflow.run, run_input, id=wf_id, task_queue=task_queue
        )
        emit(f'started {wf_id}: "{idea.title}"')
        done = asyncio.Event()
        driver = asyncio.create_task(_drive(handle, emit, done))
        try:
            outcome = await asyncio.wait_for(handle.result(), timeout=timeout_s)
        except BaseException:
            # Timeout, Ctrl-C or a failed run: once this worker exits nothing
            # polls the queue, so an open run would sit in Temporal for good.
            try:
                await handle.terminate("demo interrupted")
            except Exception:  # noqa: BLE001 -- already closed is fine
                pass
            raise
        finally:
            done.set()
            # A driver error (a query against a run that just failed) must
            # not replace the run's own exception.
            await asyncio.gather(driver, return_exceptions=True)
        # Queried while the worker is still up: a closed run answers queries
        # only by replaying on a live worker.
        summary = await handle.query(GraphWorkflow.run_summary)
    return DemoResult(
        run_id=wf_id, outcome=outcome, summary=summary, report_dir=export_root() / wf_id
    )


def render_result(result: DemoResult) -> str:
    lines = ["", f"outcome: {result.outcome}"]
    s = result.summary
    if s is not None:
        lines.append("")
        lines.append(f"{'stage':<14} {'role':<14} outcome")
        # "?" is the summary's own "not recorded" (intake has no role).
        lines += [
            f"{st.stage:<14} {st.role.replace('?', '-'):<14} {st.outcome.replace('?', '-')}"
            for st in s.stages
        ]
        lines.append("")
        lines.append(f"{'gate':<14} {'decided by':<14} approved")
        lines += [
            f"{g.gate:<14} {g.decided_by:<14} {'yes' if g.approved else 'no'}" for g in s.gates
        ]
    lines.append("")
    lines.append(f"report: {result.report_dir / 'report.html'}")
    lines.append(
        "Nothing above called a model, ran a coding CLI or touched a repository: "
        "every artifact was scripted."
    )
    lines.append("Next: python -m sdlc.cli doctor, then python -m sdlc.cli start ...")
    return "\n".join(lines)
