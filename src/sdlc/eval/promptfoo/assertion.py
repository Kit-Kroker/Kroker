"""promptfoo custom assertion: the cross-family judge, kept in Kroker's code.

ADVISORY by design (E-82 design doc 4.5): `pass` is True whatever the score,
so a noisy rubric number can never fail the gate on its own. The score is
carried out for the cross-provider regression check in eval/verdict.py, which
promptfoo structurally cannot do -- an assertion sees one output, and
assertScoringFunction sees one test, so neither can compare providers.

The ONE hard failure here is an ADR-6 violation: a judge sharing a model
family with the author is a configuration error, not a measurement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from ...agents.loader import model_family
from ...benchmarks.judge import JudgeInput, judge_artifact

# role -> the key used in case.yaml's `rubrics:` map. Migrated verbatim from
# the retired eval/compare.py.
RUBRIC_KEY: dict[str, str] = {
    "clarify": "clarifier",
    "planner": "planner",
    "qa": "qa",
    "reviewer": "reviewer",
    "analyst": "analyst",
    "merge_verdict": "merge_verdict",
}


class RubricError(Exception):
    """No rubric registered or on disk for this (case, role)."""


def load_rubric(case: str, role: str, cases_root: Path) -> str:
    case_yaml = cases_root / case / "case.yaml"
    if not case_yaml.is_file():
        raise RubricError(f"no case.yaml at {case_yaml}")
    rubrics = (yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}
               ).get("rubrics") or {}
    key = RUBRIC_KEY.get(role, role)
    rel = rubrics.get(key)
    if not rel:
        raise RubricError(
            f"no rubric for role '{role}' (key '{key}') in {case_yaml}. "
            f"Author {cases_root / case}/rubric-{key}.md and list it under "
            f"`rubrics:` before evaluating this role.")
    path = cases_root / case / rel
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RubricError(
            f"rubric file {path} named in {case_yaml} does not exist")


def grade(output: str, context: dict) -> dict:
    v = context.get("vars", {})
    author, judge = v.get("author_model", ""), v.get("judge_model", "")

    if model_family(judge) == model_family(author):
        return {"pass": False, "score": None,
                "reason": f"ADR-6 violation: judge '{judge}' shares family "
                          f"'{model_family(judge)}' with author '{author}'. "
                          f"Pick a different family."}
    try:
        rubric = load_rubric(v["case"], v["role"], Path(v["cases_root"]))
    except RubricError as e:
        return {"pass": False, "score": None, "reason": str(e)}

    qs = judge_artifact.sync(JudgeInput(
        artifact_json=output, rubric=rubric, author_model=author,
        judge_model=judge))
    if qs.score is None:
        return {"pass": True, "score": None,
                "reason": "judge unavailable (errored) — advisory, excluded "
                          "from the mean"}
    return {"pass": True, "score": qs.score,
            "reason": f"advisory rubric score {qs.score:.2f}"}


def main() -> None:
    """promptfoo invokes this file with argv[1]=output, argv[2]=context JSON
    and reads a GradingResult JSON object from stdout."""
    import json
    print(json.dumps(grade(sys.argv[1], json.loads(sys.argv[2]))))


if __name__ == "__main__":
    main()
