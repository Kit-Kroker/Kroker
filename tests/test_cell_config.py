import pytest

from sdlc.agents.loader import RegistryError
from sdlc.benchmarks.models import BenchmarkCell, CaseSpec
from sdlc.benchmarks.workflow import _cell_config
from sdlc.core.models import (
    HarnessKind,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)


def _spec():
    return CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=[HarnessKind.OPENCODE],
        models=[],
        judge_model="openai/gpt-5.2",
        rubrics={},
    )


def _idea():
    return IdeaBrief(title="c1", description="x", mode=ProjectMode.GREENFIELD)


def test_cell_config_overrides_proposer_and_harness_roles():
    cell = BenchmarkCell(
        case_id="c1",
        harness=HarnessKind.OPENCODE,
        arm_name="a",
        role_models={"architect": "anthropic:claude-opus-4-8", "dev": "zai-coding-plan/glm-5.2"},
    )
    cfg = _cell_config(PipelineConfig(), _idea(), _spec(), cell, bench_run_id="b1", rubrics={})
    assert cfg.roles["architect"].model == "anthropic:claude-opus-4-8"
    assert cfg.roles["architect"].kind == "proposer"
    assert cfg.roles["dev"].model == "zai-coding-plan/glm-5.2"
    assert cfg.roles["dev"].harness == HarnessKind.OPENCODE


def test_cell_config_rejects_adr6_violating_arm():
    # dev opus + reviewer opus (same family) → ADR-6 breach at the boundary
    cell = BenchmarkCell(
        case_id="c1",
        harness=HarnessKind.OPENCODE,
        arm_name="bad",
        role_models={"dev": "anthropic:claude-opus-4-8", "reviewer": "anthropic:claude-haiku-4-5"},
    )
    with pytest.raises(RegistryError, match="ADR-6"):
        _cell_config(PipelineConfig(), _idea(), _spec(), cell, bench_run_id="b1", rubrics={})
