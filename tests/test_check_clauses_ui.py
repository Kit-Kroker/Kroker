"""The clause report reaches the UI tree (spec C §4).

018 T049: retargeted from stage_dots (deleted with the strip, S6) to
status_pip — a surviving component — exactly as the ds-bundle spec was.
"""

import pathlib

from scripts.check_clauses import (
    UI_MARKER,
    clause_ids_in_doc,
    clause_ids_in_ui_tests,
    is_scannable,
)


def test_finds_the_status_pip_clauses():
    doc = pathlib.Path("interfaces/ui/src/components/status_pip/status_pip.md")
    assert clause_ids_in_doc(doc), "status_pip.md declares no clauses"


def test_finds_a_same_line_citation():
    assert UI_MARKER.findall("  it('x', () => {})  // clause: STATUS_PIP-2") == ["STATUS_PIP-2"]


def test_ignores_node_modules_and_build_output():
    assert not is_scannable(pathlib.Path("interfaces/ui/node_modules/pkg/readme.md"))
    assert not is_scannable(pathlib.Path("interfaces/ui/dist-ds/status_pip/empty.html"))
    assert is_scannable(pathlib.Path("interfaces/ui/src/components/status_pip/status_pip.md"))


def test_ui_clauses_are_cited_somewhere():
    declared = clause_ids_in_doc(
        pathlib.Path("interfaces/ui/src/components/status_pip/status_pip.md")
    )
    cited = clause_ids_in_ui_tests(pathlib.Path("interfaces"))
    assert declared - cited == set(), f"uncited UI clauses: {sorted(declared - cited)}"
