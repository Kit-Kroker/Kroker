"""FR-205's shared validators library: pure, workflow-safe checks.

No I/O, no top-level temporalio import -- importable from workflow code and
activities alike. This module opens the library with the plan-graph checks
migrated verbatim from stages/plan/validation.py (E-74 origin), the new
ids_unique check, and path_like_tokens -- the pure tokenizer the tree-reading
activity in activities.py consumes; evidence schemas (evidence.py) follow in
a later task.
"""

from __future__ import annotations

import re
from collections import Counter

from ..core.models import PlanConfig
from ..stages.plan.models import DevTask


def _norm_path(p: str) -> str:
    """Windows-authored hints and POSIX diff paths name the same file.

    Deliberately DIVERGES from the stages/plan/models.py twin: that copy
    ``lstrip("./")``-es every leading dot AND slash character, corrupting
    dotfile paths (``.github/workflows/ci.yaml`` -> ``github/...``). The
    drift comparison tolerates it because it normalizes both sides
    identically -- self-consistent corruption. Here a corrupted token is a
    false-missing report and, downstream, a false DISCARD of a question
    citing a file that exists, so this copy strips separators/whitespace and
    then removes ONE leading ``./`` prefix, never bare dot characters. The
    twin must stay byte-identical; change this one alone.
    """
    p = p.replace("\\", "/").strip()
    return p[2:] if p.startswith("./") else p


# A path-like token WITHOUT a separator still qualifies when it ends in a
# known source/config extension -- this is what lets `README.md` through
# while `sdlc.stages.plan.validation` (a symbol) stays out.
_PATH_EXT_RE = re.compile(
    r"[\w.-]+\.(py|ts|tsx|js|go|rs|md|yaml|yml|json|toml|txt|cfg|ini|sql|sh)$"
)

# One tokenizer run: word chars, dots, slashes, hyphens. Prose punctuation
# (`;`, quotes, parens) splits tokens off instead of riding along, so
# "configs/prod.yaml;" yields the clean path.
_TOKEN_RE = re.compile(r"[\w./\\-]+")


def path_like_tokens(text: str) -> list[str]:
    """The path-like tokens in free agent prose, normalized, sorted, deduped.

    A token qualifies when it contains a path separator (``/`` or ``\\``)
    or ends in a known source/config extension; each hit is normalized by
    the local `_norm_path` -- which deliberately diverges from the
    plan/models.py twin on dotfiles -- so ``.\\src\\app.py`` and
    ``src/app.py`` collapse to one entry while ``.github/workflows/ci.yaml``
    keeps its leading dot. Symbols (`module.attr:26`) and bare prose yield
    `[]`.

    Task 6's clarify validation feeds agent-written prose through this to
    get a checkable path list; sorting and deduping here keeps the output
    deterministic, so the activity result and any failure message quoting
    it are stable across retries.
    """
    hits = {
        _norm_path(tok)
        for tok in _TOKEN_RE.findall(text)
        if "/" in tok or "\\" in tok or _PATH_EXT_RE.search(tok)
    }
    return sorted(p for p in hits if p)


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

    Catches the failure shape the scheduler (workflows/build.py run_tasks)
    would otherwise only discover after burning a run: a dangling
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

    Precondition: callers run deps_resolve first -- a standalone call
    raises KeyError on unknown ids. Catches the failure shape the
    scheduler (workflows/build.py run_tasks) would otherwise only discover
    after burning a run: a true A->B->A cycle. Surfacing this right after
    the plan gate turns it into an immediate, legible
    `failed:plan-validation:...` instead of the scheduler's opaque
    `failed:dependency-cycle` once tasks are already mid-execution."""
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


def covers_all(tasks: list[DevTask], requirement_ids: list[str]) -> list[str]:
    """The requirement ids no task covers, sorted; an empty list is a pass.

    Ids cited in `covers` but absent from `requirement_ids` are ignored --
    a US-* cover is legal -- because the question asked here is only which
    of the requirements artifact's ids would silently ship unimplemented:
    the same dropped-requirement shape bench cases punish, discovered only
    at acceptance if nobody checks at the plan gate."""
    covered = {c for t in tasks for c in t.covers}
    return sorted(r for r in requirement_ids if r not in covered)


def task_size(tasks: list[DevTask], limits: PlanConfig) -> str | None:
    """None when every task fits the plan's size limits; otherwise the
    FIRST breach in task-list order, verbatim as the failure reason.

    A task too large to finish in one harness session wedges the scheduler
    on it -- and in wave mode, its whole wave -- after execution has
    already started. Naming the first offender right after the plan gate
    keeps the fix a plan edit instead of a mid-run rescue; the limits are
    deliberately generous (PlanConfig) so only genuinely oversized tasks
    trip them."""
    for t in tasks:
        if len(t.files_hint) > limits.max_files_hint:
            return (
                f"task {t.id!r} exceeds plan limits: "
                f"files_hint={len(t.files_hint)}>{limits.max_files_hint}"
            )
        if len(t.acceptance_criteria) > limits.max_criteria:
            return (
                f"task {t.id!r} exceeds plan limits: "
                f"criteria={len(t.acceptance_criteria)}>{limits.max_criteria}"
            )
    return None
