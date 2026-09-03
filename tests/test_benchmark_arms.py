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
    arm = Arm(
        name="all-cheap",
        default="zai-coding-plan/glm-5.2",
        role_models={"reviewer": "openai/gpt-5.2"},
    )
    resolved = arm.resolve()
    # every harness + proposer role present
    assert resolved["dev"] == "zai-coding-plan/glm-5.2"
    assert resolved["architect"] == "zai-coding-plan/glm-5.2"
    assert resolved["devops_planner"] == "zai-coding-plan/glm-5.2"
    # role_models wins over default
    assert resolved["reviewer"] == "openai/gpt-5.2"


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
