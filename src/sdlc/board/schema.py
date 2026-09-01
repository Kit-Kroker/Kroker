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

CREATE TABLE IF NOT EXISTS capability_registry (
    project          TEXT PRIMARY KEY,
    registry_version INTEGER NOT NULL DEFAULT 0,
    next_ordinal     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS capability_identity (
    project        TEXT NOT NULL,
    bc_id          TEXT NOT NULL,
    first_seen_run TEXT NOT NULL,
    status         TEXT NOT NULL,
    retired_reason TEXT,
    merged_into    TEXT,
    derived_from   TEXT,
    fingerprint    TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (project, bc_id)
);

CREATE TABLE IF NOT EXISTS capability_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project    TEXT NOT NULL,
    bc_id      TEXT NOT NULL,
    actor      TEXT NOT NULL,
    operation  TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
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
