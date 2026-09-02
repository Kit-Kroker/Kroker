# tests/test_dispositions_cli.py
"""FR-304 (E-50): `sdlc risk dispose|list|export`, mirroring
capability/cli.py's shape and its CLI-not-HTTP reasoning (OQ-11)."""

from __future__ import annotations

import argparse
import json

import pytest

from sdlc.dispositions.cli import add_dispositions_parser, run_dispositions
from sdlc.dispositions.models import Disposition
from sdlc.dispositions.store import BoardFindingDispositionStore


def _parse(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add_dispositions_parser(sub)
    return p.parse_args(argv)


def test_dispose_applies_and_reports_success(tmp_path, capsys):
    db = tmp_path / "board.sqlite3"
    args = _parse(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "SS1:hardcoded-secret:src/a.py:",
            "--disposition",
            "accepted_risk",
            "--reason",
            "reviewed, tolerated",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    assert run_dispositions(args) == 0
    assert "SS1:hardcoded-secret:src/a.py:" in capsys.readouterr().out
    store = BoardFindingDispositionStore(db=db)
    rows = store.load("p")
    store.close()
    assert rows[0].disposition is Disposition.ACCEPTED_RISK


def test_a_second_dispose_on_the_same_key_revises_it(tmp_path):
    db = tmp_path / "board.sqlite3"
    for disposition in ("false_positive", "accepted_risk"):
        args = _parse(
            [
                "risk",
                "dispose",
                "--project",
                "p",
                "--kind",
                "testability",
                "--key",
                "QS3:static-clock-access:src/a.py:",
                "--disposition",
                disposition,
                "--reason",
                "reviewed",
                "--by",
                "maks",
                "--db",
                str(db),
            ]
        )
        assert run_dispositions(args) == 0
    store = BoardFindingDispositionStore(db=db)
    rows = store.load("p")
    store.close()
    assert len(rows) == 1
    assert rows[0].disposition is Disposition.ACCEPTED_RISK


def test_list_prints_every_disposition(tmp_path, capsys):
    db = tmp_path / "board.sqlite3"
    args = _parse(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "SS1:x:src/a.py:",
            "--disposition",
            "mitigated_elsewhere",
            "--reason",
            "compensating control added",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    run_dispositions(args)
    args = _parse(["risk", "list", "--project", "p", "--db", str(db)])
    assert run_dispositions(args) == 0
    assert "SS1:x:src/a.py:" in capsys.readouterr().out


def test_export_writes_every_disposition(tmp_path):
    db = tmp_path / "board.sqlite3"
    args = _parse(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "SS1:x:src/a.py:",
            "--disposition",
            "accepted_risk",
            "--reason",
            "reviewed",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    run_dispositions(args)
    target = tmp_path / ".sdlc" / "dispositions.json"
    args = _parse(["risk", "export", "--project", "p", "--out", str(target), "--db", str(db)])
    assert run_dispositions(args) == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["dispositions"][0]["key"] == "SS1:x:src/a.py:"


def test_an_invalid_disposition_choice_is_rejected_by_argparse():
    with pytest.raises(SystemExit):
        _parse(
            [
                "risk",
                "dispose",
                "--project",
                "p",
                "--kind",
                "vulnerability",
                "--key",
                "k",
                "--disposition",
                "bogus",
                "--reason",
                "r",
                "--by",
                "maks",
            ]
        )


def test_build_parser_wires_the_risk_subcommand():
    """The main CLI dispatcher recognizes `risk`, not just the isolated
    parser this file otherwise tests against."""
    from sdlc.cli import build_parser

    args = build_parser().parse_args(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "k",
            "--disposition",
            "accepted_risk",
            "--reason",
            "r",
            "--by",
            "maks",
        ]
    )
    assert args.cmd == "risk"
    assert args.risk_cmd == "dispose"
