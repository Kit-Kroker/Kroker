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

import asyncio
import json

from pydantic import BaseModel

from ..artifacts.store import ref_to_path
from ..board.models import TaskStatus
from ..board.store import NotFoundError
from ..channels.contract import ActorChannel, Reply, default_render
from ..channels.transport import resolve_key, submit
from ..core.models import (
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)
from ..naming import slug
from . import render
from .deps import OperatorDeps
from .errors import ToolError, guard

_STATUSES = ("open", "closed", "all")


@guard
async def list_runs(deps: OperatorDeps, status: str = "open") -> str:
    """List factory runs. status is one of open, closed, all."""
    deps.note_other_tool()
    if status not in _STATUSES:
        raise ToolError(f"unknown status {status!r}; use one of {', '.join(_STATUSES)}")
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
        f"{len(snap.closed)} recently closed runs; call list_runs"
    )


@guard
async def inbox(deps: OperatorDeps) -> str:
    """Every decision the factory is waiting on, across all open runs."""
    deps.note_other_tool()
    return render.inbox_view(await deps.poller.snapshot())


async def _board(deps: OperatorDeps, fn):
    """Run fn(store) on a worker thread, against a store created and closed
    inside that same thread.

    Three things at once, all required:

    * OFF THE LOOP. sqlite here is opened with PRAGMA busy_timeout=5000, so a
      contended write blocks its caller for up to five seconds. On the event
      loop that stalls the shared FleetPoller and every dashboard SSE client,
      not merely the chat request. board/api.py gets this for free by writing
      sync `def` handlers that Starlette offloads; async verbs must ask.
    * ONE THREAD. schema.connect() leaves check_same_thread at its default of
      True, so a connection opened on the loop thread cannot legally be used
      from a worker. Creating it inside `run` is what makes the offload safe.
    * PER CALL. board/api.py:65 opens and closes a store per request for the
      same reason; a single long-lived connection pinned to the import thread
      is a latent ProgrammingError.
    """
    factory = deps.board
    if not callable(factory):
        raise ToolError(
            "OperatorDeps.board must be a zero-argument callable returning a "
            "fresh BoardStore (it is used from a worker thread, so a shared "
            "instance would cross threads); got "
            f"{type(factory).__name__}"
        )

    def run():
        store = factory()
        try:
            return fn(store)
        finally:
            store.close()

    return await asyncio.to_thread(run)


def _current_plan_version(store, project: str) -> int:
    """The plan version list_tasks defaults to, resolved the way
    board/api.py:_current_plan_version does. Runs inside _board's thread."""
    try:
        art = store.get_artifact(project, "plan")
    except NotFoundError:
        raise ToolError(
            f"project {project!r} has no plan artifact yet, so it has no "
            f"tasks; call get_project to see what it does have"
        ) from None
    if art.current_version is None:
        raise ToolError(
            f"project {project!r} has a plan artifact with no current "
            f"version; pass plan_version explicitly"
        )
    return art.current_version


@guard
async def list_projects(deps: OperatorDeps) -> str:
    """Every project the board knows about."""
    deps.note_other_tool()
    rows = await _board(deps, lambda st: st.list_projects())
    if not rows:
        return "no projects on the board"
    return "\n".join(f"{key} | {repo or 'no repo'}" for key, repo in rows)


@guard
async def get_project(deps: OperatorDeps, project: str) -> str:
    """One project: its repo, its artifact keys, and its task counters.

    The artifact keys listed here are the ONLY keys read_artifact accepts.
    """
    deps.note_other_tool()

    def _fetch(st):
        return (st.get_project(project), st.list_artifacts(project), st.stats(project))

    (key, repo), artifacts, stats = await _board(deps, _fetch)
    lines = [f"project: {key}", f"repo: {repo or 'no repo'}"]
    if artifacts:
        lines.append("artifacts:")
        lines += [
            f"  {a.key} | {a.status.value} | "
            f"version {a.current_version if a.current_version else '-'}"
            for a in artifacts
        ]
    else:
        lines.append("artifacts: none published yet")
    lines.append(f"tasks: {stats.tasks_by_status or 'none'}")
    lines.append(
        f"fix attempts: {stats.total_fix_attempts} | "
        f"with error: {stats.tasks_with_error} | "
        f"diverged: {stats.diverged_tasks}"
    )
    return "\n".join(lines)


@guard
async def list_tasks(
    deps: OperatorDeps, project: str, plan_version: int | None = None, status: str | None = None
) -> str:
    """Tasks for a project's plan. Defaults to the current plan version."""
    deps.note_other_tool()
    want = None
    if status is not None:
        try:
            want = TaskStatus(status)
        except ValueError:
            allowed = ", ".join(s.value for s in TaskStatus)
            raise ToolError(f"unknown task status {status!r}; use one of {allowed}") from None

    def _fetch(st):
        st.get_project(project)
        v = plan_version if plan_version is not None else _current_plan_version(st, project)
        return v, st.list_tasks(project, v, status=want)

    version, rows = await _board(deps, _fetch)
    if not rows:
        return f"no tasks in plan {version} of {project!r}"
    lines = [f"plan {version} of {project!r}, {len(rows)} task(s):"]
    lines += [
        f"  {t.task_id} | {t.status.value} "
        f"(authoritative {t.authoritative_status.value}) | "
        f"attempts {t.fix_attempts}"
        f"{' | error: ' + t.error if t.error else ''}"
        for t in rows
    ]
    return "\n".join(lines)


@guard
async def project_events(deps: OperatorDeps, project: str, since: int = 0) -> str:
    """The board's durable timeline for a project, oldest first."""
    deps.note_other_tool()

    def _fetch(st):
        st.get_project(project)
        return st.list_events(project, since=since)

    rows = await _board(deps, _fetch)
    if not rows:
        return f"no events for {project!r} after id {since}"
    lines = [f"{len(rows)} event(s) for {project!r}:"]
    lines += [
        f"  #{e.id} {e.at.isoformat()} | {e.subject} | {e.actor} | "
        f"{e.authority.value} | {e.from_status or '-'} -> "
        f"{e.to_status or '-'}{' | ' + e.detail if e.detail else ''}"
        for e in rows
    ]
    return "\n".join(lines)


class ArtifactRead(BaseModel):
    """One page of an artifact body.

    truncated and next_offset exist so the model knows it is holding a
    fragment: without them it fills the gap by inventing the rest.
    """

    project: str
    key: str
    version_id: int
    n: int
    sha256: str
    content: str
    total_bytes: int
    truncated: bool
    next_offset: int | None = None


@guard
async def read_artifact(
    deps: OperatorDeps, project: str, key: str, version_id: int | None = None, offset: int = 0
) -> ArtifactRead:
    """Read one page of a published artifact.

    key MUST be one of the artifact keys get_project listed for this project.
    Large artifacts are paged: when truncated is true, call again with
    offset=next_offset. Summarize what you read; do not quote it whole.
    """
    deps.note_other_tool()
    if offset < 0:
        raise ToolError("offset must be zero or positive")

    def _fetch(st):
        st.get_project(project)
        # Refuse before touching the blob store: an unknown key is the model
        # fishing, and the answer is to go back to get_project, not to search.
        try:
            art = st.get_artifact(project, key)
        except NotFoundError:
            raise ToolError(
                f"project {project!r} has no artifact {key!r}; call "
                f"get_project and use one of the keys it lists"
            ) from None

        want = version_id
        if want is None:
            if art.current_version is None:
                raise ToolError(f"artifact {key!r} in {project!r} has no published version")
            want = art.current_version
        v = st.get_version(project, want)
        if v.key != key:
            raise ToolError(f"version {want} belongs to {v.key!r}, not {key!r}")

        path = ref_to_path(v)
        if not path.exists():
            # Metadata outlives the blob (board/api.py:126): the row and its
            # sha256 are still authoritative history when runs/ was pruned.
            raise ToolError(
                f"the blob for {key!r} version {want} was pruned from the "
                f"claim-check store; sha256 {v.sha256}, uri {v.uri}"
            )

        # Seek to the page rather than reading the whole blob to return
        # 32 KB of it: an artifact big enough to need paging is exactly the
        # one whose full read costs the most, and every page paid it again.
        total = path.stat().st_size
        if offset and offset >= total:
            raise ToolError(
                f"offset {offset} is past the end of {key!r} "
                f"({total} bytes); the previous page was the last one"
            )
        with path.open("rb") as fh:
            fh.seek(offset)
            window = fh.read(deps.max_artifact_bytes)
        return v, window, total

    v, window, total = await _board(deps, _fetch)
    end = offset + len(window)
    truncated = end < total
    return ArtifactRead(
        project=project,
        key=key,
        version_id=v.id,
        n=v.n,
        sha256=v.sha256,
        content=window.decode("utf-8", errors="replace"),
        total_bytes=total,
        truncated=truncated,
        next_offset=end if truncated else None,
    )


MIN_TIMEOUT_S = 5
MAX_TIMEOUT_S = 120


class ChangeReport(BaseModel):
    """What moved while we waited, or that nothing did."""

    run_id: str | None = None
    timed_out: bool = False
    changed: list[str] = []
    detail: str = ""


def _clamp(timeout_s: int) -> int:
    return max(MIN_TIMEOUT_S, min(MAX_TIMEOUT_S, int(timeout_s)))


def _in_scope(rid: str, run_id: str | None) -> bool:
    return run_id is None or rid == run_id


def _projection(snap, run_id: str | None) -> str:
    """A stable fingerprint of the part of the fleet being followed.

    Scoped to one run on purpose: a fleet-wide fingerprint moves whenever ANY
    run moves, so a scoped follow against it would return instantly and
    forever. `at` is excluded for the reason dashboard/api.py excludes it --
    the clock is not a change.

    It fingerprints EXACTLY the fields _describe_change can name -- stage,
    status, presence, and pending keys -- and nothing else. Serialising the
    whole RunState instead (as this did originally) folds in `roles` and
    `cost_usd_total`, which move on almost every poll tick of an active run:
    every wait then returned within seconds reporting a change it could not
    describe, burning a model round trip and marching toward the consecutive
    -wait brake. A fingerprint must not be able to move in a way the report
    cannot explain.
    """
    payload = {
        "runs": sorted(
            (r.run_id, r.current_stage, r.status) for r in snap.runs if _in_scope(r.run_id, run_id)
        ),
        "pending": sorted(
            (i.run_id, d.key) for i in snap.inbox if _in_scope(i.run_id, run_id) for d in i.pending
        ),
        # Scoped like everything else: an unrelated run finishing, or an old
        # entry ageing out of CLOSED_LIMIT, must not end a wait on this run.
        "closed": sorted(c.run_id for c in snap.closed if _in_scope(c.run_id, run_id)),
    }
    return json.dumps(payload, sort_keys=True)


def _describe_change(before, after, run_id: str | None) -> tuple[list[str], str]:
    changed: list[str] = []
    before_runs = {r.run_id: r for r in before.runs}
    after_runs = {r.run_id: r for r in after.runs}
    scope = [run_id] if run_id is not None else sorted(set(before_runs) | set(after_runs))
    lines: list[str] = []
    for rid in scope:
        was, now = before_runs.get(rid), after_runs.get(rid)
        if was is not None and now is None:
            changed.append(f"{rid}:closed")
            lines.append(f"{rid} is no longer open -- it closed")
            continue
        if now is None:
            continue
        if was is None:
            changed.append(f"{rid}:appeared")
            lines.append(f"{rid} appeared: {render.run_line(now)}")
            continue
        if was.current_stage != now.current_stage:
            changed.append(f"{rid}:stage")
            lines.append(f"{rid} stage {was.current_stage} -> {now.current_stage}")
        if was.status != now.status:
            changed.append(f"{rid}:status")
            lines.append(f"{rid} status {was.status} -> {now.status}")
    before_keys = {(i.run_id, d.key) for i in before.inbox for d in i.pending}
    for item in after.inbox:
        if run_id is not None and item.run_id != run_id:
            continue
        for d in item.pending:
            if (item.run_id, d.key) not in before_keys:
                changed.append(f"{item.run_id}:pending")
                lines.append(f"{item.run_id} is now waiting on:\n{render.pending_block(d)}")
    if not lines:
        lines.append("something changed that this report does not name; call get_run for detail")
    return changed, "\n".join(lines)


@guard
async def follow(
    deps: OperatorDeps, run_id: str | None = None, timeout_s: int = 60
) -> ChangeReport:
    """Wait until something changes, then report what.

    Waits on one run when run_id is given, otherwise on the whole fleet.
    Returns as soon as a run needs a decision or finishes. Report to the
    operator between waits; consecutive waits are capped.
    """
    deps.note_follow()
    timeout_s = _clamp(timeout_s)
    before = await deps.poller.snapshot()
    if run_id is not None and not any(r.run_id == run_id for r in before.runs):
        raise ToolError(
            f"{run_id!r} is not an open run, so there is nothing to wait for; call list_runs"
        )

    baseline = _projection(before, run_id)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    async with deps.poller.subscribe() as q:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return ChangeReport(
                    run_id=run_id, timed_out=True, detail=f"nothing changed in {timeout_s}s"
                )
            try:
                snap = await asyncio.wait_for(q.get(), timeout=remaining)
            except TimeoutError:
                return ChangeReport(
                    run_id=run_id, timed_out=True, detail=f"nothing changed in {timeout_s}s"
                )
            if _projection(snap, run_id) == baseline:
                continue
            changed, detail = _describe_change(before, snap, run_id)
            return ChangeReport(run_id=run_id, timed_out=False, changed=changed, detail=detail)


class ReplyReceipt(BaseModel):
    """The outcome of one reply, in the words transport already chose.

    confirmed=False is informational, never an error: the dominant cause is
    another surface winning the race, which is FR-302 working as designed
    (transport._message). Repeat detail to the operator verbatim.
    """

    run_id: str
    key: str
    confirmed: bool
    detail: str


async def _handle(deps: OperatorDeps, run_id: str):
    client = await deps.poller._client_or_connect()
    return client.get_workflow_handle(run_id)


async def _reply(
    deps: OperatorDeps, run_id: str, key: str, reply: Reply, want: str
) -> ReplyReceipt:
    handle = await _handle(deps, run_id)
    pending = await resolve_key(handle, key)
    kind = default_render(pending).reply_kind
    if kind != want:
        right = "answer_question" if kind == "text" else "decide_gate"
        raise ToolError(f"key {key!r} on {run_id} takes a {kind} reply; use {right}")
    result = await submit(handle, pending, reply, channel=ActorChannel(actor=deps.actor))
    return ReplyReceipt(run_id=run_id, key=key, confirmed=result.confirmed, detail=result.message)


@guard
async def answer_question(deps: OperatorDeps, run_id: str, key: str, text: str) -> ReplyReceipt:
    """Answer a clarification question the run is waiting on.

    key must come from get_run or inbox; do not invent one.
    """
    deps.note_other_tool()
    return await _reply(deps, run_id, key, Reply(text=text), want="text")


@guard
async def decide_gate(
    deps: OperatorDeps, run_id: str, key: str, outcome: GateOutcome, text: str = ""
) -> ReplyReceipt:
    """Approve, reject, or request revision on a gate the run is waiting on.

    key must come from get_run or inbox. The gate round is taken from the
    pending item -- never supply one. With outcome=revise, text is the
    guidance the pipeline loops back with.
    """
    deps.note_other_tool()
    return await _reply(deps, run_id, key, Reply(outcome=outcome, text=text or None), want="gate")


@guard
async def start_run(
    deps: OperatorDeps,
    title: str,
    mode: ProjectMode,
    description: str = "",
    repo: str | None = None,
) -> str:
    """Start a new feature run. Returns the run id.

    Brownfield runs need a repo url; greenfield runs must not be given one.
    """
    deps.note_other_tool()
    if mode is ProjectMode.BROWNFIELD and not repo:
        raise ToolError(
            "a brownfield run needs repo set to the repository url; ask the "
            "operator which repository this is for"
        )
    idea = IdeaBrief(title=title, description=description, mode=mode, repo_url=repo)
    stem = slug(title)
    if not stem:
        # slug() strips everything non-alphanumeric, so a title like "!!!"
        # yields "", and the run would be started as bare "feature-".
        raise ToolError(
            f"title {title!r} has no letters or digits to build a run id "
            f"from; ask the operator for a descriptive title"
        )
    wf_id = f"feature-{stem}"
    try:
        started = await deps.starter(idea, PipelineConfig(), wf_id)
    except Exception as e:  # noqa: BLE001 -- narrowed into ToolError
        if "already started" in str(e).lower():
            raise ToolError(
                f"a run with id {wf_id!r} already exists; call get_run on it, "
                f"or start this one under a different title"
            ) from None
        raise
    # The starter's return value is authoritative: it is the id Temporal
    # actually assigned. Returning the locally computed one would quietly
    # diverge the moment a starter dedupes or decorates the id.
    return started or wf_id
