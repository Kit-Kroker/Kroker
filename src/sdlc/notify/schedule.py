"""When notifications fire. Pure: no I/O, no clock read -- `opened_at` is
supplied by the caller (workflow.now() in the workflow) so the schedule is
deterministic and replay-safe.

Totality is the design property that matters: no GateConfig may make this
raise, emit an unsorted schedule, or omit the OPENED entry. A misconfigured
schedule must never be able to hang or crash a gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..models import GateConfig, TimeoutAction
from .contract import NotifyReason

REMIND_FRACTION = 0.5     # of gate_timeout_hours, when not set explicitly
ESCALATE_FRACTION = 0.8

Schedule = list[tuple[datetime, NotifyReason]]


def build_schedule(gate_cfg: GateConfig, timeout_hours: int,
                   opened_at: datetime) -> tuple[Schedule, datetime | None]:
    """Return (sorted notification deadlines, final deadline).

    The final deadline is None under HOLD, which is what tells the caller
    that exhausting the schedule means "keep waiting" rather than "give up".
    Under any other TimeoutAction the schedule's last entry is EXPIRE at that
    same instant, so the two cannot disagree.
    """
    expires: datetime | None = (
        None if gate_cfg.on_timeout is TimeoutAction.HOLD
        else opened_at + timedelta(hours=timeout_hours))

    schedule: Schedule = [(opened_at, NotifyReason.OPENED)]

    for reason, explicit, fraction in (
        (NotifyReason.REMIND, gate_cfg.remind_after_hours, REMIND_FRACTION),
        (NotifyReason.ESCALATE, gate_cfg.escalate_after_hours,
         ESCALATE_FRACTION),
    ):
        hours = explicit if explicit is not None else timeout_hours * fraction
        at = opened_at + timedelta(hours=hours)
        if at <= opened_at:
            continue                      # collapses into OPENED
        if expires is not None and at >= expires:
            continue                      # would fire after the gate is dead
        schedule.append((at, reason))

    schedule.sort(key=lambda e: e[0])
    if expires is not None:
        schedule.append((expires, NotifyReason.EXPIRE))
    return schedule, expires
