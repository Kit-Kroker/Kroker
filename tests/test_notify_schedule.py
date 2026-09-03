"""E-9 Task 2: schedule construction is pure and total -- no configuration
may make it raise, hang, or emit an out-of-order deadline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sdlc.core.models import (
    GateConfig,
    TimeoutAction,
)
from sdlc.notify.schedule import NotifyReason, build_schedule

T0 = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _at(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def test_default_schedule_is_opened_remind_50pct_escalate_80pct_expire():
    schedule, expires = build_schedule(GateConfig(), 48, T0)
    assert schedule == [
        (T0, NotifyReason.OPENED),
        (_at(24), NotifyReason.REMIND),  # 50% of 48
        (_at(38.4), NotifyReason.ESCALATE),  # 80% of 48
        (_at(48), NotifyReason.EXPIRE),
    ]
    assert expires == _at(48)


def test_explicit_overrides_win():
    cfg = GateConfig(remind_after_hours=2, escalate_after_hours=6)
    schedule, expires = build_schedule(cfg, 48, T0)
    assert [r for _, r in schedule] == [
        NotifyReason.OPENED,
        NotifyReason.REMIND,
        NotifyReason.ESCALATE,
        NotifyReason.EXPIRE,
    ]
    assert [t for t, _ in schedule] == [T0, _at(2), _at(6), _at(48)]
    assert expires == _at(48)


def test_hold_omits_expire_and_returns_no_final_deadline():
    cfg = GateConfig(on_timeout=TimeoutAction.HOLD)
    schedule, expires = build_schedule(cfg, 48, T0)
    assert [r for _, r in schedule] == [
        NotifyReason.OPENED,
        NotifyReason.REMIND,
        NotifyReason.ESCALATE,
    ]
    assert expires is None


def test_deadlines_at_or_past_expiry_are_dropped():
    """A reminder that would fire after the gate is already dead is noise."""
    cfg = GateConfig(remind_after_hours=48, escalate_after_hours=100)
    schedule, _ = build_schedule(cfg, 48, T0)
    assert [r for _, r in schedule] == [NotifyReason.OPENED, NotifyReason.EXPIRE]


def test_out_of_order_overrides_are_sorted_not_rejected():
    """escalate before remind is a misconfiguration, not a crash."""
    cfg = GateConfig(remind_after_hours=10, escalate_after_hours=3)
    schedule, _ = build_schedule(cfg, 48, T0)
    assert [t for t, _ in schedule] == [T0, _at(3), _at(10), _at(48)]


def test_zero_timeout_hours_yields_opened_then_immediate_expire():
    schedule, expires = build_schedule(GateConfig(), 0, T0)
    assert [r for _, r in schedule] == [NotifyReason.OPENED, NotifyReason.EXPIRE]
    assert expires == T0


def test_hold_with_zero_timeout_still_notifies_open_and_never_expires():
    cfg = GateConfig(on_timeout=TimeoutAction.HOLD)
    schedule, expires = build_schedule(cfg, 0, T0)
    assert [r for _, r in schedule] == [NotifyReason.OPENED]
    assert expires is None


def test_schedule_is_always_sorted_and_starts_at_opened():
    for timeout in (0, 1, 5, 48, 720):
        for cfg in (
            GateConfig(),
            GateConfig(remind_after_hours=1),
            GateConfig(on_timeout=TimeoutAction.HOLD),
            GateConfig(remind_after_hours=99, escalate_after_hours=1),
        ):
            schedule, _ = build_schedule(cfg, timeout, T0)
            times = [t for t, _ in schedule]
            assert times == sorted(times), (cfg, timeout)
            assert schedule[0] == (T0, NotifyReason.OPENED)
