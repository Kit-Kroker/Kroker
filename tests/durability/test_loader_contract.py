"""Loader contract tests for the 003 durability seam (T010, extended 004 T012).

build_agents() must hand every role's build() a capabilities list holding
THAT role's own durability instance — fresh per role, from the supplied
factory — followed by a fresh single_retry_layer() resolver (004). With no
factory (the loader-only/eval path) the role instead receives a fresh
route_layer() resolver (005 T010) — still exactly one resolver per role,
no durability sentinel, so a bare model string reaches the shared seam.
The fixture agents under
fixture_agents/ record the call on BuiltAgent instead of building a real
pydantic_ai.Agent: the loader contract is about the CALL, not the agent
(see fixture_agents/*/agent.py).
"""

from pathlib import Path

from pydantic_ai.capabilities import ResolveModelId

from sdlc.agents.loader import build_agents
from sdlc.core.models import RoleConfig

_FIXTURES = Path(__file__).parent / "fixture_agents"
_PROPOSER_MODEL = "anthropic:glm-5.2"


def _durable_and_retry(caps: list) -> tuple[list, list]:
    """Split a received capabilities list into (non-resolver, resolver)."""
    resolvers = [c for c in caps if isinstance(c, ResolveModelId)]
    others = [c for c in caps if not isinstance(c, ResolveModelId)]
    return others, resolvers


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
    instance leads the role's capabilities list, a fresh single-retry
    resolver follows it, and no instance is shared across roles."""
    sentinels: list[object] = []

    def factory() -> object:
        dur = object()  # a fresh sentinel identity per call
        sentinels.append(dur)
        return dur

    agents = build_agents(_roles(), {}, durability_factory=factory, agents_dir=_FIXTURES)

    for key, sentinel in (("planner", sentinels[0]), ("research", sentinels[1])):
        durables, resolvers = _durable_and_retry(agents[key].received_capabilities)
        assert durables == [sentinel], f"{key}: durability instance changed"
        assert len(resolvers) == 1, f"{key}: exactly one single-retry resolver"
    assert sentinels[0] is not sentinels[1]
    planner_retry = _durable_and_retry(agents["planner"].received_capabilities)[1][0]
    research_retry = _durable_and_retry(agents["research"].received_capabilities)[1][0]
    assert planner_retry is not research_retry, "resolvers must be fresh per agent"


def test_default_and_explicit_none_attach_a_fresh_route_layer():
    """durability_factory=None (the default) is the loader-only/eval path.
    005 T010: with the factory omitted AND passed as None explicitly, each
    fixture agent receives EXACTLY ONE capability — the route_layer resolver
    (a pydantic_ai ResolveModelId) — fresh per role, with no durability
    sentinels, so a bare model string still reaches the shared seam."""
    default = build_agents(_roles(), {}, agents_dir=_FIXTURES)
    explicit = build_agents(_roles(), {}, durability_factory=None, agents_dir=_FIXTURES)

    for label, agents in (("default", default), ("explicit None", explicit)):
        for key in ("planner", "research"):
            durables, resolvers = _durable_and_retry(agents[key].received_capabilities)
            assert durables == [], f"{label}/{key}: no durability sentinel expected"
            assert len(resolvers) == 1, f"{label}/{key}: exactly one route-layer resolver expected"
        planner_layer = _durable_and_retry(agents["planner"].received_capabilities)[1][0]
        research_layer = _durable_and_retry(agents["research"].received_capabilities)[1][0]
        assert planner_layer is not research_layer, (
            f"{label}: the route layer must be fresh per role"
        )


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
    durables, _ = _durable_and_retry(research.received_capabilities)
    assert durables == [sentinels[0]]
