"""Loader contract tests for the 003 durability seam (T010).

build_agents() must hand every role's build() a one-element capabilities
list holding THAT role's own durability instance — fresh per role, from
the supplied factory — and stay capability-free when no factory is given.
The fixture agents under fixture_agents/ record the call on BuiltAgent
instead of building a real pydantic_ai.Agent: the loader contract is about
the CALL, not the agent (see fixture_agents/*/agent.py).
"""

from pathlib import Path

from sdlc.agents.loader import build_agents
from sdlc.core.models import RoleConfig

_FIXTURES = Path(__file__).parent / "fixture_agents"
_PROPOSER_MODEL = "anthropic:glm-5.2"


def _roles() -> dict[str, RoleConfig]:
    """planner (3-arg build shape) + research (5-arg shape), per the brief."""
    tool = str(_FIXTURES / "research" / "tools" / "web_search.py")
    return {
        "planner": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
        "research": RoleConfig(
            kind="research",
            model=_PROPOSER_MODEL,
            provider="fake",
            tool_files=[tool],
        ),
    }


def test_factory_gives_each_role_its_own_fresh_capability():
    """One factory call per role (planner first, dict order); the returned
    instance is the ONE element the role's build received, and no instance
    is shared across roles."""
    sentinels: list[object] = []

    def factory() -> object:
        dur = object()  # a fresh sentinel identity per call
        sentinels.append(dur)
        return dur

    agents = build_agents(_roles(), {}, durability_factory=factory, agents_dir=_FIXTURES)

    assert agents["planner"].received_capabilities == [sentinels[0]]
    assert agents["research"].received_capabilities == [sentinels[1]]
    assert sentinels[0] is not sentinels[1]


def test_default_and_explicit_none_leave_agents_capability_free():
    """durability_factory=None (the default) is the loader-only/eval path:
    fixture agents receive NO capabilities — an empty list — whether the
    factory is omitted entirely or passed as None explicitly."""
    default = build_agents(_roles(), {}, agents_dir=_FIXTURES)
    explicit = build_agents(_roles(), {}, durability_factory=None, agents_dir=_FIXTURES)
    assert default["planner"].received_capabilities == []
    assert default["research"].received_capabilities == []
    assert explicit["planner"].received_capabilities == []
    assert explicit["research"].received_capabilities == []


def test_research_build_still_receives_tool_files_and_provider():
    """The research 5-arg shape keeps its existing positionals and gains the
    capabilities keyword alongside; tool paths and provider pass unchanged."""
    research_role = {"research": _roles()["research"]}
    sentinels: list[object] = []

    def factory() -> object:
        dur = object()
        sentinels.append(dur)
        return dur

    research = build_agents(research_role, {}, durability_factory=factory, agents_dir=_FIXTURES)[
        "research"
    ]

    assert research.tool_paths == research_role["research"].tool_files
    assert research.provider == "fake"
    assert research.received_capabilities == [sentinels[0]]
