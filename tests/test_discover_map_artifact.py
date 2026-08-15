"""FR-913 (E-48): the phase artifact."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.map import (
    Capability, CapabilityMap, CandidateDisposition, DiscoverAction,
    DispositionSource,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
NC = Measurement.not_collected("discover did not run")


def _cap(bc_id="BC-001", **kw):
    base = dict(
        bc_id=bc_id, local_key="C-01", name="payments",
        confidence=Confidence.HIGH,
        members=(CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                 value="POST /pay", path="api/pay.py"),),
        member_paths=("api/pay.py",),
        cohesion=MEASURED, coupling=MEASURED,
        disposition=CandidateDisposition(
            candidate_id="C-01", action=DiscoverAction.CONFIRM,
            source=DispositionSource.BASELINE, rule="baseline_confirm"))
    return Capability(**(base | kw))


def test_capability_counts_are_derived_from_capabilities():
    m = CapabilityMap(capabilities=(_cap("BC-001"), _cap("BC-002")),
                      collected=Measurement.measured(2.0),
                      by_action={DiscoverAction.CONFIRM: 2})
    assert m.by_action[DiscoverAction.CONFIRM] == 2
    with pytest.raises(ValidationError, match="derived"):
        CapabilityMap(capabilities=(_cap(),), collected=MEASURED,
                      by_action={DiscoverAction.CONFIRM: 7})


def test_by_action_must_carry_every_action_that_occurs():
    """An absent key and a zero count are different claims, and only one of
    them is true."""
    with pytest.raises(ValidationError, match="absent from by_action"):
        CapabilityMap(capabilities=(_cap(),), collected=MEASURED,
                      by_action={})


def test_an_uncollected_map_carries_no_capabilities():
    """FR-915: a discover that did not happen has no rows."""
    CapabilityMap(collected=NC)
    with pytest.raises(ValidationError, match="no capabilities"):
        CapabilityMap(collected=NC, capabilities=(_cap(),),
                      by_action={DiscoverAction.CONFIRM: 1})


def test_a_de_scoped_candidate_never_becomes_a_capability():
    """DE_SCOPE and FLAG are verdicts ABOUT a candidate; only a surviving
    boundary gets a bc_id. A de-scoped row holding one would mean the map
    both rejected and identified the same thing."""
    with pytest.raises(ValidationError, match="de_scope|flag"):
        _cap(disposition=CandidateDisposition(
            candidate_id="C-01", action=DiscoverAction.DE_SCOPE,
            source=DispositionSource.BASELINE, rule="baseline_guardrail"))


def test_dropped_dispositions_are_recorded_not_discarded():
    """DD8: a dropped disposition is evidence about the candidate. The map
    keeps the count so the citation guard's input is auditable."""
    m = CapabilityMap(collected=MEASURED, capabilities=(_cap(),),
                      by_action={DiscoverAction.CONFIRM: 1},
                      dropped_dispositions=2, total_references=20)
    assert m.dropped_dispositions == 2


def test_capability_member_paths_are_sorted_and_deduped():
    """Finding 3: member_paths must be sorted and deduped (NFR-10)."""
    _cap(member_paths=("a.py", "b.py"))
    with pytest.raises(ValidationError, match="not sorted"):
        _cap(member_paths=("z.py", "a.py"))
    with pytest.raises(ValidationError, match="not sorted"):
        _cap(member_paths=("a.py", "a.py"))


def test_an_uncollected_map_carries_no_payload_fields():
    """Finding 2: not_collected covers dispositions, dropped counts, etc."""
    disp = CandidateDisposition(
        candidate_id="C-01", action=DiscoverAction.CONFIRM,
        source=DispositionSource.BASELINE, rule="r")
    with pytest.raises(ValidationError, match="no payload"):
        CapabilityMap(collected=NC, dispositions=(disp,))
    with pytest.raises(ValidationError, match="no payload"):
        CapabilityMap(collected=NC, dropped_dispositions=2)
    with pytest.raises(ValidationError, match="no payload"):
        CapabilityMap(collected=NC, total_references=5)
