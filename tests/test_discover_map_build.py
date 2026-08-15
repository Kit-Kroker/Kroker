# tests/test_discover_map_build.py
"""FR-913 (E-48): the fingerprint handed to resolve(), and the artifact's one
constructor."""
from __future__ import annotations

import pytest

from sdlc.assessment.discover.apply import (
    ApplyResult, LockedCandidate, StampedProposal, build_map, fingerprint_of,
)
from sdlc.assessment.discover.map import (
    CandidateDisposition, DiscoverAction, DispositionSource,
)
from sdlc.assessment.discover.models import (
    DecompositionReport, OwnershipOutcome, OwnershipReport,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.capability.models import Advisory, AdvisoryKind, SignalTier
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)


def _disp(candidate_id="C-01", action=DiscoverAction.CONFIRM):
    return CandidateDisposition(
        candidate_id=candidate_id, action=action,
        source=DispositionSource.BASELINE, rule="baseline_confirm")


def _locked(local_key="C-01", members=None, **kw):
    rows = tuple(members if members is not None else (
        CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay",
                        path="pay/api.py"),
        CandidateMember(kind=MemberKind.FILE_PATH, value="pay/core.py",
                        path="pay/core.py"),
    ))
    base = dict(
        local_key=local_key, name="payments", confidence=Confidence.HIGH,
        members=rows,
        member_paths=tuple(sorted({m.path for m in rows if m.path})),
        cohesion=MEASURED, coupling=MEASURED,
        disposition=_disp(local_key))
    return LockedCandidate(**(base | kw))


def _applied(*locked, stamped=None) -> ApplyResult:
    return ApplyResult(locked=tuple(locked),
                       stamped=stamped or StampedProposal(
                           dispositions=tuple(c.disposition for c in locked)))


def test_a_fingerprint_groups_members_by_tier():
    fp = fingerprint_of(_locked())
    assert fp.collected.state is CollectionState.MEASURED
    assert fp.tiers[SignalTier.CONTRACT] == ["POST /pay"]
    assert fp.tiers[SignalTier.LOCATIONAL] == ["pay/core.py"]
    assert fp.tiers[SignalTier.BEHAVIORAL] == []


def test_a_memberless_boundary_has_a_not_collected_fingerprint():
    """E-47a's rule: a fingerprint that could not be computed is never scored
    0. score() returns None for a not_collected side, so resolve() mints a
    fresh id and files an IDENTITY_NOT_ASSESSED advisory instead."""
    fp = fingerprint_of(_locked(members=()))
    assert fp.collected.state is CollectionState.NOT_COLLECTED
    assert "no members" in fp.collected.reason


def test_build_map_attaches_the_bc_id_from_the_lock():
    m = build_map(_applied(_locked()), {"C-01": "BC-001"})
    assert [c.bc_id for c in m.capabilities] == ["BC-001"]
    assert m.capabilities[0].local_key == "C-01"
    assert m.collected.value == 1.0


def test_by_action_counts_capabilities_not_dispositions():
    """de_scope, flag and merge occur as verdicts but never as boundaries.
    Listing them here as zeros would read as 'no candidate was de-scoped',
    which is a claim `dispositions` already answers truthfully."""
    stamped = StampedProposal(dispositions=(
        _disp("C-01"), _disp("C-02", DiscoverAction.DE_SCOPE)))
    m = build_map(_applied(_locked("C-01"), stamped=stamped),
                  {"C-01": "BC-001"})
    assert m.by_action == {DiscoverAction.CONFIRM: 1}
    assert len(m.dispositions) == 2


def test_by_action_preserves_enum_definition_order():
    """Deterministic serialization: by_action iterates DiscoverAction in
    definition order, never raw set iteration."""
    from sdlc.assessment.discover.map import SplitPartition
    c1 = _locked("C-01", disposition=_disp("C-01", DiscoverAction.CONFIRM))
    disp_split = CandidateDisposition(
        candidate_id="C-02", action=DiscoverAction.SPLIT,
        source=DispositionSource.PROPOSER, rule="proposer",
        rationale="two distinct operations",
        partitions=(SplitPartition(name="a", member_values=("POST /pay",)),
                    SplitPartition(name="b", member_values=("pay/core.py",))))
    c2 = _locked("C-02#a", disposition=disp_split)
    c3 = _locked("C-03", disposition=_disp("C-03", DiscoverAction.CONFIRM))
    stamped = StampedProposal(dispositions=(
        _disp("C-01", DiscoverAction.CONFIRM),
        disp_split,
        _disp("C-03", DiscoverAction.CONFIRM)))
    m = build_map(_applied(c1, c2, c3, stamped=stamped),
                  {"C-01": "BC-001", "C-02#a": "BC-002", "C-03": "BC-003"})
    assert list(m.by_action.keys()) == [DiscoverAction.CONFIRM, DiscoverAction.SPLIT]



def test_dropped_dispositions_sums_both_halves_of_the_guard():
    """DD8's leniency is bounded by a rate over references; both a refused
    verdict and a verdict naming a candidate that does not exist feed it."""
    stamped = StampedProposal(
        dispositions=(_disp("C-01"),
                      CandidateDisposition(
                          candidate_id="C-02", action=DiscoverAction.FLAG,
                          source=DispositionSource.DROPPED,
                          rule="dropped_missing"),),
        unknown_candidate_ids=("C-98", "C-99"), dropped=1)
    m = build_map(_applied(_locked("C-01"), stamped=stamped),
                  {"C-01": "BC-001"})
    assert m.dropped_dispositions == 3
    # Plan 3 sets this and divides by it; the zero denominator is this plan's.
    assert m.total_references == 0


def test_build_map_refuses_a_boundary_with_no_bc_id():
    """resolve() attaches every proposed capability, so a missing one is a
    lock defect rather than a degraded input -- and a KeyError inside
    workflow code would retry forever."""
    with pytest.raises(ValueError, match="no bc_id was attached"):
        build_map(_applied(_locked("C-01")), {})


def test_build_map_carries_the_reports_and_the_advisories():
    nc = Measurement.not_collected("S3 did not collect")
    m = build_map(
        _applied(_locked()), {"C-01": "BC-001"},
        advisories=[Advisory(kind=AdvisoryKind.POSSIBLE_RENAME,
                             local_key="C-01", detail="closest was BC-004")],
        decomposition=DecompositionReport(collected=nc),
        ownership=OwnershipReport(counts={o: 0 for o in OwnershipOutcome},
                                  collected=nc))
    assert m.advisories[0].kind is AdvisoryKind.POSSIBLE_RENAME
    assert m.decomposition.collected.state is CollectionState.NOT_COLLECTED
    assert m.attribution is None


def test_a_map_with_no_capabilities_is_a_measured_zero():
    """A tree with no capabilities is a real finding. A discover that could
    not run never reaches build_map -- the phase reports not_collected and
    carries no map at all."""
    m = build_map(_applied(), {})
    assert m.collected.state is CollectionState.MEASURED
    assert m.collected.value == 0.0
    assert m.capabilities == ()
