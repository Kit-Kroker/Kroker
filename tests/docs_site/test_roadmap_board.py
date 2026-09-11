"""roadmap_board: checkbox → status, keyed by the bold id; bad lines raise."""

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
- — **OQ-9** not measurable here.

## 5. User stories

- [x] **US-2** approve spec.
"""

MD_BAD = MD.replace(
    "- [x] **FR-101** thing one — with a dash.\n",
    "- [x] plain bullet without a bold id.\n- [x] **FR-101** thing one — with a dash.\n",
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
        "US-2": "done",
    }
    first = board[0].items[0]
    assert first.source == "ROADMAP.md"
    assert first.line == 5
    assert first.title.startswith("thing one")


def test_marker_without_bold_id_raises():
    with pytest.raises(UnparseableStatusLine) as ei:
        parse_board({"ROADMAP.md": MD_BAD})
    assert ei.value.line == 5


def test_bold_ids_like_stage_numbers_parse():
    board = parse_board({"docs/roadmap/x.md": "- [ ] ⚠️ **12 · quality_gate** — mostly built.\n"})
    assert board[0].items[0].id == "12 · quality_gate"
    assert board[0].items[0].status == "partial"
