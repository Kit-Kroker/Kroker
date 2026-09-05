"""Clause coverage report (spec A §9). Advisory: always exits 0.

Not a gate, deliberately. Kroker implements criterion->test traceability as a
PRODUCT feature (untraced_criteria, feature.py:528, FR-106), and B0 §4 bans
repurposing product machinery as this repo's own dev harness without a
decision that says so. Enforcing before two pilot slices have produced a
single clause would cross that line on speculation. If the pilots' report is
consistently empty and consistently useful, promoting this to a gate is three
lines in .pre-commit-config.yaml.
"""

from __future__ import annotations

import pathlib
import re

HEADING = re.compile(r"^#{2,4}\s+([A-Z][A-Z0-9_]*-\d+(?:\.\d+)*)\b")
MARKER = re.compile(r"""@pytest\.mark\.clause\(\s*["']([^"']+)["']""")
UI_MARKER = re.compile(r"//\s*clause:\s*([A-Z][A-Z0-9_]*-\d+(?:\.\d+)*)")

# rglob would otherwise walk an installed dependency tree and the generated
# preview bundle, which contain neither clauses nor citations.
_SKIP = {"node_modules", "dist", "dist-ds", ".vite", "coverage"}


def is_scannable(path: pathlib.Path) -> bool:
    return not any(part in _SKIP for part in path.parts)


def clause_ids_in_doc(path: pathlib.Path) -> set[str]:
    return {
        m.group(1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if (m := HEADING.match(line))
    }


def clause_ids_in_tests(root: pathlib.Path) -> set[str]:
    return {
        m for p in root.rglob("test_*.py") for m in MARKER.findall(p.read_text(encoding="utf-8"))
    }


def clause_ids_in_ui_tests(root: pathlib.Path) -> set[str]:
    ids: set[str] = set()
    for pattern in ("*.spec.ts", "*.pw.ts"):
        for p in root.rglob(pattern):
            if is_scannable(p):
                ids |= set(UI_MARKER.findall(p.read_text(encoding="utf-8")))
    return ids


def orphans(declared: set[str], cited: set[str]) -> tuple[set[str], set[str]]:
    """(clauses with no test, tests citing a clause that does not exist)."""
    return declared - cited, cited - declared


def main() -> int:
    declared: set[str] = set()
    for doc in pathlib.Path("src/sdlc/stages").rglob("*.md"):
        if doc.name != "AGENTS.md":
            declared |= clause_ids_in_doc(doc)
    for doc in pathlib.Path("interfaces").rglob("*.md"):
        if doc.name != "AGENTS.md" and is_scannable(doc):
            declared |= clause_ids_in_doc(doc)

    cited = clause_ids_in_tests(pathlib.Path("tests")) | clause_ids_in_ui_tests(
        pathlib.Path("interfaces")
    )
    untested, dangling = orphans(declared, cited)
    for cid in sorted(untested):
        print(f"clause with no test: {cid}")
    for cid in sorted(dangling):
        print(f"test cites unknown clause: {cid}")
    print(f"{len(declared)} clauses declared, {len(untested)} untested, {len(dangling)} dangling")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
