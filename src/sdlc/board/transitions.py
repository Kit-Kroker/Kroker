# src/sdlc/board/transitions.py
"""Task state machine. One table, one checker — both writers use it, so an
agent and the workflow cannot disagree about what a legal move is.

DONE is terminal within a plan version: the in-run fix loop happens while a
task is IN_PROGRESS (feature.py's _dev_task retries before returning), so a
completed task reopening means a new plan, hence a new plan_version. The one
sanctioned DONE -> IN_PROGRESS re-entry is a Temporal workflow reset: the
replay legitimately re-executes a task whose completion was truncated, and
the board (external state the history cannot rewind) must follow the history
rather than veto it. Everything else still treats DONE as terminal.
"""

from __future__ import annotations

from .models import TaskStatus

TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}),
    TaskStatus.IN_PROGRESS: frozenset(
        {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.QUARANTINED}
    ),
    TaskStatus.BLOCKED: frozenset(
        {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.FAILED, TaskStatus.QUARANTINED}
    ),
    TaskStatus.FAILED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.DONE}),
    TaskStatus.QUARANTINED: frozenset({TaskStatus.IN_PROGRESS}),
    # Reset replay re-entry only: see module docstring. Agents claiming tasks
    # (the live status column) never write authoritative status, so these edges
    # are reachable only from the workflow's own authoritative writes.
    TaskStatus.DONE: frozenset({TaskStatus.IN_PROGRESS}),
    # Same reset-replay reasoning: a replayed completion writes done over a
    # pre-reset failed row; the board follows the history, it does not veto it.
    # QUARANTINED keeps the narrow edge: quarantine is an operator verdict,
    # not a replay artifact.
}


def check_task_transition(frm: TaskStatus, to: TaskStatus) -> None:
    from .store import InvalidTransition  # local: avoids import cycle

    if to not in TASK_TRANSITIONS[frm]:
        raise InvalidTransition(f"{frm.value} -> {to.value} is not a permitted task transition")
