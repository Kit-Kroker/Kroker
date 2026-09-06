"""C2 freeze/thaw decision rules for the fix loop.

Pure: which attempts are repair attempts, where the drift anchor A sits, and
how a drift finding renders for the human at the gate. No `ctx`, no activity
calls, no I/O -- so the whole ratchet is testable as a table, and the module
falls in Rule 3's sandbox-safe category (docs/framework.md §3).

Split out of `step.py` for the 1000-line ceiling; `step.py` re-imports these,
so `from sdlc.stages.code.step import _next_anchor` keeps working. The audit
recorders stay in `step.py` beside `_record_escalation`, which `_record_thaw`
mirrors line for line.
"""

from __future__ import annotations

from ...vcs import DriftReport


def _is_repair_attempt(attempt: int, thawed: bool) -> bool:
    """Attempt 1 is the FREE pass -- the dev authors the contract's tests
    there. Every later attempt is a repair attempt, including the
    operator-REVISE continuation, unless a human explicitly thawed it for
    exactly this attempt."""
    return attempt > 1 and not thawed


def _next_anchor(
    current: str | None, commit_sha: str | None, *, freely_writable: bool
) -> str | None:
    """The C2 anchor rule, as a table rather than as inline loop conditions.

    A is the checkpoint of the last attempt in which tests were FREELY
    WRITABLE: attempt 1, plus any attempt a human thawed. It is captured once
    and then held -- moving it to each attempt's checkpoint would let attempt
    2 weaken a test that attempt 3 inherits as its baseline, laundering the
    weakening over two attempts. A thaw is the ONLY thing that moves it, and
    it must, or the backstop would flag the very edits the operator just
    authorized.

    `freely_writable` is the attempt's own status, not a derived one: A may
    only ever be a checkpoint the session could legitimately have written
    tests in. Deriving it from `current is None` instead would promote a
    frozen attempt's checkpoint to the baseline whenever attempt 1 produced
    none (fact 7a), laundering exactly what the ratchet exists to stop.

    `commit_sha` is None when an attempt produced no checkpoint (a swallowed
    commit failure, or a crew round-1 deadline). Then A simply does not move;
    there is deliberately no branch_point fallback."""
    if commit_sha and freely_writable:
        return commit_sha
    return current


def _drift_note(report: DriftReport) -> str:
    """The deterministic finding, rendered for the human at the fix-loop gate.

    Three channels, named separately on purpose: 'the session hid a change'
    is a different accusation from 'a test changed', and a human decides them
    differently. The patch is included so weakening is distinguishable from a
    formatter run in one look."""
    if not report.available:
        return (
            "TEST-FREEZE BACKSTOP UNAVAILABLE: "
            f"{report.unavailable_reason}. Test drift was NOT checked for this attempt."
        )
    if not report.found:
        return ""
    lines: list[str] = []
    if report.index_bit_paths:
        lines.append(
            "EVASION: the session set skip-worktree/assume-unchanged on protected "
            "paths, hiding edits from the diff: " + ", ".join(report.index_bit_paths)
        )
    if report.fence_paths:
        lines.append(
            "FROZEN TESTS CHANGED during a repair attempt: " + ", ".join(report.fence_paths)
        )
    if report.report_paths:
        lines.append(
            "TEST CONFIGURATION CHANGED during a repair attempt: " + ", ".join(report.report_paths)
        )
    if report.patch:
        lines.append("\nDrift patch:\n" + report.patch)
    return "\n".join(lines)
