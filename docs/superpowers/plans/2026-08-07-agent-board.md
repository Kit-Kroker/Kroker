# Agent Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the pipeline a persistent, queryable project-level board — versioned artifacts, tasks with a real status lifecycle, an append-only change log — writable by the workflow and safely status-writable by agents.

**Architecture:** SQLite holds the mutable graph (artifacts, versions, tasks, events); the existing claim-check `LocalFileStore` holds immutable artifact bodies. `BoardStore` is the single enforcement point for state transitions and optimistic concurrency. The workflow writes through Temporal activities in-process; agents write through a FastAPI app. Both reach the same `BoardStore`.

**Tech Stack:** Python 3.11+, `sqlite3` (stdlib), Pydantic v2, Temporal (`temporalio`), FastAPI + uvicorn, pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-agent-board-design.md`

## Global Constraints

- Board DB path: `$SDLC_BOARD_DB`, default `runs/board.sqlite3`. Resolve env **inside activities/store construction only** — never in workflow code.
- SQLite opens with `journal_mode=WAL`, `busy_timeout=5000`; all writes use `BEGIN IMMEDIATE`.
- Artifact keys are exactly `requirements`, `architecture`, `plan`.
- Evidence kinds are exactly `qa`, `review`, `deep_review`.
- `plan_version` everywhere is `artifact_version.id` (surrogate), never the ordinal `n`.
- `authoritative_status` is written **only** by workflow activities. `/stats` and any scoring read `authoritative_status`, never `status`.
- Every accepted state change appends exactly one `event` row. Rejected writes append **no** event.
- Non-deterministic I/O lives in activities only (`@activity.defn`), never in workflow code — matches `benchmarks/recorder.py:83`.
- New activities MUST be added to `worker.py`'s `activities=[...]` list; `tests/test_worker_registration.py` greps that source literal by name.
- Tests are flat in `tests/`. Default `pytest` run excludes `slow`, `temporal`, `live`, `docker` markers.
- Follow the house idiom from `benchmarks/recorder.py:55`: a plain store class owning all I/O plus thin `@activity.defn` wrappers.

**One deviation from the spec, deliberate:** the spec placed the FastAPI app at `interfaces/dashboard/api/`. `pyproject.toml` sets `packages.find where = ["src"]`, so anything under `interfaces/` is not importable by tests. The app therefore lives at `src/sdlc/board/api.py` (importable, testable), and `interfaces/dashboard/api/main.py` becomes a three-line uvicorn entrypoint importing it. Behaviour is unchanged.

---

### Task 1: Board models and SQLite schema

**Files:**
- Create: `src/sdlc/board/__init__.py`
- Create: `src/sdlc/board/models.py`
- Create: `src/sdlc/board/schema.py`
- Test: `tests/test_board_schema.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `ArtifactStatus`, `TaskStatus`, `Authority`, `ArtifactVersion`, `BoardArtifact`, `BoardTask`, `TaskEvidence`, `BoardEvent`, `BoardStats` (Pydantic models); `apply_schema(conn: sqlite3.Connection) -> None`; `connect(path: str | os.PathLike) -> sqlite3.Connection`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_schema.py
"""Board schema: idempotent DDL + WAL connection."""

import sqlite3

from sdlc.board.schema import apply_schema, connect

TABLES = {"project", "artifact", "artifact_version", "task", "task_evidence", "event"}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def test_apply_schema_creates_every_table(tmp_path):
    conn = connect(tmp_path / "b.sqlite3")
    apply_schema(conn)
    assert TABLES <= _tables(conn)


def test_apply_schema_is_idempotent(tmp_path):
    conn = connect(tmp_path / "b.sqlite3")
    apply_schema(conn)
    apply_schema(conn)  # must not raise
    assert TABLES <= _tables(conn)


def test_connect_enables_wal_and_busy_timeout(tmp_path):
    conn = connect(tmp_path / "b.sqlite3")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_task_primary_key_is_composite(tmp_path):
    conn = connect(tmp_path / "b.sqlite3")
    apply_schema(conn)
    cols = conn.execute("PRAGMA table_info(task)").fetchall()
    pk = sorted(c[1] for c in cols if c[5])  # c[5] = pk position
    assert pk == ["plan_version", "project", "task_id"]


def test_artifact_version_unique_per_project_key_n(tmp_path):
    conn = connect(tmp_path / "b.sqlite3")
    apply_schema(conn)
    ins = (
        "INSERT INTO artifact_version"
        "(project,key,n,run_id,sha256,uri,supersedes,created_at)"
        " VALUES (?,?,?,?,?,?,?,?)"
    )
    conn.execute(ins, ("p", "plan", 1, "r1", "s", "u", None, "t"))
    try:
        conn.execute(ins, ("p", "plan", 1, "r2", "s", "u", None, "t"))
        raise AssertionError("duplicate (project,key,n) must be rejected")
    except sqlite3.IntegrityError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.board'`

- [ ] **Step 3: Write the models**

```python
# src/sdlc/board/__init__.py
```

(empty file — matches `src/sdlc/artifacts/__init__.py`)

```python
# src/sdlc/board/models.py
"""Board entities. The mutable graph SQLite holds; artifact BODIES live in
the claim-check store and are referenced by uri+sha256, never inlined here."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ArtifactStatus(str, Enum):
    PROPOSED = "proposed"
    CURRENT = "current"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    QUARANTINED = "quarantined"


class Authority(str, Enum):
    """Who moved a status. Only AUTHORITATIVE writes touch
    BoardTask.authoritative_status, which is what scoring reads."""

    AUTHORITATIVE = "authoritative"  # workflow activities
    OBSERVATIONAL = "observational"  # agents


class ArtifactVersion(BaseModel):
    id: int
    project: str
    key: str
    n: int
    run_id: str
    sha256: str
    uri: str
    supersedes: int | None = None
    created_at: datetime


class BoardArtifact(BaseModel):
    project: str
    key: str
    status: ArtifactStatus
    current_version: int | None = None


class BoardTask(BaseModel):
    project: str
    plan_version: int
    task_id: str
    run_id: str
    status: TaskStatus
    authoritative_status: TaskStatus
    row_version: int
    fix_attempts: int = 0
    error: str | None = None
    branch: str | None = None
    updated_at: datetime

    @property
    def diverged(self) -> bool:
        """An agent moved status somewhere the workflow has not confirmed."""
        return self.status != self.authoritative_status


class TaskEvidence(BaseModel):
    id: int
    project: str
    plan_version: int
    task_id: str
    run_id: str
    kind: str  # qa | review | deep_review
    sha256: str
    uri: str
    created_at: datetime


class BoardEvent(BaseModel):
    id: int
    project: str
    subject: str  # "artifact:<key>" | "task:<plan_version>:<id>"
    actor: str  # "workflow:<run_id>" | "agent:<name>"
    authority: Authority
    from_status: str | None = None
    to_status: str | None = None
    at: datetime
    detail: str = ""


class BoardStats(BaseModel):
    """Board-owned counters only. Quality/cost/speed rollup stays in
    benchmarks/ — duplicating it here would produce two scores that disagree."""

    project: str
    tasks_by_status: dict[str, int] = Field(default_factory=dict)
    total_fix_attempts: int = 0
    tasks_with_error: int = 0
    diverged_tasks: int = 0
    event_count: int = 0
```

- [ ] **Step 4: Write the schema**

```python
# src/sdlc/board/schema.py
"""SQLite DDL for the board. apply_schema is idempotent — safe to call on
every BoardStore construction, which is how a fresh DB file bootstraps."""

from __future__ import annotations

import os
import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS project (
    key         TEXT PRIMARY KEY,
    repo        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact (
    project         TEXT NOT NULL,
    key             TEXT NOT NULL,
    current_version INTEGER,
    status          TEXT NOT NULL,
    PRIMARY KEY (project, key)
);

CREATE TABLE IF NOT EXISTS artifact_version (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project     TEXT NOT NULL,
    key         TEXT NOT NULL,
    n           INTEGER NOT NULL,
    run_id      TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    uri         TEXT NOT NULL,
    supersedes  INTEGER,
    created_at  TEXT NOT NULL,
    UNIQUE (project, key, n)
);

CREATE TABLE IF NOT EXISTS task (
    project              TEXT NOT NULL,
    plan_version         INTEGER NOT NULL,
    task_id              TEXT NOT NULL,
    run_id               TEXT NOT NULL,
    status               TEXT NOT NULL,
    authoritative_status TEXT NOT NULL,
    row_version          INTEGER NOT NULL DEFAULT 1,
    fix_attempts         INTEGER NOT NULL DEFAULT 0,
    error                TEXT,
    branch               TEXT,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (project, plan_version, task_id)
);

CREATE TABLE IF NOT EXISTS task_evidence (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project      TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    task_id      TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    uri          TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project     TEXT NOT NULL,
    subject     TEXT NOT NULL,
    actor       TEXT NOT NULL,
    authority   TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    at          TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_event_project_id
    ON event(project, id);
CREATE INDEX IF NOT EXISTS idx_task_project_status
    ON task(project, authoritative_status);
CREATE INDEX IF NOT EXISTS idx_version_project_key
    ON artifact_version(project, key, n);
"""

DEFAULT_DB = "runs/board.sqlite3"


def db_path() -> str:
    """Env read — call only from inside an activity or store construction."""
    return os.environ.get("SDLC_BOARD_DB", DEFAULT_DB)


def connect(path: str | os.PathLike) -> sqlite3.Connection:
    """WAL so readers never block the writer; busy_timeout so a contended
    write waits rather than raising 'database is locked' immediately."""
    p = os.fspath(path)
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(p, isolation_level=None)  # explicit BEGIN control
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_board_schema.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/ tests/test_board_schema.py
git commit -m "feat(board): entities and idempotent SQLite schema"
```

---

### Task 2: BoardStore — artifact publish and version lineage

**Files:**
- Create: `src/sdlc/board/store.py`
- Modify: `src/sdlc/artifacts/store.py:19` (add board kinds to `_SUBDIRS`)
- Test: `tests/test_board_artifacts.py`

**Interfaces:**
- Consumes: Task 1's `apply_schema`, `connect`, `db_path`, `ArtifactStatus`, `BoardArtifact`, `ArtifactVersion`; `LocalFileStore.put` (`artifacts/store.py:43`) returning `ArtifactRef`.
- Produces:
  - `class BoardError(Exception)`, `NotFoundError(BoardError)`, `ConflictError(BoardError)`, `InvalidTransition(BoardError)`
  - `BoardStore(db: str | os.PathLike | None = None, blobs: LocalFileStore | None = None)`
  - `BoardStore.ensure_project(key: str, repo: str = "") -> None`
  - `BoardStore.publish_artifact_version(project, key, run_id, content: bytes, *, status: ArtifactStatus = ArtifactStatus.CURRENT, actor: str) -> tuple[ArtifactRef, int]` — returns `(ref, artifact_version.id)`
  - `BoardStore.get_artifact(project, key) -> BoardArtifact`
  - `BoardStore.list_versions(project, key) -> list[ArtifactVersion]`
  - `BoardStore.get_version(project, version_id) -> ArtifactVersion`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_artifacts.py
"""Artifact publish: version numbering, lineage, pointer movement."""

import json

import pytest

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board.models import ArtifactStatus
from sdlc.board.store import BoardStore, NotFoundError


@pytest.fixture
def store(tmp_path):
    s = BoardStore(db=tmp_path / "b.sqlite3", blobs=LocalFileStore(root=tmp_path / "runs"))
    s.ensure_project("proj", repo="git@example:acme/x")
    return s


def test_first_publish_is_v1_and_becomes_current(store):
    ref, vid = store.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"a"}', actor="workflow:run-1"
    )
    art = store.get_artifact("proj", "architecture")
    assert art.status is ArtifactStatus.CURRENT
    assert art.current_version == vid
    versions = store.list_versions("proj", "architecture")
    assert [v.n for v in versions] == [1]
    assert versions[0].supersedes is None
    assert ref.sha256 == versions[0].sha256


def test_blob_lands_in_claim_check_store_and_round_trips(store):
    body = b'{"overview":"a"}'
    ref, _ = store.publish_artifact_version(
        "proj", "architecture", "run-1", body, actor="workflow:run-1"
    )
    assert ref_to_path(ref).read_bytes() == body
    assert "artifacts" in ref.uri


def test_second_publish_supersedes_the_first(store):
    _, v1 = store.publish_artifact_version(
        "proj", "architecture", "run-1", b"1", actor="workflow:run-1"
    )
    _, v2 = store.publish_artifact_version(
        "proj", "architecture", "run-2", b"2", actor="workflow:run-2"
    )
    art = store.get_artifact("proj", "architecture")
    assert art.current_version == v2
    by_id = {v.id: v for v in store.list_versions("proj", "architecture")}
    assert by_id[v2].supersedes == v1
    assert by_id[v2].n == 2


def test_rejected_publish_records_version_but_does_not_move_pointer(store):
    _, v1 = store.publish_artifact_version(
        "proj", "architecture", "run-1", b"1", actor="workflow:run-1"
    )
    _, v2 = store.publish_artifact_version(
        "proj",
        "architecture",
        "run-2",
        b"bad",
        status=ArtifactStatus.REJECTED,
        actor="workflow:run-2",
    )
    art = store.get_artifact("proj", "architecture")
    assert art.current_version == v1, "rejected design must not become current"
    assert len(store.list_versions("proj", "architecture")) == 2
    assert store.get_version("proj", v2).n == 2


def test_publish_appends_exactly_one_event(store):
    store.publish_artifact_version("proj", "plan", "run-1", b"{}", actor="workflow:run-1")
    events = store.list_events("proj")
    assert len(events) == 1
    assert events[0].subject == "artifact:plan"
    assert events[0].actor == "workflow:run-1"
    assert events[0].to_status == "current"


def test_unknown_artifact_raises_not_found(store):
    with pytest.raises(NotFoundError):
        store.get_artifact("proj", "architecture")


def test_versions_are_independent_per_key(store):
    store.publish_artifact_version("proj", "plan", "r", b"1", actor="workflow:r")
    store.publish_artifact_version("proj", "architecture", "r", b"1", actor="workflow:r")
    assert store.list_versions("proj", "plan")[0].n == 1
    assert store.list_versions("proj", "architecture")[0].n == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_artifacts.py -v`
Expected: FAIL — `ImportError: cannot import name 'BoardStore'`

- [ ] **Step 3: Add board kinds to the claim-check subdir map**

Modify `src/sdlc/artifacts/store.py:19`:

```python
_SUBDIRS = {
    "harness_session": "sessions",
    "harness_session_digest": "sessions",
    "board_artifact": "artifacts",
    "board_evidence": "evidence",
}
```

- [ ] **Step 4: Write the store — connection, errors, project, artifacts**

```python
# src/sdlc/board/store.py
"""BoardStore: the single enforcement point for board state.

All SQL lives here. Both writers reach the board through this class — the
workflow via board/activities.py (in-process), agents via board/api.py — so
there is exactly one place that can move a status.

Blobs go to the claim-check store (immutable, sha256-addressed); this class
owns only the mutable graph. Ordering inside a publish is: write the blob,
then commit the row. A crash between the two leaves an orphan blob, which is
harmless because blobs are content-addressed and unreferenced.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from ..artifacts.store import LocalFileStore
from ..models import ArtifactRef
from .models import ArtifactStatus, ArtifactVersion, Authority, BoardArtifact, BoardEvent
from .schema import apply_schema, connect, db_path


class BoardError(Exception):
    """Base for board write rejections."""


class NotFoundError(BoardError):
    """No such project, artifact, version, or task."""


class ConflictError(BoardError):
    """Optimistic-concurrency failure: caller's row_version is stale."""


class InvalidTransition(BoardError):
    """The requested status move is not permitted by the state machine."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BoardStore:
    def __init__(
        self, db: str | os.PathLike | None = None, blobs: LocalFileStore | None = None
    ) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)
        self._blobs = blobs if blobs is not None else LocalFileStore()

    def close(self) -> None:
        self._conn.close()

    # ---- internals ---------------------------------------------------

    def _write(self):
        """Context manager for a serialized write transaction."""
        return _Tx(self._conn)

    def _event(
        self,
        project: str,
        subject: str,
        actor: str,
        authority: Authority,
        from_status: str | None,
        to_status: str | None,
        detail: str = "",
    ) -> None:
        self._conn.execute(
            "INSERT INTO event(project,subject,actor,authority,"
            "from_status,to_status,at,detail) VALUES (?,?,?,?,?,?,?,?)",
            (project, subject, actor, authority.value, from_status, to_status, _now(), detail),
        )

    # ---- project -----------------------------------------------------

    def ensure_project(self, key: str, repo: str = "") -> None:
        with self._write():
            self._conn.execute(
                "INSERT INTO project(key,repo,created_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO NOTHING",
                (key, repo, _now()),
            )

    # ---- artifacts ---------------------------------------------------

    def publish_artifact_version(
        self,
        project: str,
        key: str,
        run_id: str,
        content: bytes,
        *,
        status: ArtifactStatus = ArtifactStatus.CURRENT,
        actor: str,
    ) -> tuple[ArtifactRef, int]:
        """Append a version. CURRENT moves the pointer and supersedes the
        previous version; REJECTED records history and moves nothing."""
        with self._write():
            row = self._conn.execute(
                "SELECT COALESCE(MAX(n),0) FROM artifact_version WHERE project=? AND key=?",
                (project, key),
            ).fetchone()
            n = int(row[0]) + 1

            prev = self._conn.execute(
                "SELECT current_version FROM artifact WHERE project=? AND key=?", (project, key)
            ).fetchone()
            prev_current = prev["current_version"] if prev else None

            ref = self._blobs.put("board_artifact", run_id, f"{key}-v{n}.json", content)

            supersedes = prev_current if status is ArtifactStatus.CURRENT else None
            cur = self._conn.execute(
                "INSERT INTO artifact_version"
                "(project,key,n,run_id,sha256,uri,supersedes,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (project, key, n, run_id, ref.sha256, ref.uri, supersedes, _now()),
            )
            version_id = int(cur.lastrowid)

            if status is ArtifactStatus.CURRENT:
                # Lineage is already recorded: the new row was inserted with
                # supersedes=prev_current. The previous row needs no update —
                # "what superseded me" is derivable by querying forwards.
                self._conn.execute(
                    "INSERT INTO artifact(project,key,current_version,status)"
                    " VALUES (?,?,?,?) ON CONFLICT(project,key) DO UPDATE SET"
                    " current_version=excluded.current_version,"
                    " status=excluded.status",
                    (project, key, version_id, ArtifactStatus.CURRENT.value),
                )
            else:
                self._conn.execute(
                    "INSERT INTO artifact(project,key,current_version,status)"
                    " VALUES (?,?,?,?) ON CONFLICT(project,key) DO NOTHING",
                    (project, key, None, status.value),
                )

            self._event(
                project,
                f"artifact:{key}",
                actor,
                Authority.AUTHORITATIVE,
                None,
                status.value,
                detail=f"v{n} sha256={ref.sha256[:12]}",
            )
        return ref, version_id

    def get_artifact(self, project: str, key: str) -> BoardArtifact:
        row = self._conn.execute(
            "SELECT project,key,current_version,status FROM artifact WHERE project=? AND key=?",
            (project, key),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no artifact {key!r} in project {project!r}")
        return BoardArtifact(
            project=row["project"],
            key=row["key"],
            current_version=row["current_version"],
            status=ArtifactStatus(row["status"]),
        )

    def list_versions(self, project: str, key: str) -> list[ArtifactVersion]:
        rows = self._conn.execute(
            "SELECT * FROM artifact_version WHERE project=? AND key=? ORDER BY n", (project, key)
        ).fetchall()
        return [ArtifactVersion(**dict(r)) for r in rows]

    def get_version(self, project: str, version_id: int) -> ArtifactVersion:
        row = self._conn.execute(
            "SELECT * FROM artifact_version WHERE project=? AND id=?", (project, version_id)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no version {version_id} in {project!r}")
        return ArtifactVersion(**dict(row))

    # ---- events ------------------------------------------------------

    def list_events(
        self, project: str, since: int = 0, subject: str | None = None
    ) -> list[BoardEvent]:
        sql = "SELECT * FROM event WHERE project=? AND id>?"
        args: list = [project, since]
        if subject is not None:
            sql += " AND subject=?"
            args.append(subject)
        rows = self._conn.execute(sql + " ORDER BY id", args).fetchall()
        return [BoardEvent(**dict(r)) for r in rows]


class _Tx:
    """BEGIN IMMEDIATE ... COMMIT / ROLLBACK. Taking the write lock up front
    is what makes two concurrent claims serialize instead of interleaving."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self):
        self._conn.execute("BEGIN IMMEDIATE")
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.execute("COMMIT")
        else:
            self._conn.execute("ROLLBACK")
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_board_artifacts.py tests/test_artifact_store.py -v`
Expected: all passed (the existing `test_artifact_store.py` must still pass — `_SUBDIRS` gained keys, changed none)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/store.py src/sdlc/artifacts/store.py tests/test_board_artifacts.py
git commit -m "feat(board): artifact publish with version lineage and pointer"
```

---

### Task 3: BoardStore — task lifecycle, state machine, optimistic concurrency

**Files:**
- Modify: `src/sdlc/board/store.py` (append task methods)
- Create: `src/sdlc/board/transitions.py`
- Test: `tests/test_board_tasks.py`

**Interfaces:**
- Consumes: Task 2's `BoardStore`, `_Tx`, `_now`, `_event`, `ConflictError`, `InvalidTransition`, `NotFoundError`; Task 1's `TaskStatus`, `Authority`, `BoardTask`; `DevTask` (`sdlc.models:294`).
- Produces:
  - `transitions.TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]]`
  - `transitions.check_task_transition(frm: TaskStatus, to: TaskStatus) -> None` (raises `InvalidTransition`)
  - `BoardStore.sync_plan_tasks(project, plan_version: int, run_id: str, tasks: list[DevTask], *, actor: str) -> int`
  - `BoardStore.get_task(project, plan_version, task_id) -> BoardTask`
  - `BoardStore.list_tasks(project, plan_version, *, status: TaskStatus | None = None, run_id: str | None = None) -> list[BoardTask]`
  - `BoardStore.set_task_authoritative(project, plan_version, task_id, status: TaskStatus, *, actor: str, fix_attempts: int | None = None, error: str | None = None, branch: str | None = None) -> BoardTask`
  - `BoardStore.set_task_observational(project, plan_version, task_id, status: TaskStatus, *, actor: str, expect_row_version: int, detail: str = "") -> BoardTask`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_tasks.py
"""Task lifecycle: state machine, the two-status split, optimistic locking."""

import threading

import pytest

from sdlc.artifacts.store import LocalFileStore
from sdlc.board.models import TaskStatus
from sdlc.board.store import BoardStore, ConflictError, InvalidTransition, NotFoundError
from sdlc.models import DevTask


def _tasks() -> list[DevTask]:
    return [
        DevTask(id="T01", title="config", description="d", acceptance_criteria=["a"]),
        DevTask(
            id="T02", title="api", description="d", acceptance_criteria=["a"], depends_on=["T01"]
        ),
    ]


@pytest.fixture
def store(tmp_path):
    s = BoardStore(db=tmp_path / "b.sqlite3", blobs=LocalFileStore(root=tmp_path / "runs"))
    s.ensure_project("proj")
    return s


@pytest.fixture
def plan_v(store):
    _, vid = store.publish_artifact_version("proj", "plan", "run-1", b"{}", actor="workflow:run-1")
    store.sync_plan_tasks("proj", vid, "run-1", _tasks(), actor="workflow:run-1")
    return vid


def test_sync_creates_pending_tasks(store, plan_v):
    tasks = store.list_tasks("proj", plan_v)
    assert [t.task_id for t in tasks] == ["T01", "T02"]
    assert all(t.status is TaskStatus.PENDING for t in tasks)
    assert all(t.authoritative_status is TaskStatus.PENDING for t in tasks)
    assert all(t.row_version == 1 for t in tasks)


def test_sync_is_idempotent(store, plan_v):
    n = store.sync_plan_tasks("proj", plan_v, "run-1", _tasks(), actor="workflow:run-1")
    assert n == 0, "re-syncing the same plan must insert nothing"
    assert len(store.list_tasks("proj", plan_v)) == 2


def test_workflow_write_moves_both_statuses(store, plan_v):
    t = store.set_task_authoritative(
        "proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:run-1"
    )
    assert t.status is TaskStatus.IN_PROGRESS
    assert t.authoritative_status is TaskStatus.IN_PROGRESS
    assert t.row_version == 2


def test_agent_write_does_not_move_authoritative_status(store, plan_v):
    before = store.get_task("proj", plan_v, "T01")
    t = store.set_task_observational(
        "proj",
        plan_v,
        "T01",
        TaskStatus.IN_PROGRESS,
        actor="agent:worker-a",
        expect_row_version=before.row_version,
    )
    assert t.status is TaskStatus.IN_PROGRESS
    assert t.authoritative_status is TaskStatus.PENDING
    assert t.diverged is True


def test_stale_row_version_is_a_conflict(store, plan_v):
    before = store.get_task("proj", plan_v, "T01")
    store.set_task_observational(
        "proj",
        plan_v,
        "T01",
        TaskStatus.IN_PROGRESS,
        actor="agent:a",
        expect_row_version=before.row_version,
    )
    with pytest.raises(ConflictError):
        store.set_task_observational(
            "proj",
            plan_v,
            "T01",
            TaskStatus.BLOCKED,
            actor="agent:b",
            expect_row_version=before.row_version,
        )


def test_invalid_transition_is_rejected(store, plan_v):
    with pytest.raises(InvalidTransition):
        store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:run-1")


def test_done_is_terminal(store, plan_v):
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")
    with pytest.raises(InvalidTransition):
        store.set_task_authoritative(
            "proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r"
        )


def test_rejected_write_appends_no_event(store, plan_v):
    before = len(store.list_events("proj"))
    with pytest.raises(InvalidTransition):
        store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")
    assert len(store.list_events("proj")) == before, "the change log records real changes only"


def test_authoritative_validates_against_authoritative_status(store, plan_v):
    """An agent moving `status` must not unlock a workflow transition."""
    before = store.get_task("proj", plan_v, "T01")
    store.set_task_observational(
        "proj",
        plan_v,
        "T01",
        TaskStatus.IN_PROGRESS,
        actor="agent:a",
        expect_row_version=before.row_version,
    )
    with pytest.raises(InvalidTransition):
        # authoritative_status is still PENDING, so PENDING -> DONE is invalid
        store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.DONE, actor="workflow:r")


def test_fix_attempts_and_error_are_recorded(store, plan_v):
    store.set_task_authoritative("proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    t = store.set_task_authoritative(
        "proj",
        plan_v,
        "T01",
        TaskStatus.FAILED,
        actor="workflow:r",
        fix_attempts=2,
        error="build failed",
        branch="task/T01",
    )
    assert (t.fix_attempts, t.error, t.branch) == (2, "build failed", "task/T01")


def test_unknown_task_raises_not_found(store, plan_v):
    with pytest.raises(NotFoundError):
        store.get_task("proj", plan_v, "T99")


def test_two_threads_claiming_one_task_yield_one_winner(tmp_path):
    """The race the whole design exists to make safe."""
    db = tmp_path / "b.sqlite3"
    setup = BoardStore(db=db, blobs=LocalFileStore(root=tmp_path / "runs"))
    setup.ensure_project("proj")
    _, vid = setup.publish_artifact_version("proj", "plan", "r", b"{}", actor="workflow:r")
    setup.sync_plan_tasks("proj", vid, "r", _tasks(), actor="workflow:r")
    rv = setup.get_task("proj", vid, "T01").row_version

    results: list[str] = []
    lock = threading.Lock()

    def claim(name: str) -> None:
        s = BoardStore(db=db, blobs=LocalFileStore(root=tmp_path / "runs"))
        try:
            s.set_task_observational(
                "proj",
                vid,
                "T01",
                TaskStatus.IN_PROGRESS,
                actor=f"agent:{name}",
                expect_row_version=rv,
            )
            with lock:
                results.append("won")
        except ConflictError:
            with lock:
                results.append("conflict")
        finally:
            s.close()

    threads = [threading.Thread(target=claim, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["conflict", "won"], f"exactly one claim must win, got {results}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_tasks.py -v`
Expected: FAIL — `AttributeError: 'BoardStore' object has no attribute 'sync_plan_tasks'`

- [ ] **Step 3: Write the state machine**

```python
# src/sdlc/board/transitions.py
"""Task state machine. One table, one checker — both writers use it, so an
agent and the workflow cannot disagree about what a legal move is.

DONE is terminal within a plan version: the in-run fix loop happens while a
task is IN_PROGRESS (feature.py's _dev_task retries before returning), so a
completed task reopening means a new plan, hence a new plan_version.
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
    TaskStatus.FAILED: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.QUARANTINED: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.DONE: frozenset(),
}


def check_task_transition(frm: TaskStatus, to: TaskStatus) -> None:
    from .store import InvalidTransition  # local: avoids import cycle

    if to not in TASK_TRANSITIONS[frm]:
        raise InvalidTransition(f"{frm.value} -> {to.value} is not a permitted task transition")
```

- [ ] **Step 4: Append the task methods to `BoardStore`**

Add these imports at the top of `src/sdlc/board/store.py`:

```python
from ..models import DevTask
from .models import BoardTask, TaskStatus
from .transitions import check_task_transition
```

Append inside `class BoardStore`:

```python
# ---- tasks -------------------------------------------------------


def sync_plan_tasks(
    self, project: str, plan_version: int, run_id: str, tasks: list[DevTask], *, actor: str
) -> int:
    """Insert one PENDING row per DevTask. Idempotent — re-running a
    workflow (Temporal retry, replay) must not duplicate or reset rows.
    Returns the number of rows actually inserted."""
    inserted = 0
    with self._write():
        for t in tasks:
            cur = self._conn.execute(
                "INSERT INTO task(project,plan_version,task_id,run_id,"
                "status,authoritative_status,row_version,fix_attempts,"
                "error,branch,updated_at) "
                "VALUES (?,?,?,?,?,?,1,0,NULL,NULL,?) "
                "ON CONFLICT(project,plan_version,task_id) DO NOTHING",
                (
                    project,
                    plan_version,
                    t.id,
                    run_id,
                    TaskStatus.PENDING.value,
                    TaskStatus.PENDING.value,
                    _now(),
                ),
            )
            if cur.rowcount:
                inserted += 1
                self._event(
                    project,
                    f"task:{plan_version}:{t.id}",
                    actor,
                    Authority.AUTHORITATIVE,
                    None,
                    TaskStatus.PENDING.value,
                    detail=t.title,
                )
    return inserted


def get_task(self, project: str, plan_version: int, task_id: str) -> BoardTask:
    row = self._conn.execute(
        "SELECT * FROM task WHERE project=? AND plan_version=? AND task_id=?",
        (project, plan_version, task_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"no task {task_id!r} in plan {plan_version} of {project!r}")
    return BoardTask(**dict(row))


def list_tasks(
    self,
    project: str,
    plan_version: int,
    *,
    status: TaskStatus | None = None,
    run_id: str | None = None,
) -> list[BoardTask]:
    sql = "SELECT * FROM task WHERE project=? AND plan_version=?"
    args: list = [project, plan_version]
    if status is not None:
        sql += " AND status=?"
        args.append(status.value)
    if run_id is not None:
        sql += " AND run_id=?"
        args.append(run_id)
    rows = self._conn.execute(sql + " ORDER BY task_id", args).fetchall()
    return [BoardTask(**dict(r)) for r in rows]


def set_task_authoritative(
    self,
    project: str,
    plan_version: int,
    task_id: str,
    status: TaskStatus,
    *,
    actor: str,
    fix_attempts: int | None = None,
    error: str | None = None,
    branch: str | None = None,
) -> BoardTask:
    """Workflow write. Validates against authoritative_status — an agent
    having moved `status` must never unlock a workflow transition."""
    with self._write():
        task = self.get_task(project, plan_version, task_id)
        check_task_transition(task.authoritative_status, status)
        self._conn.execute(
            "UPDATE task SET status=?, authoritative_status=?,"
            " row_version=row_version+1,"
            " fix_attempts=COALESCE(?,fix_attempts),"
            " error=COALESCE(?,error), branch=COALESCE(?,branch),"
            " updated_at=? "
            "WHERE project=? AND plan_version=? AND task_id=?",
            (
                status.value,
                status.value,
                fix_attempts,
                error,
                branch,
                _now(),
                project,
                plan_version,
                task_id,
            ),
        )
        self._event(
            project,
            f"task:{plan_version}:{task_id}",
            actor,
            Authority.AUTHORITATIVE,
            task.authoritative_status.value,
            status.value,
        )
    return self.get_task(project, plan_version, task_id)


def set_task_observational(
    self,
    project: str,
    plan_version: int,
    task_id: str,
    status: TaskStatus,
    *,
    actor: str,
    expect_row_version: int,
    detail: str = "",
) -> BoardTask:
    """Agent write. Moves the live view only; authoritative_status is
    untouched, so scoring and replay are unaffected by an agent that
    crashes mid-claim or reports optimistically."""
    with self._write():
        task = self.get_task(project, plan_version, task_id)
        if task.row_version != expect_row_version:
            raise ConflictError(
                f"row_version {expect_row_version} is stale; current is {task.row_version}"
            )
        check_task_transition(task.status, status)
        self._conn.execute(
            "UPDATE task SET status=?, row_version=row_version+1,"
            " updated_at=? "
            "WHERE project=? AND plan_version=? AND task_id=?",
            (status.value, _now(), project, plan_version, task_id),
        )
        self._event(
            project,
            f"task:{plan_version}:{task_id}",
            actor,
            Authority.OBSERVATIONAL,
            task.status.value,
            status.value,
            detail=detail,
        )
    return self.get_task(project, plan_version, task_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_board_tasks.py -v`
Expected: 12 passed

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/transitions.py src/sdlc/board/store.py tests/test_board_tasks.py
git commit -m "feat(board): task lifecycle with state machine and optimistic locking"
```

---

### Task 4: BoardStore — task evidence and stats

**Files:**
- Modify: `src/sdlc/board/store.py` (append evidence + stats methods)
- Test: `tests/test_board_stats.py`

**Interfaces:**
- Consumes: Task 3's `BoardStore` task methods; Task 1's `TaskEvidence`, `BoardStats`.
- Produces:
  - `BoardStore.attach_task_evidence(project, plan_version, task_id, run_id, kind: str, content: bytes) -> ArtifactRef`
  - `BoardStore.list_evidence(project, plan_version, task_id) -> list[TaskEvidence]`
  - `BoardStore.stats(project) -> BoardStats`
  - `EVIDENCE_KINDS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_stats.py
"""Evidence attachment and board-owned counters."""

import pytest

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board.models import TaskStatus
from sdlc.board.store import BoardStore
from sdlc.models import DevTask


@pytest.fixture
def seeded(tmp_path):
    s = BoardStore(db=tmp_path / "b.sqlite3", blobs=LocalFileStore(root=tmp_path / "runs"))
    s.ensure_project("proj")
    _, vid = s.publish_artifact_version("proj", "plan", "run-1", b"{}", actor="workflow:run-1")
    s.sync_plan_tasks(
        "proj",
        vid,
        "run-1",
        [
            DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"]),
            DevTask(id="T02", title="b", description="d", acceptance_criteria=["x"]),
        ],
        actor="workflow:run-1",
    )
    return s, vid


def test_evidence_round_trips(seeded):
    store, vid = seeded
    ref = store.attach_task_evidence("proj", vid, "T01", "run-1", "qa", b'{"passed":true}')
    assert ref_to_path(ref).read_bytes() == b'{"passed":true}'
    ev = store.list_evidence("proj", vid, "T01")
    assert len(ev) == 1
    assert ev[0].kind == "qa"
    assert ev[0].sha256 == ref.sha256


def test_unknown_evidence_kind_is_rejected(seeded):
    store, vid = seeded
    with pytest.raises(ValueError):
        store.attach_task_evidence("proj", vid, "T01", "run-1", "vibes", b"{}")


def test_stats_count_by_authoritative_status_only(seeded):
    store, vid = seeded
    before = store.get_task("proj", vid, "T01")
    store.set_task_observational(
        "proj",
        vid,
        "T01",
        TaskStatus.IN_PROGRESS,
        actor="agent:a",
        expect_row_version=before.row_version,
    )
    s = store.stats("proj")
    assert s.tasks_by_status["pending"] == 2, (
        "an agent's observational write must not change the counted status"
    )
    assert s.diverged_tasks == 1


def test_stats_aggregate_fix_attempts_and_errors(seeded):
    store, vid = seeded
    store.set_task_authoritative("proj", vid, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    store.set_task_authoritative(
        "proj", vid, "T01", TaskStatus.FAILED, actor="workflow:r", fix_attempts=3, error="boom"
    )
    s = store.stats("proj")
    assert s.total_fix_attempts == 3
    assert s.tasks_with_error == 1
    assert s.tasks_by_status == {"failed": 1, "pending": 1}


def test_stats_counts_events(seeded):
    store, vid = seeded
    s = store.stats("proj")
    # 1 artifact publish + 2 task creations
    assert s.event_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_stats.py -v`
Expected: FAIL — `AttributeError: 'BoardStore' object has no attribute 'attach_task_evidence'`

- [ ] **Step 3: Append evidence and stats methods**

Add to the imports in `src/sdlc/board/store.py`:

```python
from .models import BoardStats, TaskEvidence
```

Add near the top of the module, after `_now`:

```python
EVIDENCE_KINDS = frozenset({"qa", "review", "deep_review"})
```

Append inside `class BoardStore`:

```python
# ---- evidence ----------------------------------------------------


def attach_task_evidence(
    self, project: str, plan_version: int, task_id: str, run_id: str, kind: str, content: bytes
) -> ArtifactRef:
    """Per-run, immutable observation about one attempt. Unlike project
    artifacts these are never versioned and never move a pointer."""
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"evidence kind {kind!r} not in {sorted(EVIDENCE_KINDS)}")
    self.get_task(project, plan_version, task_id)  # 404 if absent
    ref = self._blobs.put("board_evidence", run_id, f"{task_id}-{kind}.json", content)
    with self._write():
        self._conn.execute(
            "INSERT INTO task_evidence(project,plan_version,task_id,"
            "run_id,kind,sha256,uri,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (project, plan_version, task_id, run_id, kind, ref.sha256, ref.uri, _now()),
        )
    return ref


def list_evidence(self, project: str, plan_version: int, task_id: str) -> list[TaskEvidence]:
    rows = self._conn.execute(
        "SELECT * FROM task_evidence WHERE project=? AND plan_version=? AND task_id=? ORDER BY id",
        (project, plan_version, task_id),
    ).fetchall()
    return [TaskEvidence(**dict(r)) for r in rows]


# ---- stats -------------------------------------------------------


def stats(self, project: str) -> BoardStats:
    """Board-owned counters only. Counted status is authoritative_status:
    an agent's optimistic write must never move a number that scoring
    or a human reads as truth."""
    by_status = {
        r["authoritative_status"]: r["n"]
        for r in self._conn.execute(
            "SELECT authoritative_status, COUNT(*) AS n FROM task "
            "WHERE project=? GROUP BY authoritative_status",
            (project,),
        ).fetchall()
    }
    agg = self._conn.execute(
        "SELECT COALESCE(SUM(fix_attempts),0) AS fixes,"
        " COALESCE(SUM(error IS NOT NULL),0) AS errs,"
        " COALESCE(SUM(status<>authoritative_status),0) AS diverged"
        " FROM task WHERE project=?",
        (project,),
    ).fetchone()
    events = self._conn.execute(
        "SELECT COUNT(*) FROM event WHERE project=?", (project,)
    ).fetchone()[0]
    return BoardStats(
        project=project,
        tasks_by_status=by_status,
        total_fix_attempts=int(agg["fixes"]),
        tasks_with_error=int(agg["errs"]),
        diverged_tasks=int(agg["diverged"]),
        event_count=int(events),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_board_stats.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/board/store.py tests/test_board_stats.py
git commit -m "feat(board): task evidence and board-owned stats"
```

---

### Task 5: `project_key` on PipelineConfig

**Files:**
- Modify: `src/sdlc/models.py` (add field to `PipelineConfig`, class starts at line 925)
- Test: `tests/test_board_project_key.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `PipelineConfig.project_key: str` (default `"default"`), read by Task 8's workflow wiring.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_project_key.py
"""Board identity is its own field — not borrowed from the memory bank."""

from sdlc.models import PipelineConfig


def test_project_key_defaults_to_default():
    assert PipelineConfig().project_key == "default"


def test_project_key_is_settable():
    assert PipelineConfig(project_key="kroker").project_key == "kroker"


def test_project_key_is_distinct_from_memory_project_bank():
    """MemoryConfig.project_bank addresses Hindsight; project_key addresses
    the board. Sharing one identifier across two stores by accident is the
    bug this test exists to prevent."""
    cfg = PipelineConfig(project_key="kroker")
    assert cfg.project_key != cfg.memory.project_bank
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_project_key.py -v`
Expected: FAIL — `AttributeError: 'PipelineConfig' object has no attribute 'project_key'`

- [ ] **Step 3: Add the field**

In `src/sdlc/models.py`, inside `class PipelineConfig` (starts line 925), add:

```python
    # Board identity (E-40). Deliberately NOT MemoryConfig.project_bank:
    # that addresses Hindsight, this addresses the board SQLite. Two stores,
    # two identifiers — sharing one by accident couples unrelated lifetimes.
    project_key: str = "default"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_board_project_key.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full fast suite for regressions**

Run: `pytest -q`
Expected: no new failures (`PipelineConfig` is widely constructed; a defaulted field must not break anything)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_board_project_key.py
git commit -m "feat(board): project_key on PipelineConfig"
```

---

### Task 6: Temporal activities and worker registration

**Files:**
- Create: `src/sdlc/board/activities.py`
- Modify: `src/sdlc/worker.py` (import + `activities=[...]` list, line ~91)
- Test: `tests/test_board_activities.py`

**Interfaces:**
- Consumes: Tasks 2–4's `BoardStore` methods; `ArtifactRef` (`sdlc.models:74`).
- Produces (all `@activity.defn`, each taking one Pydantic input model):
  - `PublishArtifactInput`/`PublishArtifactResult` + `publish_artifact_version`
  - `SyncPlanTasksInput` + `sync_plan_tasks`
  - `SetTaskStatusInput` + `set_task_authoritative`
  - `AttachEvidenceInput` + `attach_task_evidence`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_activities.py
"""Board activities: Temporal markers, worker registration, behaviour."""

import inspect

import pytest

from sdlc.board.activities import (
    AttachEvidenceInput,
    PublishArtifactInput,
    SetTaskStatusInput,
    SyncPlanTasksInput,
    attach_task_evidence,
    publish_artifact_version,
    set_task_authoritative,
    sync_plan_tasks,
)
from sdlc.board.models import TaskStatus
from sdlc.models import DevTask

ACTIVITIES = [
    publish_artifact_version,
    sync_plan_tasks,
    set_task_authoritative,
    attach_task_evidence,
]


@pytest.mark.parametrize("fn", ACTIVITIES, ids=lambda f: f.__name__)
def test_is_a_temporal_activity(fn):
    assert getattr(fn, "__temporal_activity_definition", None) is not None


@pytest.mark.parametrize("name", [f.__name__ for f in ACTIVITIES])
def test_registered_on_the_worker(name):
    from sdlc import worker

    assert name in inspect.getsource(worker), f"{name} missing from worker registration"


@pytest.fixture
def board_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "b.sqlite3"))
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "runs"))


@pytest.mark.asyncio
async def test_publish_then_sync_then_transition(board_env):
    pub = await publish_artifact_version(
        PublishArtifactInput(
            project="proj",
            key="plan",
            run_id="run-1",
            content_json='{"tasks":[]}',
            actor="workflow:run-1",
        )
    )
    assert pub.version_id > 0
    assert pub.ref.sha256

    n = await sync_plan_tasks(
        SyncPlanTasksInput(
            project="proj",
            plan_version=pub.version_id,
            run_id="run-1",
            tasks=[DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"])],
            actor="workflow:run-1",
        )
    )
    assert n == 1

    await set_task_authoritative(
        SetTaskStatusInput(
            project="proj",
            plan_version=pub.version_id,
            task_id="T01",
            status=TaskStatus.IN_PROGRESS,
            actor="workflow:run-1",
        )
    )

    ref = await attach_task_evidence(
        AttachEvidenceInput(
            project="proj",
            plan_version=pub.version_id,
            task_id="T01",
            run_id="run-1",
            kind="qa",
            content_json='{"passed":true}',
        )
    )
    assert ref.kind == "board_evidence"


@pytest.mark.asyncio
async def test_activities_are_idempotent_under_retry(board_env):
    """Temporal retries activities; a second execution must not duplicate."""
    pub = await publish_artifact_version(
        PublishArtifactInput(
            project="proj", key="plan", run_id="run-1", content_json="{}", actor="workflow:run-1"
        )
    )
    inp = SyncPlanTasksInput(
        project="proj",
        plan_version=pub.version_id,
        run_id="run-1",
        tasks=[DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"])],
        actor="workflow:run-1",
    )
    assert await sync_plan_tasks(inp) == 1
    assert await sync_plan_tasks(inp) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_activities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.board.activities'`

- [ ] **Step 3: Write the activities**

```python
# src/sdlc/board/activities.py
"""Temporal activity wrappers over BoardStore (RecordStore idiom,
benchmarks/recorder.py:83). All filesystem and env reads happen here — never
in workflow code.

These are NOT best-effort. capture_session (artifacts/capture.py:29) swallows
storage failures because losing a transcript must not block delivery; the
board is different — agents read tasks from it, so a permanently failed write
must surface. Temporal's RetryPolicy absorbs transient failures; the store's
writes are idempotent so a retry is safe.
"""

from __future__ import annotations

from pydantic import BaseModel
from temporalio import activity

from ..models import ArtifactRef, DevTask
from .models import ArtifactStatus, TaskStatus
from .store import BoardStore


class PublishArtifactInput(BaseModel):
    project: str
    key: str  # requirements | architecture | plan
    run_id: str
    content_json: str
    actor: str
    status: ArtifactStatus = ArtifactStatus.CURRENT
    repo: str = ""


class PublishArtifactResult(BaseModel):
    ref: ArtifactRef
    version_id: int


class SyncPlanTasksInput(BaseModel):
    project: str
    plan_version: int
    run_id: str
    tasks: list[DevTask]
    actor: str


class SetTaskStatusInput(BaseModel):
    project: str
    plan_version: int
    task_id: str
    status: TaskStatus
    actor: str
    fix_attempts: int | None = None
    error: str | None = None
    branch: str | None = None


class AttachEvidenceInput(BaseModel):
    project: str
    plan_version: int
    task_id: str
    run_id: str
    kind: str  # qa | review | deep_review
    content_json: str


@activity.defn
async def publish_artifact_version(inp: PublishArtifactInput) -> PublishArtifactResult:
    store = BoardStore()
    try:
        store.ensure_project(inp.project, inp.repo)
        ref, version_id = store.publish_artifact_version(
            inp.project,
            inp.key,
            inp.run_id,
            inp.content_json.encode("utf-8"),
            status=inp.status,
            actor=inp.actor,
        )
        return PublishArtifactResult(ref=ref, version_id=version_id)
    finally:
        store.close()


@activity.defn
async def sync_plan_tasks(inp: SyncPlanTasksInput) -> int:
    store = BoardStore()
    try:
        return store.sync_plan_tasks(
            inp.project, inp.plan_version, inp.run_id, inp.tasks, actor=inp.actor
        )
    finally:
        store.close()


@activity.defn
async def set_task_authoritative(inp: SetTaskStatusInput) -> None:
    store = BoardStore()
    try:
        store.set_task_authoritative(
            inp.project,
            inp.plan_version,
            inp.task_id,
            inp.status,
            actor=inp.actor,
            fix_attempts=inp.fix_attempts,
            error=inp.error,
            branch=inp.branch,
        )
    finally:
        store.close()


@activity.defn
async def attach_task_evidence(inp: AttachEvidenceInput) -> ArtifactRef:
    store = BoardStore()
    try:
        return store.attach_task_evidence(
            inp.project,
            inp.plan_version,
            inp.task_id,
            inp.run_id,
            inp.kind,
            inp.content_json.encode("utf-8"),
        )
    finally:
        store.close()
```

- [ ] **Step 4: Register on the worker**

In `src/sdlc/worker.py`, add the import beside the other module imports (near line 36's `from .artifacts.read import load_session`):

```python
from .board.activities import (
    attach_task_evidence,
    publish_artifact_version,
    set_task_authoritative,
    sync_plan_tasks,
)
```

And add to the `activities=[...]` list (near line 105, beside `load_session`):

```python
(
    publish_artifact_version,
    sync_plan_tasks,
)
(
    set_task_authoritative,
    attach_task_evidence,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_board_activities.py tests/test_worker_registration.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/activities.py src/sdlc/worker.py tests/test_board_activities.py
git commit -m "feat(board): temporal activities and worker registration"
```

---

### Task 7: FastAPI read API

**Files:**
- Create: `src/sdlc/board/api.py`
- Create: `interfaces/dashboard/api/main.py`
- Modify: `pyproject.toml` (add `fastapi`, `uvicorn`)
- Test: `tests/test_board_api_reads.py`

**Interfaces:**
- Consumes: Tasks 2–4's `BoardStore` read methods; `NotFoundError`.
- Produces: `create_app(store_factory: Callable[[], BoardStore] | None = None) -> FastAPI`; `app` module-level instance; `MAX_CONTENT_BYTES: int`.

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add to `[project] dependencies`:

```toml
    "fastapi>=0.115",
    "uvicorn>=0.30",
```

Run: `uv sync` (or `pip install -e .`)

`httpx` is already a dependency, so FastAPI's `TestClient` needs nothing further.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_board_api_reads.py
"""Board read API: shapes, filters, content resolution, error codes."""

import pytest
from fastapi.testclient import TestClient

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board.api import create_app
from sdlc.board.models import TaskStatus
from sdlc.board.store import BoardStore
from sdlc.models import DevTask


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "b.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("proj", repo="git@example:acme/x")
    _, vid = seed.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"first"}', actor="workflow:run-1"
    )
    _, plan_v = seed.publish_artifact_version(
        "proj", "plan", "run-1", b'{"tasks":[]}', actor="workflow:run-1"
    )
    seed.sync_plan_tasks(
        "proj",
        plan_v,
        "run-1",
        [
            DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"]),
            DevTask(id="T02", title="b", description="d", acceptance_criteria=["x"]),
        ],
        actor="workflow:run-1",
    )
    seed.set_task_authoritative("proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    seed.attach_task_evidence("proj", plan_v, "T01", "run-1", "qa", b"{}")
    seed.close()

    app = create_app(lambda: BoardStore(db=db, blobs=blobs))
    c = TestClient(app)
    c.plan_v = plan_v
    c.arch_v = vid
    return c


def test_list_projects(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert [p["key"] for p in r.json()] == ["proj"]


def test_project_detail_lists_artifacts_and_task_rollup(client):
    body = client.get("/projects/proj").json()
    assert {a["key"] for a in body["artifacts"]} == {"architecture", "plan"}
    assert body["stats"]["tasks_by_status"] == {"in_progress": 1, "pending": 1}


def test_artifact_versions_carry_lineage(client):
    body = client.get("/projects/proj/artifacts/architecture").json()
    assert [v["n"] for v in body] == [1]
    assert body[0]["supersedes"] is None


def test_version_content_is_returned(client):
    r = client.get(f"/projects/proj/artifacts/architecture/versions/{client.arch_v}")
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == '{"overview":"first"}'
    assert body["truncated"] is False
    assert body["sha256"]


def test_tasks_default_to_current_plan_version(client):
    body = client.get("/projects/proj/tasks").json()
    assert {t["task_id"] for t in body} == {"T01", "T02"}


def test_tasks_filter_by_status(client):
    body = client.get("/projects/proj/tasks?status=in_progress").json()
    assert [t["task_id"] for t in body] == ["T01"]


def test_task_detail_includes_evidence(client):
    body = client.get("/projects/proj/tasks/T01").json()
    assert body["task"]["task_id"] == "T01"
    assert [e["kind"] for e in body["evidence"]] == ["qa"]


def test_events_are_the_change_log(client):
    body = client.get("/projects/proj/events").json()
    subjects = [e["subject"] for e in body]
    assert "artifact:architecture" in subjects
    assert f"task:{client.plan_v}:T01" in subjects


def test_events_since_filters(client):
    everything = client.get("/projects/proj/events").json()
    tail = client.get(f"/projects/proj/events?since={everything[0]['id']}").json()
    assert len(tail) == len(everything) - 1


def test_unknown_project_is_404(client):
    assert client.get("/projects/nope").status_code == 404


def test_unknown_artifact_is_404(client):
    assert client.get("/projects/proj/artifacts/requirements").status_code == 404


def test_missing_blob_is_410(client):
    from types import SimpleNamespace

    v = client.get("/projects/proj/artifacts/architecture").json()[0]
    ref_to_path(SimpleNamespace(uri=v["uri"])).unlink()
    r = client.get(f"/projects/proj/artifacts/architecture/versions/{v['id']}")
    assert r.status_code == 410
    assert r.json()["detail"]["sha256"] == v["sha256"]


def test_content_over_cap_is_truncated(tmp_path):
    from sdlc.board import api as api_mod

    db = tmp_path / "b2.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs2")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("p")
    _, vid = seed.publish_artifact_version(
        "p", "plan", "r", b"x" * (api_mod.MAX_CONTENT_BYTES + 10), actor="workflow:r"
    )
    seed.close()
    c = TestClient(create_app(lambda: BoardStore(db=db, blobs=blobs)))
    body = c.get(f"/projects/p/artifacts/plan/versions/{vid}").json()
    assert body["truncated"] is True
    assert len(body["content"]) == api_mod.MAX_CONTENT_BYTES
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_board_api_reads.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.board.api'`

- [ ] **Step 4: Write the read API**

```python
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

from typing import Callable

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from ..artifacts.store import ref_to_path
from .models import (
    ArtifactVersion,
    BoardArtifact,
    BoardEvent,
    BoardStats,
    BoardTask,
    TaskEvidence,
    TaskStatus,
)
from .store import BoardStore, NotFoundError

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


def create_app(store_factory: Callable[[], BoardStore] | None = None) -> FastAPI:
    factory = store_factory or BoardStore
    app = FastAPI(title="SDLC Agent Board", version="1.0")

    def get_store() -> BoardStore:
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

    def _require_project(store: BoardStore, project: str) -> dict:
        row = store._conn.execute(
            "SELECT key, repo FROM project WHERE key=?", (project,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"no project {project!r}")
        return {"key": row["key"], "repo": row["repo"]}

    app.state.require_project = _require_project
    app.state.current_plan_version = _current_plan_version
    app.state.get_store = get_store

    @app.get("/projects", response_model=list[ProjectSummary])
    def list_projects(store: BoardStore = Depends(get_store)):
        rows = store._conn.execute("SELECT key, repo FROM project ORDER BY key").fetchall()
        return [ProjectSummary(key=r["key"], repo=r["repo"]) for r in rows]

    @app.get("/projects/{project}", response_model=ProjectDetail)
    def get_project(project: str, store: BoardStore = Depends(get_store)):
        meta = _require_project(store, project)
        rows = store._conn.execute(
            "SELECT project,key,current_version,status FROM artifact WHERE project=? ORDER BY key",
            (project,),
        ).fetchall()
        return ProjectDetail(
            key=meta["key"],
            repo=meta["repo"],
            artifacts=[BoardArtifact(**dict(r)) for r in rows],
            stats=store.stats(project),
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
        path = ref_to_path(v)
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

    return app


app = create_app()
```

Note `ref_to_path` takes anything with a `.uri` attribute; `ArtifactVersion` has one, so it works directly.

- [ ] **Step 5: Write the uvicorn entrypoint**

```python
# interfaces/dashboard/api/main.py
"""uvicorn entrypoint. All logic is in sdlc.board.api — this file exists so
the service can be started without the package layout mattering.

    uvicorn interfaces.dashboard.api.main:app --port 8500
"""

from sdlc.board.api import app

__all__ = ["app"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_board_api_reads.py -v`
Expected: 13 passed

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/board/api.py interfaces/dashboard/api/main.py pyproject.toml tests/test_board_api_reads.py
git commit -m "feat(board): FastAPI read API over BoardStore"
```

---

### Task 8: Agent write routes with If-Match

**Files:**
- Modify: `src/sdlc/board/api.py` (add two write routes)
- Test: `tests/test_board_api_writes.py`

**Interfaces:**
- Consumes: Task 7's `create_app`, `get_store`, `_current_plan_version`, `_require_project`; Task 3's `set_task_observational`, `ConflictError`, `InvalidTransition`.
- Produces: `POST /projects/{project}/tasks/{task_id}/claim`, `PATCH /projects/{project}/tasks/{task_id}`; request model `TaskPatch`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_api_writes.py
"""Agent write routes: If-Match, conflict, invalid transition, authority."""

import pytest
from fastapi.testclient import TestClient

from sdlc.artifacts.store import LocalFileStore
from sdlc.board.api import create_app
from sdlc.board.store import BoardStore
from sdlc.models import DevTask


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "b.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("proj")
    _, plan_v = seed.publish_artifact_version(
        "proj", "plan", "run-1", b"{}", actor="workflow:run-1"
    )
    seed.sync_plan_tasks(
        "proj",
        plan_v,
        "run-1",
        [
            DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"]),
        ],
        actor="workflow:run-1",
    )
    seed.close()
    c = TestClient(create_app(lambda: BoardStore(db=db, blobs=blobs)))
    c.plan_v = plan_v
    return c


def test_claim_moves_status_and_bumps_row_version(client):
    r = client.post(
        "/projects/proj/tasks/T01/claim", headers={"If-Match": "1", "X-Actor": "agent:worker-a"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["row_version"] == 2


def test_claim_does_not_move_authoritative_status(client):
    body = client.post(
        "/projects/proj/tasks/T01/claim", headers={"If-Match": "1", "X-Actor": "agent:a"}
    ).json()
    assert body["authoritative_status"] == "pending", (
        "an agent claim is observational — scoring must not see it"
    )


def test_second_claim_with_stale_if_match_is_409(client):
    client.post("/projects/proj/tasks/T01/claim", headers={"If-Match": "1", "X-Actor": "agent:a"})
    r = client.post(
        "/projects/proj/tasks/T01/claim", headers={"If-Match": "1", "X-Actor": "agent:b"}
    )
    assert r.status_code == 409


def test_missing_if_match_is_428(client):
    r = client.post("/projects/proj/tasks/T01/claim", headers={"X-Actor": "agent:a"})
    assert r.status_code == 428


def test_invalid_transition_is_422(client):
    r = client.patch(
        "/projects/proj/tasks/T01",
        json={"status": "done"},
        headers={"If-Match": "1", "X-Actor": "agent:a"},
    )
    assert r.status_code == 422


def test_rejected_write_appends_no_event(client):
    before = len(client.get("/projects/proj/events").json())
    client.patch(
        "/projects/proj/tasks/T01",
        json={"status": "done"},
        headers={"If-Match": "1", "X-Actor": "agent:a"},
    )
    assert len(client.get("/projects/proj/events").json()) == before


def test_patch_records_actor_and_detail(client):
    client.patch(
        "/projects/proj/tasks/T01",
        json={"status": "blocked", "detail": "waiting on infra"},
        headers={"If-Match": "1", "X-Actor": "agent:worker-a"},
    )
    ev = client.get("/projects/proj/events").json()[-1]
    assert ev["actor"] == "agent:worker-a"
    assert ev["authority"] == "observational"
    assert ev["detail"] == "waiting on infra"


def test_unknown_task_is_404(client):
    r = client.patch(
        "/projects/proj/tasks/T99",
        json={"status": "blocked"},
        headers={"If-Match": "1", "X-Actor": "agent:a"},
    )
    assert r.status_code == 404


def test_stale_plan_cannot_claim_on_current_plan(client, tmp_path):
    """An agent holding an old plan version addresses that plan, not the
    current one — it must not silently claim a task on today's plan."""
    r = client.post(
        f"/projects/proj/tasks/T01/claim?plan={client.plan_v + 99}",
        headers={"If-Match": "1", "X-Actor": "agent:a"},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_api_writes.py -v`
Expected: FAIL — 405 Method Not Allowed (routes do not exist)

- [ ] **Step 3: Add the write routes**

Add to the imports in `src/sdlc/board/api.py`:

```python
from fastapi import Header
from .store import ConflictError, InvalidTransition
```

Add the request model beside the other models:

```python
class TaskPatch(BaseModel):
    status: TaskStatus
    detail: str = ""
```

Add inside `create_app`, before `return app`:

```python
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
    event row exists — the change log records real changes only."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_board_api_writes.py tests/test_board_api_reads.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/board/api.py tests/test_board_api_writes.py
git commit -m "feat(board): agent claim and patch routes with If-Match"
```

---

### Task 9: Wire the board into FeatureWorkflow

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (activity options constant; `_board_*` helpers; call sites at the clarify, architecture, plan, and task stages)
- Test: `tests/test_board_wiring.py`

**Interfaces:**
- Consumes: Task 6's activities and input models; Task 5's `PipelineConfig.project_key`.
- Produces: `BOARD_ACT` options constant; `FeatureWorkflow._board_publish`, `._board_sync_tasks`, `._board_task_status`, `._board_evidence`; `self._plan_version: int | None` workflow state.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_wiring.py
"""The board call sites exist and are wired to the right stages."""

import inspect

from sdlc.workflows import feature


def test_board_activity_options_have_retries():
    """Board writes are NOT best-effort: agents read tasks from the board,
    so a failed write must retry rather than be swallowed like EXPORT_ACT."""
    assert feature.BOARD_ACT["retry_policy"].maximum_attempts >= 3


def test_workflow_imports_board_activities():
    src = inspect.getsource(feature)
    for name in (
        "publish_artifact_version",
        "sync_plan_tasks",
        "set_task_authoritative",
        "attach_task_evidence",
    ):
        assert name in src, f"{name} not wired into feature.py"


def test_every_project_artifact_key_is_published():
    src = inspect.getsource(feature)
    for key in ('"requirements"', '"architecture"', '"plan"'):
        assert key in src, f"no board publish for artifact key {key}"


def test_rejected_gate_publishes_rejected_status():
    src = inspect.getsource(feature)
    assert "ArtifactStatus.REJECTED" in src, "a rejected design must still be recorded as history"


def test_board_helpers_exist_on_the_workflow():
    for name in ("_board_publish", "_board_sync_tasks", "_board_task_status", "_board_evidence"):
        assert hasattr(feature.FeatureWorkflow, name), f"missing {name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_wiring.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.workflows.feature' has no attribute 'BOARD_ACT'`

- [ ] **Step 3: Add the options constant and imports**

In `src/sdlc/workflows/feature.py`, beside the other `*_ACT` constants (near line 137's `EXPORT_ACT`):

```python
# E-40: the board is NOT best-effort like EXPORT_ACT. Agents read tasks from
# it, so a lost write is a correctness bug, not a missing report. The store's
# writes are idempotent (sync uses ON CONFLICT DO NOTHING), so retrying is
# safe.
BOARD_ACT = dict(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=5)
)
```

Inside the existing `with workflow.unsafe.imports_passed_through():` block where the other models are imported (near line 66), add:

```python
from ..board.activities import (
    AttachEvidenceInput,
    PublishArtifactInput,
    SetTaskStatusInput,
    SyncPlanTasksInput,
    attach_task_evidence,
    publish_artifact_version,
    set_task_authoritative,
    sync_plan_tasks,
)
from ..board.models import ArtifactStatus, TaskStatus
```

- [ ] **Step 4: Add the helper methods**

Add to `class FeatureWorkflow`, beside `_record` (near line 605):

```python
async def _board_publish(
    self, cfg: PipelineConfig, key: str, content_json: str, *, approved: bool = True
) -> int:
    """Publish one project artifact version. A rejected gate still writes
    history — the pointer just does not move."""
    run_id = workflow.info().workflow_id
    result = await workflow.execute_activity(
        publish_artifact_version,
        PublishArtifactInput(
            project=cfg.project_key,
            key=key,
            run_id=run_id,
            content_json=content_json,
            actor=f"workflow:{run_id}",
            status=(ArtifactStatus.CURRENT if approved else ArtifactStatus.REJECTED),
        ),
        **BOARD_ACT,
    )
    return result.version_id


async def _board_sync_tasks(
    self, cfg: PipelineConfig, plan_version: int, tasks: list[DevTask]
) -> None:
    run_id = workflow.info().workflow_id
    await workflow.execute_activity(
        sync_plan_tasks,
        SyncPlanTasksInput(
            project=cfg.project_key,
            plan_version=plan_version,
            run_id=run_id,
            tasks=tasks,
            actor=f"workflow:{run_id}",
        ),
        **BOARD_ACT,
    )


async def _board_task_status(
    self,
    cfg: PipelineConfig,
    task_id: str,
    status: TaskStatus,
    *,
    fix_attempts: int | None = None,
    error: str | None = None,
    branch: str | None = None,
) -> None:
    if self._plan_version is None:
        return  # no plan published (early rejection)
    run_id = workflow.info().workflow_id
    await workflow.execute_activity(
        set_task_authoritative,
        SetTaskStatusInput(
            project=cfg.project_key,
            plan_version=self._plan_version,
            task_id=task_id,
            status=status,
            actor=f"workflow:{run_id}",
            fix_attempts=fix_attempts,
            error=error,
            branch=branch,
        ),
        **BOARD_ACT,
    )


async def _board_evidence(
    self, cfg: PipelineConfig, task_id: str, kind: str, content_json: str
) -> None:
    if self._plan_version is None:
        return
    await workflow.execute_activity(
        attach_task_evidence,
        AttachEvidenceInput(
            project=cfg.project_key,
            plan_version=self._plan_version,
            task_id=task_id,
            run_id=workflow.info().workflow_id,
            kind=kind,
            content_json=content_json,
        ),
        **BOARD_ACT,
    )
```

Initialise the state field in `__init__` beside the other workflow state:

```python
        self._plan_version: int | None = None
```

- [ ] **Step 5: Add the call sites**

**Clarify** — after the clarify stage's `_record` call (near line 1955):

```python
        await self._board_publish(cfg, "requirements", reqs.model_dump_json())
```

**Architecture** — replace the `if not gate.approved: return "rejected:architecture"` block (near line 2050) with:

```python
await self._board_publish(cfg, "architecture", arch.model_dump_json(), approved=gate.approved)
if not gate.approved:
    return "rejected:architecture"
```

**Plan** — after the plan stage's gate check, capture the version and sync tasks:

```python
self._plan_version = await self._board_publish(
    cfg, "plan", plan.model_dump_json(), approved=gate.approved
)
if not gate.approved:
    return "rejected:plan"
await self._board_sync_tasks(cfg, self._plan_version, plan.tasks)
```

**Task start** — at the top of `run_one` (near line 2104):

```python
        async def run_one(t: DevTask) -> TaskResult:
            await self._board_task_status(cfg, t.id, TaskStatus.IN_PROGRESS)
```

**Task end** — where `run_one` returns its `TaskResult`, map the result:

```python
_BOARD_STATUS = {
    "done": TaskStatus.DONE,
    "failed": TaskStatus.FAILED,
    "quarantined": TaskStatus.QUARANTINED,
}
await self._board_task_status(
    cfg,
    t.id,
    _BOARD_STATUS[result.status],
    fix_attempts=result.attempts,
    branch=result.branch,
    error=(result.notes or None if result.status != "done" else None),
)
for kind, report in (
    ("qa", result.qa),
    ("review", result.review),
    ("deep_review", result.deep_review),
):
    if report is not None:
        await self._board_evidence(cfg, t.id, kind, report.model_dump_json())
return result
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_board_wiring.py -v`
Expected: 5 passed

- [ ] **Step 7: Run the temporal end-to-end suite**

Run: `pytest -m temporal -k "greenfield or feature" -v`
Expected: existing workflow tests still pass — the board writes must not change any run's return string

- [ ] **Step 8: Run the whole fast suite**

Run: `pytest -q`
Expected: no new failures

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_board_wiring.py
git commit -m "feat(board): wire board writes into FeatureWorkflow stages"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Module layout `board/` | 1, 2, 3, 6 |
| SQLite storage, WAL, `BEGIN IMMEDIATE` | 1, 2 |
| Blobs via claim-check store, `_SUBDIRS` | 2 |
| `project_key` on `PipelineConfig` | 5 |
| Two artifact classes (project vs evidence) | 2, 4 |
| Schema — all six tables | 1 |
| Plan-scoped task identity | 3 |
| Two-status split | 3, 4, 8 |
| Optimistic concurrency, `If-Match` | 3, 8 |
| Agent write routes (only two) | 8 |
| Read routes (all eight) | 7 |
| Workflow activities (all four) | 6 |
| Content reads byte-capped, kind-checked | 7 |
| `/stats` disjoint from `benchmarks/` | 4 |
| Workflow wiring table | 9 |
| Rejected gate writes history, no pointer move | 2, 9 |
| Error-handling table (409/422/428/404/410, truncation) | 3, 7, 8 |
| Retryable, not best-effort | 6, 9 |
| `fastapi`/`uvicorn` dependencies | 7 |

No gaps found.

**Placeholder scan:** every step contains runnable code or an exact command. No "TBD", no "add error handling", no "similar to Task N".

**Type consistency check — two fixes applied while reviewing:**
- `ref_to_path` accepts any object with `.uri`; `ArtifactVersion` carries `uri`, so Task 7 passes the version directly rather than constructing an `ArtifactRef`. Noted inline in Task 7 Step 4.
- `set_task_observational`'s parameter is `expect_row_version` in Tasks 3 and 8 alike; the HTTP header is `If-Match` and is converted at the boundary in `_agent_write`, not passed through raw.

Names verified consistent across tasks: `publish_artifact_version`, `sync_plan_tasks`, `set_task_authoritative`, `set_task_observational`, `attach_task_evidence`, `list_evidence`, `list_events`, `stats`, `get_artifact`, `list_versions`, `get_version`, `get_task`, `list_tasks`, `ensure_project`, `check_task_transition`, `BOARD_ACT`, `_plan_version`.

**Known follow-ups (out of scope, recorded in the spec's Open Questions):** joining `/stats` with `BenchmarkRecord`; retention for board rows.
