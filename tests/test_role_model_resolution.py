from sdlc.models import PipelineConfig, RoleConfig
from sdlc.workflows.feature import resolve_role_model
from sdlc.memoization.cache import content_key


def test_resolver_falls_back_to_registry_default():
    cfg = PipelineConfig()  # no proposer overrides
    # architect stage default comes from STAGE_MODELS (registry)
    from sdlc.agents.roles import STAGE_MODELS
    assert resolve_role_model(cfg, "architect") == STAGE_MODELS["architect"]


def test_resolver_prefers_per_run_override():
    cfg = PipelineConfig()
    cfg.roles["architect"] = RoleConfig(kind="proposer", model="openai/gpt-5.2")
    assert resolve_role_model(cfg, "architect") == "openai/gpt-5.2"


def test_resolver_maps_stage_to_role_name():
    # stage 'plan' resolves through role 'planner'
    cfg = PipelineConfig()
    cfg.roles["planner"] = RoleConfig(kind="proposer", model="openai/gpt-5.2")
    assert resolve_role_model(cfg, "plan") == "openai/gpt-5.2"


def test_memo_key_moves_with_per_role_model():
    base = PipelineConfig()
    override = PipelineConfig()
    override.roles["architect"] = RoleConfig(kind="proposer", model="openai/gpt-5.2")
    k_base = content_key("architect", "{}", "sha", resolve_role_model(base, "architect"), "none")
    k_over = content_key("architect", "{}", "sha", resolve_role_model(override, "architect"), "none")
    assert k_base != k_over
