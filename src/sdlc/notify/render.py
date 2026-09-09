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


# F4. Which artifact renders a gate's notification may link.
#
# A gate links what is ALREADY on the board when it opens, and never its own
# key: `_board_publish` runs only after a gate is decided
# (workflows/feature.py:560/585/602), so a gate's own artifact does not exist
# at notification time and a link to it would 404. The order below is the
# publish order.
_ALL_ARTIFACTS = ("requirements", "architecture", "plan")
_GATE_LINKS: dict[str, tuple[str, ...]] = {
    "clarify": (),  # nothing published yet
    "architecture": ("requirements",),
    "plan": ("requirements", "architecture"),
    "merge": _ALL_ARTIFACTS,
    "deploy": _ALL_ARTIFACTS,
    # Opened by the deploy stage after a failed smoke check
    # (stages/deploy/step.py:212). Every publish has happened by then, and
    # this is precisely a gate where a human needs the plan in front of them.
    "deploy_failed": _ALL_ARTIFACTS,
}


def _artifact_links(gate: str, base_url: str | None, project: str | None) -> list[str]:
    """Deep links to the readable renders. Empty whenever anything needed is
    missing -- an unset base_url or project omits the links and never fails
    the notification."""
    if not base_url or not project:
        return []
    # A per-task escalation gate is `task:<id>`; by then every publish has
    # happened, so it gets the full set.
    keys = _ALL_ARTIFACTS if gate.startswith("task:") else _GATE_LINKS.get(gate, ())
    if not keys:
        return []
    root = base_url.rstrip("/")
    return [
        "",
        "  background:",
        *[f"    {root}/projects/{project}/artifacts/{key}/current/markdown" for key in keys],
    ]


def render_notification(
    pending: PendingDecision,
    reason: NotifyReason,
    run_id: str,
    opened_at: datetime,
    now: datetime,
    deadline: datetime | None,
    base_url: str | None,
    project: str | None = None,
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
        lines += _artifact_links(gate or "", base_url, project)

    return "\n".join(lines)
