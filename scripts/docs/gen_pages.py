"""gen-files entry point: pull living sources in as virtual pages.

The living docs stay where co-location requires them to be (root, stage
folders); mkdocs sees virtual copies at their repo-relative paths, so links
between them resolve exactly as they do on GitHub (spec §3). Nothing here is
written to the working tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

# mkdocs-gen-files execs this file without the repo root on sys.path (CI runs
# the `mkdocs` console script), so the sibling generators under scripts/docs/
# need the root added before they are importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import mkdocs_gen_files  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

ROOT_DOCS = [
    "README.md",
    "PRD.md",
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "BENCHMARK.md",
    "SDLC-spec-v2.md",
]

STAGE_CONTRACTS = sorted(
    str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "src" / "sdlc" / "stages").glob("*/*.md")
)


def pull_virtual(repo_rel: str) -> None:
    """Register a virtual copy of a repo file at its repo-relative path."""
    src = REPO_ROOT / repo_rel
    with mkdocs_gen_files.open(repo_rel, "w", encoding="utf-8") as f:
        f.write(src.read_text(encoding="utf-8"))


def generate() -> None:
    for repo_rel in ROOT_DOCS:
        pull_virtual(repo_rel)
    for repo_rel in STAGE_CONTRACTS:
        pull_virtual(repo_rel)

    from scripts.docs import roadmap_board

    board = roadmap_board.parse_board(roadmap_board.board_sources(REPO_ROOT))
    with mkdocs_gen_files.open(roadmap_board.BOARD_PAGE, "w", encoding="utf-8") as f:
        f.write(roadmap_board.render_board(board))

    from scripts.docs import agent_registry

    roles = agent_registry.read_roles(REPO_ROOT / "agents")
    crew = agent_registry.read_crew(REPO_ROOT / "crew" / "roles")
    with mkdocs_gen_files.open(agent_registry.REGISTRY_PAGE, "w", encoding="utf-8") as f:
        f.write(agent_registry.render_registry(roles, crew))


generate()
