"""C7: realized-outcome labels (ruling OQ9).

Pure. Both labels are "1 - badness" on [0, 1], the same scale the proposer's
self-reported confidence uses -- the agreement statistic compares them
directly, so they must not live on different scales.

None means UNLABELLABLE, and an unlabellable gate decision produces no sample
at all. It never degrades to a default like 1.0, which would silently vote
"that went fine" for a run that measured nothing.
"""

from __future__ import annotations

from ..core.models import RunSummary
from ..stages.plan.models import PlanDrift
from .models import CalibrationSample, LabelSource
from .verdict import bucket_key


def unhinted_ratio(drift: PlanDrift) -> float:
    """Ruling OQ9(1): the continuous quantity, not merge's binary per-task
    threshold flag (merge/step.py:87-95). Continuous so the label can
    discriminate instead of collapsing into two clusters."""
    if drift.files_touched <= 0:
        return 0.0
    return min(len(drift.touched_unhinted) / drift.files_touched, 1.0)


def plan_drift_label(ratios: list[float]) -> float | None:
    """Mean-aggregated across the run's measured tasks, inverted, clamped."""
    if not ratios:
        return None
    mean = sum(ratios) / len(ratios)
    return max(0.0, min(1.0, 1.0 - mean))


def fix_attempt_label(attempts: list[int], max_fix_attempts: int) -> float | None:
    """Ruling OQ9(2): capped at cfg.max_fix_attempts, mean-aggregated per run.
    Project-relative baselining is deliberately deferred rather than adding a
    second undefined normalization now."""
    if not attempts or max_fix_attempts <= 0:
        return None
    mean = sum(min(a, max_fix_attempts) / max_fix_attempts for a in attempts) / len(attempts)
    return max(0.0, min(1.0, 1.0 - mean))


# --- run-level labelling ---------------------------------------------------

# Ruling OQ2: `merge` is deliberately absent. It has no attributable
# post-merge outcome signal (spec 3), so a merge auto-approve produces no
# sample, its bucket never reaches the floor, and its SOFT auto-approve
# therefore never fires. That is a consequence of the data, not a branch on
# the gate name -- do not add one.
_DRIFT_GATES = frozenset({"plan"})
_FIX_ATTEMPT_GATES = frozenset({"architecture"})

# Ruling OQ9's population is the run's TASKS, not every stage row. Task
# attempts are recorded under stage="code" (code/step.py:752-772), which is
# also the only stage that carries plan_drift. Every OTHER stage emits a row
# with fix_attempts=0 (intake, clarify, architecture, plan, review, qa,
# merge, deploy), so aggregating across all of them drags a disastrous run
# up toward "mostly fine": five tasks each exhausting max_fix_attempts=2,
# plus six zero rows, would label 0.625 instead of 0.0. That dilution is the
# vacuity direction OQ9's pinning exists to prevent, so the population is
# filtered rather than assumed. Each ATTEMPT emits its own row, so the mean
# is over attempts -- which is the intended reading: the label measures what
# the fix loop cost, not how many distinct tasks entered it.
_TASK_STAGE = "code"

# Spec 3 names the cross-family LLM rubric score "the strongest available
# quality signal", and ruling OQ1 prefers it when benchmarking. It is not
# the only thing QualityScore carries: the code stage records a CONTRACT
# score of 1.0/0.0 (code/step.py:760-761) and merge does likewise. Those are
# pass/fail bookkeeping, not a rubric judgment, and must never displace a
# proxy label while wearing the judge's name.
_LLM_JUDGE = "llm_judge"


def _judge_label(summary: RunSummary, gate: str) -> float | None:
    """Spec 4.2.1: the judge score FOR THIS STAGE -- not a run-wide blend, in
    which the architect's score would help authorize the plan gate and vice
    versa. The two proposer stages record under their own gate's name
    (architecture/step.py:200, plan/step.py:121), so the gate name IS the
    stage key and no mapping table is needed."""
    scores = [
        s.quality_score
        for s in summary.stages
        if s.stage == gate and s.quality_score is not None and s.quality_judge == _LLM_JUDGE
    ]
    if not scores:
        return None
    return max(0.0, min(1.0, sum(scores) / len(scores)))


def calibration_samples_for(
    summary: RunSummary, *, max_fix_attempts: int, benchmarking: bool
) -> list[CalibrationSample]:
    """Pure. Every SOFT gate this run auto-approved on a self-reported
    confidence, scored against what the rest of the run then did.

    The gate filter is narrower than "decided_by == 'policy'": GatePolicy.OFF
    synthesizes that too (gates.py:195-198), and the budget gate emits its own
    GATE_DECIDED. Only a SOFT gate that had a confidence to honour is
    evidence about whether honouring confidence works.
    """
    source = LabelSource.BENCHMARK if benchmarking else LabelSource.PRODUCTION_PROXY
    tasks = [s for s in summary.stages if s.stage == _TASK_STAGE]
    drift = plan_drift_label([s.plan_drift for s in tasks if s.plan_drift is not None])
    fixes = fix_attempt_label([s.fix_attempts for s in tasks], max_fix_attempts)

    out: list[CalibrationSample] = []
    for g in summary.gates:
        if g.policy != "soft" or g.decided_by != "policy" or g.confidence is None:
            continue
        # Per-gate, not hoisted: the judge label is attributed to the stage
        # that earned it.
        judged = _judge_label(summary, g.gate) if benchmarking else None
        if g.gate in _DRIFT_GATES:
            label = judged if judged is not None else drift
        elif g.gate in _FIX_ATTEMPT_GATES:
            label = judged if judged is not None else fixes
        else:
            label = None
        if label is None:
            continue
        out.append(
            CalibrationSample(
                gate=g.gate,
                bucket_key=bucket_key(g.author_model, source),
                confidence=g.confidence,
                outcome_label=label,
                run_id=summary.run_id,
            )
        )
    return out
