"""Compare a working-tree prompt against a committed one: run each variant on
the fixture, judge both against the case rubric, return a pure EvalReport."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..agents.loader import model_family
from ..benchmarks.judge import JudgeInput, judge_artifact
from .fixtures import DEPS_ROLES, SUPPORTED_ROLES, load_fixture
from .runner import run_variant


class EvalError(Exception):
    """A user-facing eval failure (bad role, missing fixture/rubric, same-family
    judge). The CLI turns it into a message + non-zero exit."""


# role -> the key used in case.yaml's `rubrics:` map. Only `clarifier` has a
# shipped rubric today; the rest become eval-able when a rubric-<key>.md is
# authored and listed in a case.yaml.
RUBRIC_KEY: dict[str, str] = {
    "clarify": "clarifier",
    "planner": "planner",
    "qa": "qa",
    "reviewer": "reviewer",
    "analyst": "analyst",
    "merge_verdict": "merge_verdict",
}


class RunScore(BaseModel):
    score_a: float | None
    score_b: float | None
    delta: float | None
    components_a: dict[str, float] = Field(default_factory=dict)
    components_b: dict[str, float] = Field(default_factory=dict)


class EvalReport(BaseModel):
    role: str
    case: str
    judge_model: str
    against_ref: str
    unchanged: bool = False
    no_baseline: bool = False
    runs: list[RunScore] = Field(default_factory=list)
    mean_a: float | None = None
    mean_b: float | None = None
    mean_delta: float | None = None


def read_ref_text(ref: str, rel_path: str, repo_root: Path) -> str | None:
    """`git show <ref>:<rel_path>`; None if the path does not exist at ref."""
    proc = subprocess.run(["git", "show", f"{ref}:{rel_path}"],
                          cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout


def load_rubric(case: str, role: str, cases_root: Path) -> str:
    case_yaml = cases_root / case / "case.yaml"
    if not case_yaml.is_file():
        raise EvalError(f"no case.yaml at {case_yaml}")
    rubrics = (yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}
               ).get("rubrics") or {}
    key = RUBRIC_KEY[role]
    rel = rubrics.get(key)
    if not rel:
        raise EvalError(
            f"no rubric for role '{role}' (key '{key}') in {case_yaml}. "
            f"Author benchmarks/cases/{case}/rubric-{key}.md and add it under "
            f"`rubrics:` before evaluating this role.")
    return (cases_root / case / rel).read_text(encoding="utf-8")


def _mean(vals: list[float | None]) -> float | None:
    nums = [v for v in vals if v is not None]
    return sum(nums) / len(nums) if nums else None


def compare(role: str, case: str, *, against_ref: str, k: int,
            agents_dir: Path, cases_root: Path, repo_root: Path,
            judge_model: str) -> EvalReport:
    if role in DEPS_ROLES:
        raise EvalError(
            f"role '{role}' carries deps; deps-aware eval is future work")
    if role not in SUPPORTED_ROLES:
        raise EvalError(f"unknown role '{role}'; supported: "
                        f"{', '.join(sorted(SUPPORTED_ROLES))}")

    fixture_path = agents_dir / role / "fixtures" / f"{case}.json"
    if not fixture_path.is_file():
        raise EvalError(
            f"no fixture at {fixture_path}. Create one with "
            f"`sdlc eval capture --from <run_id> --case {case}`.")
    fixture = load_fixture(fixture_path)

    if model_family(judge_model) == model_family(fixture.model):
        raise EvalError(
            f"judge model '{judge_model}' shares a family with the author "
            f"model '{fixture.model}' (ADR-6); pick a different family.")

    report = EvalReport(role=role, case=case, judge_model=judge_model,
                        against_ref=against_ref)

    rel = f"agents/{role}/instructions.md"
    b_text = (agents_dir / role / "instructions.md").read_text(encoding="utf-8")
    a_text = read_ref_text(against_ref, rel, repo_root)
    if a_text is None:
        report.no_baseline = True
    elif a_text == b_text:
        report.unchanged = True
        return report

    rubric = load_rubric(case, role, cases_root)

    def _score(artifact_json: str) -> tuple[float | None, dict[str, float]]:
        qs = judge_artifact.sync(JudgeInput(
            artifact_json=artifact_json, rubric=rubric,
            author_model=fixture.model, judge_model=judge_model))
        return qs.score, qs.components

    for _ in range(k):
        out_b = run_variant(role, b_text, fixture, agents_dir)
        score_b, comp_b = _score(out_b)
        if report.no_baseline:
            report.runs.append(RunScore(score_a=None, score_b=score_b,
                                        delta=None, components_b=comp_b))
            continue
        out_a = run_variant(role, a_text, fixture, agents_dir)
        score_a, comp_a = _score(out_a)
        delta = (None if score_a is None or score_b is None
                 else score_b - score_a)
        report.runs.append(RunScore(score_a=score_a, score_b=score_b,
                                    delta=delta, components_a=comp_a,
                                    components_b=comp_b))

    report.mean_a = _mean([r.score_a for r in report.runs])
    report.mean_b = _mean([r.score_b for r in report.runs])
    report.mean_delta = _mean([r.delta for r in report.runs])
    return report
