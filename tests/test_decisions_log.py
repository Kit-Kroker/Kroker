"""FR-304: the decision-log read surface over the retro exports.

Mirrors `calibration/store.py::gate_decisions_from_exports`'s discipline:
coverage is runs that closed AND exported; a malformed summary is skipped,
never fatal to the sweep; a missing root is an empty answer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sdlc.core.models import GateOutcome
from sdlc.observability.decisions import DecisionLogRow, decisions_from_exports, render_decisions


def _gate_row(gate: str, **kw) -> dict:
    base = {"gate": gate, "round": 1, "policy": "hard", "decided_by": "human", "approved": True}
    base.update(kw)
    return base


def _summary_json(run_id: str, gates: list[dict], *, title: str = "", project_key=None) -> str:
    s = {
        "run_id": run_id,
        "mode": "greenfield",
        "outcome": "deployed:http://pr",
        "terminal_stage": "deploy",
        "started_at": "2026-11-15T08:00:00+00:00",
        "ended_at": "2026-11-15T09:00:00+00:00",
        "duration_s": 3600.0,
        "gates": gates,
        "title": title,
        "project_key": project_key,
    }
    return json.dumps(s)


def _write_run(root: Path, run_id: str, content: str) -> None:
    d = root / run_id
    d.mkdir(parents=True)
    (d / "summary.json").write_text(content, encoding="utf-8")


TWO_RUNS = [
    (
        "run-a",
        _summary_json(
            "run-a",
            [
                _gate_row(
                    "merge",
                    outcome="approve",
                    reviewer="maksim",
                    comments="ok",
                    decided_at="2026-11-15T09:10:00+00:00",
                ),
            ],
            title="Alpha",
            project_key="kroker",
        ),
    ),
    (
        "run-b",
        _summary_json(
            "run-b",
            [
                _gate_row(
                    "architecture",
                    outcome="revise",
                    decided_by="policy",
                    decided_at="2026-11-15T09:20:00+00:00",
                ),
                _gate_row(
                    "deploy",
                    outcome="reject",
                    decided_by="timeout",
                    decided_at="2026-11-15T09:30:00+00:00",
                ),
            ],
            title="Beta",
            project_key="kroker",
        ),
    ),
]


def _two_runs(tmp_path: Path) -> Path:
    for run_id, content in TWO_RUNS:
        _write_run(tmp_path, run_id, content)
    return tmp_path


def test_reads_full_rows_across_runs(tmp_path):
    rows = decisions_from_exports(_two_runs(tmp_path))
    assert [r.gate for r in rows] == ["merge", "architecture", "deploy"]
    a = rows[0]
    assert (a.run_id, a.title, a.project_key) == ("run-a", "Alpha", "kroker")
    assert a.outcome is GateOutcome.APPROVE and a.reviewer == "maksim"
    assert a.comments == "ok" and a.decided_at == datetime(2026, 11, 15, 9, 10, tzinfo=UTC)


def test_filters_run_gate_decided_by(tmp_path):
    root = _two_runs(tmp_path)
    assert [r.run_id for r in decisions_from_exports(root, run="run-b")] == ["run-b", "run-b"]
    assert [r.gate for r in decisions_from_exports(root, gate="deploy")] == ["deploy"]
    assert [r.gate for r in decisions_from_exports(root, decided_by="timeout")] == ["deploy"]
    # combined narrows conjunctively
    assert decisions_from_exports(root, run="run-a", decided_by="timeout") == []


def test_limit_keeps_most_recent_tail(tmp_path):
    rows = decisions_from_exports(_two_runs(tmp_path), limit=2)
    assert [r.gate for r in rows] == ["architecture", "deploy"]  # ascending order's tail


def test_limit_zero_is_empty(tmp_path):
    assert decisions_from_exports(_two_runs(tmp_path), limit=0) == []


def test_missing_root_is_empty_not_error(tmp_path):
    assert decisions_from_exports(tmp_path / "nope") == []


def test_malformed_summary_is_skipped(tmp_path):
    _write_run(tmp_path, "run-a", '{"run_id": "run-a", "gates": [ trunc')  # truncated json
    _write_run(tmp_path, "run-b", TWO_RUNS[1][1])
    rows = decisions_from_exports(tmp_path)
    assert [r.run_id for r in rows] == ["run-b", "run-b"]


def test_old_style_summary_yields_rows_with_none_fields(tmp_path):
    """A pre-FR-304 summary.json: gates rows carry none of the new keys."""
    content = _summary_json(
        "run-old",
        [{"gate": "merge", "round": 1, "policy": "soft", "decided_by": "human", "approved": True}],
    )
    _write_run(tmp_path, "run-old", content)
    (row,) = decisions_from_exports(tmp_path)
    assert row.outcome is None and row.comments is None
    assert row.reviewer is None and row.decided_at is None


def test_render_is_deterministic_table_with_empty_state(tmp_path):
    assert render_decisions([]) == (
        "no decisions recorded (runs that closed and exported under the export root)"
    )
    # an existing-but-decisionless root renders the same empty state
    (tmp_path / "run-empty").mkdir()
    (tmp_path / "run-empty" / "summary.json").write_text(
        _summary_json("run-empty", []), encoding="utf-8"
    )
    assert render_decisions(decisions_from_exports(tmp_path)).startswith("no decisions recorded")
    # non-empty render: header + one line per row, stable across calls
    sample = [
        DecisionLogRow(
            run_id="run-a",
            title="Alpha",
            project_key="kroker",
            gate="merge",
            round=1,
            policy="hard",
            decided_by="human",
            outcome=GateOutcome.APPROVE,
            reviewer="maksim",
            comments="ok",
            decided_at=datetime(2026, 11, 15, 9, 10, tzinfo=UTC),
        )
    ]
    first, second = render_decisions(sample), render_decisions(sample)
    assert first == second
    assert first.count("\n") == 1  # header + one row
    assert "merge" in first and "maksim" in first


def test_truncated_multibyte_summary_is_skipped(tmp_path):
    """Review finding 1: a crashed run's truncated write can cut a multi-byte
    UTF-8 character mid-sequence. That run is skipped like any malformed
    summary — UnicodeDecodeError must not escape the sweep."""
    (tmp_path / "run-a" / "summary.json").parent.mkdir(parents=True)
    (tmp_path / "run-a" / "summary.json").write_bytes(
        b'{"run_id": "run-a", "gates": [{"gate": "merge\xc3"}'
    )  # \xc3 opening a multi-byte sequence, then cut
    _write_run(tmp_path, "run-b", TWO_RUNS[1][1])
    rows = decisions_from_exports(tmp_path)
    assert [r.run_id for r in rows] == ["run-b", "run-b"]
