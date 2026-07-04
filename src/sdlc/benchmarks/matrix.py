"""Expand a CaseSpec into the (harness × model) cell list, enforcing the
ADR-6 cross-family judge rule: the judge model's family must differ from
EVERY author model's family in the matrix."""
from __future__ import annotations

from .models import BenchmarkCell, CaseSpec


class SameFamilyJudgeError(ValueError):
    pass


def _family(model: str) -> str:
    # "anthropic:claude-sonnet-4-6" → "anthropic"; "openai/gpt-5.2" → "openai"
    sep = ":" if ":" in model else "/"
    return model.split(sep, 1)[0].lower()


def expand_matrix(spec: CaseSpec) -> list[BenchmarkCell]:
    judge_family = _family(spec.judge_model)
    author_families = {_family(m) for m in spec.models}
    if judge_family in author_families:
        raise SameFamilyJudgeError(
            f"judge model family {judge_family!r} matches an author model "
            f"family in {sorted(author_families)}; ADR-6 requires the judge "
            f"to differ from every author family")
    return [
        BenchmarkCell(case_id=spec.case_id, harness=h, model=m)
        for h in spec.harnesses for m in spec.models
    ]
