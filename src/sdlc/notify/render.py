"""Notification text. E-6's default_render already turns a PendingDecision
into title/body/rows; this module only adds the envelope -- why you are being
told now, when it dies, and the exact command that decides it.

ASCII-only, like every other operator-facing string in the project.
"""

from __future__ import annotations

from datetime import datetime

from ..channels.contract import default_render
from ..pending import PendingDecision
from .contract import NotifyReason

_LEAD = {
    NotifyReason.OPENED: "is awaiting you",
    NotifyReason.REMIND: "is still awaiting you (reminder)",
    NotifyReason.ESCALATE: "is still awaiting a decision (escalated)",
    NotifyReason.EXPIRE: "has expired undecided",
}


def _hours(delta) -> str:
    return f"{int(delta.total_seconds() // 3600)}h"


def render_notification(
    pending: PendingDecision,
    reason: NotifyReason,
    run_id: str,
    opened_at: datetime,
    now: datetime,
    deadline: datetime | None,
    base_url: str | None,
) -> str:
    r = default_render(pending)
    gate = getattr(pending, "gate", None)
    subject = f"Gate '{gate}'" if gate else "A question"

    lines = [f"{subject} {_LEAD[reason]} on run {run_id}", "", r.title]
    if r.body:
        lines.append(r.body)

    timing = f"  opened {_hours(now - opened_at)} ago"
    if deadline is None:
        timing += " - does not expire"
    elif deadline > now:
        timing += f" - expires in {_hours(deadline - now)}"
    lines += ["", timing]

    if r.rows:
        lines.append("")
        width = max(len(name) for name, _ in r.rows)
        lines += [f"  {name:<{width}}  {detail}" for name, detail in r.rows]

    if r.suggested:
        lines += ["", f"  suggested: {r.suggested}"]

    lines.append("")
    if reason is not NotifyReason.EXPIRE:
        if gate:
            lines += [
                f"  sdlc approve {run_id} --gate {gate}",
                f"  sdlc reject {run_id} --gate {gate}",
            ]
        else:
            lines.append(f"  sdlc answer {run_id} --question {pending.key}")
        if base_url:
            lines.append(f"  {base_url.rstrip('/')}/runs/{run_id}")

    return "\n".join(lines)
