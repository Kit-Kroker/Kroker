"""The clause report reaches the UI tree (spec C §4)."""

import pathlib

from scripts.check_clauses import (
    UI_MARKER,
    clause_ids_in_doc,
    clause_ids_in_ui_tests,
    is_scannable,
)


def test_finds_the_stage_dots_clauses():
    doc = pathlib.Path("interfaces/ui/src/components/stage_dots/stage_dots.md")
    assert "STAGE_DOTS-1.2" in clause_ids_in_doc(doc)


def test_finds_a_same_line_citation():
    assert UI_MARKER.findall("  it('x', () => {})  // clause: STAGE_DOTS-2") == ["STAGE_DOTS-2"]


def test_ignores_node_modules_and_build_output():
    assert not is_scannable(pathlib.Path("interfaces/ui/node_modules/pkg/readme.md"))
    assert not is_scannable(pathlib.Path("interfaces/ui/dist-ds/stage_dots/empty.html"))
    assert is_scannable(pathlib.Path("interfaces/ui/src/components/stage_dots/stage_dots.md"))


def test_ui_clauses_are_cited_somewhere():
    declared = clause_ids_in_doc(
        pathlib.Path("interfaces/ui/src/components/stage_dots/stage_dots.md")
    )
    cited = clause_ids_in_ui_tests(pathlib.Path("interfaces"))
    assert declared - cited == set(), f"uncited UI clauses: {sorted(declared - cited)}"
