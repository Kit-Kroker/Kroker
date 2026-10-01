"""Edge-case contract tests for the 003 durability seam (T010 companion,
qa-chaos): the failure modes AROUND the factory call, not the happy path.

Complements tests/durability/test_loader_contract.py (qa-happy) on the same
fixture_agents/ registry: a raising factory must propagate, instances stay
per-role, capabilities reach build() as a KEYWORD on both shapes, the
duplicate-agent-name guard keeps firing with a factory supplied, and an
explicit None factory is the capability-free default.
"""

from pathlib import Path

import pytest

from sdlc.agents.loader import RegistryError, build_agents
from sdlc.core.models import RoleConfig

_FIXTURES = Path(__file__).parent / "fixture_agents"
_TOOL = _FIXTURES / "research" / "tools" / "web_search.py"
_PROPOSER_MODEL = "anthropic:glm-5.2"


def _roles() -> dict[str, RoleConfig]:
    """planner (3-arg build shape) + research (5-arg shape), per the brief."""
    return {
        "planner": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
        "research": RoleConfig(
            kind="research",
            model=_PROPOSER_MODEL,
            provider="fake",
            tool_files=[str(_TOOL)],
        ),
    }


class FactoryBoom(RuntimeError):
    """The misbehaving factory's own exception type, so the assertion can
    tell propagation apart from a RegistryError wrap."""


def test_raising_durability_factory_propagates():
    """A factory that raises must propagate ITS OWN exception: the loader
    neither swallows the failure into a RegistryError about imports nor
    silently skips the factory and builds capability-free agents."""
    calls: list[object] = []

    def factory() -> object:
        calls.append(object())
        raise FactoryBoom("durability factory exploded")

    with pytest.raises(FactoryBoom):
        build_agents(_roles(), {}, durability_factory=factory, agents_dir=_FIXTURES)
    assert calls, "factory was never invoked"


def test_factory_called_once_per_role_instances_not_shared():
    """With BOTH roles present the factory runs exactly once per role, in
    registry order, and no capability object is shared between planner and
    research (a shared instance would bind one TemporalDurability to two
    agents)."""
    sentinels: list[object] = []

    def factory() -> object:
        dur = object()  # a fresh sentinel identity per call
        sentinels.append(dur)
        return dur

    agents = build_agents(_roles(), {}, durability_factory=factory, agents_dir=_FIXTURES)

    assert len(sentinels) == 2, "factory must run exactly once per role"
    assert agents["planner"].received_capabilities == [sentinels[0]]
    assert agents["research"].received_capabilities == [sentinels[1]]
    assert sentinels[0] is not sentinels[1]


def test_capabilities_reach_build_as_keyword_not_positional():
    """capabilities is keyword-only on every build shape. The research 5-arg
    build keeps tool_paths/provider positional, so a loader that passed the
    durability instance positionally would misbind the whole call; the full
    tuple -- model, tool file, provider, [durability] -- must land in the
    right parameters on both shapes."""
    dur = object()

    agents = build_agents(_roles(), {}, durability_factory=lambda: dur, agents_dir=_FIXTURES)
    planner, research = agents["planner"], agents["research"]

    assert planner.name == "planner_agent"
    assert planner.received_capabilities == [dur]
    assert research.tool_paths == [str(_TOOL)]
    assert research.provider == "fake"
    assert research.received_capabilities == [dur]


_DUPE_AGENT_SRC = """\
# No @dataclass: loader._load_build execs this without a sys.modules entry,
# which dataclass processing requires (reviewer finding, Phase 2).
class BuiltAgent:
    def __init__(self, name, received_capabilities):
        self.name = name
        self.received_capabilities = received_capabilities


def build(model, instructions, model_settings, *, capabilities=()):
    return BuiltAgent("dupe_agent", list(capabilities))
"""


def test_agent_name_collision_still_guarded_with_factory(tmp_path):
    """The existing duplicate-agent-name guard keeps firing when a
    durability factory IS supplied: two roles building agents of the same
    .name collide on Temporal activity names and fail closed with a
    RegistryError naming BOTH roles."""
    for role in ("alpha", "beta"):
        d = tmp_path / role
        d.mkdir()
        (d / "agent.py").write_text(_DUPE_AGENT_SRC, encoding="utf-8")

    roles = {
        "alpha": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
        "beta": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
    }
    with pytest.raises(RegistryError) as excinfo:
        # object IS a factory of fresh instances: object() per call.
        build_agents(roles, {}, durability_factory=object, agents_dir=tmp_path)

    message = str(excinfo.value)
    assert "alpha" in message and "beta" in message


def test_explicit_none_factory_is_the_capability_free_default():
    """durability_factory=None passed EXPLICITLY (not omitted) is the same
    loader-only/eval path: no error, and nothing else about the call
    changes -- agents come back with their names and research positionals
    intact and no capabilities at all."""
    agents = build_agents(_roles(), {}, durability_factory=None, agents_dir=_FIXTURES)

    assert agents["planner"].name == "planner_agent"
    assert agents["planner"].received_capabilities == []
    assert agents["research"].tool_paths == [str(_TOOL)]
    assert agents["research"].provider == "fake"
    assert agents["research"].received_capabilities == []
