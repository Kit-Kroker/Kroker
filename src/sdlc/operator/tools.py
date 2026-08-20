"""The operator's twelve verbs (E-86).

Plain async functions taking OperatorDeps first. No pydantic_ai, no fastapi:
agent.py adapts these for the chat surface and E-11's MCP server will adapt
the same functions, so anything framework-shaped belongs in the adapter and
not here. tests/test_operator_layering.py enforces it.

Reads return rendered ASCII text (render.py). read_artifact, follow, and the
three writes return typed models, because their fields -- truncated,
next_offset, timed_out, confirmed -- carry meaning the model must branch on
rather than read prose about.
"""
from __future__ import annotations

from ..board.models import TaskStatus
from ..board.store import NotFoundError
from .deps import OperatorDeps
from .errors import ToolError, guard
from . import render

_STATUSES = ("open", "closed", "all")



@guard
async def list_runs(deps: OperatorDeps, status: str = "open") -> str:
    """List factory runs. status is one of open, closed, all."""
    deps.note_other_tool()
    if status not in _STATUSES:
        raise ToolError(
            f"unknown status {status!r}; use one of {', '.join(_STATUSES)}")
    return render.runs_view(await deps.poller.snapshot(), status)


@guard
async def get_run(deps: OperatorDeps, run_id: str) -> str:
    """Detail for one run, including every decision it is waiting on."""
    deps.note_other_tool()
    snap = await deps.poller.snapshot()
    for r in snap.runs:
        if r.run_id == run_id:
            return render.run_detail(r, render.pending_for(snap, run_id))
    for c in snap.closed:
        if c.run_id == run_id:
            return render.summary_line(c)
    raise ToolError(
        f"no run {run_id!r} among {len(snap.runs)} open and "
        f"{len(snap.closed)} recently closed runs; call list_runs")


@guard
async def inbox(deps: OperatorDeps) -> str:
    """Every decision the factory is waiting on, across all open runs."""
    deps.note_other_tool()
    return render.inbox_view(await deps.poller.snapshot())


def _current_plan_version(deps: OperatorDeps, project: str) -> int:
    """The plan version list_tasks defaults to, resolved the way
    board/api.py:_current_plan_version does."""
    try:
        art = deps.board.get_artifact(project, "plan")
    except NotFoundError as e:
        raise ToolError(
            f"project {project!r} has no plan artifact yet, so it has no "
            f"tasks; call get_project to see what it does have") from None
    if art.current_version is None:
        raise ToolError(
            f"project {project!r} has a plan artifact with no current "
            f"version; pass plan_version explicitly")
    return art.current_version


@guard
async def list_projects(deps: OperatorDeps) -> str:
    """Every project the board knows about."""
    deps.note_other_tool()
    rows = deps.board.list_projects()
    if not rows:
        return "no projects on the board"
    return "\n".join(f"{key} | {repo or 'no repo'}" for key, repo in rows)


@guard
async def get_project(deps: OperatorDeps, project: str) -> str:
    """One project: its repo, its artifact keys, and its task counters.

    The artifact keys listed here are the ONLY keys read_artifact accepts.
    """
    deps.note_other_tool()
    key, repo = deps.board.get_project(project)
    artifacts = deps.board.list_artifacts(project)
    stats = deps.board.stats(project)
    lines = [f"project: {key}", f"repo: {repo or 'no repo'}"]
    if artifacts:
        lines.append("artifacts:")
        lines += [f"  {a.key} | {a.status.value} | "
                  f"version {a.current_version if a.current_version else '-'}"
                  for a in artifacts]
    else:
        lines.append("artifacts: none published yet")
    lines.append(f"tasks: {stats.tasks_by_status or 'none'}")
    lines.append(f"fix attempts: {stats.total_fix_attempts} | "
                 f"with error: {stats.tasks_with_error} | "
                 f"diverged: {stats.diverged_tasks}")
    return "\n".join(lines)


@guard
async def list_tasks(deps: OperatorDeps, project: str,
                     plan_version: int | None = None,
                     status: str | None = None) -> str:
    """Tasks for a project's plan. Defaults to the current plan version."""
    deps.note_other_tool()
    deps.board.get_project(project)
    version = (plan_version if plan_version is not None
               else _current_plan_version(deps, project))
    want = None
    if status is not None:
        try:
            want = TaskStatus(status)
        except ValueError:
            allowed = ", ".join(s.value for s in TaskStatus)
            raise ToolError(
                f"unknown task status {status!r}; use one of {allowed}"
            ) from None
    rows = deps.board.list_tasks(project, version, status=want)
    if not rows:
        return f"no tasks in plan {version} of {project!r}"
    lines = [f"plan {version} of {project!r}, {len(rows)} task(s):"]
    lines += [f"  {t.task_id} | {t.status.value} "
              f"(authoritative {t.authoritative_status.value}) | "
              f"attempts {t.fix_attempts}"
              f"{' | error: ' + t.error if t.error else ''}"
              for t in rows]
    return "\n".join(lines)


@guard
async def project_events(deps: OperatorDeps, project: str,
                         since: int = 0) -> str:
    """The board's durable timeline for a project, oldest first."""
    deps.note_other_tool()
    deps.board.get_project(project)
    rows = deps.board.list_events(project, since=since)
    if not rows:
        return f"no events for {project!r} after id {since}"
    lines = [f"{len(rows)} event(s) for {project!r}:"]
    lines += [f"  #{e.id} {e.at.isoformat()} | {e.subject} | {e.actor} | "
              f"{e.authority.value} | {e.from_status or '-'} -> "
              f"{e.to_status or '-'}{' | ' + e.detail if e.detail else ''}"
              for e in rows]
    return "\n".join(lines)

