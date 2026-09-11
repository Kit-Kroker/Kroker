"""The built site contains exactly the v1 page set (spec §9.3).

Needs mkdocs, so it skips in the default dev install and runs in the
docs CI job (which installs .[dev,docs]).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mkdocs")

REPO = Path(__file__).resolve().parents[2]


def _build(site_dir: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", str(site_dir)],
        cwd=REPO,
        check=True,
    )


def _built_sources(site_dir: Path) -> list[str]:
    # mkdocs writes a <page>/index.html per page at its src path; the
    # top-level virtual README.md becomes the site root index.html.
    return [
        p.parent.relative_to(site_dir).as_posix() if p.parent != site_dir else "."
        for p in site_dir.rglob("index.html")
    ]


def test_strict_build_page_set(tmp_path: Path):
    site = tmp_path / "site"
    _build(site)
    sources = _built_sources(site)
    assert "ARCHITECTURE" in sources
    assert "src/sdlc/stages/qa/qa" in sources
    assert "templates/stage-AGENTS" in sources  # !templates/ beats the default
    assert "." in sources  # README renders as the site root
    forbidden = [s for s in sources if s.startswith(("superpowers", "reports", "schemas"))]
    assert forbidden == []
    assert not [s for s in sources if "AGENTS" in s and s != "templates/stage-AGENTS"]
    # Repo-file links become GitHub blob URLs after the hook rewrites them
    # (README's own schema-page links left with the P3 cutover, so assert on
    # a page that links out of the site — the roadmap board's source column).
    board_html = (site / "generated" / "roadmap-board" / "index.html").read_text(encoding="utf-8")
    assert "github.com/Kit-Kroker/Kroker/blob/main/" in board_html


def test_benchmark_page_empty_state_in_build(tmp_path: Path):
    """Without runs/, the site renders the benchmark empty state (spec §9.2)
    linking to the one dated snapshot let through by exclude_docs (§9.7)."""
    from scripts.aggregate_benchmarks import EMPTY_MESSAGE

    site = tmp_path / "site"
    _build(site)
    page = site / "generated" / "benchmark-analysis" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert EMPTY_MESSAGE in html
    assert "reports/2026-08-15-benchmark-analysis.html" in html
    reports = list((site / "reports").iterdir())
    assert [p.name for p in reports] == ["2026-08-15-benchmark-analysis.html"]
    assert not (site / "generated" / "benchmark-analysis.html").exists()
