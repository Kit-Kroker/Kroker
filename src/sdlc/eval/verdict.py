"""The cross-provider gate verdict -- pure, over promptfoo's results.json.

promptfoo cannot decide this: an assertion sees one output and
assertScoringFunction sees one test, so neither can compare providers
(E-82 design doc 4.5). Keeping it here makes the subtlest logic in the
increment a pure function, exhaustively testable with zero model calls.

Not-measured is never rendered as passed: an all-errored judge yields
JudgeStatus.UNAVAILABLE, mirroring WasteBag's rule that a None bag must not
be confused with an all-zero one.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, Field

_ABSOLUTE_MARKER = "absolute.py"
_JUDGE_MARKER = "assertion.py"

# Sentinel prefix on an advisory judge's `reason` meaning "not measured".
#
# promptfoo's GradingResult requires `score` to be a NUMBER -- it rejects null
# outright, and omitting it lets promptfoo default a passing assertion to 1.0,
# which would silently read as a perfect judgment. So an errored judge reports
# a numeric placeholder and flags itself here; _scores drops those rows before
# any mean is taken. Not-measured must never become a score.
JUDGE_UNAVAILABLE = "JUDGE_UNAVAILABLE"
# Native promptfoo assertion types that gate (design doc 4.5). They carry no
# `value` path, so they are recognised by `type` instead of by marker.
_ABSOLUTE_TYPES = {"cost", "latency"}


class GateVerdict(StrEnum):
    PASS = "pass"
    FAIL_ABSOLUTE = "fail_absolute"
    FAIL_REGRESSION = "fail_regression"
    ERRORED = "errored"


class JudgeStatus(StrEnum):
    MEASURED = "measured"
    UNAVAILABLE = "unavailable"
    NO_BASELINE = "no_baseline"


class PromptGateResult(BaseModel):
    verdict: GateVerdict
    judge_status: JudgeStatus
    reason: str
    role: str = ""
    case: str = ""
    prompt_sha_baseline: str = ""
    prompt_sha_working: str = ""
    mean_baseline: float | None = None
    mean_working: float | None = None
    delta: float | None = None
    floor: float | None = None
    n_baseline: int = 0
    n_working: int = 0
    # The individual judge scores behind the means. Bounded by `repeat`
    # (default 3), so this is a handful of floats. Persisted because the
    # scratch results.json is deleted (gate.py:107) and without them no
    # sensitivity claim about this gate is reproducible after the fact.
    scores_baseline: list[float] = Field(default_factory=list)
    scores_working: list[float] = Field(default_factory=list)
    absolute_failures: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _rows(results: dict) -> list[dict]:
    return (results.get("results") or {}).get("results") or []


def _components(row: dict) -> list[dict]:
    return (row.get("gradingResult") or {}).get("componentResults") or []


def _label(row: dict) -> str:
    return (row.get("provider") or {}).get("label", "")


def _scores(rows: list[dict]) -> list[float | None]:
    """Judge scores, with unavailable ones normalised to None.

    A row flagged JUDGE_UNAVAILABLE carries a placeholder number that must not
    reach the mean -- see the constant's docstring for why it cannot simply
    be null."""
    out: list[float | None] = []
    for row in rows:
        for c in _components(row):
            if _JUDGE_MARKER not in str((c.get("assertion") or {}).get("value")):
                continue
            if JUDGE_UNAVAILABLE in str(c.get("reason") or ""):
                out.append(None)
            else:
                out.append(c.get("score"))
    return out


def _absolute_failures(rows: list[dict]) -> list[str]:
    """Failures of any ABSOLUTE check: the output-type assertion (matched by
    file marker) and the native cost/latency gates (matched by type)."""
    out: list[str] = []
    for row in rows:
        for c in _components(row):
            a = c.get("assertion") or {}
            is_absolute = (
                _ABSOLUTE_MARKER in str(a.get("value")) or a.get("type") in _ABSOLUTE_TYPES
            )
            if is_absolute and not c.get("pass", True):
                out.append(c.get("reason") or f"{a.get('type', 'absolute')} assertion failed")
    return out


def _stderr(vals: list[float]) -> float:
    """Standard error of the mean. Zero for n < 2 -- with one sample there is
    no variance estimate, so the fixed floor decides (design doc 4.5)."""
    if len(vals) < 2:
        return 0.0
    return statistics.stdev(vals) / (len(vals) ** 0.5)


def decide(results: dict, *, delta_min: float = 0.05) -> PromptGateResult:
    rows = _rows(results)
    base_rows = [r for r in rows if _label(r) == "baseline"]
    work_rows = [r for r in rows if _label(r) == "working"]

    failures = _absolute_failures(work_rows)
    # promptfoo copies a failed assertion's reason into the row's `error`
    # field, so row.error alone does NOT mean the provider failed -- a veto
    # or output-type failure on a real artifact also lands there. Only an
    # error NOT explained by an absolute failure is a genuine "gate could
    # not run" (spec 6). The distinction is the difference between the gate
    # having teeth (a veto fires -> FAIL_ABSOLUTE) and not (every assertion
    # failure reads as infra noise -> ERRORED). Surfaced by the E-83
    # mutation suite's scope_dropped case.
    provider_error = next(
        (r["error"] for r in rows if r.get("error") and r["error"] not in failures), None
    )
    if provider_error is not None:
        return PromptGateResult(
            verdict=GateVerdict.ERRORED,
            judge_status=JudgeStatus.UNAVAILABLE,
            reason=f"gate could not run — provider error: {provider_error} "
            f"(this is NOT a prompt regression)",
        )

    if failures:
        return PromptGateResult(
            verdict=GateVerdict.FAIL_ABSOLUTE,
            judge_status=JudgeStatus.UNAVAILABLE,
            absolute_failures=failures,
            reason=f"absolute check failed: {failures[0]}",
        )

    base = [s for s in _scores(base_rows) if s is not None]
    work = [s for s in _scores(work_rows) if s is not None]

    class _KeptScores(TypedDict):
        scores_baseline: list[float]
        scores_working: list[float]

    kept: _KeptScores = {"scores_baseline": base, "scores_working": work}

    if not base_rows:
        return PromptGateResult(
            verdict=GateVerdict.PASS,
            judge_status=JudgeStatus.NO_BASELINE,
            mean_working=statistics.fmean(work) if work else None,
            n_working=len(work),
            **kept,
            reason="no committed baseline — working-tree score only",
        )

    if not base or not work:
        # The measured side's mean IS reported. The regression is NOT
        # evaluated -- delta/floor stay None -- but a score that was
        # produced must reach the record. Dropping it is how OQ-P5's
        # "scored 1.00" observation became unrecoverable: the number lived
        # only in the results.json that run_gate deletes in its finally.
        return PromptGateResult(
            verdict=GateVerdict.PASS,
            judge_status=JudgeStatus.UNAVAILABLE,
            mean_baseline=statistics.fmean(base) if base else None,
            mean_working=statistics.fmean(work) if work else None,
            n_baseline=len(base),
            n_working=len(work),
            **kept,
            reason="judge unavailable on at least one side — regression NOT "
            "evaluated (not measured, not passed)",
        )

    mb, mw = statistics.fmean(base), statistics.fmean(work)
    delta = mw - mb
    pooled = (_stderr(base) ** 2 + _stderr(work) ** 2) ** 0.5
    floor = max(delta_min, 2 * pooled)

    regressed = mw < mb - floor
    return PromptGateResult(
        verdict=GateVerdict.FAIL_REGRESSION if regressed else GateVerdict.PASS,
        judge_status=JudgeStatus.MEASURED,
        mean_baseline=mb,
        mean_working=mw,
        delta=delta,
        floor=floor,
        n_baseline=len(base),
        n_working=len(work),
        **kept,
        reason=(
            f"{'regression' if regressed else 'within noise'}: "
            f"baseline {mb:.2f} -> working {mw:.2f} "
            f"(delta {delta:+.2f}, floor {floor:.2f})"
        ),
    )


def write_result(result: PromptGateResult, out_dir: Path) -> Path:
    """Prompt-gate results live in runs/prompt_evals/ and are joined to
    BenchmarkRecord ONLY by prompt_sha. They must never be written into the
    benchmark record stream -- build_heatmap divides by distinct run_id, so
    runless records would deflate real cases' rework density (design doc 2)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = result.created_at.strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{ts}-{result.role or 'role'}-{result.case or 'case'}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
