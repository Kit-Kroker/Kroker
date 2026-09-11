"""link_hook: relative links resolve against repo paths; dead targets raise."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs.link_hook import (
    BLOB_BASE,
    MissingLinkTarget,
    resolve_repo_path,
    rewrite_href,
    rewrite_markdown,
)


def test_resolve_joins_and_normalises():
    assert resolve_repo_path("docs/framework.md", "reference/foundation.md") == (
        "docs/reference/foundation.md"
    )
    assert resolve_repo_path("ARCHITECTURE.md", "docs/framework.md") == ("docs/framework.md")
    assert resolve_repo_path("src/sdlc/stages/qa/qa.md", "../../harness/base.py") == (
        "src/sdlc/harness/base.py"
    )


def test_rewrite_to_site_page_emits_md_relative_href(tmp_path: Path):
    # README (virtual, repo path README.md) links docs/framework.md, whose
    # site src_uri is framework.md (in-tree under docs_dir).
    pages = {"docs/framework.md": "framework.md", "README.md": "README.md"}
    out = rewrite_href("README.md", "README.md", "docs/framework.md", pages, tmp_path)
    assert out == "framework.md"

    # A stage contract links a sibling stage contract.
    pages = {
        "src/sdlc/stages/qa/qa.md": "src/sdlc/stages/qa/qa.md",
        "src/sdlc/stages/plan/plan.md": "src/sdlc/stages/plan/plan.md",
    }
    out = rewrite_href(
        "src/sdlc/stages/qa/qa.md",
        "src/sdlc/stages/qa/qa.md",
        "../plan/plan.md#clauses",
        pages,
        tmp_path,
    )
    assert out == "../plan/plan.md#clauses"


def test_rewrite_to_repo_file_emits_blob_url(tmp_path: Path):
    (tmp_path / "src" / "sdlc").mkdir(parents=True)
    (tmp_path / "src" / "sdlc" / "worker.py").write_text("x", encoding="utf-8")
    pages: dict[str, str] = {}
    out = rewrite_href("ARCHITECTURE.md", "ARCHITECTURE.md", "src/sdlc/worker.py", pages, tmp_path)
    assert out == BLOB_BASE + "src/sdlc/worker.py"


def test_image_targets_use_raw_url(tmp_path: Path):
    img = tmp_path / "docs" / "img.png"
    img.parent.mkdir()
    img.write_bytes(b"png")
    out = rewrite_href("docs/framework.md", "framework.md", "img.png", {}, tmp_path)
    assert out == "https://github.com/Kit-Kroker/Kroker/raw/main/docs/img.png"


def test_missing_target_raises(tmp_path: Path):
    with pytest.raises(MissingLinkTarget) as ei:
        rewrite_href("README.md", "README.md", "no/such/file.py", {}, tmp_path)
    assert ei.value.resolved == "no/such/file.py"


def test_pure_anchor_and_absolute_pass_through(tmp_path: Path):
    assert rewrite_href("README.md", "README.md", "#section", {}, tmp_path) == ("#section")
    assert (
        rewrite_href("README.md", "README.md", "https://example.com/x", {}, tmp_path)
        == "https://example.com/x"
    )


def test_rewrite_markdown_skips_fences_and_rewrites_links(tmp_path: Path):
    (tmp_path / "worker.py").write_text("x", encoding="utf-8")
    md = (
        "# T\n\nSee [worker](worker.py) and\n\n```\n[dead](nope.py)\n```\n\n"
        "and `code [span](nope.py)` stays.\n"
    )
    out = rewrite_markdown(md, "README.md", "README.md", {}, tmp_path)
    assert f"[worker]({BLOB_BASE}worker.py)" in out
    assert "[dead](nope.py)" in out  # inside a fence: untouched
    assert "code [span](nope.py)" in out  # no fence/inline-code awareness needed
