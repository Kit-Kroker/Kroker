# src/sdlc/board/api.py
"""HTTP surface over BoardStore.

Lives under src/ (not interfaces/) because pyproject's packages.find is
rooted at src — anything outside it is not importable by tests.
interfaces/dashboard/api/main.py is the uvicorn entrypoint.

Reads are unrestricted; writes are the two narrow agent routes in Task 8.
Content reads are byte-capped the way load_session is (artifacts/read.py:18)
so one large artifact cannot blow a consumer's context.
"""

from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from ..artifacts.store import ref_to_path
from ..core.models import (
    ArtifactRef,
)
from .models import (
    ArtifactVersion,
    BoardArtifact,
    BoardEvent,
    BoardStats,
    BoardTask,
    TaskEvidence,
    TaskStatus,
)
from .store import BoardStore, ConflictError, InvalidTransition, NotFoundError

MAX_CONTENT_BYTES = 512 * 1024


class ProjectDetail(BaseModel):
    key: str
    repo: str
    artifacts: list[BoardArtifact]
    stats: BoardStats


class ProjectSummary(BaseModel):
    key: str
    repo: str


class VersionContent(BaseModel):
    id: int
    n: int
    run_id: str
    sha256: str
    uri: str
    content: str
    truncated: bool


class TaskDetail(BaseModel):
    task: BoardTask
    evidence: list[TaskEvidence]


class TaskPatch(BaseModel):
    status: TaskStatus
    detail: str = ""


def create_app(store_factory: Callable[[], BoardStore] | None = None) -> FastAPI:
    factory = store_factory or BoardStore
    app = FastAPI(title="SDLC Agent Board", version="1.0")

    def get_store() -> Generator[BoardStore, None, None]:
        store = factory()
        try:
            yield store
        finally:
            store.close()

    def _current_plan_version(store: BoardStore, project: str) -> int:
        try:
            art = store.get_artifact(project, "plan")
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        if art.current_version is None:
            raise HTTPException(404, f"project {project!r} has no current plan")
        return art.current_version

    def _require_project(store: BoardStore, project: str) -> tuple[str, str]:
        try:
            return store.get_project(project)
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/projects", response_model=list[ProjectSummary])
    def list_projects(store: BoardStore = Depends(get_store)):
        return [ProjectSummary(key=k, repo=r) for k, r in store.list_projects()]

    @app.get("/projects/{project}", response_model=ProjectDetail)
    def get_project(project: str, store: BoardStore = Depends(get_store)):
        key, repo = _require_project(store, project)
        return ProjectDetail(
            key=key, repo=repo, artifacts=store.list_artifacts(project), stats=store.stats(project)
        )

    @app.get("/projects/{project}/artifacts/{key}", response_model=list[ArtifactVersion])
    def list_versions(project: str, key: str, store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        try:
            store.get_artifact(project, key)
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        return store.list_versions(project, key)

    @app.get(
        "/projects/{project}/artifacts/{key}/versions/{version_id}", response_model=VersionContent
    )
    def get_version(
        project: str, key: str, version_id: int, store: BoardStore = Depends(get_store)
    ):
        _require_project(store, project)
        try:
            v = store.get_version(project, version_id)
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        if v.key != key:
            raise HTTPException(404, f"version {version_id} belongs to {v.key!r}, not {key!r}")
        path = ref_to_path(ArtifactRef(kind=v.key, uri=v.uri, sha256=v.sha256))
        if not path.exists():
            # Metadata outlives the blob: the version row and its sha256 are
            # still authoritative history even when runs/ has been pruned.
            raise HTTPException(
                410,
                {
                    "message": "blob pruned from the claim-check store",
                    "sha256": v.sha256,
                    "uri": v.uri,
                },
            )
        data = path.read_bytes()
        truncated = len(data) > MAX_CONTENT_BYTES
        return VersionContent(
            id=v.id,
            n=v.n,
            run_id=v.run_id,
            sha256=v.sha256,
            uri=v.uri,
            content=data[:MAX_CONTENT_BYTES].decode("utf-8", errors="replace"),
            truncated=truncated,
        )

    @app.get("/projects/{project}/tasks", response_model=list[BoardTask])
    def list_tasks(
        project: str,
        status: TaskStatus | None = None,
        run_id: str | None = None,
        plan: int | None = None,
        store: BoardStore = Depends(get_store),
    ):
        # `status` here filters the LIVE view (BoardTask.status) — what an
        # agent reads to avoid a task another agent already claimed. This is
        # deliberately NOT authoritative_status: /stats counts the
        # authoritative column so scoring is unaffected by optimistic agent
        # writes, while /tasks?status= shows the live view agents act on.
        _require_project(store, project)
        pv = plan if plan is not None else _current_plan_version(store, project)
        return store.list_tasks(project, pv, status=status, run_id=run_id)

    @app.get("/projects/{project}/tasks/{task_id}", response_model=TaskDetail)
    def get_task(
        project: str, task_id: str, plan: int | None = None, store: BoardStore = Depends(get_store)
    ):
        _require_project(store, project)
        pv = plan if plan is not None else _current_plan_version(store, project)
        try:
            task = store.get_task(project, pv, task_id)
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        return TaskDetail(task=task, evidence=store.list_evidence(project, pv, task_id))

    @app.get("/projects/{project}/events", response_model=list[BoardEvent])
    def list_events(
        project: str,
        since: int = 0,
        subject: str | None = None,
        store: BoardStore = Depends(get_store),
    ):
        _require_project(store, project)
        return store.list_events(project, since=since, subject=subject)

    @app.get("/projects/{project}/stats", response_model=BoardStats)
    def get_stats(project: str, store: BoardStore = Depends(get_store)):
        _require_project(store, project)
        return store.stats(project)

    def _agent_write(
        store: BoardStore,
        project: str,
        task_id: str,
        status: TaskStatus,
        plan: int | None,
        if_match: str | None,
        actor: str,
        detail: str,
    ) -> BoardTask:
        """Shared body for both agent routes. Every rejection maps to a
        status code here; the store raised, so nothing was written and no
        event row exists — the change log records real changes only.

        X-Actor is self-asserted by the caller: any client can claim any
        identity. This is scope-correct (the spec assumes an unauthenticated
        internal network), but it means the audit trail's trustworthiness
        rests on the caller being honest — enforce identity upstream of this
        endpoint before relying on `actor` for accountability."""
        _require_project(store, project)
        if if_match is None:
            raise HTTPException(428, "If-Match: <row_version> is required for agent writes")
        try:
            expect = int(if_match)
        except ValueError as e:
            raise HTTPException(400, "If-Match must be an integer") from e
        pv = plan if plan is not None else _current_plan_version(store, project)
        try:
            return store.set_task_observational(
                project, pv, task_id, status, actor=actor, expect_row_version=expect, detail=detail
            )
        except NotFoundError as e:
            raise HTTPException(404, str(e)) from e
        except ConflictError as e:
            raise HTTPException(409, str(e)) from e
        except InvalidTransition as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/projects/{project}/tasks/{task_id}/claim", response_model=BoardTask)
    def claim_task(
        project: str,
        task_id: str,
        plan: int | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
        x_actor: str = Header(default="agent:unknown", alias="X-Actor"),
        store: BoardStore = Depends(get_store),
    ):
        return _agent_write(
            store, project, task_id, TaskStatus.IN_PROGRESS, plan, if_match, x_actor, detail="claim"
        )

    @app.patch("/projects/{project}/tasks/{task_id}", response_model=BoardTask)
    def patch_task(
        project: str,
        task_id: str,
        patch: TaskPatch,
        plan: int | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
        x_actor: str = Header(default="agent:unknown", alias="X-Actor"),
        store: BoardStore = Depends(get_store),
    ):
        return _agent_write(
            store, project, task_id, patch.status, plan, if_match, x_actor, detail=patch.detail
        )

    return app


app = create_app()
