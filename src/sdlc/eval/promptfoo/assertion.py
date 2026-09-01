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

from pathlib import Path

import yaml

# Absolute: promptfoo loads this file standalone (see provider.py).
from sdlc.agents.loader import model_family, model_id
from sdlc.benchmarks.judge import JudgeInput, _judge_sync
from sdlc.eval.verdict import JUDGE_UNAVAILABLE

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
    rubrics = (yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}).get("rubrics") or {}
    key = RUBRIC_KEY.get(role, role)
    rel = rubrics.get(key)
    if not rel:
        raise RubricError(
            f"no rubric for role '{role}' (key '{key}') in {case_yaml}. "
            f"Author {cases_root / case}/rubric-{key}.md and list it under "
            f"`rubrics:` before evaluating this role."
        )
    path = cases_root / case / rel
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RubricError(f"rubric file {path} named in {case_yaml} does not exist") from None


def grade(output: str, context: dict) -> dict:
    v = context.get("vars", {})
    author, judge = v.get("author_model", ""), v.get("judge_model", "")

    if model_family(judge) == model_family(author):
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"ADR-6 violation: judge '{judge}' shares family "
            f"'{model_family(judge)}' with author '{author}'. "
            f"Pick a different family.",
        }
    # Family alone is not enough. A provider prefix says who SERVES a model,
    # not what it is -- this repo runs `anthropic:glm-5.2` against
    # ANTHROPIC_BASE_URL=api.z.ai, so `zai-coding-plan/glm-5.2` would clear
    # the family check while being the very same weights grading their own
    # output. loader.py:237 already guards the adversary this way; the judge
    # needs the same guard for the same reason.
    if model_id(judge) == model_id(author):
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"ADR-6 violation: judge '{judge}' and author "
            f"'{author}' are the same model "
            f"'{model_id(judge)}' behind different provider "
            f"prefixes. Two prefixes over the same weights "
            f"decorrelate nothing.",
        }
    try:
        rubric = load_rubric(v["case"], v["role"], Path(v["cases_root"]))
    except RubricError as e:
        return {"pass": False, "score": 0.0, "reason": str(e)}

    qs = _judge_sync(
        JudgeInput(artifact_json=output, rubric=rubric, author_model=author, judge_model=judge)
    )
    if qs.score is None:
        # promptfoo rejects a null score and would default a missing one to
        # 1.0, so report a placeholder number and flag it; verdict._scores
        # drops JUDGE_UNAVAILABLE rows before averaging.
        return {
            "pass": True,
            "score": 0.0,
            "reason": f"{JUDGE_UNAVAILABLE}: judge errored — advisory, excluded from the mean",
        }
    return {"pass": True, "score": qs.score, "reason": f"advisory rubric score {qs.score:.2f}"}


def get_assert(output: str, context) -> dict:
    """promptfoo's Python assertion entry point.

    The name is fixed by promptfoo: it does
    `getattr(script_module, "get_assert")` and calls it with the output and a
    context carrying `vars`. (Older docs describe an argv/stdout protocol;
    the installed CLI uses this function contract.) Returns a GradingResult
    dict: {pass, score, reason}.
    """
    return grade(output, _as_dict(context))


def _as_dict(context) -> dict:
    """promptfoo may hand over a dict or an object exposing `vars`."""
    if isinstance(context, dict):
        return context
    return {"vars": getattr(context, "vars", {}) or {}}
