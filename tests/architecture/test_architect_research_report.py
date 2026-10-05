"""The architect's research tool, reported side: the inner run's usage comes
back beside the brief (plan D7 report tests; tasks.md T002).

Part 1 added tests 1, 2, 6, 7, 8 (PIN) and 8a; part 2 adds 3, 4 and 5 (after
test 2) and 9 and 10 (at the end). Import discipline (T002): symbols that do
not exist on the base commit -- ``research_subquery_reported``,
``tool_return``, ``metadata_for``, ``SubRunUsage`` -- are imported INSIDE the
test functions that use them, so this module collects on the base commit and
the base-API tests (8, 8a) run there. On the base commit: test 8 passes (PIN),
8a fails on behaviour (the ``UsageLimitExceeded`` escapes the un-degraded
``research_subquery`` -- the SC-001 evidence for N3), 1, 2, 3, 4, 5, 6, 7 and
10 fail by import or attribute error (they are not SC-001 evidence), and test
9 passes wherever the tool surface is unchanged: it pins the literal captured
on the base commit."""

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ToolReturn

import sdlc.agents.roles as roles
from sdlc.stages.research.deps import BudgetExceeded, ResearchDeps
from sdlc.stages.research.models import Gap, ResearchBrief

_QUESTION = "how many collars fit in one zone?"


def _make_deps(**extra) -> ResearchDeps:
    return ResearchDeps(
        run_id="r1",
        provider="fake",
        max_searches=5,
        max_fetches=10,
        max_cost_usd=1.0,
        **extra,
    )


class _FakeResult:
    """Just enough of a pydantic_ai run result: the toolset reads .output."""

    def __init__(self, output):
        self.output = output


class _CountingAgent:
    """Fake t_research: adds known counts to the caller-owned ``usage=`` kwarg
    and answers with a canned brief. Accepts **kwargs so it works against the
    base call shape (question, deps=) and the reported call shape (which adds
    usage= and usage_limits=)."""

    def __init__(self, brief):
        self.brief = brief
        self.kwargs = None

    async def run(self, question, *args, **kwargs):
        self.kwargs = kwargs
        usage = kwargs.get("usage")
        if usage is not None:
            usage.input_tokens += 101
            usage.output_tokens += 23
            usage.cache_read_tokens += 5
            usage.cache_write_tokens += 7
        return _FakeResult(self.brief)


class _SilentAgent:
    """Answers without touching the usage kwarg: the caller-owned counts stay
    zero, so the reported function must give back report=None."""

    def __init__(self, brief):
        self.brief = brief

    async def run(self, question, *args, **kwargs):
        return _FakeResult(self.brief)


@pytest.mark.asyncio
async def test_reported_function_returns_the_brief_and_the_inner_spend(monkeypatch):
    """Plan D7 report test 1 (RED 6.2): the reported entry point returns the
    brief AND a report of the counts the inner run added to the caller-owned
    usage object. On base the function does not exist (attribute error)."""
    from sdlc.observability.sub_run_usage import SubRunUsage
    from sdlc.stages.research import toolset

    brief = ResearchBrief(summary="canned")
    agent = _CountingAgent(brief)
    monkeypatch.setattr(roles, "t_research", agent)

    got, report = await toolset.research_subquery_reported(_make_deps(), _QUESTION)

    assert got == brief
    assert isinstance(report, SubRunUsage)
    assert (report.input_tokens, report.output_tokens) == (101, 23)
    assert (report.cache_read_tokens, report.cache_write_tokens) == (5, 7)


@pytest.mark.asyncio
async def test_inner_run_is_bounded_by_the_deps_request_limit(monkeypatch):
    """Plan D7 report test 2 (RED N3): the inner run is called with
    usage_limits whose request_limit is the deps' max_requests. On base the
    function does not exist, and ResearchDeps carries no max_requests field."""
    from sdlc.stages.research import toolset

    agent = _CountingAgent(ResearchBrief(summary="canned"))
    monkeypatch.setattr(roles, "t_research", agent)
    deps = _make_deps(max_requests=7)  # extra="ignore" on base; a field after T008

    await toolset.research_subquery_reported(deps, _QUESTION)

    limits = agent.kwargs.get("usage_limits")
    assert limits is not None, "the inner run must be bounded by usage_limits"
    assert limits.request_limit == deps.max_requests


class _LimitStopAgent:
    """Fake t_research: banks known counts on the caller-owned ``usage=`` kwarg,
    then stops the way the real inner run stops at the request limit, raising
    the exception handed to it."""

    def __init__(self, exc):
        self.exc = exc

    async def run(self, question, *args, **kwargs):
        usage = kwargs.get("usage")
        if usage is not None:
            usage.input_tokens += 61
            usage.output_tokens += 17
            usage.cache_read_tokens += 3
            usage.cache_write_tokens += 9
        raise self.exc


@pytest.mark.asyncio
async def test_usage_limit_stop_degrades_with_our_own_text_and_still_reports(
    monkeypatch,
):
    """Plan D7 report test 3 (RED N3, AM2): a request-limit stop degrades to a
    gap-only brief whose text is OURS -- it names the limit in plain words and
    never leaks the library's advice or its documentation URL -- and the counts
    banked before the raise are still reported. On base the reported function
    does not exist (attribute error)."""
    from sdlc.stages.research import toolset

    exc = UsageLimitExceeded("The next request would exceed the request_limit of 7")
    # The library appends its advice and docs URL to whatever message it is
    # given (baseline.md E3): str(exc) is the real text verbatim, and keeping
    # it out of the brief is exactly what this test pins.
    assert "Consider raising the limit" in str(exc) and "http" in str(exc)
    monkeypatch.setattr(roles, "t_research", _LimitStopAgent(exc))
    deps = _make_deps(max_requests=7)

    brief, report = await toolset.research_subquery_reported(deps, _QUESTION)

    reason = "request limit exhausted (7 requests)"
    assert len(brief.gaps) == 1
    assert reason in brief.gaps[0].why_it_matters
    assert reason in brief.summary
    for text in (brief.gaps[0].why_it_matters, brief.summary):
        assert "http" not in text, "the library's docs URL must never reach the model"
        assert "Consider raising the limit" not in text, (
            "the library's advice must never reach the model"
        )
    assert report is not None
    assert (report.input_tokens, report.output_tokens) == (61, 17)
    assert (report.cache_read_tokens, report.cache_write_tokens) == (3, 9)


class _BudgetStopAgent:
    """Fake t_research: banks known counts on the caller-owned ``usage=`` kwarg,
    then stops the way the real inner run stops at the budget, raising the
    exception handed to it."""

    def __init__(self, exc):
        self.exc = exc

    async def run(self, question, *args, **kwargs):
        usage = kwargs.get("usage")
        if usage is not None:
            usage.input_tokens += 44
            usage.output_tokens += 11
            usage.cache_read_tokens += 6
            usage.cache_write_tokens += 2
        raise self.exc


@pytest.mark.asyncio
async def test_budget_stop_degrades_exactly_as_today_and_still_reports(monkeypatch):
    """Plan D7 report test 4 (RED EC3): a BudgetExceeded stop degrades to
    today's gap-only brief, field for field, and the counts banked before the
    raise are still reported -- the budget path gains a report and loses
    nothing. On base the reported function does not exist (attribute error)."""
    from sdlc.stages.research import toolset

    exc_text = "search budget exhausted (5 searches)"
    monkeypatch.setattr(roles, "t_research", _BudgetStopAgent(BudgetExceeded(exc_text)))
    deps = _make_deps()

    brief, report = await toolset.research_subquery_reported(deps, _QUESTION)

    assert brief == ResearchBrief(
        gaps=[
            Gap(
                sub_question_id="architect-midrun",
                what_is_missing=_QUESTION,
                why_it_matters=exc_text,
            )
        ],
        summary=(
            f"Research budget exhausted before this sub-question could be answered: {exc_text}"
        ),
    )
    assert report is not None
    assert (report.input_tokens, report.output_tokens) == (44, 11)
    assert (report.cache_read_tokens, report.cache_write_tokens) == (6, 2)


@pytest.mark.asyncio
async def test_a_real_agent_stops_at_the_deps_request_limit(monkeypatch):
    """Plan D7 report test 5 (RED N3): a REAL pydantic_ai agent that loops on a
    trivial tool (the baseline E3 pattern) stops at the deps' request limit: no
    exception escapes, the brief degrades to a single gap with no findings, and
    the spend the loop left in the caller-owned usage is reported. On base the
    reported function does not exist (attribute error)."""
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from sdlc.stages.research import toolset

    def loop_forever(messages, info: AgentInfo) -> ModelResponse:
        # 2.51 auto-generates a tool_call_id per part, so the loop never stalls.
        return ModelResponse(parts=[ToolCallPart("get_value", {"x": 1})])

    agent = Agent(FunctionModel(loop_forever), deps_type=ResearchDeps)

    @agent.tool
    def get_value(ctx: RunContext[ResearchDeps], x: int) -> int:
        """Trivial tool the loop never leaves."""
        return x

    monkeypatch.setattr(roles, "t_research", agent)

    brief, report = await toolset.research_subquery_reported(_make_deps(max_requests=3), _QUESTION)

    assert len(brief.gaps) == 1
    assert brief.grounded_findings == [] and brief.inferred_findings == []
    assert report is not None
    assert report.input_tokens > 0 and report.output_tokens > 0


@pytest.mark.asyncio
async def test_report_names_the_answering_model(monkeypatch):
    """Plan D7 report test 6 (RED EC6): the report's model is the forwarded
    research_model when set, else the registry's research model, else the
    literal "unknown". On base the function does not exist."""
    from sdlc.stages.research import toolset

    # deps.research_model set: the override answered.
    agent = _CountingAgent(ResearchBrief(summary="canned"))
    monkeypatch.setattr(roles, "t_research", agent)
    _, report = await toolset.research_subquery_reported(
        _make_deps(research_model="override-model"), _QUESTION
    )
    assert report is not None
    assert report.model == "override-model"

    # unset: the registry's research entry answered.
    agent = _CountingAgent(ResearchBrief(summary="canned"))
    monkeypatch.setattr(roles, "t_research", agent)
    _, report = await toolset.research_subquery_reported(_make_deps(), _QUESTION)
    registry_model = roles.REGISTRY["research"].model
    assert registry_model is not None, "expected the shipped registry to declare a research model"
    assert report is not None
    assert report.model == registry_model

    # registry model None: the sentinel, so pricing is asked and answers no dollars.
    entry = roles.REGISTRY["research"]
    monkeypatch.setitem(roles.REGISTRY, "research", entry.model_copy(update={"model": None}))
    agent = _CountingAgent(ResearchBrief(summary="canned"))
    monkeypatch.setattr(roles, "t_research", agent)
    _, report = await toolset.research_subquery_reported(_make_deps(), _QUESTION)
    assert report is not None
    assert report.model == "unknown"


@pytest.mark.asyncio
async def test_tool_return_carries_the_report_only_when_there_is_one(monkeypatch):
    """Plan D7 report test 7 (RED): zero inner spend gives report=None and the
    bare brief back from tool_return; a spend gives a ToolReturn whose
    return_value is the brief and whose metadata is metadata_for(report). On
    base neither tool_return nor metadata_for exists."""
    from sdlc.observability.sub_run_usage import metadata_for
    from sdlc.stages.research import toolset

    brief = ResearchBrief(summary="canned")
    monkeypatch.setattr(roles, "t_research", _SilentAgent(brief))
    _, report = await toolset.research_subquery_reported(_make_deps(), _QUESTION)
    assert report is None
    assert toolset.tool_return(brief, None) is brief

    agent = _CountingAgent(brief)
    monkeypatch.setattr(roles, "t_research", agent)
    _, report = await toolset.research_subquery_reported(_make_deps(), _QUESTION)
    out = toolset.tool_return(brief, report)
    assert isinstance(out, ToolReturn)
    assert out.return_value == brief
    assert out.metadata == metadata_for(report)


@pytest.mark.asyncio
async def test_research_subquery_returns_a_brief(monkeypatch):
    """Plan D7 report test 8 (PIN): the existing entry point still returns a
    ResearchBrief. Must pass on the base commit and keep passing once T008
    turns research_subquery into a thin wrapper over the reported function."""
    from sdlc.stages.research import toolset

    brief = ResearchBrief(summary="canned")
    monkeypatch.setattr(roles, "t_research", _SilentAgent(brief))

    got = await toolset.research_subquery(_make_deps(), _QUESTION)

    assert isinstance(got, ResearchBrief)
    assert got == brief


class _LimitExceededAgent:
    """Base-API fake: the signature the plan pins for 8a -- positional deps,
    **kwargs for the future usage=/usage_limits= -- raising the library's
    limit exception out of the inner run."""

    async def run(self, question, deps, **kwargs):
        raise UsageLimitExceeded("request_limit of 2 exceeded")


@pytest.mark.asyncio
async def test_research_subquery_degrades_instead_of_raising_on_usage_limit_exceeded(
    monkeypatch,
):
    """Plan D7 report test 8a (RED, base API; the SC-001 evidence for N3): a
    request-limit stop inside the inner run must degrade to a gap-only brief
    exactly like a budget stop does, never escape. On base only BudgetExceeded
    is caught, so the exception escapes and this test fails on that behaviour."""
    from sdlc.stages.research import toolset

    monkeypatch.setattr(roles, "t_research", _LimitExceededAgent())

    brief = await toolset.research_subquery(_make_deps(), _QUESTION)

    assert isinstance(brief, ResearchBrief)
    assert brief.gaps, "a limit stop must degrade to a gap-only brief, not raise"
    gap = brief.gaps[0]
    assert gap.what_is_missing == _QUESTION
    assert gap.sub_question_id == "architect-midrun"
    assert brief.grounded_findings == [] and brief.inferred_findings == []


_RESEARCH_TOOL_DEFINITION = {
    # Captured on the branch base (e5c8ef8) from build(TestModel(), ...)'s
    # registered research tool -- its tool_def name, description and parameters
    # schema, dumped with json.dumps(..., sort_keys=True). FR-001/FR-009: what
    # the model receives must not change.
    "name": "research",
    "description": (
        "Consult grounded research on a sub-question. Draws down this run's\n"
        "shared research budget (SGR Routing: local vs. web)."
    ),
    "parameters_json_schema": {
        "additionalProperties": False,
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
        "type": "object",
    },
}


def test_architect_research_tool_surface_is_pinned():
    """Plan D7 report test 9: the research tool the architect agent registers
    keeps its exact surface -- name, description, parameters schema (FR-001/
    FR-009: what the model receives must not change) -- and its function still
    returns a plain ResearchBrief. Self-contained: the live agent toolset is
    compared against the literal above; no discovery run needed."""
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.settings import ModelSettings

    from agents.architect.agent import build

    agent = build(TestModel(), "instructions", ModelSettings())

    tools: dict = {}
    for toolset in agent.toolsets:
        registered = getattr(toolset, "tools", None)
        if isinstance(registered, dict):
            tools.update(registered)
    tool = tools["research"]

    assert {
        "name": tool.tool_def.name,
        "description": tool.tool_def.description,
        "parameters_json_schema": tool.tool_def.parameters_json_schema,
    } == _RESEARCH_TOOL_DEFINITION

    assert tool.function.__annotations__["return"] is ResearchBrief


def test_research_deps_round_trips_max_requests():
    """Plan D7 report test 10 (RED, the limit field; lands with the toolset):
    ResearchDeps carries max_requests (ge=1; the default 40 equals
    ResearchConfig's), omitted from the dump at the default so the no-override
    payload stays byte-identical (FR-010) and serialized when set; 0 is
    rejected. On base the field does not exist (extra kwargs are ignored), so
    the first read-back raises AttributeError."""
    from sdlc.core.models import ResearchConfig

    default_dump = _make_deps().model_dump()
    assert "max_requests" not in default_dump
    round_tripped = ResearchDeps.model_validate(default_dump)
    assert round_tripped.max_requests == 40
    assert round_tripped.max_requests == ResearchConfig().max_requests

    custom = _make_deps(max_requests=12)
    assert custom.model_dump()["max_requests"] == 12
    assert ResearchDeps.model_validate(custom.model_dump()).max_requests == 12

    with pytest.raises(ValidationError):
        _make_deps(max_requests=0)
