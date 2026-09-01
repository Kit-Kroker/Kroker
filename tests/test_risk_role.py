# tests/test_risk_role.py
"""RD7: the risk proposer is an OPTIONAL, KNOWN role, exactly as discover
is -- an assessment-only agent must not fail boot on a feature-only
deployment."""

from sdlc.agents import loader, roles


def test_risk_is_optional_not_required():
    assert "risk" in loader.OPTIONAL_ROLES
    assert "risk" not in loader.PROPOSER_ROLES
    assert "risk" not in loader.REQUIRED_ROLES


def test_risk_is_a_known_directory():
    """KNOWN_ROLES gates RECOGNITION: the unknown-directory check must keep
    biting on agents/risk/."""
    assert "risk" in loader.KNOWN_ROLES


def test_risk_is_a_stage_with_a_model_and_a_prompt_sha():
    """The assess memo key reads both from here rather than from a second
    registry."""
    assert roles.STAGE_ROLES["risk"] == "risk"
    assert roles.STAGE_MODELS["risk"] == roles.REGISTRY["risk"].model
    assert len(roles.PROMPT_SHAS["risk"]) == 64


def test_t_risk_is_built_and_registered():
    assert roles.t_risk is not None
    assert roles.t_risk in roles.ALL_TEMPORAL_AGENTS


def test_the_proposer_can_only_return_dispositions():
    """ADR-22 at the type: five disposition families and nothing else. A
    proposer that could return a CapabilityRisk would author the number
    FR-917 gates on."""
    from sdlc.assessment.risk.models import RiskProposal

    assert set(RiskProposal.model_fields) == {
        "threats",
        "vulnerabilities",
        "controls",
        "boundaries",
        "escalations",
    }
