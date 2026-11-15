"""`sdlc decisions` — FR-304's queryable decision log over the run exports.

Read-only and local-only (no Temporal client), like `sdlc calibration`.
These tests pin the wiring: parser flags, the local-only clause, and the
printed table over fixture exports.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sdlc import cli
from sdlc.cli import build_parser


def _write_run(root: Path, run_id: str, gates: list[dict]) -> None:
    d = root / run_id
    d.mkdir(parents=True)
    (d / "summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "mode": "greenfield",
                "outcome": "deployed:http://pr",
                "terminal_stage": "deploy",
                "started_at": "2026-11-15T08:00:00+00:00",
                "ended_at": "2026-11-15T09:00:00+00:00",
                "duration_s": 3600.0,
                "gates": gates,
            }
        ),
        encoding="utf-8",
    )


def _two_runs(tmp_path: Path) -> Path:
    _write_run(
        tmp_path,
        "run-a",
        [
            {
                "gate": "merge", "round": 1, "policy": "hard", "decided_by": "human",
                "approved": True, "outcome": "approve", "reviewer": "maksim",
                "comments": "ok", "decided_at": "2026-11-15T09:10:00+00:00",
            }
        ],
    )
    _write_run(
        tmp_path,
        "run-b",
        [
            {
                "gate": "deploy", "round": 1, "policy": "hard", "decided_by": "timeout",
                "approved": False, "outcome": "reject",
                "decided_at": "2026-11-15T09:30:00+00:00",
            }
        ],
    )
    return tmp_path


def _run_main(capsys, monkeypatch, *argv: str) -> str:
    monkeypatch.setattr("sys.argv", ["sdlc", "decisions", *argv])
    asyncio.run(cli.main())
    return capsys.readouterr().out


def test_parser_accepts_decisions_with_its_flags():
    args = build_parser().parse_args(
        ["decisions", "--run", "r1", "--gate", "merge", "--decided-by", "human",
         "--limit", "5", "--exports", "/tmp/x"]
    )
    assert args.cmd == "decisions"
    assert (args.run, args.gate, args.decided_by, args.limit, args.exports) == (
        "r1", "merge", "human", 5, "/tmp/x"
    )


def test_decisions_needs_no_temporal_client():
    args = build_parser().parse_args(["decisions"])
    assert cli._needs_temporal_client(args) is False


def test_decisions_prints_the_log_over_fixture_exports(capsys, monkeypatch, tmp_path):
    out = _run_main(capsys, monkeypatch, "--exports", str(tmp_path := _two_runs(tmp_path)))
    assert "merge" in out and "maksim" in out
    assert "deploy" in out and "reject" in out
    assert "run-a" in out and "run-b" in out


def test_decided_by_filter_narrows_the_log(capsys, monkeypatch, tmp_path):
    out = _run_main(capsys, monkeypatch, "--exports", str(_two_runs(tmp_path)), "--decided-by", "human")
    assert "merge" in out
    assert "deploy" not in out


def test_missing_exports_root_is_a_friendly_line_and_exit_zero(capsys, monkeypatch, tmp_path):
    out = _run_main(capsys, monkeypatch, "--exports", str(tmp_path / "nope"))
    assert out.startswith("no decisions recorded")
