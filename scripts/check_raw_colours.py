"""The raw-colour gate (018 R-10, SC-004).

Components and stores under the two UI source trees may name colours and
fonts only through tokens: any hex literal, rgb(/rgba( function or
font-family name literal in a .vue or .ts file is a defect. This script
scans the trees, reports every hit as path:line and exits 1.

Exempt subtrees, matched as path segments: tokens/ (the palette itself),
api/mock/ (fixture data) and __fixtures__/ (generated dumps). A directory
merely containing one of those substrings is not exempt.

The gate is deliberately context-free: '#fade' inside a querySelector
string is flagged like any hex literal (qa-chaos pin, T003). Regex holes
carved for rare id-selector names are worse than a rename.

Runs as a step of scripts/check_ui.py (after the typecheck) and directly:
python scripts/check_raw_colours.py [root ...] — with no argument it
scans the two shipped source roots.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ROOTS = (
    "interfaces/ui/src",
    "interfaces/dashboard/frontend/src",
)

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB = re.compile(r"rgba?\(", re.IGNORECASE)
FONT = re.compile(r"""font-family\s*:\s*["'][^"']+["']""", re.IGNORECASE)

EXEMPT_SEGMENTS = frozenset({"tokens", "__fixtures__"})
EXEMPT_PAIRS = frozenset({("api", "mock")})

SCANNED_SUFFIXES = (".vue", ".ts")


def is_exempt(rel: Path) -> bool:
    """True inside an exempt subtree, matched as whole path segments."""
    parts = rel.parts
    if any(part in EXEMPT_SEGMENTS for part in parts):
        return True
    return any((parts[i], parts[i + 1]) in EXEMPT_PAIRS for i in range(len(parts) - 1))


def hits(line: str) -> bool:
    return bool(HEX.search(line) or RGB.search(line) or FONT.search(line))


def scan(root: Path) -> list[str]:
    """One path:line report per offending line, repo-relative posix paths."""
    reports: list[str] = []
    for suffix in SCANNED_SUFFIXES:
        for path in sorted(root.rglob(f"*{suffix}")):
            rel = path.relative_to(root)
            if is_exempt(rel):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if hits(line):
                    reports.append(f"{rel.as_posix()}:{lineno}")
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        default=DEFAULT_ROOTS,
        help="trees to scan (default: the two shipped UI source roots)",
    )
    args = parser.parse_args(argv)

    reports: list[str] = []
    for root in args.roots:
        reports.extend(scan(REPO_ROOT / root if not Path(root).is_absolute() else Path(root)))
    for report in reports:
        print(report)
    if reports:
        print(f"raw colours found: {len(reports)} hit(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
