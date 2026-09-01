"""FR-913 (E-48): the deterministic packet the proposer judges."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.map import (
    GUARDRAIL_RULES,
    CandidateContext,
    DiscoverContext,
    GraphSummary,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
NC = Measurement.not_collected("upstream degraded")
GRAPH = GraphSummary(
    parsed=10, unparsed=2, edges=14, unresolved_relative_rate=Measurement.measured(0.0)
)


def _ctx(**kw):
    base = dict(
        candidate_id="C-01",
        name="payments",
        confidence=Confidence.HIGH,
        sources=("S3-payments",),
        source_rules=("s3_http_route",),
        members=(
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="api/pay.py"),
        ),
        member_paths=("api/pay.py",),
        cohesion=MEASURED,
        coupling=MEASURED,
        guardrail_only=False,
    )
    return CandidateContext(**(base | kw))


def test_the_context_never_carries_the_reference_graph():
    """DD4: DiscoverContext travels through workflow history to reach the
    proposer. An edge list in history is the open FR-702 hazard."""
    assert "reference_graph" not in DiscoverContext.model_fields
    assert DiscoverContext.model_fields["graph"].annotation is GraphSummary
    assert "edges" not in CandidateContext.model_fields


def test_guardrail_only_is_derived_from_the_source_rules():
    """DD6's input. Derived and asserted, so a deserialized payload cannot
    disagree with its own arithmetic -- AttributionReport.meets_floor's rule."""
    _ctx(source_rules=("s1_layer_name",), guardrail_only=True)
    _ctx(source_rules=("s1_layer_name", "s1_generic_name"), guardrail_only=True)
    _ctx(source_rules=("s1_layer_name", "s3_http_route"), guardrail_only=False)
    with pytest.raises(ValidationError, match="derived"):
        _ctx(source_rules=("s1_layer_name",), guardrail_only=False)
    with pytest.raises(ValidationError, match="derived"):
        _ctx(source_rules=("s3_http_route",), guardrail_only=True)


def test_a_candidate_with_no_source_rules_is_not_guardrail_only():
    """Vacuous truth is the wrong answer here: 'every rule is a layer rule'
    is true of no rules, and DE-SCOPEing a candidate we know nothing about
    would delete it on an absence of evidence."""
    _ctx(source_rules=(), guardrail_only=False)
    with pytest.raises(ValidationError, match="derived"):
        _ctx(source_rules=(), guardrail_only=True)


def test_guardrail_rules_are_exactly_s1s_two_non_domain_rules():
    assert GUARDRAIL_RULES == {"s1_layer_name", "s1_generic_name"}


def test_member_paths_are_sorted_and_deduped():
    _ctx(member_paths=("a.py", "b.py"))
    with pytest.raises(ValidationError, match="not sorted"):
        _ctx(member_paths=("b.py", "a.py"))


def test_an_uncollected_context_carries_no_candidates():
    """FR-915: a packet that could not be built has no rows."""
    DiscoverContext(collected=NC, graph=GRAPH)
    with pytest.raises(ValidationError, match="no candidates"):
        DiscoverContext(collected=NC, graph=GRAPH, candidates=(_ctx(),))


def test_a_collected_context_may_legitimately_have_no_candidates():
    """A tree with no capabilities is a measured zero, not a failure."""
    ctx = DiscoverContext(collected=Measurement.measured(0.0), graph=GRAPH)
    assert ctx.candidates == ()
