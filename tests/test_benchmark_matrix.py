import pytest

from sdlc.benchmarks.matrix import SameFamilyJudgeError, expand_matrix
from sdlc.benchmarks.models import CaseSpec
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
