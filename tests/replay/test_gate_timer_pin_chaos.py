"""Chaos/edge RED contracts for the gate-timer pin (bug golden-tick-race).

The replay drivers signal a gate decision the instant query("status") first
answers awaiting:<gate>. When that signal is server-recorded before the
gate's OPENED `notify` activity completes, the resumed gate's wait_condition
(decision already true) issues StartTimer and CancelTimer inside ONE
workflow-task completion and Temporal core ELIDES the pair: no TIMER_STARTED
reaches the history, so the captured projection is one "timer" short of the
golden (SG-3 flake, probe-proven 3/3 in-container). The approved fix
(Direction A) pins the drivers in tests/replay/scenarios.py:
- D1: decide() must not signal "submit_gate_decision" until fetch_history()
  shows a TIMER_STARTED with event_id greater than the most recent
  ACTIVITY_TASK_SCHEDULED whose activity type name is "notify"; past the
  bound it raises AssertionError naming the gate and sends NO signal.
- D2: the wait is bounded by scenarios.GATE_TIMER_PIN_TIMEOUT_S (poll
  interval scenarios.GATE_TIMER_PIN_POLL_S); rows monkeypatch the bound with
  raising=False so the constant-less pre-fix module still fails as a clean
  RED rather than an error.
- A1/A2: answer_clarify()'s FIRST "answer_question" signal waits for any
  TIMER_STARTED (anchor = history start); same bound, error names "clarify".

Pre-fix census: rows 1, 2, 3, 4 and 6 are the RED carriers (the pre-fix
drivers signal on first status sight and never call fetch_history); row 5's
payload row may already hold pre-fix -- its fetch-ordering assertion (the
row-1 family) is that row's RED carrier. Rows run on scripted duck-typed
handles (no dev server, fast tier) with REAL temporalio EventType values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from temporalio.api.enums.v1 import EventType

from sdlc.core.models import GateDecision
from tests.replay import scenarios

_SCHEDULED = EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
_TIMER_STARTED = EventType.EVENT_TYPE_TIMER_STARTED
_TIMER_FIRED = EventType.EVENT_TYPE_TIMER_FIRED
_TIMER_CANCELED = EventType.EVENT_TYPE_TIMER_CANCELED


@dataclass
class _Event:
    """Duck-typed HistoryEvent slice: event_id, the REAL EventType int, the
    activity type name on notify schedulings; the chained properties let the
    pin helper walk the real attribute path onto a real history event."""

    event_id: int
    event_type: int
    name: str | None = None

    @property
    def activity_task_scheduled_event_attributes(self) -> _Event:
        return self

    @property
    def activity_type(self) -> _Event:
        return self


@dataclass
class _History:
    events: list[_Event]


def _notify_scheduled(event_id: int) -> _Event:
    return _Event(event_id, int(_SCHEDULED), "notify")


def _timer_started(event_id: int) -> _Event:
    return _Event(event_id, int(_TIMER_STARTED))


def _timer_fired(event_id: int) -> _Event:
    return _Event(event_id, int(_TIMER_FIRED))


def _timer_canceled(event_id: int) -> _Event:
    return _Event(event_id, int(_TIMER_CANCELED))


@dataclass
class _SignalRecord:
    name: str
    payload: Any
    args: Any
    events: list[_Event]  # history snapshot as last seen at signal time
    fetches: int  # fetch_history() calls before the signal


class _ScriptedHandle:
    """query() answers the scripted status; fetch_history() walks the state
    script one step per call, sticking on the last; signal() records the
    snapshot/payload/fetch count AT SIGNAL TIME. Pre-fix drivers never
    fetch, so their records show fetches == 0: the RED signature."""

    def __init__(self, status: str, states: list[list[_Event]]) -> None:
        self._status = status
        self._states = states
        self._idx = 0
        self._seen = states[0]
        self.fetches = 0
        self.signals: list[_SignalRecord] = []

    async def query(self, name: str) -> str:
        return self._status

    async def signal(self, name: str, payload: Any = None, args: Any = None) -> None:
        self.signals.append(_SignalRecord(name, payload, args, list(self._seen), self.fetches))

    async def fetch_history(self) -> _History:
        snap = self._states[self._idx]
        self._idx = min(self._idx + 1, len(self._states) - 1)
        self._seen = snap
        self.fetches += 1
        return _History(events=list(snap))


def _timer_ids(events: list[_Event]) -> set[int]:
    return {e.event_id for e in events if e.event_type == _TIMER_STARTED}


def _latest_notify_id(events: list[_Event]) -> int:
    return max((e.event_id for e in events if e.name == "notify"), default=0)


def _gate_signals(handle: _ScriptedHandle) -> list[_SignalRecord]:
    return [s for s in handle.signals if s.name == "submit_gate_decision"]


@pytest.mark.asyncio
async def test_decide_polls_until_the_gate_remind_timer_is_recorded() -> None:
    """Row 1 (RED carrier) -- delayed timer: the qualifying TIMER_STARTED
    exists only from the 5th fetch_history() call, so the helper must keep
    polling, never signalling on the notify-only history; its signal lands
    with the timer in sight. Pre-fix signals at fetch 0: RED."""
    base = [_notify_scheduled(5)]
    states = [base, list(base), list(base), list(base), [*base, _timer_started(6)]]
    handle = _ScriptedHandle("awaiting:architecture", states)

    await scenarios.decide(handle, "architecture", 1, scenarios.A)

    assert len(records := _gate_signals(handle)) == 1
    rec = records[0]
    assert rec.fetches >= 5, "golden-tick-race: signalled before the 5th fetch -- early signal"
    anchor = _latest_notify_id(rec.events)
    assert any(tid > anchor for tid in _timer_ids(rec.events)), "no timer past the anchor yet"


@pytest.mark.asyncio
async def test_decide_timeout_withholds_the_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 2 (RED carrier) -- never-appearing timer: past the pinched bound,
    decide must raise AssertionError naming the gate and send NO signal;
    raising=False keeps the constant-less pre-fix module a clean RED.
    Pre-fix decide signals and returns: RED."""
    monkeypatch.setattr(scenarios, "GATE_TIMER_PIN_TIMEOUT_S", 0.2, raising=False)
    handle = _ScriptedHandle("awaiting:deploy", [[_notify_scheduled(5)]])

    with pytest.raises(AssertionError) as ei:
        await scenarios.decide(handle, "deploy", 1, scenarios.A)

    assert "deploy" in str(ei.value)
    assert not _gate_signals(handle), "golden-tick-race: signal sent despite timer-pin timeout"


@pytest.mark.asyncio
async def test_clarify_timeout_withholds_first_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 3 (RED carrier) -- never-appearing timer, A1/A2: the FIRST
    answer_question signal is pinned to any TIMER_STARTED (anchor = history
    start); none ever recorded means the helper raises naming "clarify"
    before any answer goes out. Pre-fix dumps every answer: RED."""
    monkeypatch.setattr(scenarios, "GATE_TIMER_PIN_TIMEOUT_S", 0.2, raising=False)
    handle = _ScriptedHandle("awaiting:clarify", [[_notify_scheduled(1)]])

    with pytest.raises(AssertionError) as ei:
        await scenarios.answer_clarify(handle)

    assert "clarify" in str(ei.value)
    answered = [s for s in handle.signals if s.name == "answer_question"]
    assert not answered, "golden-tick-race: answer_question signalled despite the clarify pin"


@pytest.mark.asyncio
async def test_decide_anchors_on_the_latest_notify_not_the_stale_resolved_pair() -> None:
    """Row 4 (RED carrier) -- adversarial anchor: an older gate's RESOLVED
    pair (notify 10 / timer 11 / fired 12) exists from fetch 1; the new
    gate's notify (20) lands on fetch 2, its remind timer (21) on fetch 4,
    and the qualifying timer must exceed the LATEST notify: RED pre-fix."""
    stale = [_notify_scheduled(10), _timer_started(11), _timer_fired(12)]
    fresh = [*stale, _notify_scheduled(20)]
    states = [stale, fresh, list(fresh), [*fresh, _timer_started(21)]]
    handle = _ScriptedHandle("awaiting:architecture", states)

    await scenarios.decide(handle, "architecture", 2, scenarios.A)

    assert len(records := _gate_signals(handle)) == 1
    rec = records[0]
    assert rec.fetches >= 4, "golden-tick-race: signalled before the new gate's timer existed"
    assert max(_timer_ids(rec.events)) > 20, "anchored on the stale pair (11), not notify 20"


@pytest.mark.asyncio
async def test_decide_payload_is_untouched_by_the_pin() -> None:
    """Row 5 -- payload integrity under pinning: with the timer delayed to
    fetch 3 the payload must still be the exact GateDecision -- pinning may
    reorder WHEN the signal flies, never WHAT it carries. The payload row
    may already hold pre-fix; the fetch-ordering assertion (row-1 family) is
    this row's RED carrier."""
    base = [_notify_scheduled(7)]
    states = [base, list(base), [*base, _timer_started(8)]]
    handle = _ScriptedHandle("awaiting:plan", states)

    await scenarios.decide(handle, "plan", 2, scenarios.V)

    rec = _gate_signals(handle)[0]
    assert rec.fetches >= 3  # RED carrier pre-fix (the pin never ran)
    assert rec.payload == GateDecision(
        gate="plan", round=2, outcome=scenarios.V, decided_by="human"
    )


@pytest.mark.asyncio
async def test_decide_waits_out_the_stale_pair_while_the_new_notify_is_unrecorded() -> None:
    """Row 6 (RED carrier) -- no premature anchor signal: at fetch 1 only the
    PREVIOUS gate's RESOLVED pair is on record (notify 3 / timer 4 /
    TIMER_CANCELED 5 -- the only stale shape reality can produce: a gate's
    remind timer is always canceled before the next gate opens, and the
    status query can never see awaiting:<gate> before that gate's own OPENED
    notify scheduling exists, so an uncanceled stale pair is impossible);
    the new gate's notify (10) lands on fetch 2 and its timer (11) on fetch
    3, and the signal must wait for the NEW pending pair -- a pin that
    counts resolved timers would fire inside the exact race window the fix
    closes. Pre-fix signals at fetch 0: RED."""
    stale = [_notify_scheduled(3), _timer_started(4), _timer_canceled(5)]
    states = [
        stale,
        [*stale, _notify_scheduled(10)],
        [*stale, _notify_scheduled(10), _timer_started(11)],
    ]
    handle = _ScriptedHandle("awaiting:architecture", states)

    await scenarios.decide(handle, "architecture", 1, scenarios.A)

    assert len(records := _gate_signals(handle)) == 1
    rec = records[0]
    assert rec.fetches >= 3, "golden-tick-race: signalled before the new notify's timer existed"
    assert any(e.event_id == 10 for e in rec.events), "signal predates the new notify scheduling"
    assert max(_timer_ids(rec.events)) > 10, "signalled on the stale pair (timer 4)"
