import pytest

from sdlc.agents.loader import RegistryError, validate_run_roles


def test_passes_when_families_differ():
    validate_run_roles({"dev": "zai-coding-plan/glm-5.2", "reviewer": "openai/gpt-5.2"})  # no raise


def test_rejects_dev_reviewer_same_family():
    with pytest.raises(RegistryError, match="ADR-6"):
        validate_run_roles(
            {"dev": "anthropic:claude-opus-4-8", "reviewer": "openai/claude-opus-4-8"}
        )


def test_rejects_deep_review_sharing_dev_family():
    with pytest.raises(RegistryError, match="deep_review"):
        validate_run_roles(
            {
                "dev": "anthropic:claude-opus-4-8",
                "reviewer": "openai/gpt-5.2",
                "deep_review": "bedrock:claude-opus-4-8",
            }
        )


def test_deep_review_absent_is_fine():
    validate_run_roles(
        {"dev": "zai-coding-plan/glm-5.2", "reviewer": "openai/gpt-5.2"}
    )  # no deep_review key, no raise


def test_missing_dev_or_reviewer_raises():
    with pytest.raises(RegistryError):
        validate_run_roles({"dev": "zai-coding-plan/glm-5.2"})


# ADR-6 amended: the invariant is over the model id, for every judge role.
JUDGES = ("reviewer", "deep_review", "qa", "merge_verdict")


def test_rejects_same_weights_behind_different_prefixes():
    # The shipped-registry hole: same glm-5.3 behind zai: and zai-coding-plan/.
    with pytest.raises(RegistryError, match="ADR-6"):
        validate_run_roles({"dev": "zai-coding-plan/glm-5.3", "reviewer": "zai:glm-5.3"})


def test_accepts_different_model_same_vendor():
    validate_run_roles(
        {"dev": "zai-coding-plan/glm-5.3", "reviewer": "zai:glm-5.3-flash"}
    )  # option 1: decorrelates weights, not vendor


@pytest.mark.parametrize("judge", JUDGES)
def test_every_judge_must_differ_from_dev_by_model_id(judge):
    roles = {"dev": "zai-coding-plan/glm-5.3", "reviewer": "zai:glm-5.3-flash"}
    roles[judge] = "zai:glm-5.3"
    with pytest.raises(RegistryError, match=judge):
        validate_run_roles(roles)


@pytest.mark.parametrize("judge", JUDGES)
def test_every_judge_passes_when_distinct(judge):
    validate_run_roles(
        {
            "dev": "zai-coding-plan/glm-5.3",
            "reviewer": "zai:glm-5.3-flash",
            judge: "zai:glm-5.3-flash",
        }
    )
