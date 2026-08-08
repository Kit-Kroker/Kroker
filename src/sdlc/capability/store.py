"""FR-913 (E-47a): identity persistence.

ADR-19 — adapters, not substrate. The ABC is the seam; BoardIdentityStore is
the one reference implementation, backed by the E-78 board's SQLite file and
reusing its optimistic-concurrency discipline rather than inventing a second
scheme in the same database.

All identity SQL lives here. See board/store.py's docstring for why this is
a second SQL owner over one file rather than a violation of its rule.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from ..board.schema import apply_schema, connect, db_path
from .models import CapabilityFingerprint, CapabilityIdentity


class IdentityStoreError(Exception):
    """Base for identity write rejections."""


class IdentityConflictError(IdentityStoreError):
    """Optimistic-concurrency failure: caller's registry_version is stale.

    The caller must reload and RE-MATCH, not replay its computed
    attachments — the registry it matched against has moved.
    """


class IdentityNotFoundError(IdentityStoreError):
    """No such project or bc_id."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapabilityIdentityStore(ABC):
    @abstractmethod
    def load(self, project: str) -> list[CapabilityIdentity]:
        """Every row for the project, sorted by bc_id. Includes retired rows
        (they are match candidates) and merged rows (callers exclude them)."""

    @abstractmethod
    def registry_version(self, project: str) -> int:
        """0 for a project that has never been written."""

    @abstractmethod
    def apply(self, project: str, rows: Sequence[CapabilityIdentity], *,
              expected_version: int, actor: str = "system",
              operation: str = "resolve",
              detail: str | None = None) -> int:
        """Upsert rows in one transaction. Returns the new registry_version.

        `detail` overrides the per-row event detail (which otherwise records
        row.status.value); a correction passes its human reason here so the
        calibration signal the contracts claim to retain is actually kept."""

    @abstractmethod
    def allocator(self, project: str) -> Callable[[], str]:
        """A fresh `BC-NNN` minter. Never returns an id that has ever been
        allocated for this project, retired or not — invariant 1."""


class BoardIdentityStore(CapabilityIdentityStore):
    def __init__(self, db: str | os.PathLike | None = None) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def load(self, project: str) -> list[CapabilityIdentity]:
        rows = self._conn.execute(
            "SELECT bc_id, first_seen_run, status, retired_reason, "
            "merged_into, derived_from, fingerprint "
            "FROM capability_identity WHERE project = ? ORDER BY bc_id",
            (project,)).fetchall()
        return [CapabilityIdentity(
            bc_id=r[0], project=project, first_seen_run=r[1], status=r[2],
            retired_reason=r[3], merged_into=r[4], derived_from=r[5],
            fingerprint=CapabilityFingerprint.model_validate_json(r[6]))
            for r in rows]

    def registry_version(self, project: str) -> int:
        row = self._conn.execute(
            "SELECT registry_version FROM capability_registry WHERE "
            "project = ?", (project,)).fetchone()
        return row[0] if row else 0

    def apply(self, project: str, rows: Sequence[CapabilityIdentity], *,
              expected_version: int, actor: str = "system",
              operation: str = "resolve",
              detail: str | None = None) -> int:
        # BEGIN IMMEDIATE takes the write lock up front (mirroring
        # board/store.py's _Tx), so the version read and the row writes are
        # one atomic transaction. connect() uses isolation_level=None, so the
        # plain `with conn:` context manager would NOT group these -- each
        # statement would autocommit and the optimistic check would race.
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            current = self.registry_version(project)
            if current != expected_version:
                raise IdentityConflictError(
                    f"registry_version for '{project}' is {current}, caller "
                    f"expected {expected_version}; reload and re-match "
                    f"(do not replay computed attachments)")
            self._conn.execute(
                "INSERT INTO capability_registry (project, registry_version, "
                "next_ordinal) VALUES (?, 0, 1) "
                "ON CONFLICT(project) DO NOTHING", (project,))
            for row in rows:
                self._conn.execute(
                    "INSERT INTO capability_identity (project, bc_id, "
                    "first_seen_run, status, retired_reason, merged_into, "
                    "derived_from, fingerprint, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(project, bc_id) DO UPDATE SET "
                    "status=excluded.status, "
                    "retired_reason=excluded.retired_reason, "
                    "merged_into=excluded.merged_into, "
                    "derived_from=excluded.derived_from, "
                    "fingerprint=excluded.fingerprint, "
                    "updated_at=excluded.updated_at",
                    (project, row.bc_id, row.first_seen_run,
                     row.status.value,
                     row.retired_reason.value if row.retired_reason else None,
                     row.merged_into, row.derived_from,
                     row.fingerprint.model_dump_json(), _now()))
                self._conn.execute(
                    "INSERT INTO capability_event (project, bc_id, actor, "
                    "operation, detail, created_at) VALUES (?,?,?,?,?,?)",
                    (project, row.bc_id, actor, operation,
                     detail if detail is not None else row.status.value,
                     _now()))
            self._conn.execute(
                "UPDATE capability_registry SET registry_version = ?, "
                "next_ordinal = MAX(next_ordinal, ?) WHERE project = ?",
                (expected_version + 1, _max_ordinal(rows) + 1, project))
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return expected_version + 1

    def allocator(self, project: str) -> Callable[[], str]:
        # Ensure the registry row exists so the mint-time UPDATE has a row to
        # advance. (apply() does the same insert inside its own transaction;
        # this is idempotent and covers the resolve() path, which mints before
        # any apply.)
        self._conn.execute(
            "INSERT INTO capability_registry (project, registry_version, "
            "next_ordinal) VALUES (?, 0, 1) "
            "ON CONFLICT(project) DO NOTHING", (project,))

        def _allocate() -> str:
            # Reserve the ordinal AT MINT TIME, atomically. The never-reuse
            # invariant (an id is never handed to a second capability) cannot
            # rest on the caller persisting minted rows: resolve() returns ids
            # inside IdentityAttachment objects, not as CapabilityIdentity
            # rows, so a caller that persists only the matched/retired set
            # would leave next_ordinal unmoved and remint the same ids next
            # run. Advancing the counter here on every call means a
            # minted-but-unpersisted id is burned (a gap), never reused --
            # which is what invariant 1 actually requires.
            advanced = self._conn.execute(
                "UPDATE capability_registry SET next_ordinal = next_ordinal + 1 "
                "WHERE project = ? RETURNING next_ordinal",
                (project,)).fetchone()
            return f"BC-{advanced[0] - 1:03d}"

        return _allocate


def _max_ordinal(rows: Sequence[CapabilityIdentity]) -> int:
    """Highest numeric suffix in this batch. next_ordinal only ever moves
    forward (MAX in the UPDATE), so a retired id is never handed out again."""
    best = 0
    for r in rows:
        _, _, suffix = r.bc_id.partition("-")
        if suffix.isdigit():
            best = max(best, int(suffix))
    return best
