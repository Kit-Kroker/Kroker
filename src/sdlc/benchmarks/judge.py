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

from temporalio import activity

from .models import QualityScore


@dataclass
class JudgeInput:
    artifact_json: str          # the stage's emitted artifact, serialized
    rubric: str                 # rubric markdown/text for this case+stage
    author_model: str           # to assert cross-family at call time
    judge_model: str | None = None     # model the judge should USE (A1)


JudgeFn = Callable[[JudgeInput], str]
_judge_fn: JudgeFn | None = None


def _set_judge_fn(fn: JudgeFn | None) -> None:
    global _judge_fn
    _judge_fn = fn


def _default_judge(inp: JudgeInput) -> str:
    # Production default: a Pydantic AI Agent call on a cross-family model.
    # Implemented in a later hardening task; for now raise so misconfiguration
    # surfaces as judge="error" rather than a silent wrong answer.
    raise RuntimeError("no judge configured; set one via _set_judge_fn or "
                       "wire the production Pydantic AI agent")


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
