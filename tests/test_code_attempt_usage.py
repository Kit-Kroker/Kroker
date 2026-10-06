"""The code attempt's MODEL_USAGE event (FR-015a): a harness that reported
no price must be recorded as no price — the cost_usd key is emitted only
when the harness carried dollars — while the token fold into the code
spend bag keeps working for every case."""

from datetime import UTC, datetime

from sdlc.core.models import HarnessKind, RoleUsage
from sdlc.harness.models import HarnessRunResult
from sdlc.observability.summary import _role_rollup
from sdlc.observability.trace import RunEvent, RunEventKind
from sdlc.stages.code.usage import _record_attempt_usage


class _FakeCtx:
    """Captures emit calls; the real StageContext is workflow-bound."""

    def __init__(self):
        self.emitted = []

    def emit(self, kind, stage=None, **data):
        self.emitted.append((kind, stage, data))


def _run(cost_usd):
    return HarnessRunResult(
        harness=HarnessKind.OPENCODE,
        exit_code=0,
        summary="ok",
        input_tokens=100,
        output_tokens=20,
        cost_usd=cost_usd,
    )


def _recorded_event(fake):
    """The captured emit, back on the wire as the trace event it becomes."""
    kind, stage, data = fake.emitted[0]
    assert kind is RunEventKind.MODEL_USAGE
    assert stage == "code"
    return RunEvent(seq=0, at=datetime.now(UTC), kind=kind, data=data)


def test_a_missing_price_emits_no_cost_usd_key():
    """FR-015a: cost_usd=None is 'no price'; the event must omit the key,
    not print a real 0.0 — a missing price must never read as free dollars."""
    ctx = _FakeCtx()
    _record_attempt_usage(ctx, RoleUsage(role="dev", model="m"), _run(None), "m")
    assert "cost_usd" not in ctx.emitted[0][2]


def test_a_real_zero_is_emitted_as_zero():
    """A harness that genuinely reported $0.00 keeps its zero on the wire."""
    ctx = _FakeCtx()
    _record_attempt_usage(ctx, RoleUsage(role="dev", model="m"), _run(0.0), "m")
    assert ctx.emitted[0][2]["cost_usd"] == "0.0"


def test_a_priced_call_emits_its_price():
    ctx = _FakeCtx()
    _record_attempt_usage(ctx, RoleUsage(role="dev", model="m"), _run(0.25), "m")
    assert ctx.emitted[0][2]["cost_usd"] == "0.25"


def test_tokens_still_fold_into_the_code_spend_bag():
    """The bag fold (merge_usage) is unchanged, priced or not."""
    code_spend = RoleUsage(role="dev", model="m")
    ctx = _FakeCtx()
    _record_attempt_usage(ctx, code_spend, _run(None), "m")
    assert code_spend.input_tokens == 100
    assert code_spend.output_tokens == 20
    assert code_spend.calls == 1


def test_rollup_over_a_no_key_event_leaves_the_role_unpriced():
    """FR-015a end to end: the emitted no-key event rolls up to a dev row
    with its tokens intact and cost_usd None."""
    code_spend = RoleUsage(role="dev", model="m")
    ctx = _FakeCtx()
    _record_attempt_usage(ctx, code_spend, _run(None), "m")
    roles = {u.role: u for u in _role_rollup([_recorded_event(ctx)])}
    assert roles["dev"].cost_usd is None
    assert roles["dev"].input_tokens == 100
    assert roles["dev"].output_tokens == 20


def _wire_event(data):
    """A MODEL_USAGE event straight off the wire (011 T004 edge)."""
    return RunEvent(seq=0, at=datetime.now(UTC), kind=RunEventKind.MODEL_USAGE, data=data)


def test_rollup_over_a_wire_event_without_the_key_keeps_tokens():
    """FR-015a consequence at the rollup: an event with NO cost_usd key
    rolls up to a dev row with cost_usd None and its tokens intact — a
    missing price must never discard tokens."""
    event = _wire_event(
        {
            "role": "dev",
            "model": "m",
            "calls": "1",
            "input_tokens": "100",
            "output_tokens": "20",
            "cache_read_tokens": "0",
            "cache_write_tokens": "0",
            # no cost_usd key
        }
    )
    roles = {u.role: u for u in _role_rollup([event])}
    assert roles["dev"].cost_usd is None
    assert roles["dev"].input_tokens == 100
    assert roles["dev"].output_tokens == 20


def test_rollup_over_a_wire_zero_maps_the_honest_zero():
    """An event that DOES carry cost_usd='0.0' rolls up to a real 0.0: the
    wire cannot distinguish an honest zero from a missing price — this pins
    that the server no longer CREATES zero events for unpriced runs (the
    emit omits the key) but still maps the honest zeros it receives."""
    event = _wire_event(
        {
            "role": "dev",
            "model": "m",
            "calls": "1",
            "input_tokens": "100",
            "output_tokens": "20",
            "cache_read_tokens": "0",
            "cache_write_tokens": "0",
            "cost_usd": "0.0",
        }
    )
    roles = {u.role: u for u in _role_rollup([event])}
    assert roles["dev"].cost_usd == 0.0
