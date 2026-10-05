"""RoleHost._run_role harvests sub-run usage reports (plan D7 harvest tests;
tasks.md T004): a tool that ran a model inside its own activity hands the
usage back as tool-return metadata under the literal key ``sdlc_sub_run_usage``
and the single model-egress point must price it once per answering model,
track it under role ``research`` and fold the spend into the caller's bag.

Part 1 added tests 1, 2, 3 (PIN), 5 (PIN) and 6 (PIN); part 2 adds test 4
(after test 3) and the ReportHost-backed tests 7-8 (at the end). Import
discipline: the file imports NOTHING that does not exist on the base commit
-- reports are literal dicts and the key is spelled as a literal -- so it
collects and runs on base, where tests 1, 2, 4, 7 and 8 fail on behaviour
(no research tracking, no research pricing, no fold) and 3, 5, 6 pass
(PIN)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from temporalio import workflow

from sdlc.core.models import GateDecision, GateOutcome, PipelineConfig, RoleUsage
from sdlc.memoization.activities import cache_get
from sdlc.observability.trace import RunEventKind
from sdlc.pricing import price_usage
from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.workflows.report_host import ReportHost
from sdlc.workflows.role_host import RoleHost

_ARCHITECT_LABEL = "architect-model"

_CANNED_SPEC = ArchitectureSpec(overview="canned", decisions=[])
_CANNED_SPEC_JSON = _CANNED_SPEC.model_dump_json()


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class _Part:
    part_kind: str
    metadata: object = None


@dataclass
class _Message:
    parts: list


@dataclass
class _RunResult:
    """The guard-file result shape: .output and .usage, no new_messages."""

    output: str = "ok"
    usage: _Usage = field(default_factory=_Usage)


class _MessagesResult:
    """A result whose new_messages() carries stub messages with parts."""

    def __init__(self, usage, messages):
        self.output = "ok"
        self.usage = usage
        self._messages = messages

    def new_messages(self):
        return self._messages


class _RecordingAgent:
    def __init__(self, result):
        self.result = result

    async def run(self, *args, **kwargs):
        return self.result


class _Host(RoleHost):
    """RoleHost with _track_usage recorded (the guard-file stub; ReportHost
    joins the MRO only in part 2's tests 7-8)."""

    def __init__(self) -> None:
        super().__init__()
        self.tracked: list[dict[str, object]] = []

    def _track_usage(self, **kw: object) -> None:
        self.tracked.append(kw)


def _report(model, input_tokens, output_tokens, cache_read=0, cache_write=0):
    """The report as the tool hands it over: a LITERAL metadata dict under the
    literal key (no new symbol imported anywhere in this file)."""
    return {
        "sdlc_sub_run_usage": {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
        }
    }


def _tool_return(metadata):
    return _Part(part_kind="tool-return", metadata=metadata)


def _messages_result(usage, messages):
    return _MessagesResult(usage, messages)


def _bag() -> RoleUsage:
    return RoleUsage(role="architect", model=_ARCHITECT_LABEL)


def _fake_activities(prices, recorded):
    """An execute_activity stand-in: records every (activity, input), answers
    price_usage from `prices`, and fails loudly on anything else so an
    unintended path surfaces."""

    async def fake(act, inp, *args, **kwargs):
        recorded.append((act, inp))
        if act is price_usage:
            return prices[inp.model]
        raise AssertionError(f"unexpected activity {act!r} in this test")

    return fake


def _priced(recorded):
    return [inp for act, inp in recorded if act is price_usage]


@pytest.mark.asyncio
async def test_one_report_is_tracked_as_research_and_priced(monkeypatch):
    """Plan D7 harvest test 1 (RED 6.2, base API; the SC-001 evidence for
    6.2): after the architect's own accounting, ONE report in the messages is
    tracked as one research call (report model and counts, into=None) and
    priced with exactly one price_usage input. On base there is no research
    track call and no such price input."""
    recorded: list = []
    monkeypatch.setattr(
        workflow,
        "execute_activity",
        _fake_activities({_ARCHITECT_LABEL: 0.5, "m-research": 0.25}, recorded),
    )
    host, bag = _Host(), _bag()
    agent = _RecordingAgent(
        _messages_result(
            _Usage(100, 10),
            [_Message(parts=[_tool_return(_report("m-research", 11, 2, 3, 4))])],
        )
    )

    await host._run_role(PipelineConfig(), "architect", _ARCHITECT_LABEL, agent, "p", into=bag)

    architect = host.tracked[0]
    assert architect["role"] == "architect"
    assert architect["model"] == _ARCHITECT_LABEL
    assert architect["into"] is bag
    assert architect["cost_usd"] == 0.5

    research = [t for t in host.tracked if t["role"] == "research"]
    assert len(research) == 1, "the report must be tracked exactly once as research"
    call = research[0]
    assert call["model"] == "m-research"
    assert (call["input_tokens"], call["output_tokens"]) == (11, 2)
    assert (call["cache_read_tokens"], call["cache_write_tokens"]) == (3, 4)
    assert call["into"] is None

    priced = _priced(recorded)
    assert [i.model for i in priced] == [_ARCHITECT_LABEL, "m-research"]


@pytest.mark.asyncio
async def test_reports_are_priced_once_per_model_and_folded_into_the_bag(monkeypatch):
    """Plan D7 harvest test 2 (RED AM3, SC-003): three reports over two
    models are priced ONCE per model with that model's SUMMED counts (in
    first-seen order), tracked per report in message order -- first report of
    a model carries the batch dollars, later ones 0.0 -- and the caller's bag
    grows by the architect's usage plus the sums while keeping its model and
    exactly one added call."""
    recorded: list = []
    monkeypatch.setattr(workflow, "now", lambda: _AT)
    monkeypatch.setattr(
        workflow,
        "execute_activity",
        _fake_activities({_ARCHITECT_LABEL: 0.5, "m1": 0.25, "m2": 0.75}, recorded),
    )
    host, bag = _ReportingHost(), _bag()
    agent = _RecordingAgent(
        _messages_result(
            _Usage(100, 10),
            [
                _Message(
                    parts=[
                        _tool_return(_report("m1", 10, 1, 1, 0)),
                        _tool_return(_report("m1", 20, 2, 2, 0)),
                    ]
                ),
                _Message(parts=[_tool_return(_report("m2", 30, 3, 0, 0))]),
            ],
        )
    )

    await host._run_role(PipelineConfig(), "architect", _ARCHITECT_LABEL, agent, "p", into=bag)

    priced = _priced(recorded)
    assert [i.model for i in priced] == [_ARCHITECT_LABEL, "m1", "m2"]
    assert (priced[1].input_tokens, priced[1].output_tokens) == (30, 3)
    assert (priced[1].cache_read_tokens, priced[1].cache_write_tokens) == (3, 0)
    assert (priced[2].input_tokens, priced[2].output_tokens) == (30, 3)
    assert (priced[2].cache_read_tokens, priced[2].cache_write_tokens) == (0, 0)

    research = [t for t in host.tracked if t["role"] == "research"]
    assert [t["model"] for t in research] == ["m1", "m1", "m2"]
    assert (research[0]["input_tokens"], research[0]["output_tokens"]) == (10, 1)
    assert (research[0]["cache_read_tokens"], research[0]["cache_write_tokens"]) == (1, 0)
    assert (research[1]["input_tokens"], research[1]["output_tokens"]) == (20, 2)
    assert (research[1]["cache_read_tokens"], research[1]["cache_write_tokens"]) == (2, 0)
    assert (research[2]["input_tokens"], research[2]["output_tokens"]) == (30, 3)
    assert (research[2]["cache_read_tokens"], research[2]["cache_write_tokens"]) == (0, 0)
    assert research[0]["cost_usd"] == 0.25
    assert research[1]["cost_usd"] == 0.0
    assert research[2]["cost_usd"] == 0.75
    assert all(t["into"] is None for t in research)

    assert bag.calls == 1, "the harvest never adds a call to the caller's bag"
    assert bag.model == _ARCHITECT_LABEL
    assert (bag.input_tokens, bag.output_tokens) == (160, 16)
    assert (bag.cache_read_tokens, bag.cache_write_tokens) == (3, 0)
    assert bag.cost_usd == 1.5


@pytest.mark.asyncio
async def test_no_reports_change_nothing_today(monkeypatch):
    """Plan D7 harvest test 3 (PIN, FR-005): a result with no message
    accessor at all, and one whose messages hold only a metadata-less
    tool-return part, must both leave exactly today's single architect track
    and single own price input. Green on base and after the harvest."""
    recorded: list = []
    monkeypatch.setattr(
        workflow, "execute_activity", _fake_activities({_ARCHITECT_LABEL: 0.5}, recorded)
    )
    host = _Host()
    await host._run_role(
        PipelineConfig(),
        "architect",
        _ARCHITECT_LABEL,
        _RecordingAgent(_RunResult(usage=_Usage(100, 10))),
        "p",
        into=_bag(),
    )
    assert len(host.tracked) == 1
    assert host.tracked[0]["role"] == "architect"
    assert [i.model for i in _priced(recorded)] == [_ARCHITECT_LABEL]

    recorded = []
    monkeypatch.setattr(
        workflow, "execute_activity", _fake_activities({_ARCHITECT_LABEL: 0.5}, recorded)
    )
    host = _Host()
    await host._run_role(
        PipelineConfig(),
        "architect",
        _ARCHITECT_LABEL,
        _RecordingAgent(_messages_result(_Usage(100, 10), [_Message(parts=[_tool_return(None)])])),
        "p",
        into=_bag(),
    )
    assert len(host.tracked) == 1
    assert host.tracked[0]["role"] == "architect"
    assert [i.model for i in _priced(recorded)] == [_ARCHITECT_LABEL]


@pytest.mark.asyncio
async def test_pricing_failure_for_a_report_model_still_tracks_and_spares_the_bag(
    monkeypatch,
):
    """Plan D7 harvest test 4 (RED EC5): pricing RAISING for a report's model
    must not fail the stage -- the architect keeps its price, the report is
    still tracked under research with cost_usd=None and its own counts, and
    the caller's bag gains ONLY the architect's dollars. On base the report is
    never priced and never tracked."""
    recorded: list = []

    async def failing_for_m1(act, inp, *args, **kwargs):
        recorded.append((act, inp))
        if act is price_usage:
            if inp.model == "m1":
                raise RuntimeError("pricing table down for m1")
            return 0.5
        raise AssertionError(f"unexpected activity {act!r} in this test")

    monkeypatch.setattr(workflow, "execute_activity", failing_for_m1)
    monkeypatch.setattr(workflow, "now", lambda: _AT)
    host, bag = _ReportingHost(), _bag()
    agent = _RecordingAgent(
        _messages_result(
            _Usage(100, 10),
            [_Message(parts=[_tool_return(_report("m1", 11, 2, 3, 4))])],
        )
    )

    await host._run_role(PipelineConfig(), "architect", _ARCHITECT_LABEL, agent, "p", into=bag)

    assert [i.model for i in _priced(recorded)] == [_ARCHITECT_LABEL, "m1"]
    architect = host.tracked[0]
    assert architect["role"] == "architect"
    assert architect["cost_usd"] == 0.5

    research = [t for t in host.tracked if t["role"] == "research"]
    assert len(research) == 1, "the unpriced report must still be tracked as research"
    call = research[0]
    assert call["model"] == "m1"
    assert (call["input_tokens"], call["output_tokens"]) == (11, 2)
    assert (call["cache_read_tokens"], call["cache_write_tokens"]) == (3, 4)
    assert call["cost_usd"] is None
    assert call["into"] is None

    assert bag.cost_usd == 0.5, "the unpriced report must add no dollars to the bag"


@pytest.mark.asyncio
async def test_architect_pricing_failure_degrades_to_none(monkeypatch):
    """Plan D7 harvest test 5 (PIN): the architect's own pricing failure
    degrades to cost_usd=None and must never fail the stage (the shared _price
    keeps this after D4). Green on base."""

    async def failing(act, inp, *args, **kwargs):
        if act is price_usage:
            raise RuntimeError("pricing table down")
        raise AssertionError(f"unexpected activity {act!r} in this test")

    monkeypatch.setattr(workflow, "execute_activity", failing)
    host = _Host()

    await host._run_role(
        PipelineConfig(),
        "architect",
        _ARCHITECT_LABEL,
        _RecordingAgent(_RunResult(usage=_Usage(100, 10))),
        "p",
        into=_bag(),
    )

    assert len(host.tracked) == 1
    assert host.tracked[0]["role"] == "architect"
    assert host.tracked[0]["cost_usd"] is None


@pytest.mark.asyncio
async def test_cache_hit_never_runs_the_closure(monkeypatch):
    """Plan D7 harvest test 6 (PIN, EC1, SC-004): a memoization cache hit
    returns before the closure that calls run_role -- nothing tracked, nothing
    priced. Green on base and after the harvest (the closure never runs)."""
    recorded: list = []

    async def fake(act, inp, *args, **kwargs):
        recorded.append((act, inp))
        if act is cache_get:
            return _CANNED_SPEC_JSON
        raise AssertionError(f"unexpected activity {act!r} in this test")

    monkeypatch.setattr(workflow, "execute_activity", fake)
    host = _Host()
    ran: list = []

    async def closure():
        ran.append(True)
        return ArchitectureSpec(overview="ran", decisions=[])

    spec, hit = await host._cached_stage(
        PipelineConfig(memoization_enabled=True),
        "architect",
        "key-json",
        ArchitectureSpec,
        closure,
        prompt_digest="",
    )

    assert hit is True
    assert spec == _CANNED_SPEC
    assert ran == [], "a cache hit must not run the closure"
    assert host.tracked == []
    assert [act for act, _ in recorded if act is price_usage] == []


_AT = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class _ReportingHost(ReportHost, RoleHost):
    """RoleHost with the REAL ReportHost._track_usage: state lands in
    _role_usage, MODEL_USAGE events in _trace, and the caller's bag gets the
    real fold (merge_usage semantics: calls bump, model relabel) — the bag
    assertions of tests 2 and 4 need exactly that. Also records every
    _track_usage call for the per-report share assertions, and _gate is a
    recording stub that approves, so budget behaviour is observable."""

    def __init__(self) -> None:
        super().__init__()
        self.gate_calls: list[tuple[str, object]] = []
        self.tracked: list[dict[str, object]] = []

    def _track_usage(self, **kw: object) -> None:
        self.tracked.append(kw)
        return super()._track_usage(**kw)

    async def _gate(self, key, settings, **kw):
        self.gate_calls.append((key, kw.get("context")))
        return GateDecision(gate="budget", outcome=GateOutcome.APPROVE, decided_by="policy")


@pytest.mark.asyncio
async def test_the_harvests_research_cost_reaches_the_budget_gate(monkeypatch):
    """Plan D7 harvest test 7 (RED budget): after one reported run the host's
    _role_usage holds the research row's cost, and _check_budget counts it --
    a 1.0 total against a 1.0 threshold crosses once, the gate sees the
    research dollars in its context rows, and the approval lifts the threshold
    so the loop exits. On base there is no research row: the total stays 0.25
    and the gate is never called."""
    monkeypatch.setattr(workflow, "now", lambda: _AT)
    monkeypatch.setattr(
        workflow,
        "execute_activity",
        _fake_activities({_ARCHITECT_LABEL: 0.25, "m1": 0.75}, []),
    )
    host = _ReportingHost()
    agent = _RecordingAgent(
        _messages_result(
            _Usage(100, 10),
            [_Message(parts=[_tool_return(_report("m1", 11, 2, 3, 4))])],
        )
    )

    await host._run_role(PipelineConfig(), "architect", _ARCHITECT_LABEL, agent, "p", into=_bag())

    architect_row = host._role_usage.get("architect")
    assert architect_row is not None and architect_row.cost_usd == 0.25
    research_row = host._role_usage.get("research")
    assert research_row is not None, "the harvest must leave a research row in _role_usage"
    assert research_row.cost_usd == 0.75

    host._budget_threshold = 1.0
    await host._check_budget(PipelineConfig(run_budget_usd=1.0))

    assert len(host.gate_calls) == 1, "a 1.0 total at a 1.0 threshold must gate once"
    key, context = host.gate_calls[0]
    assert key == "budget"
    assert context is not None and context.spec_summary is not None
    assert "research" in context.spec_summary, "the gate rows must name the research spend"
    assert "0.7500" in context.spec_summary
    assert host._budget_threshold == 2.0, "the approval must lift the threshold so the loop exits"


@pytest.mark.asyncio
async def test_model_usage_events_roll_up_to_exactly_the_role_usage(monkeypatch):
    """Plan D7 harvest test 8 (RED rollup): per-role usage rebuilt from ONLY
    the emitted MODEL_USAGE events equals _role_usage for BOTH roles -- the
    caller-bag fold (the harvest's add_spend) emits no event and touches no
    _role_usage row, so nothing is double counted. On base there is no
    research event and no research row, and the rebuild misses the role."""
    monkeypatch.setattr(workflow, "now", lambda: _AT)
    monkeypatch.setattr(
        workflow,
        "execute_activity",
        _fake_activities({_ARCHITECT_LABEL: 0.25, "m1": 0.75}, []),
    )
    host = _ReportingHost()
    agent = _RecordingAgent(
        _messages_result(
            _Usage(100, 10),
            [_Message(parts=[_tool_return(_report("m1", 11, 2, 3, 4))])],
        )
    )

    await host._run_role(PipelineConfig(), "architect", _ARCHITECT_LABEL, agent, "p", into=_bag())

    events = [e for e in host._trace if e.kind is RunEventKind.MODEL_USAGE]
    assert len(events) == 2, "one architect call and one research report: two events"

    rebuilt: dict[str, dict[str, object]] = {}
    for event in events:
        row = rebuilt.setdefault(
            event.data["role"],
            {
                "model": event.data["model"],
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cost_usd": None,
            },
        )
        row["model"] = event.data["model"]
        row["calls"] = int(row["calls"]) + int(event.data["calls"])
        for name in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            row[name] = int(row[name]) + int(event.data[name])
        if "cost_usd" in event.data:
            row["cost_usd"] = (row["cost_usd"] or 0.0) + float(event.data["cost_usd"])

    assert set(rebuilt) == {"architect", "research"}
    assert set(host._role_usage) == {"architect", "research"}
    for role, usage in host._role_usage.items():
        row = rebuilt[role]
        assert row["model"] == usage.model
        assert row["calls"] == usage.calls
        assert (
            row["input_tokens"],
            row["output_tokens"],
            row["cache_read_tokens"],
            row["cache_write_tokens"],
        ) == (
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
        )
        assert row["cost_usd"] == usage.cost_usd
