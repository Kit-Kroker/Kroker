from scripts.check_clauses import clause_ids_in_doc, orphans


def test_clause_ids_are_parsed_from_headings(tmp_path):
    doc = tmp_path / "clarify.md"
    doc.write_text("## CLARIFY-1 Routing\n\n### CLARIFY-1.1 [FR-101]\ntext\n", encoding="utf-8")
    assert clause_ids_in_doc(doc) == {"CLARIFY-1", "CLARIFY-1.1"}


def test_orphans_reports_both_directions():
    declared = {"CLARIFY-1.1", "CLARIFY-1.2"}
    cited = {"CLARIFY-1.1", "CLARIFY-9.9"}
    untested, dangling = orphans(declared, cited)
    assert untested == {"CLARIFY-1.2"}
    assert dangling == {"CLARIFY-9.9"}
