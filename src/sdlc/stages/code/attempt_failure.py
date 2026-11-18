"""026 T016 (FR-010, FR-040): the per-task lint's contribution to the task
verdict and the retry prompt, as pure functions.

No ctx, no I/O — table-testable like freeze.py. The step imports these
inside its imports_passed_through block; the module imports nothing from a
workflow context, so the Temporal sandbox loads it isolated and cheap.
"""

from __future__ import annotations

import fnmatch
from typing import Any


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
