"""Cross-family LLM-judge for proposer-stage artifacts.

The real LLM call is behind JudgeFn so tests inject a fake and CI makes no
model calls. On any failure (exception, bad JSON, out-of-range) we return
QualityScore(score=None, judge="error") — the judge never raises, so a
broken judge can never fail a benchmark cell; the record is simply excluded
from the composite.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pydantic_ai import Agent
from temporalio import activity

from .models import QualityScore


@dataclass
class JudgeInput:
    artifact_json: str          # the stage's emitted artifact, serialized
    rubric: str                 # rubric markdown/text for this case+stage
    author_model: str           # to assert cross-family at call time
    judge_model: str | None = None     # model the judge should USE (A1)


def _build_judge_input(artifact_json: str, rubrics: dict[str, str],
                       stage: str, author_model: str,
                       judge_model: str | None) -> JudgeInput | None:
    """Build a JudgeInput iff a rubric is registered for ``stage``.

    ``stage`` is the rubric-map key — i.e. the keys carried on
    ``BenchmarkConfig.rubrics`` (populated from ``CaseSpec.rubrics`` by
    ``load_case_assets``): e.g. ``clarifier`` / ``architect``. It is NOT
    necessarily the record's ``stage`` field, which uses a different
    vocabulary (``clarify`` / ``architecture``).

    Returns ``None`` when no rubric exists for the stage (or it is empty),
    so the workflow skips judging and emits the record with a graceful
    ``quality_score=None`` instead. Pure function — no I/O — so it can be
    unit-tested without a Temporal environment.
    """
    rubric = rubrics.get(stage, "")
    if not rubric:
        return None
    return JudgeInput(
        artifact_json=artifact_json,
        rubric=rubric,
        author_model=author_model,
        judge_model=judge_model,
    )


JudgeFn = Callable[[JudgeInput], str]
_judge_fn: JudgeFn | None = None


def _set_judge_fn(fn: JudgeFn | None) -> None:
    global _judge_fn
    _judge_fn = fn


_JUDGE_SYSTEM_PROMPT = (
    "You are an impartial quality judge. Score the supplied artifact against "
    "the supplied rubric. Respond with ONLY a JSON object of exactly this "
    "shape and nothing else (no prose, no markdown fences):\n"
    '  {"score": <float between 0.0 and 1.0>, '
    '"components": {<name>: <float between 0.0 and 1.0>}}\n'
    "The overall \"score\" must reflect the artifact's rubric compliance; "
    "each component score must be grounded in a named rubric criterion."
)


def _run_judge_agent(model, system_prompt: str, user_prompt: str) -> str:
    """Construct a Pydantic AI agent lazily and run it synchronously.

    The agent is built per call (never at module import) to avoid the
    eager-construction smell that bit ``agents/roles.py``. Kept as a small,
    explicitly-patchable seam: ``TestModel`` cannot flow through
    ``JudgeInput.judge_model`` (typed ``str | None``), so tests patch this
    helper rather than the ``Agent`` class.
    """
    agent = Agent(model, name="benchmark_judge", system_prompt=system_prompt)
    result = agent.run_sync(user_prompt)
    return result.output


def _default_judge(inp: JudgeInput) -> str:
    # Production default: a Pydantic AI Agent call on the configured
    # cross-family judge model. Returns the raw JSON string; parsing,
    # clamping and error-handling live in ``_judge_sync``.
    if inp.judge_model is None:
        raise RuntimeError(
            "no judge_model configured; cannot run production judge "
            "(set BenchmarkConfig.judge_model or inject a fn via "
            "_set_judge_fn)")
    user_prompt = (
        f"Rubric:\n{inp.rubric}\n\nArtifact:\n{inp.artifact_json}"
    )
    return _run_judge_agent(
        inp.judge_model, _JUDGE_SYSTEM_PROMPT, user_prompt)


def _judge_sync(inp: JudgeInput) -> QualityScore:
    fn = _judge_fn or _default_judge
    try:
        raw = fn(inp)
        payload = json.loads(raw)
        score = float(payload.get("score", 0.0))
        score = max(0.0, min(1.0, score))      # clamp
        components = payload.get("components") or {}
        return QualityScore(score=score, components=components,
                            judge="llm_judge")
    except Exception:
        return QualityScore(score=None, judge="error")


@activity.defn
async def judge_artifact(inp: JudgeInput) -> QualityScore:
    return _judge_sync(inp)


# test convenience
judge_artifact.sync = _judge_sync   # type: ignore[attr-defined]


# Repo root, derived from this module's location (editable install resolves
# __file__ to the worktree source). Used to locate golden-case dirs:
#   <root>/benchmarks/cases/<case_id>/
_CASES_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "cases"


@activity.defn
async def load_case_assets(case_id: str,
                           rubric_files: dict[str, str]) -> dict[str, str]:
    """Read each rubric file and return {stage: rubric_text}.

    ``rubric_files`` is the CaseSpec.rubrics map (stage -> file path). Paths
    may be absolute or relative to the case dir
    (``benchmarks/cases/<case_id>/``). A missing file is skipped — that stage
    simply won't be judged — so the workflow never crashes on a absent rubric.

    All filesystem I/O lives here (the activity); the workflow passes only
    serializable args (``case_id`` + the path map).
    """
    case_dir = _CASES_DIR / case_id
    out: dict[str, str] = {}
    for stage, rel in rubric_files.items():
        p = Path(rel) if Path(rel).is_absolute() else case_dir / rel
        if p.exists():
            out[stage] = p.read_text(encoding="utf-8")
    return out
