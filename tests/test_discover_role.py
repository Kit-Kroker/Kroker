# tests/test_discover_role.py
"""E-48 DD7/P3-D3: the discover proposer is an OPTIONAL, KNOWN role."""
from sdlc.agents import loader, roles


def test_discover_is_optional_not_required():
    """An assessment-only agent must not fail boot on a feature-only
    deployment -- DD7's reason for OPTIONAL_ROLES over PROPOSER_ROLES."""
    assert "discover" in loader.OPTIONAL_ROLES
    assert "discover" not in loader.PROPOSER_ROLES
    assert "discover" not in loader.REQUIRED_ROLES


def test_discover_is_a_known_directory():
    """KNOWN_ROLES gates RECOGNITION: the unknown-directory check must keep
    biting on agents/discover/."""
    assert "discover" in loader.KNOWN_ROLES


def test_discover_is_a_stage_with_a_model_and_a_prompt_sha():
    """P3-D3: DD10's memo key reads both from here rather than from a second
    registry."""
    assert roles.STAGE_ROLES["discover"] == "discover"
    assert roles.STAGE_MODELS["discover"] == roles.REGISTRY["discover"].model
    assert len(roles.PROMPT_SHAS["discover"]) == 64


def test_t_discover_is_built_and_registered():
    assert roles.t_discover is not None
    assert roles.t_discover in roles.ALL_TEMPORAL_AGENTS


def test_the_proposer_can_only_return_dispositions():
    """ADR-22 at the type: the output_type has one field and it is
    dispositions. A proposer that could return capabilities would author."""
    from sdlc.assessment.discover.map import DiscoverProposal
    assert set(DiscoverProposal.model_fields) == {"dispositions"}
