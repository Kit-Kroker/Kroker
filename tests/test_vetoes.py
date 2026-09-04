"""The veto engine: rubric criteria that state an absolute override.

Three rubrics on disk say a component "scores 0 regardless of how good the
rest is". A mean-of-components LLM judge structurally cannot express that,
and rubric-qa.md:15's veto is a boolean over three typed fields. These run
deterministically, with zero model calls."""

import pytest
from pydantic import BaseModel

from sdlc.benchmarks.vetoes import VetoConfigError, check, parse_vetoes, validate_fields

CLARIFY_YAML = """
- id: scope_preserved
  kind: mentions_all
  terms: [sleeping, eating, drinking, litter box, playing, fighting]
  fields: [functional_requirements, open_questions]
"""

QA_YAML = """
- id: internal_consistency
  kind: not_both
  field: tests_passed
  equals: true
  and_any_nonempty: [failing_tests, issues]
"""


def test_mentions_all_passes_when_every_term_present():
    artifact = {
        "functional_requirements": [
            "detect sleeping, eating and drinking",
            "detect litter box, playing and fighting",
        ],
        "open_questions": [],
    }
    assert check(artifact, parse_vetoes(CLARIFY_YAML)) == []


def test_mentions_all_fails_and_names_the_missing_terms():
    artifact = {"functional_requirements": ["detect sleeping and eating"], "open_questions": []}
    failures = check(artifact, parse_vetoes(CLARIFY_YAML))
    assert len(failures) == 1
    assert failures[0].veto_id == "scope_preserved"
    assert "drinking" in failures[0].reason
    assert "fighting" in failures[0].reason
    assert "sleeping" not in failures[0].reason  # present, not reported


def test_mentions_all_is_case_insensitive():
    artifact = {
        "functional_requirements": ["SLEEPING, Eating, DRINKING, Litter Box, playing, FIGHTING"],
        "open_questions": [],
    }
    assert check(artifact, parse_vetoes(CLARIFY_YAML)) == []


def test_mentions_all_does_not_match_substrings_of_other_words():
    """Bare substring matching made 'eating' match 'creating', 'red' match
    'required', 'playing' match 'replaying'. A veto that passes on those is a
    false negative -- it was the hole that made the scope_dropped OQ-P5 result
    unreliable (E-83 review)."""
    artifact = {
        "functional_requirements": [
            "creating the required replay logic; sleeping; drinking; litter box; fighting"
        ],
        "open_questions": [],
    }
    failures = check(artifact, parse_vetoes(CLARIFY_YAML))
    ids = [f.veto_id for f in failures]
    assert ids == ["scope_preserved"]
    reason = failures[0].reason
    assert "eating" in reason and "red" in reason and "playing" in reason
    # 'sleeping' / 'drinking' / 'litter box' / 'fighting' ARE genuinely
    # present as words, so they must NOT be reported missing.
    assert "sleeping" not in reason
    assert "drinking" not in reason


def test_mentions_all_with_no_fields_searches_the_whole_artifact():
    vetoes = parse_vetoes("- id: v\n  kind: mentions_all\n  terms: [alpha]\n")
    assert check({"anything": {"nested": "alpha"}}, vetoes) == []
    assert len(check({"anything": "beta"}, vetoes)) == 1


def test_not_both_fails_on_the_contradiction():
    artifact = {"tests_passed": True, "failing_tests": ["t::a"], "issues": []}
    failures = check(artifact, parse_vetoes(QA_YAML))
    assert len(failures) == 1
    assert failures[0].veto_id == "internal_consistency"
    assert "failing_tests" in failures[0].reason


def test_not_both_passes_when_the_trigger_field_does_not_match():
    artifact = {"tests_passed": False, "failing_tests": ["t::a"], "issues": []}
    assert check(artifact, parse_vetoes(QA_YAML)) == []


def test_not_both_passes_when_all_listed_fields_are_empty():
    artifact = {"tests_passed": True, "failing_tests": [], "issues": []}
    assert check(artifact, parse_vetoes(QA_YAML)) == []


def test_nonempty_fails_on_an_empty_field():
    vetoes = parse_vetoes("- id: v\n  kind: nonempty\n  fields: [summary]\n")
    assert len(check({"summary": ""}, vetoes)) == 1
    assert len(check({"summary": "   "}, vetoes)) == 1
    assert check({"summary": "real"}, vetoes) == []


def test_nonempty_fails_on_a_missing_field():
    """A field the artifact does not carry cannot be non-empty. Treating
    absence as a pass would make the veto vacuous."""
    vetoes = parse_vetoes("- id: v\n  kind: nonempty\n  fields: [summary]\n")
    assert len(check({}, vetoes)) == 1


def test_unknown_kind_is_a_config_error():
    with pytest.raises(VetoConfigError) as e:
        parse_vetoes("- id: v\n  kind: vibes\n")
    assert "vibes" in str(e.value)


def test_malformed_yaml_is_a_config_error():
    with pytest.raises(VetoConfigError):
        parse_vetoes("- id: v\n  kind: mentions_all\n")  # terms missing


def test_empty_text_yields_no_vetoes():
    assert parse_vetoes("") == []


class _Output(BaseModel):
    tests_passed: bool
    failing_tests: list[str] = []
    issues: list[str] = []


def test_validate_fields_accepts_known_fields():
    validate_fields(parse_vetoes(QA_YAML), _Output)


def test_validate_fields_rejects_an_unknown_field():
    bad = parse_vetoes("- id: v\n  kind: nonempty\n  fields: [not_a_field]\n")
    with pytest.raises(VetoConfigError) as e:
        validate_fields(bad, _Output)
    assert "not_a_field" in str(e.value)


def test_shipped_veto_files_parse_and_match_their_output_types():
    """The two authored veto files must parse AND name only real fields.

    This is the load-time check the design puts ahead of judge time, run
    against the real ClarifiedRequirements and QAReport."""
    from pathlib import Path

    from sdlc.stages.clarify.models import ClarifiedRequirements
    from sdlc.stages.qa.models import QAReport

    case = Path(__file__).resolve().parents[1] / "benchmarks" / "cases" / "cat-cafe-monitoring"
    for filename, output_type in (
        ("vetoes-clarifier.yaml", ClarifiedRequirements),
        ("vetoes-qa.yaml", QAReport),
    ):
        vetoes = parse_vetoes((case / filename).read_text(encoding="utf-8"))
        assert vetoes, f"{filename} declares no vetoes"
        validate_fields(vetoes, output_type)


def test_case_yaml_registers_both_veto_files():
    from pathlib import Path

    import yaml as _yaml

    case = Path(__file__).resolve().parents[1] / "benchmarks" / "cases" / "cat-cafe-monitoring"
    data = _yaml.safe_load((case / "case.yaml").read_text(encoding="utf-8"))
    assert data["vetoes"] == {"clarifier": "vetoes-clarifier.yaml", "qa": "vetoes-qa.yaml"}
    for rel in data["vetoes"].values():
        assert (case / rel).is_file()
