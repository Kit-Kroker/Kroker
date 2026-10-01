"""Fail-closed loader tests for the 003 durability seam (T015).

The contract's fail-closed list
(.specify/specs/003-temporal-durability-migration/contracts/
loader-build-contract.md): with a factory supplied, build_agents() must
reject — RegistryError naming the role — an asset whose build() does not
accept capabilities, drops them, attaches a second durability, weakens the
factory's activity config, keeps the default model heartbeat, or binds a
durability under another name; and accept the forwarding build.

Each case writes ONE role dir into a tmp registry. The fixture agents are
REAL pydantic_ai Agents on TestModel (not stubs): the loader's checks walk
the capability chain via TemporalDurability.from_agent, which only works on
real agents. RED today: the current build_agents verifies nothing, so rows
1-7 fail with DID NOT RAISE and only the control row passes.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

from sdlc.agents.loader import RegistryError, build_agents
from sdlc.core.models import RoleConfig

_PROPOSER_MODEL = "anthropic:glm-5.2"


def _factory() -> TemporalDurability:
    """The canonical factory every case builds against: 10 min / 3 attempts,
    model-request heartbeat disabled."""
    return TemporalDurability(
        activity_config=ActivityConfig(
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        ),
        model_activity_config={"heartbeat_timeout": None},
    )


def _load(tmp_path: Path, source: str) -> dict:
    """Write ONE role dir ('planner', agent name 'x_agent') and build it."""
    role_dir = tmp_path / "planner"
    role_dir.mkdir()
    (role_dir / "agent.py").write_text(source, encoding="utf-8")
    roles = {"planner": RoleConfig(kind="proposer", model=_PROPOSER_MODEL)}
    return build_agents(roles, {}, durability_factory=_factory, agents_dir=tmp_path)


# Generated agent.py modules. Each is self-contained (own imports) and
# constructs a real Agent so from_agent can walk its capability chain.
_PROLOGUE = """\
from datetime import timedelta

from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

OURS = ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=3),
)


def ours(**extra):
    return TemporalDurability(
        activity_config=OURS, model_activity_config={"heartbeat_timeout": None}, **extra
    )
"""

_OLD_SHAPE = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings):
    return Agent(TestModel(), name="x_agent", output_type=str)
"""
)

_DROPS_CAPABILITIES = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings, *, capabilities=()):
    return Agent(TestModel(), name="x_agent", output_type=str)
"""
)

_ATTACHES_SECOND = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings, *, capabilities=()):
    return Agent(
        TestModel(), name="x_agent", output_type=str, capabilities=[ours(), *capabilities]
    )
"""
)

_WEAKER_START_TO_CLOSE = (
    _PROLOGUE
    + """\

WEAKER = ActivityConfig(
    start_to_close_timeout=timedelta(minutes=20),
    retry_policy=RetryPolicy(maximum_attempts=3),
)


def build(model, instructions, model_settings):
    return Agent(
        TestModel(),
        name="x_agent",
        output_type=str,
        capabilities=[
            TemporalDurability(
                activity_config=WEAKER, model_activity_config={"heartbeat_timeout": None}
            )
        ],
    )
"""
)

_WEAKER_ATTEMPTS = (
    _PROLOGUE
    + """\

WEAKER = ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=5),
)


def build(model, instructions, model_settings):
    return Agent(
        TestModel(),
        name="x_agent",
        output_type=str,
        capabilities=[
            TemporalDurability(
                activity_config=WEAKER, model_activity_config={"heartbeat_timeout": None}
            )
        ],
    )
"""
)

_DEFAULT_HEARTBEAT = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings):
    return Agent(
        TestModel(),
        name="x_agent",
        output_type=str,
        capabilities=[TemporalDurability(activity_config=OURS)],
    )
"""
)

_NAME_MISMATCH = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings):
    return Agent(
        TestModel(), name="x_agent", output_type=str, capabilities=[ours(name="other_agent")]
    )
"""
)

_FORWARDS = (
    _PROLOGUE
    + """\

def build(model, instructions, model_settings, *, capabilities=()):
    return Agent(
        TestModel(), name="x_agent", output_type=str, capabilities=list(capabilities)
    )
"""
)


def test_old_shape_build_rejected(tmp_path):
    """A build() without a capabilities parameter cannot receive the
    factory's durability at all: the loader wraps the TypeError and names
    the role."""
    with pytest.raises(RegistryError, match="planner"):
        _load(tmp_path, _OLD_SHAPE)


def test_capability_dropping_build_rejected(tmp_path):
    """A build() that accepts capabilities but returns an Agent with NO
    TemporalDurability in its chain: from_agent finds None, fail closed."""
    with pytest.raises(RegistryError, match="planner"):
        _load(tmp_path, _DROPS_CAPABILITIES)


def test_second_own_durability_rejected(tmp_path):
    """A build() that attaches its OWN TemporalDurability alongside the
    forwarded ones: two instances on one agent, from_agent raises UserError,
    and the loader wraps it as RegistryError."""
    with pytest.raises(RegistryError, match="planner"):
        _load(tmp_path, _ATTACHES_SECOND)


def test_weaker_start_to_close_rejected(tmp_path):
    """A bound activity_config with a LONGER start_to_close_timeout than the
    factory's (20 min vs 10) weakens the durability budget: fail closed."""
    with pytest.raises(RegistryError, match="planner"):
        _load(tmp_path, _WEAKER_START_TO_CLOSE)


def test_weaker_maximum_attempts_rejected(tmp_path):
    """A bound retry policy with MORE attempts than the factory's (5 vs 3)
    multiplies the provider-call budget beyond the Temporal attempt budget:
    fail closed."""
    with pytest.raises(RegistryError, match="planner"):
        _load(tmp_path, _WEAKER_ATTEMPTS)


def test_default_model_heartbeat_rejected(tmp_path):
    """A durability without model_activity_config keeps the SDK's default
    30 s model heartbeat; the contract requires heartbeat_timeout None:
    fail closed."""
    with pytest.raises(RegistryError, match="planner"):
        _load(tmp_path, _DEFAULT_HEARTBEAT)


def test_durability_name_mismatch_rejected(tmp_path):
    """A durability bound under a name other than the agent's (other_agent
    vs x_agent) registers activities under an unexpected name: fail
    closed."""
    with pytest.raises(RegistryError, match="planner"):
        _load(tmp_path, _NAME_MISMATCH)


def test_forwarding_build_accepted(tmp_path):
    """Control row (non-regression, green today and after T016): the build
    that forwards the passed capabilities to a real Agent is accepted and
    the built agent comes back."""
    agents = _load(tmp_path, _FORWARDS)
    assert isinstance(agents["planner"], Agent)
    assert agents["planner"].name == "x_agent"
