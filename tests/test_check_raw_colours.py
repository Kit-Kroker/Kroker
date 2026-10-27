"""Contract tests for scripts/check_raw_colours.py (018 T003).

The script is the raw-colour gate (SC-004, R-10): given a tree root it
scans ``.vue`` and ``.ts`` files for hex, ``rgb(``, ``rgba(`` and
font-family literals, exempts ``tokens/``, ``api/mock/`` and
``__fixtures__/`` subtrees, exits 1 on any hit, and reports each hit as
``path:line``. RED (T003): the script does not exist yet; T004 creates
it and the raw-colour sweep (T005) makes it pass on the real tree.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_raw_colours.py"

OFFENDING_VUE_HEX = "<style scoped>\n.card { color: #fff; }\n</style>\n"
OFFENDING_TS_RGBA = "export const tint = 'rgba(1, 2, 3, 0.5)';\n"
OFFENDING_VUE_FONT = (
    "<style scoped>\n.card { font-family: 'IBM Plex Sans', sans-serif; }\n</style>\n"
)


def run_check(tree: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(tree)],
        capture_output=True,
        text=True,
        check=False,
    )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_vue_hex_literal_fails_with_path_line(tmp_path: Path) -> None:
    write(tmp_path / "interfaces" / "ui" / "src" / "components" / "Card.vue", OFFENDING_VUE_HEX)
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert re.search(r"Card\.vue:\d+", result.stdout), result.stdout


def test_ts_rgba_literal_fails_with_path_line(tmp_path: Path) -> None:
    path = write(
        tmp_path / "interfaces" / "dashboard" / "frontend" / "src" / "shared" / "tint.ts",
        OFFENDING_TS_RGBA,
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    rel = re.escape(path.relative_to(tmp_path).as_posix())
    assert re.search(rel + r":\d+", result.stdout), result.stdout


def test_vue_font_family_name_fails_with_path_line(tmp_path: Path) -> None:
    write(
        tmp_path / "interfaces" / "dashboard" / "frontend" / "src" / "components" / "Card.vue",
        OFFENDING_VUE_FONT,
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert re.search(r"Card\.vue:\d+", result.stdout), result.stdout


def test_exempt_dirs_pass(tmp_path: Path) -> None:
    offenders = {
        "interfaces/ui/src/tokens/accent.ts": "export const c = '#ffffff';\n",
        "interfaces/dashboard/frontend/src/api/mock/rows.ts": (
            "export const c = 'rgba(9, 9, 9, 0.9)';\n"
        ),
        "interfaces/dashboard/frontend/src/api/__fixtures__/demo.vue": OFFENDING_VUE_FONT,
        "interfaces/ui/src/tokens/legacy.vue": OFFENDING_VUE_HEX,
    }
    for rel, text in offenders.items():
        write(tmp_path / rel, text)
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_ts_rgb_literal_fails_with_path_line(tmp_path: Path) -> None:
    # R-10: the gate fails on rgb( (no alpha) too, not only rgba(.
    path = write(
        tmp_path / "interfaces" / "ui" / "src" / "composables" / "tint.ts",
        "export const tint = 'rgb(1, 2, 3)';\n",
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    rel = re.escape(path.relative_to(tmp_path).as_posix())
    assert re.search(rel + r":\d+", result.stdout), result.stdout


def test_uppercase_hex_literal_fails(tmp_path: Path) -> None:
    # CSS hex is case-insensitive; #FFF must hit the same gate as #fff.
    write(
        tmp_path / "interfaces" / "ui" / "src" / "components" / "Card.vue",
        OFFENDING_VUE_HEX.upper(),
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert re.search(r"Card\.vue:\d+", result.stdout), result.stdout


def test_all_offenders_reported_across_files(tmp_path: Path) -> None:
    # Every hit is reported as path:line — not only the first one found.
    first = write(
        tmp_path / "interfaces" / "ui" / "src" / "components" / "Card.vue", OFFENDING_VUE_HEX
    )
    second = write(
        tmp_path / "interfaces" / "dashboard" / "frontend" / "src" / "shared" / "tint.ts",
        OFFENDING_TS_RGBA,
    )
    third = write(
        tmp_path / "interfaces" / "ui" / "src" / "components" / "Badge.vue", OFFENDING_VUE_FONT
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    for path in (first, second, third):
        rel = re.escape(path.relative_to(tmp_path).as_posix())
        assert re.search(rel + r":\d+", result.stdout), result.stdout


def test_exemption_is_path_segment_not_substring(tmp_path: Path) -> None:
    # Exempt dirs match as path segments: a sibling dir merely containing
    # the substring ("tokensExtra") is NOT exempt.
    path = write(
        tmp_path / "interfaces" / "ui" / "src" / "tokensExtra" / "x.vue", OFFENDING_VUE_HEX
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    rel = re.escape(path.relative_to(tmp_path).as_posix())
    assert re.search(rel + r":\d+", result.stdout), result.stdout


def test_hex_like_id_selector_still_fails(tmp_path: Path) -> None:
    # Pinned: the gate stays context-free — '#fade' in a querySelector is
    # flagged like any hex literal; rename the id or tokenise, regex holes
    # are worse than a rare rename (T004 must not grow context rules).
    path = write(
        tmp_path / "interfaces" / "ui" / "src" / "composables" / "focus.ts",
        "export const focusCard = () => document.querySelector('#fade');\n",
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    rel = re.escape(path.relative_to(tmp_path).as_posix())
    assert re.search(rel + r":\d+", result.stdout), result.stdout


def test_ts_font_family_other_name_fails(tmp_path: Path) -> None:
    # R-10: any font-family name literal fails, not just IBM Plex Sans.
    path = write(
        tmp_path / "interfaces" / "ui" / "src" / "composables" / "mono.ts",
        "export const mono = 'font-family: \"IBM Plex Mono\", monospace';\n",
    )
    result = run_check(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    rel = re.escape(path.relative_to(tmp_path).as_posix())
    assert re.search(rel + r":\d+", result.stdout), result.stdout


def test_clean_tree_passes(tmp_path: Path) -> None:
    write(
        tmp_path / "interfaces" / "ui" / "src" / "components" / "Card.vue",
        "<style scoped>\n.card { color: var(--ink-primary); }\n</style>\n",
    )
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
