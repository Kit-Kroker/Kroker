"""Stage-internal types. ClarifyRoute is the supervisor's output and
ProbeResult one probe's; merge folds both into ClarifiedRequirements. Neither
is ever persisted or shown to a human."""

from sdlc.clarify.models import ClarifyRoute, ProbeResult
from sdlc.core.models import (
    ClarificationDimension,
)
from sdlc.models import (
    OpenQuestion,
)

C4 = ClarificationDimension.INTERFACE_SPEC


def test_a_route_with_no_live_dimensions_is_valid():
    # A one-line CSS tweak should route to zero probes. That is the primary
    # cost control, so it must not be an error.
    route = ClarifyRoute(
        summary="s",
        functional_requirements=["fr"],
        non_functional_requirements=[],
        out_of_scope=[],
        questions=[],
        live_dimensions=[],
    )
    assert route.live_dimensions == []


def test_a_probe_that_abstains_returns_an_empty_question_list():
    # is_ambiguous() == 0 is a valid, expected answer -- not a failure.
    assert ProbeResult(dimension=C4, questions=[]).questions == []


def test_a_probe_carries_its_own_dimension_back():
    # merge attributes questions by the ProbeResult's dimension, so it must
    # survive the round trip even if the model omitted it per question.
    p = ProbeResult(
        dimension=C4, questions=[OpenQuestion(id="P1", question="q?", why_it_matters="w")]
    )
    assert p.dimension is C4


def test_route_defaults_keep_the_body_lists_present():
    route = ClarifyRoute(summary="s")
    assert route.functional_requirements == []
    assert route.questions == []
