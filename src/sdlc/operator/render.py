"""Models -> compact ASCII text for the agent (E-86 spec 5.4).

The agent must never receive a JSON dump of RunState: it costs tokens
proportional to fields nobody asked about, and it invites the model to quote
internal field names back at the operator. Every read verb returns text from
this module instead.

ASCII only, per channels/transport.py:12 -- the same strings can reach a
Windows console through the CLI or a log line.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..channels.contract import default_render
from ..channels.inbox import RunInbox
from ..core.models import (
    RunState,
    RunSummary,
)
from ..dashboard.fleet import FleetSnapshot
from ..pending import ClarifyPending, PendingDecision

ORIENTATION_CAP = 20


def _cost(v: float | None) -> str:
    # None is not zero: RunState documents that a pricing miss must never
    # read as a free run.
    return "cost unknown" if v is None else f"${v:.2f}"


def _pending_summary(pending: Sequence[PendingDecision]) -> str:
    if not pending:
        return "pending: none"
    parts = []
    for d in pending:
        if isinstance(d, ClarifyPending):
            parts.append(d.key)
        else:
            parts.append(f"{d.gate} (round {d.round})")
    return "pending: " + ", ".join(parts)


def run_line(run: RunState, pending: Sequence[PendingDecision] = ()) -> str:
    return " | ".join(
        [
            run.run_id,
            run.mode,
            f"stage {run.current_stage or 'not started'}",
            run.status,
            _pending_summary(pending),
            _cost(run.cost_usd_total),
        ]
    )


def summary_line(s: RunSummary) -> str:
    status = getattr(s, "status", getattr(s, "outcome", "closed"))
    return " | ".join([s.run_id, "closed", status, _cost(getattr(s, "cost_usd_total", None))])


def pending_block(d: PendingDecision) -> str:
    r = default_render(d)
    lines = [
        f"key: {r.key}",
        f"title: {r.title}",
        f"reply with: {r.reply_kind}",
        f"detail: {r.body}",
    ]
    if r.suggested:
        lines.append(f"suggested: {r.suggested}")
    lines.extend(f"  {name}: {value}" for name, value in r.rows)
    return "\n".join(lines)


def pending_for(snap: FleetSnapshot, run_id: str) -> list[PendingDecision]:
    for item in snap.inbox:
        if item.run_id == run_id:
            return list(item.pending)
    return []


def runs_view(snap: FleetSnapshot, status: str) -> str:
    lines: list[str] = []
    if status in ("open", "all"):
        lines += [run_line(r, pending_for(snap, r.run_id)) for r in snap.runs]
    if status in ("closed", "all"):
        lines += [summary_line(c) for c in snap.closed]
    if not lines:
        return f"no {status} runs"
    head = f"{len(lines)} {status} run(s):"
    return "\n".join([head, *lines])


def run_detail(run: RunState, pending: Sequence[PendingDecision]) -> str:
    blocks = [
        run_line(run, pending),
        f"title: {run.title}",
        f"started: {run.started_at.isoformat()}",
    ]
    if run.repo_url:
        blocks.append(f"repo: {run.repo_url}")
    if run.budget_usd is not None:
        blocks.append(f"budget: ${run.budget_usd:.2f} ({run.budget_crossings} crossing(s))")
    for d in pending:
        blocks.append("--\n" + pending_block(d))
    return "\n".join(blocks)


def _inbox_run_block(item: RunInbox) -> str:
    return "\n".join([f"run: {item.run_id}", *(pending_block(d) for d in item.pending)])


def inbox_view(snap: FleetSnapshot) -> str:
    if not snap.inbox:
        return f"checked {snap.total_open_runs} open run(s); nothing pending a decision"
    blocks = [_inbox_run_block(i) for i in snap.inbox]
    head = f"{len(snap.inbox)} of {snap.total_open_runs} open run(s) owe a decision:"
    return "\n\n".join([head, *blocks])


def orientation(snap: FleetSnapshot, cap: int = ORIENTATION_CAP) -> str:
    if not snap.runs:
        return "no open runs"
    if len(snap.runs) > cap:
        return f"{snap.total_open_runs} open runs -- too many to list; call list_runs for detail"
    lines = [run_line(r, pending_for(snap, r.run_id)) for r in snap.runs]
    return "\n".join(lines)
