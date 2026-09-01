"""Which probes may run, per project mode. Pure -- no model, no I/O.

C3 and C5 are skipped in greenfield because there is no existing architecture
or convention for a requirement to be ambiguous AGAINST: a C5 probe on an
empty tree can only ask which conventions we should adopt, which authors a
decision rather than resolving an ambiguity (E-85 D5)."""

from sdlc.clarify.routing import (
    PROBE_DIMENSIONS,
    SUPERVISOR_DIMENSIONS,
    grounded_dimensions,
    live_dimensions,
    permitted_dimensions,
)
from sdlc.models import ClarificationDimension as CD
from sdlc.models import ProjectMode

ALL = list(CD)


def test_the_supervisor_owns_c1_and_c2_and_nothing_else():
    assert SUPERVISOR_DIMENSIONS == (CD.FUNCTIONAL_INTENT, CD.BUSINESS_SEMANTICS)


def test_probes_own_the_other_four():
    assert PROBE_DIMENSIONS == (
        CD.TECHNICAL_CONTEXT,
        CD.INTERFACE_SPEC,
        CD.CODE_STRUCTURE,
        CD.DATA_SEMANTICS,
    )


def test_the_two_sets_do_not_overlap():
    assert not set(SUPERVISOR_DIMENSIONS) & set(PROBE_DIMENSIONS)


def test_brownfield_permits_all_four_probe_dimensions():
    assert permitted_dimensions(ProjectMode.BROWNFIELD) == PROBE_DIMENSIONS


def test_greenfield_skips_technical_context_and_code_structure():
    assert permitted_dimensions(ProjectMode.GREENFIELD) == (CD.INTERFACE_SPEC, CD.DATA_SEMANTICS)


def test_a_greenfield_request_for_c5_is_refused():
    # The supervisor asked; the mode forbids it.
    assert live_dimensions([CD.CODE_STRUCTURE], ProjectMode.GREENFIELD) == ()


def test_live_dimensions_are_returned_in_canonical_c1_to_c6_order():
    got = live_dimensions([CD.DATA_SEMANTICS, CD.TECHNICAL_CONTEXT], ProjectMode.BROWNFIELD)
    assert got == (CD.TECHNICAL_CONTEXT, CD.DATA_SEMANTICS)


def test_a_duplicate_request_probes_once():
    got = live_dimensions([CD.INTERFACE_SPEC, CD.INTERFACE_SPEC], ProjectMode.BROWNFIELD)
    assert got == (CD.INTERFACE_SPEC,)


def test_requesting_nothing_probes_nothing():
    # A one-line CSS tweak. Routing is the primary cost control.
    assert live_dimensions([], ProjectMode.BROWNFIELD) == ()


def test_a_supervisor_dimension_is_never_probed():
    assert live_dimensions([CD.FUNCTIONAL_INTENT], ProjectMode.BROWNFIELD) == ()


def test_brownfield_probes_must_all_cite_evidence():
    assert grounded_dimensions(ProjectMode.BROWNFIELD) == frozenset(PROBE_DIMENSIONS)


def test_greenfield_probes_have_no_tree_to_cite():
    assert grounded_dimensions(ProjectMode.GREENFIELD) == frozenset()
