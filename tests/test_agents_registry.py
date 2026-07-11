import pytest

from sdlc.agents.loader import (
    RegistryError, load_registry, model_family, validate_registry,
)
from sdlc.models import RoleConfig


def test_model_family_splits_on_colon_and_slash():
    assert model_family("anthropic:glm-5.2") == "anthropic"
    assert model_family("zai-coding-plan/glm-5.2") == "zai-coding-plan"
    assert model_family("OpenAI/gpt-5.2") == "openai"


def test_shipped_registry_loads_and_validates():
    roles = load_registry()                      # default config/agents.yaml
    assert "developer" in roles and "reviewer" in roles
    validate_registry(roles)                     # must not raise


def test_same_family_dev_and_reviewer_rejected():
    roles = {
        "developer": RoleConfig(kind="harness", model="zai-coding-plan/glm-5.2"),
        "reviewer": RoleConfig(kind="proposer", model="zai-coding-plan/other"),
    }
    with pytest.raises(RegistryError, match="family"):
        validate_registry(roles)


def test_different_family_accepted():
    roles = {
        "developer": RoleConfig(kind="harness", model="zai-coding-plan/glm-5.2"),
        "reviewer": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
    }
    validate_registry(roles)                     # no raise


def test_missing_role_rejected():
    with pytest.raises(RegistryError, match="developer and reviewer"):
        validate_registry({"developer": RoleConfig(model="a:b")})


def test_deep_review_harness_reviewer_must_differ_from_developer():
    from sdlc.models import HarnessKind
    roles = {
        "developer": RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                                model="zai-coding-plan/glm-5.2"),
        "reviewer": RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                               model="anthropic:glm-5.2"),
    }
    with pytest.raises(RegistryError, match="harness"):
        validate_registry(roles)


def test_load_registry_via_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "agents.yaml"
    cfg.write_text(
        "version: 1\nroles:\n"
        "  developer:\n    kind: harness\n    harness: opencode\n"
        "    model: zai-coding-plan/glm-5.2\n"
        "  reviewer:\n    kind: proposer\n    model: anthropic:glm-5.2\n",
        encoding="utf-8")
    monkeypatch.setenv("SDLC_AGENTS_CONFIG", str(cfg))
    roles = load_registry()
    assert roles["reviewer"].model == "anthropic:glm-5.2"
    assert roles["reviewer"].harness is None
