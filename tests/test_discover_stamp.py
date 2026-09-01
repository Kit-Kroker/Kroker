# tests/test_discover_stamp.py
"""FR-913 (E-48 DD7/DD8): what verification refuses, and how it says so."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.apply import StampedProposal, stamp
from sdlc.assessment.discover.map import (
    CandidateContext,
    CandidateDisposition,
    DiscoverAction,
    DiscoverContext,
    DiscoverProposal,
    DispositionSource,
    GraphSummary,
    ProposedDisposition,
    SplitPartition,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
GRAPH = GraphSummary(
    parsed=4, unparsed=0, edges=3, unresolved_relative_rate=Measurement.measured(0.0)
)


def _member(value: str) -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value, path="pay/api.py")


def _ctx(candidate_id="C-01", values=("POST /pay",), **kw):
    members = tuple(_member(v) for v in values)
    base = dict(
        candidate_id=candidate_id,
        name="payments",
        confidence=Confidence.HIGH,
        sources=("S3-payments",),
        source_rules=("s3_http_route",),
        members=members,
        member_paths=("pay/api.py",),
        cohesion=MEASURED,
        coupling=MEASURED,
        guardrail_only=False,
    )
    return CandidateContext(**(base | kw))


def _context(*candidates) -> DiscoverContext:
    return DiscoverContext(
        candidates=candidates or (_ctx(),), graph=GRAPH, collected=Measurement.measured(1.0)
    )


def _prop(**kw) -> ProposedDisposition:
    base = dict(
        candidate_id="C-01",
        action=DiscoverAction.CONFIRM,
        rationale="four routes and a table, one owner",
    )
    return ProposedDisposition(**(base | kw))


def _only(result: StampedProposal) -> CandidateDisposition:
    assert len(result.dispositions) == 1
    return result.dispositions[0]


def test_no_proposal_is_the_baseline_for_every_candidate():
    """DD7's first fallback: the role is not shipped, or the stage is off."""
    got = stamp(_context(), None)
    assert _only(got).source is DispositionSource.BASELINE
    assert got.dropped == 0


def test_a_clean_proposal_is_stamped_proposer():
    got = stamp(_context(), DiscoverProposal(dispositions=[_prop()]))
    d = _only(got)
    assert d.source is DispositionSource.PROPOSER
    assert d.rule == "proposer"
    assert d.rationale.startswith("four routes")


def test_a_missing_disposition_is_dropped_not_baselined():
    """DD7's second fallback, and the reason the two must not converge: the
    model ran and failed to dispose, which is evidence about the candidate.
    Laundering it into a baseline CONFIRM would silently confirm a boundary
    nobody judged (unbuilt_signal vs failed_signal)."""
    got = stamp(_context(), DiscoverProposal(dispositions=[]))
    d = _only(got)
    assert d.action is DiscoverAction.FLAG
    assert d.source is DispositionSource.DROPPED
    assert d.rule == "dropped_missing"
    assert got.dropped == 1


def test_a_duplicated_disposition_is_dropped():
    got = stamp(_context(), DiscoverProposal(dispositions=[_prop(), _prop()]))
    assert _only(got).rule == "dropped_duplicated"


def test_a_disposition_naming_no_candidate_is_recorded_by_id():
    """DD8 item 1. The id is kept rather than only counted: with no row to
    carry it, the id is the only record verification leaves behind."""
    got = stamp(_context(), DiscoverProposal(dispositions=[_prop(), _prop(candidate_id="C-99")]))
    assert got.unknown_candidate_ids == ("C-99",)
    assert _only(got).source is DispositionSource.PROPOSER


def test_a_merge_into_an_unknown_target_is_dropped():
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[_prop(action=DiscoverAction.MERGE, merge_into="C-99")]),
    )
    assert _only(got).rule == "dropped_merge_target"


def test_a_merge_into_itself_is_dropped():
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[_prop(action=DiscoverAction.MERGE, merge_into="C-01")]),
    )
    assert _only(got).rule == "dropped_merge_self"


def test_a_merge_into_a_target_that_did_not_survive_is_dropped():
    """The second pass. A merge into a de-scoped or itself-merged candidate
    would fold the loser's members into nothing, and merge CHAINS die here
    too: in A->B->C, B's action is MERGE rather than CONFIRM."""
    got = stamp(
        _context(_ctx("C-01"), _ctx("C-02"), _ctx("C-03")),
        DiscoverProposal(
            dispositions=[
                _prop(candidate_id="C-01", action=DiscoverAction.MERGE, merge_into="C-02"),
                _prop(candidate_id="C-02", action=DiscoverAction.MERGE, merge_into="C-03"),
                _prop(candidate_id="C-03"),
            ]
        ),
    )
    by_id = {d.candidate_id: d for d in got.dispositions}
    assert by_id["C-01"].rule == "dropped_merge_target_not_confirmed"
    assert by_id["C-02"].action is DiscoverAction.MERGE
    assert by_id["C-03"].action is DiscoverAction.CONFIRM


def test_a_split_into_fewer_than_two_partitions_is_dropped():
    got = stamp(
        _context(),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(SplitPartition(name="a", member_values=("POST /pay",)),),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_partitions"


def test_a_split_naming_a_member_the_candidate_lacks_is_dropped():
    """DD8 item 3: a SPLIT partitions the candidate's OWN members. No
    invented members."""
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("POST /pay",)),
                        SplitPartition(name="b", member_values=("DELETE /invented",)),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_members"


def test_a_split_with_an_empty_partition_is_dropped():
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("POST /pay",)),
                        SplitPartition(name="b", member_values=()),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_members"


def test_a_split_with_overlapping_partitions_is_dropped():
    """A member on both sides is not a partition."""
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("GET /pay", "POST /pay")),
                        SplitPartition(name="b", member_values=("POST /pay",)),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_overlap"


def test_a_split_with_duplicate_partition_names_is_dropped():
    """local_key is built from the partition name, and resolve() raises on a
    duplicate local_key -- so this would crash the lock rather than degrade."""
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("POST /pay",)),
                        SplitPartition(name="a", member_values=("GET /pay",)),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_names"


def test_a_malformed_disposition_is_dropped_rather_than_raising():
    """The catch-all. ProposedDisposition accepts shapes CandidateDisposition
    refuses -- here, a CONFIRM carrying a merge target -- and a model can
    produce anything. Constructing it must degrade, never crash the phase."""
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[_prop(action=DiscoverAction.CONFIRM, merge_into="C-02")]),
    )
    assert _only(got).rule == "dropped_malformed"


def test_dropped_is_derived_from_the_rows():
    with pytest.raises(ValidationError, match="derived"):
        StampedProposal(dispositions=(), dropped=3)


def test_refused_unknown_candidate_id_lands_in_unknown_candidate_ids():
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[]),
        refusals={"GHOST_99": ("dropped_ref_unresolved", "nope.py does not resolve")},
    )
    assert "GHOST_99" in got.unknown_candidate_ids
    assert got.dropped == 1  # C-01 missing from proposal (dropped)


def test_two_dispositions_where_one_is_refused_stamps_dropped_duplicated():
    # Model emitted 2 rows for C-01; one was refused by verify_refs, one survived
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[_prop(candidate_id="C-01")]),
        refusals={"C-01": ("dropped_quote_unverified", "bad quote")},
    )
    assert _only(got).rule == "dropped_duplicated"
    assert _only(got).action is DiscoverAction.FLAG
