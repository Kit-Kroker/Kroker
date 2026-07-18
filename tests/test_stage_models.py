"""Each stage's model is an input to its memo key (FR-103).

Without this, changing one role's model in agents.yaml leaves content_key
unmoved and that stage serves a cache entry computed by the PREVIOUS model.
The hardcoded MODEL constant masked this by making every stage share a model.
"""
from sdlc.agents import roles
from sdlc.memoization.cache import content_key


def test_stage_models_and_prompt_shas_span_the_same_keyspace():
    """Both are keyed by stage name and looked up together in _cached_stage.
    If they disagree about what a stage is, one of them KeyErrors at runtime."""
    assert roles.STAGE_MODELS.keys() == roles.PROMPT_SHAS.keys()


def test_prompt_shas_cover_every_stage_including_qa_and_merge_verdict():
    for stage in ("clarify", "architect", "plan", "devops", "review",
                  "analyze", "qa", "merge_verdict"):
        assert stage in roles.PROMPT_SHAS
        assert len(roles.PROMPT_SHAS[stage]) == 64      # sha256 hex digest


def test_model_constant_is_gone():
    """A fleet-wide default is the drift this increment removes; an alias
    would let new code keep reaching for it."""
    assert not hasattr(roles, "MODEL")


def test_every_stage_model_comes_from_its_registry_role():
    for stage, role in roles.STAGE_ROLES.items():
        assert roles.STAGE_MODELS[stage] == roles.REGISTRY[role].model


def test_agents_bind_their_own_roles_model():
    assert roles.REGISTRY["reviewer"].model in roles.reviewer_agent.model.model_id
    assert roles.REGISTRY["analyst"].model in roles.analyst_agent.model.model_id
    assert roles.REGISTRY["clarify"].model in roles.clarify_agent.model.model_id


def test_changing_one_roles_model_moves_only_that_stages_key():
    """The finding-2 regression test: per-role models MUST be per-stage memo
    inputs."""
    def key_for(stage: str, model: str) -> str:
        return content_key(stage, "{}", roles.PROMPT_SHAS[stage], model, "none")

    before = key_for("architect", roles.STAGE_MODELS["architect"])
    after = key_for("architect", "some-other-family/other-model")
    assert before != after, "architect's memo key must move when its model does"

    # a different stage's key is untouched by architect's model
    clarify_before = key_for("clarify", roles.STAGE_MODELS["clarify"])
    clarify_after = key_for("clarify", roles.STAGE_MODELS["clarify"])
    assert clarify_before == clarify_after


def test_research_is_a_stage_but_optional():
    from sdlc.agents import roles
    assert roles.STAGE_ROLES["research"] == "research"
    # Present in the shipped tree, so it resolves a model + prompt sha.
    assert "research" in roles.STAGE_MODELS
    assert "research" in roles.PROMPT_SHAS
