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
from .models import (ArtifactStatus, ArtifactVersion, Authority, BoardArtifact,
                     BoardEvent)
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

    # ---- artifacts ---------------------------------------------------

    def publish_artifact_version(
            self, project: str, key: str, run_id: str, content: bytes, *,
            status: ArtifactStatus = ArtifactStatus.CURRENT,
            actor: str) -> tuple[ArtifactRef, int]:
        """Append a version. CURRENT moves the pointer and supersedes the
        previous version; REJECTED records history and moves nothing."""
        with self._write():
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
