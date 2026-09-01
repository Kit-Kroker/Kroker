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
