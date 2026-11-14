"""FR-205's shared validators library: pure, workflow-safe checks.

No I/O, no top-level temporalio import -- importable from workflow code and
activities alike. This module opens the library with the plan-graph checks
migrated verbatim from stages/plan/validation.py (E-74 origin) and the new
ids_unique check; later tasks add tree-reading validators (activities.py)
and evidence schemas (evidence.py).
"""

from __future__ import annotations

from collections import Counter

from ..stages.plan.models import DevTask


def ids_unique(tasks: list[DevTask]) -> str | None:
    """None when task ids are unique; otherwise a human-readable reason.

    Downstream the plan stage collapses tasks into ``{t.id: t}``; duplicate
    ids silently drop tasks before the DAG checks ever see them -- the same
    dropped-task shape as bench-todo-api-greenfield-1785868165's plan
    revision, discovered only deep into execution. Naming the duplicates
    right after the plan gate makes the planner's mistake legible instead."""
    counts = Counter(t.id for t in tasks)
    duplicates = sorted(tid for tid, n in counts.items() if n > 1)
    if duplicates:
        return f"duplicate task id(s): {duplicates!r}"
    return None


def deps_resolve(tasks: list[DevTask]) -> str | None:
    """None when every task's depends_on resolves to another task in the
    same plan; otherwise a human-readable reason.

    Catches the failure shape the scheduler's ready-loop (run_one's caller,
    below) would otherwise only discover after burning a run: a dangling
    reference (a revision round dropped a task while a survivor still cites
    its id -- exactly bench-todo-api-greenfield-1785868165's single-task
    T7-depends-on-T3..T6 plan). Surfacing this right after the plan gate
    turns it into an immediate, legible `failed:plan-validation:...` instead
    of the scheduler's opaque `failed:dependency-cycle` once tasks are
    already mid-execution."""
    ids = {t.id for t in tasks}
    for t in tasks:
        unknown = [d for d in t.depends_on if d not in ids]
        if unknown:
            return f"task {t.id!r} depends on unknown task id(s) {unknown!r}"
    return None


def dag_acyclic(tasks: list[DevTask]) -> str | None:
    """None when the dependency graph has no cycle; otherwise a
    human-readable reason.

    Catches the failure shape the scheduler's ready-loop (run_one's caller,
    below) would otherwise only discover after burning a run: a true
    A->B->A cycle. Surfacing this right after the plan gate turns it into an
    immediate, legible `failed:plan-validation:...` instead of the
    scheduler's opaque `failed:dependency-cycle` once tasks are already
    mid-execution."""
    ids = {t.id for t in tasks}
    by_id = {t.id: t for t in tasks}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(ids, WHITE)

    def visit(tid: str, path: list[str]) -> str | None:
        color[tid] = GRAY
        for dep in by_id[tid].depends_on:
            if color[dep] == GRAY:
                cycle = path[path.index(dep) :] + [dep]
                return " -> ".join(cycle)
            if color[dep] == WHITE:
                found = visit(dep, path + [dep])
                if found:
                    return found
        color[tid] = BLACK
        return None

    for t in tasks:
        if color[t.id] == WHITE:
            cycle = visit(t.id, [t.id])
            if cycle:
                return f"dependency cycle: {cycle}"
    return None


def validate_task_graph(tasks: list[DevTask]) -> str | None:
    """None when every task's depends_on resolves to another task in the
    same plan and the graph has no cycle; otherwise a human-readable reason.

    Composition of deps_resolve and dag_acyclic -- behavior-identical (same
    failure messages, same precedence) to the pre-FR-205
    stages/plan/validation.py module this package replaced; ids_unique is a
    separate check callers run before it."""
    return deps_resolve(tasks) or dag_acyclic(tasks)
