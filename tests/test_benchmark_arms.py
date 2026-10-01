import pytest

from sdlc.agents.loader import RegistryError
from sdlc.benchmarks.matrix import expand_matrix
from sdlc.benchmarks.models import Arm, BenchmarkCell, CaseSpec
from sdlc.core.models import (
    HarnessKind,
)


def test_arm_resolve_named_only():
    arm = Arm(
        name="frontier-arch",
        role_models={"architect": "anthropic:claude-opus-4-8", "dev": "zai-coding-plan/glm-5.2"},
    )
    assert arm.resolve() == {
        "architect": "anthropic:claude-opus-4-8",
        "dev": "zai-coding-plan/glm-5.2",
    }


def test_arm_resolve_default_fills_all_overridable_roles():
    # 004 T018: ids moved to the provider:model form — a default fans out to
    # proposer roles too, and only the proposer subset is validated, so the
    # default itself must be a valid proposer id. The harness roles still
    # receive the same string verbatim.
    arm = Arm(
        name="all-cheap",
        default="anthropic:glm-5.2",
        role_models={"reviewer": "openai:gpt-5.2"},
    )
    resolved = arm.resolve()
    # every harness + proposer role present
    assert resolved["dev"] == "anthropic:glm-5.2"
    assert resolved["architect"] == "anthropic:glm-5.2"
    assert resolved["devops_planner"] == "anthropic:glm-5.2"
    # role_models wins over default
    assert resolved["reviewer"] == "openai:gpt-5.2"


def test_expansion_rejects_an_arm_default_that_is_not_a_proposer_model():
    """FR-004 (004 T018): a default fans out to proposer roles, so a harness
    grammar string as default is refused at matrix expansion, before any
    cell exists. RED on main: expand_matrix happily builds the cell."""
    spec = CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=["opencode"],
        models=[],
        judge_model="openai/gpt-5.2",
        arms=[Arm(name="bad-default", default="zai-coding-plan/glm-5.2")],
    )
    with pytest.raises(RegistryError, match=r"provider:model"):
        expand_matrix(spec)


def test_expansion_rejects_an_invalid_proposer_role_model():
    spec = CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=["opencode"],
        models=[],
        # judge family must not collide with the arm's on main, or the
        # existing SameFamilyJudgeError fires first and muddies the RED
        judge_model="anthropic:claude-opus-4-8",
        arms=[Arm(name="bad-reviewer", role_models={"reviewer": "openai/gpt-5.2"})],
    )
    with pytest.raises(RegistryError, match=r"provider:model"):
        expand_matrix(spec)


def test_expansion_leaves_harness_only_arms_and_the_judge_alone():
    """FR-005: harness roles keep their grammar; the judge is not a proposer
    role and is not validated here (its retry stacking is the T037 inbox
    task). Both pins hold before and after 004."""
    spec = CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=["opencode"],
        models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2",
    )
    cells = expand_matrix(spec)
    assert cells
    assert all("zai-coding-plan/glm-5.2" in c.role_models.values() for c in cells)


def test_expansion_accepts_valid_proposer_arms():
    spec = CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=["opencode"],
        models=[],
        judge_model="anthropic:claude-opus-4-8",
        arms=[
            Arm(
                name="frontier",
                role_models={"architect": "openai:gpt-5.2", "dev": "zai-coding-plan/glm-5.2"},
            )
        ],
    )
    cells = expand_matrix(spec)
    assert [c.arm_name for c in cells] == ["frontier"]
    assert cells[0].role_models["architect"] == "openai:gpt-5.2"


def test_cell_id_uses_arm_name():
    cell = BenchmarkCell(
        case_id="c1",
        harness=HarnessKind.OPENCODE,
        arm_name="frontier-arch",
        role_models={"dev": "zai-coding-plan/glm-5.2"},
    )
    assert cell.cell_id == "c1#opencode#frontier-arch"


def test_casespec_arms_default_empty():
    spec = CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=[HarnessKind.OPENCODE],
        models=["m"],
        judge_model="openai/gpt-5.2",
    )
    assert spec.arms == []
