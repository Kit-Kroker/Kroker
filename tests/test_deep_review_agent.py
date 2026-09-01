import pytest

from sdlc.agents import roles
from sdlc.agents.loader import (
    KNOWN_ROLES,
    OPTIONAL_ROLES,
    RegistryError,
    load_registry,
    model_family,
    validate_registry,
)
from sdlc.models import DeepReviewReport, RoleConfig
from tests.test_agents_registry import _complete_registry


def test_deep_review_in_optional_roles():
    assert "deep_review" in OPTIONAL_ROLES
    assert "deep_review" in KNOWN_ROLES


def test_shipped_deep_review_builds_a_report_agent():
    assert roles.deep_review_agent is not None
    assert roles.deep_review_agent.output_type is DeepReviewReport
    assert roles.t_deep_review in roles.ALL_TEMPORAL_AGENTS
    assert "deep_review" in roles.STAGE_MODELS
    assert len(roles.PROMPT_SHAS["deep_review"]) == 64


def test_shipped_deep_review_family_differs_from_dev():
    reg = load_registry()
    assert model_family(reg["deep_review"].model) != model_family(reg["dev"].model)


def test_same_family_deep_review_and_dev_rejected():
    roles_ = _complete_registry(deep_review=RoleConfig(kind="proposer", model="zai-coding-plan/x"))
    with pytest.raises(RegistryError, match="deep_review"):
        validate_registry(roles_)


def test_registry_without_deep_review_still_validates():
    # deep_review is OPTIONAL: _complete_registry omits it and must pass.
    validate_registry(_complete_registry())
