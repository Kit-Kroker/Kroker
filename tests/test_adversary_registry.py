"""The adversary's decorrelation is by MODEL IDENTITY, not provider prefix.

model_family() splits on the provider, which is wrong in both directions
against the shipped registry: it accepts zai-coding-plan/glm-5.2 vs
anthropic:glm-5.2 (same weights, no decorrelation) and would reject
anthropic:claude-sonnet-4-6 vs anthropic:glm-5.2 (different weights, real
decorrelation). See spec OQ-A4.
"""
import pytest

from sdlc.agents.loader import RegistryError, check_adversary_model, model_id


def test_model_id_strips_provider_prefix():
    assert model_id("anthropic:glm-5.2") == "glm-5.2"
    assert model_id("zai-coding-plan/glm-5.2") == "glm-5.2"
    assert model_id("anthropic:claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_model_id_without_separator_is_the_whole_string():
    assert model_id("glm-5.2") == "glm-5.2"


def test_same_model_behind_different_providers_is_rejected():
    with pytest.raises(RegistryError, match="adversary"):
        check_adversary_model({
            "dev": "zai-coding-plan/glm-5.2",
            "reviewer": "anthropic:glm-5.2",
            "adversary": "openai/glm-5.2",
        })


def test_sharing_the_reviewers_model_is_rejected():
    with pytest.raises(RegistryError, match="adversary"):
        check_adversary_model({
            "dev": "zai-coding-plan/glm-5.2",
            "reviewer": "anthropic:glm-5.2",
            "adversary": "anthropic:glm-5.2",
        })


def test_different_model_sharing_a_provider_is_accepted():
    check_adversary_model({
        "dev": "zai-coding-plan/glm-5.2",
        "reviewer": "anthropic:glm-5.2",
        "adversary": "anthropic:claude-sonnet-4-6",
    })


def test_absent_adversary_is_a_noop():
    check_adversary_model({
        "dev": "zai-coding-plan/glm-5.2",
        "reviewer": "anthropic:glm-5.2",
    })
