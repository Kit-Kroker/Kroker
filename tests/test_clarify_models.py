"""E-85 taxonomy fields are ADDITIVE. A ClarifiedRequirements written before
E-85 must still validate, because `benchmark score --all` re-parses records
off disk and RunSummary.clarifications feeds the SC-4 rollup."""
import pytest
from pydantic import ValidationError

from sdlc.models import (ClarificationDimension, ClarificationOutcome,
                         ClarifiedRequirements, OpenQuestion)

PRE_E85_JSON = """
{"summary": "s",
 "functional_requirements": ["fr"],
 "non_functional_requirements": [],
 "out_of_scope": [],
 "open_questions": [{"id": "Q1", "question": "q?", "why_it_matters": "w"}]}
"""


def test_the_taxonomy_has_exactly_the_six_swe_rpg_dimensions():
    assert [d.value for d in ClarificationDimension] == [
        "C1", "C2", "C3", "C4", "C5", "C6"]


def test_a_pre_e85_artifact_still_validates():
    reqs = ClarifiedRequirements.model_validate_json(PRE_E85_JSON)
    assert reqs.open_questions[0].dimension is None
    assert reqs.dimensions_probed == []
    assert reqs.dropped == []


def test_new_question_fields_default_to_none():
    q = OpenQuestion(id="Q1", question="q?", why_it_matters="w")
    assert (q.dimension, q.asked_by, q.materiality, q.evidence) == (
        None, None, None, None)


def test_a_question_can_carry_its_dimension_and_provenance():
    q = OpenQuestion(id="Q1", question="q?", why_it_matters="w",
                     dimension=ClarificationDimension.INTERFACE_SPEC,
                     asked_by="probe:C4", materiality=0.9,
                     evidence="src/api/routes.py")
    assert q.dimension is ClarificationDimension.INTERFACE_SPEC
    assert q.materiality == 0.9


def test_materiality_is_bounded_to_the_unit_interval():
    with pytest.raises(ValidationError):
        OpenQuestion(id="Q1", question="q?", why_it_matters="w",
                     materiality=1.5)


def test_clarification_outcome_carries_an_optional_dimension():
    o = ClarificationOutcome(question_id="Q1", question="q?",
                             answered_by="human")
    assert o.dimension is None
