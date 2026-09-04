"""The handoff extraction role ships and is wired like every other role."""

from sdlc.agents import roles
from sdlc.agents.loader import KNOWN_ROLES, OPTIONAL_ROLES, load_registry
from sdlc.stages.code.models import HandoffSummary


def test_handoff_is_a_known_optional_role():
    assert "handoff" in OPTIONAL_ROLES
    assert "handoff" in KNOWN_ROLES


def test_registry_loads_handoff_with_a_model():
    registry = load_registry()
    assert registry["handoff"].kind == "proposer"
    assert registry["handoff"].model


def test_handoff_agent_emits_a_HandoffSummary():
    assert roles.handoff_agent is not None
    assert roles.handoff_agent.output_type is HandoffSummary


def test_handoff_temporal_agent_is_registered():
    assert roles.t_handoff is not None
    assert roles.t_handoff in roles.ALL_TEMPORAL_AGENTS


def test_handoff_stage_is_mapped():
    assert roles.STAGE_ROLES["handoff"] == "handoff"
    assert roles.STAGE_MODELS["handoff"]
