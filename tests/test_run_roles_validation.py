import pytest

from sdlc.agents.loader import RegistryError, validate_run_roles


def test_passes_when_families_differ():
    validate_run_roles({"dev": "zai-coding-plan/glm-5.2",
                        "reviewer": "openai/gpt-5.2"})  # no raise


def test_rejects_dev_reviewer_same_family():
    with pytest.raises(RegistryError, match="ADR-6"):
        validate_run_roles({"dev": "anthropic:claude-opus-4-8",
                            "reviewer": "anthropic:claude-haiku-4-5"})


def test_rejects_deep_review_sharing_dev_family():
    with pytest.raises(RegistryError, match="deep_review"):
        validate_run_roles({"dev": "anthropic:claude-opus-4-8",
                            "reviewer": "openai/gpt-5.2",
                            "deep_review": "anthropic:claude-haiku-4-5"})


def test_deep_review_absent_is_fine():
    validate_run_roles({"dev": "zai-coding-plan/glm-5.2",
                        "reviewer": "openai/gpt-5.2"})  # no deep_review key, no raise


def test_missing_dev_or_reviewer_raises():
    with pytest.raises(RegistryError):
        validate_run_roles({"dev": "zai-coding-plan/glm-5.2"})
