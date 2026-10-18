"""Happy-path contracts for the replay gate-timer pin (bug golden-tick-race).

A driver's gate-decision signal races the gate's remind-timer creation;
when the signal wins, the resumed gate calls wait_condition with the
decision already true, Temporal core elides the StartTimer+CancelTimer pair
issued within one workflow-task completion, and the capture lands one
"timer" short of the golden (SG-3). The approved fix (Direction A) pins
the drivers in tests/replay/scenarios.py: decide() signals only once
fetch_history() shows a TIMER_STARTED with event_id greater than the most
recent notify ACTIVITY_TASK_SCHEDULED (D1); answer_clarify() sends the
FIRST answer_question only once some TIMER_STARTED exists (A1), the rest
unpinned; both waits poll GATE_TIMER_PIN_POLL_S, are bounded by
GATE_TIMER_PIN_TIMEOUT_S, raise naming the gate and never signal on expiry
(D2/A2); everything else -- wait_for's "status" query, the positional
GateDecision payload, args=[qid, "yes"] answers -- is unchanged (D3). The
race-window rows are the deterministic RED backbone (pre-fix the drivers
signal without fetching history); the "already visible" controls stay
green pre-fix, the temporal row window-dependent.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from temporalio.api.common.v1 import ActivityType
from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import ActivityTaskScheduledEventAttributes, HistoryEvent

import tests.replay.scenarios as scenarios
from sdlc.core.models import GateDecision, GateOutcome
from tests.fakes.canned import QUESTION_IDS
from tests.replay.harness import GRAPH_STARTER, capture, load_golden
from tests.replay.scenarios import SCENARIOS, answer_clarify, decide

_REMIND_TIMER = HistoryEvent(event_id=9, event_type=EventType.EVENT_TYPE_TIMER_STARTED)


def _sched(event_id: int, name: str) -> HistoryEvent:
    attrs = ActivityTaskScheduledEventAttributes(activity_type=ActivityType(name=name))
    return HistoryEvent(
        event_id=event_id,
        event_type=EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
        activity_task_scheduled_event_attributes=attrs,
    )


def _awaiting_history(timer: bool) -> list[HistoryEvent]:
    """A just-OPENED gate's tail; the LATER non-notify scheduling forces the
    D1 anchor to filter by name. `timer` adds the remind timer the race
    hides (id 9 > the notify anchor at 6, and > 0 = A1's anchor)."""
    scheds = [_sched(6, "notify"), _sched(7, "export_run_artifacts")]
    return [*scheds, _REMIND_TIMER] if timer else scheds


@dataclass
class _Sent:
    name: str
    payload: Any
    kwargs: dict[str, Any]
    history: tuple[HistoryEvent, ...]  # what fetch_history() shows RIGHT NOW


@dataclass
class FakeHandle:
    """WorkflowHandle stand-in: "status" answers from the first poll; the
    remind timer enters history only after `reveal_timer_after` fetches --
    the race window, made deterministic."""

    status: str
    reveal_timer_after: int = 0
    fetches: int = 0
    queries: list[str] = field(default_factory=list)
    signals: list[_Sent] = field(default_factory=list)

    def _visible(self) -> list[HistoryEvent]:
        return _awaiting_history(self.fetches >= self.reveal_timer_after)

    async def query(self, name: str) -> str:
        self.queries.append(name)
        return self.status

    async def signal(self, name: str, payload: Any = None, **kwargs: Any) -> None:
        self.signals.append(_Sent(name, payload, dict(kwargs), tuple(self._visible())))

    async def fetch_history(self) -> Any:
        self.fetches += 1
        return SimpleNamespace(events=self._visible())


def _pin_timer(history: tuple[HistoryEvent, ...]) -> int | None:
    """The qualifying timer per D1 (anchor: most recent notify scheduling; 0
    = start of history, A1's rule), over the ground truth recorded at
    signal time -- not over the driver's code."""
    anchor = max(
        (
            ev.event_id
            for ev in history
            if ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
            and ev.activity_task_scheduled_event_attributes.activity_type.name == "notify"
        ),
        default=0,
    )
    timers = [ev.event_id for ev in history if ev.event_type == EventType.EVENT_TYPE_TIMER_STARTED]
    return next((i for i in timers if i > anchor), None)


def test_pin_constants_exist_at_the_pinned_values():
    """The fix ships the two knobs; the expiry row monkeypatches them (raising=False)."""
    assert getattr(scenarios, "GATE_TIMER_PIN_POLL_S", None) == 0.02
    assert getattr(scenarios, "GATE_TIMER_PIN_TIMEOUT_S", None) == 30.0


@pytest.mark.asyncio
async def test_decide_waits_for_the_remind_timer_before_signalling():
    """D1 across the race window (timer visible only on the 3rd fetch): the
    decision goes out exactly once, D3-shaped, but only once a qualifying
    TIMER_STARTED is on record. RED pre-fix: signal precedes the timer."""
    handle = FakeHandle("awaiting:architecture", reveal_timer_after=3)
    await decide(handle, "architecture", 1, GateOutcome.REJECT, guidance="too costly")
    assert handle.queries == ["status"]  # D3: wait_for semantics unchanged
    (rec,) = handle.signals  # exactly one signal
    assert rec.name == "submit_gate_decision"
    decision = rec.payload
    assert isinstance(decision, GateDecision) and decision.guidance == "too costly"
    got = (decision.gate, decision.round, decision.outcome, decision.decided_by)
    assert got == ("architecture", 1, GateOutcome.REJECT, "human")
    assert not rec.kwargs  # D3: the decision rides the positional argument
    assert _pin_timer(rec.history) is not None, (
        "golden-tick-race: the decision was recorded before any "
        "TIMER_STARTED followed the gate's OPENED notify -- the timer pair "
        "is then elided and the capture lands one 'timer' short (SG-3)"
    )


@pytest.mark.asyncio
async def test_signals_go_out_promptly_when_the_timer_is_already_up():
    """Controls (golden ordering): timer on the first fetch -> no polling delay. GREEN pre-fix."""
    gate = FakeHandle("awaiting:architecture")
    await decide(gate, "architecture", 1, GateOutcome.APPROVE)
    (rec,) = gate.signals
    assert _pin_timer(rec.history) is not None
    assert gate.fetches <= 2, "the pin must not delay the control window"
    clarify = FakeHandle("awaiting:clarify")
    await answer_clarify(clarify)
    assert len(clarify.signals) == len(QUESTION_IDS) and clarify.fetches <= 2


_TIMEOUT_DRIVES: list[tuple[str, Callable[[FakeHandle], Awaitable[None]]]] = [
    ("architecture", lambda h: decide(h, "architecture", 1, GateOutcome.APPROVE)),
    ("clarify", answer_clarify),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "drive"), _TIMEOUT_DRIVES, ids=["decide", "clarify"])
async def test_pin_wait_is_bounded_and_signals_nothing_on_expiry(gate, drive, monkeypatch):
    """D2/A2: timer never shows -> AssertionError naming the gate, no signal. RED pre-fix."""
    handle = FakeHandle(f"awaiting:{gate}", reveal_timer_after=10**9)
    monkeypatch.setattr(scenarios, "GATE_TIMER_PIN_TIMEOUT_S", 0.05, raising=False)
    monkeypatch.setattr(scenarios, "GATE_TIMER_PIN_POLL_S", 0.001, raising=False)
    with pytest.raises(AssertionError, match=gate):
        await drive(handle)
    assert not handle.signals, "no decision may cross the wire when the pin expires"


@pytest.mark.asyncio
async def test_answer_clarify_pins_the_first_answer_on_a_started_timer():
    """A1 across the race window: the FIRST answer_question waits for any
    TIMER_STARTED; every QUESTION_ID still gets answered with the exact
    production call shape. RED pre-fix."""
    handle = FakeHandle("awaiting:clarify", reveal_timer_after=3)
    await answer_clarify(handle)
    answers = [s for s in handle.signals if s.name == "answer_question"]
    assert len(answers) == len(QUESTION_IDS)
    assert _pin_timer(answers[0].history) is not None, (
        "golden-tick-race: the first answer_question crossed before any "
        "TIMER_STARTED existed -- the capture can then drop a 'timer' (SG-3)"
    )
    for rec, qid in zip(answers, QUESTION_IDS, strict=True):
        assert rec.kwargs == {"args": [qid, "yes"]}  # scenarios.py call shape


@pytest.mark.temporal  # the ONLY temporal-tier row: per-test opt-in, not module-wide
@pytest.mark.asyncio
async def test_budget_arch_reject_capture_is_deterministic(monkeypatch, tmp_path):
    """Five consecutive sandboxed GraphWorkflow captures of budget_arch_reject
    (answer_clarify + two decide() calls = three race windows) must each
    reproduce the committed golden command projection, and each other.
    Window-dependent pre-fix: it may pass on a lucky window -- the RED
    backbone is the fake-handle rows."""
    scenario = next(s for s in SCENARIOS if s.name == "budget_arch_reject")
    golden = load_golden("budget_arch_reject")["commands"]
    runs: list[list[str]] = []
    for i in range(5):
        captured = await capture(
            scenario, GRAPH_STARTER, monkeypatch, tmp_path / f"run{i}", sandboxed=True
        )
        assert captured.golden["commands"] == golden, f"run {i}: SG-3 projection differs"
        runs.append(captured.golden["commands"])
    assert all(r == runs[0] for r in runs)
