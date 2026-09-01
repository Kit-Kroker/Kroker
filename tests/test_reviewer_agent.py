from sdlc.agents import roles
from sdlc.agents.loader import load_registry, model_family
from sdlc.models import ReviewReport


def test_reviewer_agent_emits_review_report():
    assert roles.reviewer_agent.output_type is ReviewReport


def test_reviewer_registered_for_temporal():
    assert roles.t_reviewer in roles.ALL_TEMPORAL_AGENTS


def test_review_prompt_sha_present():
    assert "review" in roles.PROMPT_SHAS
    assert len(roles.PROMPT_SHAS["review"]) == 64  # sha256 hexdigest


def test_reviewer_model_family_differs_from_dev():
    """The bound reviewer model must be a different family than the model that
    actually writes code — the ADR-6 invariant. 'dev' (not 'developer') is what
    feature.py:434 resolves for coding tasks."""
    reg = load_registry()
    assert model_family(reg["reviewer"].model) != model_family(reg["dev"].model)
    # the agent actually binds that reviewer model
    assert reg["reviewer"].model in roles.reviewer_agent.model.model_id
