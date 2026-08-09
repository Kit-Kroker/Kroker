"""Expand a CaseSpec into (harness × arm) cells, enforcing the ADR-6
cross-family judge rule: the judge model's family must differ from EVERY
model explicitly named in EVERY arm."""
from __future__ import annotations

from .models import Arm, BenchmarkCell, CaseSpec


class SameFamilyJudgeError(ValueError):
    pass


class NetworkRequiredCaseError(ValueError):
    pass


def _family(model: str) -> str:
    # "anthropic:claude-sonnet-4-6" → "anthropic"; "openai/gpt-5.2" → "openai"
    sep = ":" if ":" in model else "/"
    return model.split(sep, 1)[0].lower()


def _arms_for(spec: CaseSpec) -> list[Arm]:
    if spec.arms:
        return spec.arms
    # backward compat: one arm per model, harness roles only (proposers keep
    # the registry default, exactly as the pre-E-37 uniform sweep did).
    return [
        Arm(name=_family(m) + "-" + m.rsplit("/", 1)[-1].rsplit(":", 1)[-1],
            role_models={"dev": m, "test": m, "devops": m})
        for m in spec.models
    ]


def expand_matrix(spec: CaseSpec) -> list[BenchmarkCell]:
    if spec.network_required:
        raise NetworkRequiredCaseError(
            f"case {spec.case_id!r} declares network_required: its oracle "
            f"needs live egress, which NFR-5 forbids until the E-21 network "
            f"tier exists. The case is quarantined, not broken.")
    arms = _arms_for(spec)
    judge_family = _family(spec.judge_model)
    # every model a producer role is explicitly set to, across all arms
    author_models = {
        m for arm in arms for m in arm.resolve().values()
    }
    author_families = {_family(m) for m in author_models}
    if judge_family in author_families:
        raise SameFamilyJudgeError(
            f"judge model family {judge_family!r} matches a producer model "
            f"family in {sorted(author_families)}; ADR-6 requires the judge "
            f"to differ from every producer family in the matrix")
    return [
        BenchmarkCell(case_id=spec.case_id, harness=h,
                      arm_name=arm.name, role_models=arm.resolve())
        for h in spec.harnesses for arm in arms
    ]
