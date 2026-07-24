import pytest

from sdlc.benchmarks.matrix import SameFamilyJudgeError, expand_matrix
from sdlc.benchmarks.models import Arm, CaseSpec
from sdlc.models import HarnessKind


def _spec(models, judge="openai/gpt-5.2"):
    return CaseSpec(
        case_id="c1", idea_summary="x",
        harnesses=[HarnessKind.CLAUDE_CODE, HarnessKind.OPENCODE], models=models,
        judge_model=judge, rubrics={})


def test_full_cross_product():
    cells = expand_matrix(_spec(["anthropic:claude-sonnet-4-6",
                                  "anthropic:claude-opus-4-8"]))
    assert len(cells) == 2 * 2     # 2 harnesses × 2 models


def test_rejects_same_family_judge():
    # author family anthropic, judge family anthropic → reject (ADR-6)
    spec = _spec(["anthropic:claude-sonnet-4-6"],
                 judge="anthropic:claude-haiku-3-5")
    with pytest.raises(SameFamilyJudgeError):
        expand_matrix(spec)


def test_different_family_judge_ok():
    cells = expand_matrix(_spec(["anthropic:claude-sonnet-4-6"],
                                judge="openai/gpt-5.2"))
    assert len(cells) == 2


def test_cell_ids_unique():
    cells = expand_matrix(_spec(["anthropic:claude-sonnet-4-6",
                                  "openai/gpt-5.2"], judge="google/gemini-2-pro"))
    ids = [c.cell_id for c in cells]
    assert len(ids) == len(set(ids))   # all unique
    assert len(cells) == 4


def _spec_arms(arms, harnesses=None, judge="openai/gpt-5.2"):
    return CaseSpec(
        case_id="c1", idea_summary="x",
        harnesses=harnesses or [HarnessKind.OPENCODE],
        models=[], arms=arms, judge_model=judge, rubrics={})


def test_arms_cross_harnesses():
    spec = _spec_arms(
        [Arm(name="a", role_models={"dev": "zai-coding-plan/glm-5.2"}),
         Arm(name="b", role_models={"dev": "openai/gpt-5.2"})],
        harnesses=[HarnessKind.CLAUDE_CODE, HarnessKind.OPENCODE],
        judge="google/gemini-2-pro")
    cells = expand_matrix(spec)
    assert len(cells) == 2 * 2
    assert {c.arm_name for c in cells} == {"a", "b"}


def test_arm_role_models_reach_cell():
    spec = _spec_arms([Arm(name="a",
                           role_models={"architect": "anthropic:claude-opus-4-8",
                                        "dev": "zai-coding-plan/glm-5.2"})])
    (cell,) = expand_matrix(spec)
    assert cell.role_models["architect"] == "anthropic:claude-opus-4-8"


def test_judge_rejects_family_shared_with_any_arm_model():
    spec = _spec_arms(
        [Arm(name="a", role_models={"architect": "openai/gpt-5.2"})],
        judge="openai/gpt-5.2")     # judge shares family with an arm producer
    with pytest.raises(SameFamilyJudgeError):
        expand_matrix(spec)


def test_backward_compat_models_desugar_to_harness_arms():
    # old-style spec: models set, arms empty → one arm per model, harness-only
    spec = CaseSpec(case_id="c1", idea_summary="x",
                    harnesses=[HarnessKind.OPENCODE],
                    models=["zai-coding-plan/glm-5.2", "openai/gpt-5.2"],
                    judge_model="google/gemini-2-pro", rubrics={})
    cells = expand_matrix(spec)
    assert len(cells) == 2
    for c in cells:
        # only the 3 harness roles are overridden; no proposer keys
        assert set(c.role_models) == {"dev", "test", "devops"}

