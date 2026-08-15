# tests/test_discover_apply.py
"""FR-913 (E-48): verified dispositions become the boundaries the lock
identifies."""
from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.apply import (
    ApplyResult, LockedCandidate, StampedProposal, apply, stamp,
)
from sdlc.assessment.discover.map import (
    CandidateContext, CandidateDisposition, DiscoverAction, DiscoverContext,
    DiscoverProposal, DispositionSource, GraphSummary, ProposedDisposition,
    SplitPartition,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)
GRAPH = GraphSummary(parsed=4, unparsed=0, edges=3,
                     unresolved_relative_rate=Measurement.measured(0.0))


def _member(value: str, path: str) -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value, path=path)


def _ctx(candidate_id="C-01", name="payments",
         members=(("POST /pay", "pay/api.py"),), **kw):
    rows = tuple(_member(v, p) for v, p in members)
    base = dict(
        candidate_id=candidate_id, name=name, confidence=Confidence.HIGH,
        sources=("S3-payments",), source_rules=("s3_http_route",),
        members=rows,
        member_paths=tuple(sorted({m.path for m in rows if m.path})),
        cohesion=MEASURED, coupling=MEASURED, guardrail_only=False)
    return CandidateContext(**(base | kw))


def _context(*candidates) -> DiscoverContext:
    return DiscoverContext(candidates=candidates, graph=GRAPH,
                           collected=Measurement.measured(
                               float(len(candidates))))


def _applied(context, *proposed) -> ApplyResult:
    return apply(context, stamp(context, DiscoverProposal(
        dispositions=list(proposed))))


def _prop(candidate_id, action=DiscoverAction.CONFIRM, **kw):
    return ProposedDisposition(candidate_id=candidate_id, action=action,
                               rationale="judged", **kw)


def test_a_confirmed_candidate_becomes_one_locked_candidate():
    got = apply(_context(_ctx()), stamp(_context(_ctx()), None))
    assert [c.local_key for c in got.locked] == ["C-01"]
    assert got.locked[0].name == "payments"


def test_a_de_scoped_or_flagged_candidate_produces_no_boundary():
    """DE_SCOPE and FLAG are verdicts ABOUT a candidate; only a surviving
    boundary is handed to the lock."""
    context = _context(_ctx("C-01"), _ctx("C-02", name="orders"))
    got = _applied(context,
                   _prop("C-01", DiscoverAction.DE_SCOPE),
                   _prop("C-02", DiscoverAction.FLAG))
    assert got.locked == ()
    assert len(got.stamped.dispositions) == 2


def test_a_merged_candidate_folds_its_members_into_the_winner():
    context = _context(
        _ctx("C-01", members=(("POST /pay", "pay/api.py"),)),
        _ctx("C-02", name="billing", members=(("GET /bill", "bill/api.py"),)))
    got = _applied(context,
                   _prop("C-01"),
                   _prop("C-02", DiscoverAction.MERGE, merge_into="C-01"))
    assert [c.local_key for c in got.locked] == ["C-01"]
    winner = got.locked[0]
    assert {m.value for m in winner.members} == {"POST /pay", "GET /bill"}
    assert winner.member_paths == ("bill/api.py", "pay/api.py")


def test_a_merge_winner_loses_its_cohesion_and_coupling():
    """P2-D2: build_context computed both over the ORIGINAL member set and
    then discarded the reference graph (DD4), so the number no longer
    describes this boundary and cannot be recomputed here."""
    context = _context(
        _ctx("C-01"),
        _ctx("C-02", name="billing", members=(("GET /bill", "bill/api.py"),)))
    got = _applied(context,
                   _prop("C-01"),
                   _prop("C-02", DiscoverAction.MERGE, merge_into="C-01"))
    winner = got.locked[0]
    assert winner.cohesion.state is CollectionState.NOT_COLLECTED
    assert "absorbed" in winner.cohesion.reason
    assert winner.coupling.state is CollectionState.NOT_COLLECTED


def test_a_confirmed_candidate_that_absorbed_nothing_keeps_its_metrics():
    got = apply(_context(_ctx()), stamp(_context(_ctx()), None))
    assert got.locked[0].cohesion.value == 1.0
    assert got.locked[0].coupling.value == 1.0


def test_a_split_produces_one_boundary_per_partition():
    context = _context(_ctx("C-01", members=(("POST /pay", "pay/api.py"),
                                             ("GET /bill", "bill/api.py"))))
    got = _applied(context, _prop("C-01", DiscoverAction.SPLIT, partitions=(
        SplitPartition(name="billing", member_values=("GET /bill",)),
        SplitPartition(name="charging", member_values=("POST /pay",)),
    )))
    assert [c.local_key for c in got.locked] == ["C-01#billing",
                                                 "C-01#charging"]
    billing = got.locked[0]
    assert {m.value for m in billing.members} == {"GET /bill"}
    assert billing.member_paths == ("bill/api.py",)


def test_a_split_part_loses_its_cohesion_and_coupling():
    context = _context(_ctx("C-01", members=(("POST /pay", "pay/api.py"),
                                             ("GET /bill", "bill/api.py"))))
    got = _applied(context, _prop("C-01", DiscoverAction.SPLIT, partitions=(
        SplitPartition(name="billing", member_values=("GET /bill",)),
        SplitPartition(name="charging", member_values=("POST /pay",)),
    )))
    for part in got.locked:
        assert part.cohesion.state is CollectionState.NOT_COLLECTED
        assert "partition" in part.cohesion.reason


def test_local_keys_must_be_unique_and_sorted():
    """resolve() raises on a duplicate local_key, so a caller that produced
    one would crash the lock rather than degrade."""
    locked = LockedCandidate(
        local_key="C-01", name="payments", confidence=Confidence.HIGH,
        members=(), member_paths=(), cohesion=MEASURED, coupling=MEASURED,
        disposition=CandidateDisposition(
            candidate_id="C-01", action=DiscoverAction.CONFIRM,
            source=DispositionSource.BASELINE, rule="baseline_confirm"))
    with pytest.raises(ValidationError, match="unique and sorted"):
        ApplyResult(locked=(locked, locked), stamped=StampedProposal())


def test_apply_is_order_independent():
    """NFR-10: byte-identical regardless of the order the candidates and
    dispositions arrive in."""
    candidates = [_ctx("C-01"), _ctx("C-02", name="orders"),
                  _ctx("C-03", name="billing")]
    props = [_prop("C-01"), _prop("C-02"),
             _prop("C-03", DiscoverAction.MERGE, merge_into="C-01")]
    first = _applied(_context(*candidates), *props).model_dump_json()
    for _ in range(5):
        shuffled = props[:]
        random.shuffle(shuffled)
        assert _applied(_context(*candidates),
                        *shuffled).model_dump_json() == first
