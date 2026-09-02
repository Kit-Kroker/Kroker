"""FR-304/FR-917 (E-50): finding-disposition persistence.

ADR-19 -- adapters, not substrate. BoardFindingDispositionStore is the one
reference implementation, backed by the E-78 board's SQLite file and
reusing BoardIdentityStore's optimistic-concurrency discipline rather than
inventing a second scheme in the same database.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from ..board.schema import apply_schema, connect, db_path
from .models import Disposition, FindingDisposition


class FindingDispositionStoreError(Exception):
    """Base for finding-disposition write rejections."""


class FindingDispositionConflictError(FindingDispositionStoreError):
    """Optimistic-concurrency failure: caller's expected_version is stale."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class FindingDispositionStore(ABC):
    @abstractmethod
    def load(self, project: str) -> list[FindingDisposition]:
        """Every live disposition for the project, sorted by (kind, key)."""

    @abstractmethod
    def registry_version(self, project: str) -> int:
        """0 for a project that has never been written."""

    @abstractmethod
    def apply(
        self,
        project: str,
        disposition: FindingDisposition,
        *,
        expected_version: int,
        actor: str,
        operation: str = "dispose",
        detail: str | None = None,
    ) -> int:
        """Upsert one disposition, keyed on (project, kind, key). Returns
        the new registry_version."""

    @abstractmethod
    def events(self, project: str, kind: str, key: str) -> list[str]:
        """Every operation recorded for this (project, kind, key), oldest
        first -- the audit trail apply() writes alongside the live row on
        every call, revision included. Read-only surface over
        finding_disposition_event, for a caller (or a test) that needs the
        history rather than just the current disposition."""


class BoardFindingDispositionStore(FindingDispositionStore):
    def __init__(self, db: str | os.PathLike | None = None) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def load(self, project: str) -> list[FindingDisposition]:
        rows = self._conn.execute(
            "SELECT kind, key, disposition, approved_by, reason, decided_at "
            "FROM finding_disposition WHERE project = ? ORDER BY kind, key",
            (project,),
        ).fetchall()
        return [
            FindingDisposition(
                kind=r[0],
                key=r[1],
                disposition=Disposition(r[2]),
                approved_by=r[3],
                reason=r[4],
                decided_at=r[5],
            )
            for r in rows
        ]

    def registry_version(self, project: str) -> int:
        row = self._conn.execute(
            "SELECT registry_version FROM finding_disposition_registry WHERE project = ?",
            (project,),
        ).fetchone()
        return row[0] if row else 0

    def apply(
        self,
        project: str,
        disposition: FindingDisposition,
        *,
        expected_version: int,
        actor: str,
        operation: str = "dispose",
        detail: str | None = None,
    ) -> int:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            current = self.registry_version(project)
            if current != expected_version:
                raise FindingDispositionConflictError(
                    f"registry_version for '{project}' is {current}, caller "
                    f"expected {expected_version}; reload before disposing again"
                )
            self._conn.execute(
                "INSERT INTO finding_disposition_registry (project, registry_version) "
                "VALUES (?, 0) ON CONFLICT(project) DO NOTHING",
                (project,),
            )
            self._conn.execute(
                "INSERT INTO finding_disposition (project, kind, key, disposition, "
                "approved_by, reason, decided_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(project, kind, key) DO UPDATE SET "
                "disposition=excluded.disposition, approved_by=excluded.approved_by, "
                "reason=excluded.reason, decided_at=excluded.decided_at",
                (
                    project,
                    disposition.kind,
                    disposition.key,
                    disposition.disposition.value,
                    disposition.approved_by,
                    disposition.reason,
                    disposition.decided_at.isoformat(),
                ),
            )
            self._conn.execute(
                "INSERT INTO finding_disposition_event (project, kind, key, actor, "
                "operation, detail, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    project,
                    disposition.kind,
                    disposition.key,
                    actor,
                    operation,
                    detail if detail is not None else disposition.disposition.value,
                    _now(),
                ),
            )
            self._conn.execute(
                "UPDATE finding_disposition_registry SET registry_version = ? WHERE project = ?",
                (expected_version + 1, project),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return expected_version + 1

    def events(self, project: str, kind: str, key: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT operation FROM finding_disposition_event WHERE project = ? AND kind = ? "
            "AND key = ? ORDER BY id",
            (project, kind, key),
        ).fetchall()
        return [r[0] for r in rows]
