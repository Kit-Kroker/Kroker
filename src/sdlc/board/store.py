# src/sdlc/board/store.py
"""BoardStore: the single enforcement point for board state.

All board-state SQL lives here — artifacts, tasks, events. Both writers reach
the board through this class — the workflow via board/activities.py
(in-process), agents via board/api.py — so there is exactly one place that can
move a status.

Blobs go to the claim-check store (immutable, sha256-addressed); this class
owns only the mutable graph. Ordering inside a publish is: write the blob,
then commit the row. A crash between the two leaves an orphan blob, which is
harmless because blobs are content-addressed and unreferenced.

Capability identity (E-47a) is a different domain with its own enforcement
point, capability/store.py; its DDL still lives in schema.py, which owns every
table in this database file.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone

from ..artifacts.store import LocalFileStore
from ..models import ArtifactRef, DevTask
from .models import (ArtifactStatus, ArtifactVersion, Authority, BoardArtifact,
                     BoardEvent, BoardStats, BoardTask, TaskEvidence,
                     TaskStatus)
from .schema import apply_schema, connect, db_path
from .transitions import check_task_transition


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


EVIDENCE_KINDS = frozenset({"qa", "review", "deep_review"})


class BoardStore:
    def __init__(self, db: str | os.PathLike | None = None,
                 blobs: LocalFileStore | None = None) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)
        self._blobs = blobs if blobs is not None else LocalFileStore()

    def close(self) -> None:
        self._conn.close()

    # ---- internals ---------------------------------------------------

    def _write(self):
        """Context manager for a serialized write transaction."""
        return _Tx(self._conn)

    def _event(self, project: str, subject: str, actor: str,
               authority: Authority, from_status: str | None,
               to_status: str | None, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO event(project,subject,actor,authority,"
            "from_status,to_status,at,detail) VALUES (?,?,?,?,?,?,?,?)",
            (project, subject, actor, authority.value, from_status,
             to_status, _now(), detail))

    # ---- project -----------------------------------------------------

    def ensure_project(self, key: str, repo: str = "") -> None:
        with self._write():
            self._conn.execute(
                "INSERT INTO project(key,repo,created_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO NOTHING", (key, repo, _now()))

    def list_projects(self) -> list[tuple[str, str]]:
        """(key, repo) for every project, ordered by key. The HTTP layer maps
        these to its response model; the store owns the SQL so a Postgres
        backend can swap in without touching callers."""
        rows = self._conn.execute(
            "SELECT key, repo FROM project ORDER BY key").fetchall()
        return [(r["key"], r["repo"]) for r in rows]

    def get_project(self, project: str) -> tuple[str, str]:
        """(key, repo) for one project, raising NotFoundError if absent."""
        row = self._conn.execute(
            "SELECT key, repo FROM project WHERE key=?", (project,)).fetchone()
        if row is None:
            raise NotFoundError(f"no project {project!r}")
        return row["key"], row["repo"]

    def list_artifacts(self, project: str) -> list[BoardArtifact]:
        """Every artifact row for a project, ordered by key."""
        rows = self._conn.execute(
            "SELECT project,key,current_version,status FROM artifact "
            "WHERE project=? ORDER BY key", (project,)).fetchall()
        return [BoardArtifact(**dict(r)) for r in rows]

    # ---- artifacts ---------------------------------------------------

    def publish_artifact_version(
            self, project: str, key: str, run_id: str, content: bytes, *,
            status: ArtifactStatus = ArtifactStatus.CURRENT,
            actor: str) -> tuple[ArtifactRef, int]:
        """Append a version. CURRENT moves the pointer and supersedes the
        previous version; REJECTED records history and moves nothing.

        Idempotent under Temporal re-execution: if this run already published
        byte-identical content for this (project, key), return the existing
        version rather than creating a duplicate with a bogus supersedes link.
        Scoped to run_id — Temporal re-execution is always within one workflow
        run, so a *different* run publishing identical content (the common
        case under _cached_stage memoization) still appends its own version."""
        sha = hashlib.sha256(content).hexdigest()
        with self._write():
            prior = self._conn.execute(
                "SELECT id, sha256, uri FROM artifact_version "
                "WHERE project=? AND key=? AND run_id=? AND sha256=? "
                "ORDER BY id LIMIT 1",
                (project, key, run_id, sha)).fetchone()
            if prior is not None:
                # The pointer and event were already moved by the first
                # execution; a re-execution changes nothing.
                return (ArtifactRef(kind="board_artifact",
                                    uri=prior["uri"],
                                    sha256=prior["sha256"]),
                        int(prior["id"]))

            row = self._conn.execute(
                "SELECT COALESCE(MAX(n),0) FROM artifact_version "
                "WHERE project=? AND key=?", (project, key)).fetchone()
            n = int(row[0]) + 1

            prev = self._conn.execute(
                "SELECT current_version FROM artifact WHERE project=? "
                "AND key=?", (project, key)).fetchone()
            prev_current = prev["current_version"] if prev else None

            ref = self._blobs.put("board_artifact", run_id,
                                  f"{key}-v{n}.json", content)

            supersedes = (prev_current
                          if status is ArtifactStatus.CURRENT else None)
            cur = self._conn.execute(
                "INSERT INTO artifact_version"
                "(project,key,n,run_id,sha256,uri,supersedes,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (project, key, n, run_id, ref.sha256, ref.uri,
                 supersedes, _now()))
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
                    (project, key, version_id, ArtifactStatus.CURRENT.value))
            else:
                self._conn.execute(
                    "INSERT INTO artifact(project,key,current_version,status)"
                    " VALUES (?,?,?,?) ON CONFLICT(project,key) DO NOTHING",
                    (project, key, None, status.value))

            self._event(project, f"artifact:{key}", actor,
                        Authority.AUTHORITATIVE, None, status.value,
                        detail=f"v{n} sha256={ref.sha256[:12]}")
        return ref, version_id

    def get_artifact(self, project: str, key: str) -> BoardArtifact:
        row = self._conn.execute(
            "SELECT project,key,current_version,status FROM artifact "
            "WHERE project=? AND key=?", (project, key)).fetchone()
        if row is None:
            raise NotFoundError(f"no artifact {key!r} in project {project!r}")
        return BoardArtifact(project=row["project"], key=row["key"],
                             current_version=row["current_version"],
                             status=ArtifactStatus(row["status"]))

    def list_versions(self, project: str, key: str) -> list[ArtifactVersion]:
        rows = self._conn.execute(
            "SELECT * FROM artifact_version WHERE project=? AND key=? "
            "ORDER BY n", (project, key)).fetchall()
        return [ArtifactVersion(**dict(r)) for r in rows]

    def get_version(self, project: str, version_id: int) -> ArtifactVersion:
        row = self._conn.execute(
            "SELECT * FROM artifact_version WHERE project=? AND id=?",
            (project, version_id)).fetchone()
        if row is None:
            raise NotFoundError(f"no version {version_id} in {project!r}")
        return ArtifactVersion(**dict(row))

    # ---- events ------------------------------------------------------

    def list_events(self, project: str, since: int = 0,
                    subject: str | None = None) -> list[BoardEvent]:
        sql = "SELECT * FROM event WHERE project=? AND id>?"
        args: list = [project, since]
        if subject is not None:
            sql += " AND subject=?"
            args.append(subject)
        rows = self._conn.execute(sql + " ORDER BY id", args).fetchall()
        return [BoardEvent(**dict(r)) for r in rows]

    # ---- tasks -------------------------------------------------------

    def sync_plan_tasks(self, project: str, plan_version: int, run_id: str,
                        tasks: list[DevTask], *, actor: str) -> int:
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
                    (project, plan_version, t.id, run_id,
                     TaskStatus.PENDING.value, TaskStatus.PENDING.value,
                     _now()))
                if cur.rowcount:
                    inserted += 1
                    self._event(project,
                                f"task:{plan_version}:{t.id}", actor,
                                Authority.AUTHORITATIVE, None,
                                TaskStatus.PENDING.value, detail=t.title)
        return inserted

    def get_task(self, project: str, plan_version: int,
                 task_id: str) -> BoardTask:
        row = self._conn.execute(
            "SELECT * FROM task WHERE project=? AND plan_version=? "
            "AND task_id=?", (project, plan_version, task_id)).fetchone()
        if row is None:
            raise NotFoundError(
                f"no task {task_id!r} in plan {plan_version} of {project!r}")
        return BoardTask(**dict(row))

    def list_tasks(self, project: str, plan_version: int, *,
                   status: TaskStatus | None = None,
                   run_id: str | None = None) -> list[BoardTask]:
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
            self, project: str, plan_version: int, task_id: str,
            status: TaskStatus, *, actor: str,
            fix_attempts: int | None = None, error: str | None = None,
            branch: str | None = None) -> BoardTask:
        """Workflow write. Validates against authoritative_status — an agent
        having moved `status` must never unlock a workflow transition.

        Idempotent under Temporal re-execution: if authoritative_status is
        already the target (the write already committed but its completion
        wasn't reported), return the row unchanged rather than raising
        InvalidTransition — otherwise all retries fail identically and a
        transient worker blip permanently fails the run."""
        with self._write():
            task = self.get_task(project, plan_version, task_id)
            if task.authoritative_status == status:
                return task            # already applied; re-execution is a no-op
            check_task_transition(task.authoritative_status, status)
            self._conn.execute(
                "UPDATE task SET status=?, authoritative_status=?,"
                " row_version=row_version+1,"
                " fix_attempts=COALESCE(?,fix_attempts),"
                " error=COALESCE(?,error), branch=COALESCE(?,branch),"
                " updated_at=? "
                "WHERE project=? AND plan_version=? AND task_id=?",
                (status.value, status.value, fix_attempts, error, branch,
                 _now(), project, plan_version, task_id))
            self._event(project, f"task:{plan_version}:{task_id}", actor,
                        Authority.AUTHORITATIVE,
                        task.authoritative_status.value, status.value)
        return self.get_task(project, plan_version, task_id)

    def set_task_observational(
            self, project: str, plan_version: int, task_id: str,
            status: TaskStatus, *, actor: str, expect_row_version: int,
            detail: str = "") -> BoardTask:
        """Agent write. Moves the live view only; authoritative_status is
        untouched, so scoring and replay are unaffected by an agent that
        crashes mid-claim or reports optimistically."""
        with self._write():
            task = self.get_task(project, plan_version, task_id)
            if task.row_version != expect_row_version:
                raise ConflictError(
                    f"row_version {expect_row_version} is stale; "
                    f"current is {task.row_version}")
            check_task_transition(task.status, status)
            self._conn.execute(
                "UPDATE task SET status=?, row_version=row_version+1,"
                " updated_at=? "
                "WHERE project=? AND plan_version=? AND task_id=?",
                (status.value, _now(), project, plan_version, task_id))
            self._event(project, f"task:{plan_version}:{task_id}", actor,
                        Authority.OBSERVATIONAL, task.status.value,
                        status.value, detail=detail)
        return self.get_task(project, plan_version, task_id)

    # ---- evidence ----------------------------------------------------

    def attach_task_evidence(self, project: str, plan_version: int,
                             task_id: str, run_id: str, kind: str,
                             content: bytes) -> ArtifactRef:
        """Per-run, immutable observation about one attempt. Unlike project
        artifacts these are never versioned and never move a pointer.

        Idempotent under Temporal re-execution: dedupes on
        (task, run_id, kind, sha256) so a retried activity doesn't double the
        rows. Distinct content (a genuinely different report) is kept."""
        if kind not in EVIDENCE_KINDS:
            raise ValueError(
                f"evidence kind {kind!r} not in {sorted(EVIDENCE_KINDS)}")
        self.get_task(project, plan_version, task_id)     # 404 if absent
        sha = hashlib.sha256(content).hexdigest()
        with self._write():
            prior = self._conn.execute(
                "SELECT sha256, uri FROM task_evidence "
                "WHERE project=? AND plan_version=? AND task_id=? "
                "AND run_id=? AND kind=? AND sha256=? LIMIT 1",
                (project, plan_version, task_id, run_id, kind, sha)
            ).fetchone()
            if prior is not None:
                return ArtifactRef(kind="board_evidence",
                                   uri=prior["uri"],
                                   sha256=prior["sha256"])
            ref = self._blobs.put(
                "board_evidence", run_id,
                f"{task_id}-{kind}.json", content)
            self._conn.execute(
                "INSERT INTO task_evidence(project,plan_version,task_id,"
                "run_id,kind,sha256,uri,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (project, plan_version, task_id, run_id, kind,
                 ref.sha256, ref.uri, _now()))
        return ref

    def list_evidence(self, project: str, plan_version: int,
                      task_id: str) -> list[TaskEvidence]:
        rows = self._conn.execute(
            "SELECT * FROM task_evidence WHERE project=? AND plan_version=? "
            "AND task_id=? ORDER BY id",
            (project, plan_version, task_id)).fetchall()
        return [TaskEvidence(**dict(r)) for r in rows]

    # ---- stats -------------------------------------------------------

    def stats(self, project: str) -> BoardStats:
        """Board-owned counters only. Counted status is authoritative_status:
        an agent's optimistic write must never move a number that scoring
        or a human reads as truth."""
        by_status = {
            r["authoritative_status"]: r["n"] for r in self._conn.execute(
                "SELECT authoritative_status, COUNT(*) AS n FROM task "
                "WHERE project=? GROUP BY authoritative_status",
                (project,)).fetchall()}
        agg = self._conn.execute(
            "SELECT COALESCE(SUM(fix_attempts),0) AS fixes,"
            " COALESCE(SUM(error IS NOT NULL),0) AS errs,"
            " COALESCE(SUM(status<>authoritative_status),0) AS diverged"
            " FROM task WHERE project=?", (project,)).fetchone()
        events = self._conn.execute(
            "SELECT COUNT(*) FROM event WHERE project=?",
            (project,)).fetchone()[0]
        return BoardStats(
            project=project, tasks_by_status=by_status,
            total_fix_attempts=int(agg["fixes"]),
            tasks_with_error=int(agg["errs"]),
            diverged_tasks=int(agg["diverged"]),
            event_count=int(events))


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
