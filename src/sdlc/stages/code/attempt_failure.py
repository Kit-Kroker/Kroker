"""026 T016/T020 (FR-010, FR-021, FR-040): the per-task lint's contribution
to the task verdict and retry prompt, and the classified attempt cause —
as pure functions.

No ctx, no I/O — table-testable like freeze.py. The step imports these
inside its imports_passed_through block; the module imports nothing from a
workflow context, so the Temporal sandbox loads it isolated and cheap.
"""

from __future__ import annotations

import fnmatch
from typing import Any

# Module-level on purpose: this module loads through step.py's
# imports_passed_through block (outside the sandbox, at worker start), so
# these resolve at load time. Lazy imports inside attempt_failure() would
# execute MID-WORKFLOW during replay — the sandbox's isolated re-import
# of qa.step changes the command path a recorded history sees (026 T020,
# found by tests/review/test_review_step_shadowing_chaos.py).
from ...benchmarks.models import AttemptFailure
from ..qa.step import _fix_loop_issues
from .freeze import _drift_note

# The fixed order of the failure vocabulary (data-model row 17): the
# sequence a reader scans, not the order checks were hit.
_CHECK_ORDER = ("tests", "qa", "drift", "review", "lint", "no_feedback")
_SUMMARY_MAX = 500


def _lint_ok(qa_raw: Any, report_only: list[str]) -> bool:
    """Whether the task's own scoped lint admits this attempt.

    FR-010's ruling, kept byte-for-byte with the merge gate's semantics:
    an UNMEASURED lint (None, or NOT_COLLECTED with its reason) never
    fails a task — merge stays the fail-closed gate of record — and a
    MEASURED report fails only on findings OUTSIDE the report-only globs
    (the repair fences: a finding inside a fenced test file is reported,
    never a loop trigger). Path matching is fnmatch, so a glob must match
    the whole path ('tests/**' never matches 'tests-x/a.py')."""
    lint = getattr(qa_raw, "lint", None)
    if lint is None:
        return True
    introduced = getattr(lint, "introduced", None) or []
    for finding in introduced:
        path = getattr(finding, "path", "")
        # empty globs are dropped: fnmatch("", "") is True, so a stray ""
        # entry would fence a finding with no path (and fence nothing else)
        if not any(g and fnmatch.fnmatch(path, g) for g in report_only):
            return False
    return True


def _lint_input(
    workflow_id: str, task_id: str, branch_point: str, report_only: list[str]
) -> dict[str, Any]:
    """The three lint kwargs code/step.py adds to its QAInput (026 T016):
    the task's branch point as the pinned base, a per-task sibling base
    key under the worktrees root, and the repair fences as report-only
    globs. A dict, so the call site stays one line inside step.py's
    1000-line budget; empty branch_point reads as "no lint" activity-side
    (falsy), exactly like a legacy call."""
    return {
        "lint_base": branch_point,
        "lint_key": f"{workflow_id}/base-{task_id}",
        "lint_report_only": list(report_only),
    }


def attempt_failure(
    qa_raw: Any,
    qa: Any,
    drift: Any,
    review_ok: bool,
    review: Any = None,
    report_only: list[str] | tuple[str, ...] = (),
) -> Any:
    """026 T020 (FR-021): why this attempt failed, classified — or None on a
    pass. Pure: called unconditionally before the code record, so every
    failed attempt says which checks failed and what the dev was shown.

    The pass rule mirrors the step's `task_passed` plus review_ok exactly;
    `checks` follows the fixed vocabulary order; `summary` is the
    fix-loop text joined to the drift note with the step's "\\n- "
    separator, cut to 500 chars — the reason rides `failure`, never
    `error`."""
    hit = {
        "tests": not qa_raw.tests_passed,
        "qa": bool(qa.issues or qa.failing_tests),
        "drift": bool(drift.found),
        "review": not review_ok,
        "lint": not _lint_ok(qa_raw, list(report_only)),
    }
    summary = "\n- ".join(
        x
        for x in (
            _fix_loop_issues(qa, qa_raw, review),
            _drift_note(drift) if drift.found else "",
        )
        if x
    )[:_SUMMARY_MAX]
    if not any(hit.values()):
        return None
    checks = [c for c in _CHECK_ORDER[:-1] if hit[c]]
    if not summary:
        checks.append("no_feedback")  # last: a failure with nothing shown
    return AttemptFailure(checks=checks, summary=summary)


def _qa_failure(failure: Any) -> Any:
    """The QA record's restricted copy (026 T020): the `tests` and `qa`
    checks only — drift/review/lint are the task's story, not the qa
    stage's own verdict. None passes through unchanged."""
    if failure is None:
        return None
    checks = [c for c in failure.checks if c in ("tests", "qa")]
    if not checks:
        return None
    return AttemptFailure(checks=checks, summary=failure.summary)
