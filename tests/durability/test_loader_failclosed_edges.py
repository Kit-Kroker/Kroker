"""Edge-case fail-closed loader tests for the 003 durability seam (T015
companion, qa-chaos): the checks' DIRECTION and SCOPE, not their mere
existence. Complements tests/durability/test_loader_failclosed.py (qa-happy):

1. tighter-than-factory is NOT weaker: own 5 min / 2 attempts must be
   accepted and must come back bound on the agent;
2. stub agents (no root_capability) are skipped by verification entirely;
3. checks are per-role: a bad second role is named alone;
4. fail CLOSED: exactly RegistryError, raised (no partial dict escapes);
5. harness roles consume no factory instance.

RED today: rows 3-4 fail with DID NOT RAISE (build_agents verifies nothing
yet). Rows 1, 2 and 5 are guard rows: green today by construction, they
must SURVIVE T016 — they pin the over-rejection and crash regressions the
implementation is most likely to introduce (rejecting tighter configs,
calling from_agent on stubs, charging harness roles a durability).
"""

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

from sdlc.agents.loader import RegistryError, build_agents
from sdlc.core.models import HarnessKind, RoleConfig

_FIXTURES = Path(__file__).parent / "fixture_agents"
_TOOL = _FIXTURES / "research" / "tools" / "web_search.py"
_PROPOSER_MODEL = "anthropic:glm-5.2"


def _factory() -> TemporalDurability:
    """The canonical factory: 10 min / 3 attempts, model heartbeat disabled.
    Every row judges configs against THIS floor."""
    return TemporalDurability(
        activity_config=ActivityConfig(
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        ),
        model_activity_config={"heartbeat_timeout": None},
    )


def _fixture_roles() -> dict[str, RoleConfig]:
    """The two stub-shape roles of fixture_agents/ (planner 3-arg, research
    5-arg), for rows that need built agents without real pydantic_ai ones."""
    return {
        "planner": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
        "research": RoleConfig(
            kind="research",
            model=_PROPOSER_MODEL,
            provider="fake",
            tool_files=[str(_TOOL)],
        ),
    }


# Generated agent.py modules, one role per case: self-contained (own
# imports), real pydantic_ai Agents so from_agent can walk the chain.
_PROLOGUE = """\
from datetime import timedelta

from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig
"""

_HEALTHY_FORWARDS = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings, *, capabilities=()):
    return Agent(
        TestModel(), name="good_agent", output_type=str, capabilities=list(capabilities)
    )
"""
)

_DROPS_CAPABILITIES = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings, *, capabilities=()):
    return Agent(TestModel(), name="bad_agent", output_type=str)
"""
)

# Does NOT forward: forwarding alongside its own would be the two-instance
# case (qa-happy's row). Tighter-only is the allowed not-weaker direction.
_TIGHTER_OWN = (
    _PROLOGUE
    + """\

TIGHTER = ActivityConfig(
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=2),
)


def build(model, instructions, model_settings, *, capabilities=()):
    return Agent(
        TestModel(),
        name="x_agent",
        output_type=str,
        capabilities=[
            TemporalDurability(
                activity_config=TIGHTER, model_activity_config={"heartbeat_timeout": None}
            )
        ],
    )
"""
)


def _one_role_registry(tmp_path: Path, source: str) -> dict[str, RoleConfig]:
    role_dir = tmp_path / "planner"
    role_dir.mkdir()
    (role_dir / "agent.py").write_text(source, encoding="utf-8")
    return {"planner": RoleConfig(kind="proposer", model=_PROPOSER_MODEL)}


def test_tighter_own_durability_not_weaker_accepted_and_bound(tmp_path):
    """The loader rejects only WEAKER-than-factory configs (longer s2c, more
    attempts). An asset binding its own TIGHTER durability (5 min < 10,
    2 attempts < 3, heartbeat None) stays legal -- and that instance, not
    the factory's, is what the agent runs with."""
    roles = _one_role_registry(tmp_path, _TIGHTER_OWN)
    agents = build_agents(roles, {}, durability_factory=_factory, agents_dir=tmp_path)

    bound = TemporalDurability.from_agent(agents["planner"])
    assert bound is not None
    assert bound.activity_config["start_to_close_timeout"] == timedelta(minutes=5)
    assert bound.activity_config["retry_policy"].maximum_attempts == 2
    assert bound.name == "x_agent"


def test_stub_agents_skip_durability_verification():
    """Fixture stubs record the call but carry no root_capability, so
    from_agent cannot even run on them: with a factory supplied the loader
    must return them unchanged -- verified NOTHING, crashed on NOTHING --
    still handing each its own capability instance. Guard row: T016 that
    calls from_agent unconditionally dies here with AttributeError."""
    sentinels: list[object] = []

    def factory() -> object:
        dur = object()
        sentinels.append(dur)
        return dur

    agents = build_agents(_fixture_roles(), {}, durability_factory=factory, agents_dir=_FIXTURES)
    planner, research = agents["planner"], agents["research"]

    assert not isinstance(planner, Agent)
    assert not hasattr(planner, "root_capability")
    assert planner.name == "planner_agent"
    assert planner.received_capabilities == [sentinels[0]]
    assert research.name == "research_agent"
    assert research.received_capabilities == [sentinels[1]]


def test_per_role_check_names_only_the_failing_role(tmp_path):
    """Checks run per role INDEPENDENTLY: with a healthy forwarding role
    first and a capability-dropping role second, the RegistryError names
    the FAILING role alone -- never the healthy one."""
    for role, source in (
        ("healthy", _HEALTHY_FORWARDS),
        ("dropping", _DROPS_CAPABILITIES),
    ):
        role_dir = tmp_path / role
        role_dir.mkdir()
        (role_dir / "agent.py").write_text(source, encoding="utf-8")
    roles = {
        "healthy": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
        "dropping": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
    }

    with pytest.raises(RegistryError) as excinfo:
        build_agents(roles, {}, durability_factory=_factory, agents_dir=tmp_path)

    message = str(excinfo.value)
    assert "dropping" in message
    assert "healthy" not in message


def test_fail_closed_raises_exactly_registryerror(tmp_path):
    """Fail closed, not fail silent: a dropping role must RAISE -- a partial
    agents dict must never escape -- and the exception is exactly
    RegistryError (a ValueError subclass), not a raw UserError or TypeError
    leaking through."""
    for role, source in (
        ("healthy", _HEALTHY_FORWARDS),
        ("dropping", _DROPS_CAPABILITIES),
    ):
        role_dir = tmp_path / role
        role_dir.mkdir()
        (role_dir / "agent.py").write_text(source, encoding="utf-8")
    roles = {
        "healthy": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
        "dropping": RoleConfig(kind="proposer", model=_PROPOSER_MODEL),
    }

    with pytest.raises(RegistryError) as excinfo:
        build_agents(roles, {}, durability_factory=_factory, agents_dir=tmp_path)

    assert type(excinfo.value) is RegistryError
    assert isinstance(excinfo.value, ValueError)


def test_factory_runs_once_per_non_harness_role_only():
    """Harness roles are skipped before any durability exists: 2 proposers
    (planner, research) + 1 harness role means EXACTLY 2 factory calls --
    harness must not consume a durability instance. Guard row: T016 moving
    the factory call breaks the N-roles/N-instances economy here."""
    calls: list[object] = []

    def factory() -> object:
        dur = object()
        calls.append(dur)
        return dur

    roles = {
        **_fixture_roles(),
        "dev": RoleConfig(kind="harness", harness=HarnessKind.OPENCODE, model=_PROPOSER_MODEL),
    }
    agents = build_agents(roles, {}, durability_factory=factory, agents_dir=_FIXTURES)

    assert len(calls) == 2
    assert set(agents) == {"planner", "research"}
