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
from typing import Callable

from temporalio import activity

from .models import QualityScore


@dataclass
class JudgeInput:
    artifact_json: str          # the stage's emitted artifact, serialized
    rubric: str                 # rubric markdown/text for this case+stage
    author_model: str           # to assert cross-family at call time


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
