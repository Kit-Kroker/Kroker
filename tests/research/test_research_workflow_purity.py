"""009 D4 (FR-002, A4): the research retain path names no file access.

Workflow code must not read the verify stage's page files: replay then
depends on host disk state. This pins step.py and retain.py to that rule
statically — a whole identifier equal to a verifier file helper (or `os`,
`Path`, `open`) is a defect, however it got there. Identifiers are compared
whole, never by substring: `verify_brief_activity` is allowed.
"""

from __future__ import annotations

import ast
from pathlib import Path

STAGE = Path(__file__).resolve().parents[2] / "src" / "sdlc" / "stages" / "research"
STEP = STAGE / "step.py"
RETAIN = STAGE / "retain.py"

BANNED_IDENTIFIERS = {
    "verify_brief",
    "pages_dir",
    "page_filename",
    "write_page",
    "open",
    "Path",
    "os",
}

# step.py may import these two names from .verify; nothing else.
STEP_VERIFY_IMPORT_ALLOWLIST = {"brief_digest", "verify_brief_activity"}


def _identifier_findings(path: Path) -> list[str]:
    """Banned whole identifiers: a Name, an attribute, an imported name/alias."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in BANNED_IDENTIFIERS:
            out.append(f"{path.name}:{node.lineno}: banned identifier {node.id!r} (name)")
        if isinstance(node, ast.Attribute) and node.attr in BANNED_IDENTIFIERS:
            out.append(f"{path.name}:{node.lineno}: banned identifier {node.attr!r} (attribute)")
        if isinstance(node, ast.alias):
            names = [node.name, node.asname] if node.asname else [node.name]
            for name in names:
                if name in BANNED_IDENTIFIERS:
                    out.append(f"{path.name}:{node.lineno}: banned identifier {name!r} (import)")
    return out


def _verify_imports(path: Path) -> list[str]:
    """Names imported via `from .verify import ...`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level >= 1 and node.module == "verify":
            out.extend(alias.name for alias in node.names)
    return out


def test_retain_names_no_file_access():
    assert _identifier_findings(RETAIN) == []


def test_step_names_no_file_access():
    assert _identifier_findings(STEP) == []


def test_retain_imports_nothing_from_verify():
    assert _verify_imports(RETAIN) == []


def test_step_verify_imports_only_the_allowed_names():
    imported = _verify_imports(STEP)
    assert set(imported) <= STEP_VERIFY_IMPORT_ALLOWLIST


def test_the_lint_catches_a_banned_name(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from .verify import verify_brief\n", encoding="utf-8")
    assert _identifier_findings(bad)
    assert _verify_imports(bad) == ["verify_brief"]


def test_the_lint_spares_verify_brief_activity(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("x = verify_brief_activity\n", encoding="utf-8")
    assert _identifier_findings(good) == []
    assert _verify_imports(good) == []
