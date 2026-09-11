"""roadmap_board: checkbox → status, keyed by the bold id; bad markers raise."""

from __future__ import annotations

import pytest

from scripts.docs.roadmap_board import (
    UnparseableStatusLine,
    parse_board,
)

MD = """# Roadmap

## 2. Stages

- [x] **FR-101** thing one — with a dash.
- [ ] ⚠️ **FR-102** thing two is partial.
- [ ] **FR-103** thing three not started.
- — **OQ-9** not measurable here (bare dash).
- [ ] — **NFR-9** not measurable here (bracket plus governing dash).
- [x] ✅ **FR-104** done, with a checkmark decoration.

## 5. User stories

- [x] **US-2** approve spec.
"""

MD_BAD = MD.replace(
    "- [x] **FR-101** thing one — with a dash.\n",
    "- [~] **FR-101** thing one — with a dash.\n",
)


def test_parses_all_four_statuses_and_sections():
    board = parse_board({"ROADMAP.md": MD})
    assert [s.title for s in board] == ["2. Stages", "5. User stories"]
    items = {i.id: i.status for s in board for i in s.items}
    assert items == {
        "FR-101": "done",
        "FR-102": "partial",
        "FR-103": "notstarted",
        "OQ-9": "notmeasurable",
        "NFR-9": "notmeasurable",
        "FR-104": "done",
        "US-2": "done",
    }
    first = board[0].items[0]
    assert first.source == "ROADMAP.md"
    assert first.line == 5
    assert first.title.startswith("thing one")


def test_unknown_bracket_marker_raises():
    with pytest.raises(UnparseableStatusLine) as ei:
        parse_board({"ROADMAP.md": MD_BAD})
    assert ei.value.line == 5


def test_idless_status_lines_are_commentary_not_items():
    board = parse_board(
        {
            "ROADMAP.md": (
                "- [ ] ⚠️ Layered `src/factory/` tree — aspirational, no id.\n"
                "- [x] **FR-1** real item.\n"
            )
        }
    )
    assert [i.id for s in board for i in s.items] == ["FR-1"]


def test_bold_ids_like_stage_numbers_parse():
    board = parse_board({"docs/roadmap/x.md": "- [ ] ⚠️ **12 · quality_gate** — built.\n"})
    assert board[0].items[0].id == "12 · quality_gate"
    assert board[0].items[0].status == "partial"


def test_render_board_tables_and_totals():
    from scripts.docs.roadmap_board import render_board

    board = parse_board({"ROADMAP.md": MD})
    md = render_board(board)
    assert "| Id | Status | Title | Source |" in md
    assert "| **FR-101** | done |" in md
    assert "[ROADMAP.md:5](https://github.com/Kit-Kroker/Kroker/blob/main/ROADMAP.md#L5)" in md
    assert "| done | 3 |" in md.split("## Totals")[1]
    assert "| notmeasurable | 2 |" in md.split("## Totals")[1]


def test_board_parity_against_real_sources():
    """Spec §9.4: board totals equal an independent recount of the sources."""
    import re
    from pathlib import Path

    from scripts.docs.roadmap_board import board_sources, parse_board, render_board

    repo = Path(__file__).resolve().parents[2]
    texts = board_sources(repo)
    totals: dict[str, int] = {}
    # Independent recount: naive per-line marker count. The dash forms (bare
    # and bracket-plus-dash) both count as notmeasurable. Every branch
    # requires the bold id — id-less commentary checkboxes (ROADMAP §14)
    # are not board items.
    for text in texts.values():
        for line in text.splitlines():
            if re.match(r"^\s*[-*]\s+\[x\]\s*✅?\s*\*\*", line):
                totals["done"] = totals.get("done", 0) + 1
            elif re.match(r"^\s*[-*]\s+\[\s\]\s*⚠️\s*\*\*", line):
                totals["partial"] = totals.get("partial", 0) + 1
            elif re.match(r"^\s*[-*]\s+(—|\[\s\]\s+—)\s*\*\*", line):
                totals["notmeasurable"] = totals.get("notmeasurable", 0) + 1
            elif re.match(r"^\s*[-*]\s+\[\s\]\s*(✅\s*)?\*\*", line):
                totals["notstarted"] = totals.get("notstarted", 0) + 1
    board = parse_board(texts)
    md = render_board(board)
    for status, count in totals.items():
        assert f"| {status} | {count} |" in md, (status, count)
