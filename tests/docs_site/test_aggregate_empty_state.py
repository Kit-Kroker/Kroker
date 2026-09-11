"""aggregate/build_html: absent or empty runs render an explicit empty state.

Pure-Python module under test — no mkdocs, so this runs in the default
fast tier.
"""

from __future__ import annotations

from pathlib import Path

from scripts.aggregate_benchmarks import (
    EMPTY_MESSAGE,
    aggregate,
    build_html,
)


def test_missing_runs_dir_returns_empty_dataset(tmp_path: Path):
    assert aggregate(tmp_path / "nope") == {}


def test_empty_runs_dir_returns_empty_dataset(tmp_path: Path):
    (tmp_path / "runs").mkdir()
    assert aggregate(tmp_path / "runs") == {}


def test_build_html_empty_state():
    html = build_html({})
    assert EMPTY_MESSAGE in html
    assert "Chart" not in html  # no dead chart scaffolding on the empty page
