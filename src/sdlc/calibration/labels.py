"""C7: realized-outcome labels (ruling OQ9).

Pure. Both labels are "1 - badness" on [0, 1], the same scale the proposer's
self-reported confidence uses -- the agreement statistic compares them
directly, so they must not live on different scales.

None means UNLABELLABLE, and an unlabellable gate decision produces no sample
at all. It never degrades to a default like 1.0, which would silently vote
"that went fine" for a run that measured nothing.
"""

from __future__ import annotations

from ..stages.plan.models import PlanDrift


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
