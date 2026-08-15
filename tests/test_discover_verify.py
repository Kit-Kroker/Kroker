# tests/test_discover_verify.py
"""E-48 DD8 items 4-5: every reference resolves, every quote byte-verifies,
and a violation drops the ITEM -- it does not fail the phase."""
from sdlc.assessment.discover.map import (
    DiscoverAction, DiscoverProposal, DispositionSource, EvidenceRef,
    ProposedDisposition,
)
from sdlc.assessment.discover.verify import verify_refs

SRC = "def charge(order_id):\n    return gateway.charge(order_id)\n"


def _proposal(*rows: ProposedDisposition) -> DiscoverProposal:
    return DiscoverProposal(dispositions=list(rows))


def _row(cid: str, **kw) -> ProposedDisposition:
    return ProposedDisposition(
        candidate_id=cid, action=DiscoverAction.CONFIRM,
        rationale="it is a capability", **kw)


def test_a_resolving_reference_survives():
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-2"),)))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals == {}
    assert out.total_references == 1
    assert out.unresolved_references == 0
    assert len(out.proposal.dispositions) == 1


def test_a_fabricated_path_refuses_its_disposition():
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="nope.py"),)))
    out = verify_refs(p, {"nope.py": None})
    rule, detail = out.refusals["C1"]
    assert rule == "dropped_ref_unresolved"
    assert "nope.py" in detail
    assert out.unresolved_references == 1
    # the refused row is gone from the surviving proposal
    assert out.proposal.dispositions == []


def test_a_line_range_outside_the_file_refuses_its_disposition():
    """DD8 item 4: the range must lie INSIDE the file. SRC has two lines."""
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-9"),)))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals["C1"][0] == "dropped_ref_line_range"
    assert out.unresolved_references == 1


def test_an_empty_file_resolves_and_is_not_confused_with_a_missing_one():
    """read_committed_bytes returns "" for an empty file and None for an
    unresolved one -- truthiness must not collapse them."""
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="empty.py"),)))
    out = verify_refs(p, {"empty.py": ""})
    assert out.refusals == {}
    assert out.unresolved_references == 0


def test_counts_are_over_references_not_dispositions():
    """P3-D2: the guard's denominator is references."""
    p = _proposal(_row("C1", evidence=(
        EvidenceRef(path="pay.py", lines="1-2"),
        EvidenceRef(path="ghost.py"),
    )))
    out = verify_refs(p, {"pay.py": SRC, "ghost.py": None})
    assert out.total_references == 2
    assert out.unresolved_references == 1
    assert out.fabrication_rate == 0.5


def test_a_proposal_with_no_references_has_a_zero_rate_not_a_zero_division():
    out = verify_refs(_proposal(_row("C1")), {})
    assert out.total_references == 0
    assert out.fabrication_rate == 0.0


def test_one_bad_reference_does_not_refuse_a_different_candidate():
    """A violation drops the ITEM. Discover is a lens over many candidates."""
    p = _proposal(
        _row("C1", evidence=(EvidenceRef(path="ghost.py"),)),
        _row("C2", evidence=(EvidenceRef(path="pay.py", lines="1-2"),)),
    )
    out = verify_refs(p, {"ghost.py": None, "pay.py": SRC})
    assert set(out.refusals) == {"C1"}
    assert [d.candidate_id for d in out.proposal.dispositions] == ["C2"]


def test_verification_is_order_independent():
    """NFR-10: byte-identical across input order."""
    rows = [_row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-2"),)),
            _row("C2", evidence=(EvidenceRef(path="ghost.py"),)),
            _row("C3")]
    blobs = {"pay.py": SRC, "ghost.py": None}
    a = verify_refs(_proposal(*rows), blobs)
    b = verify_refs(_proposal(*reversed(rows)), blobs)
    assert a.refusals == b.refusals
    assert a.total_references == b.total_references
    assert a.unresolved_references == b.unresolved_references


def test_a_quote_that_byte_verifies_survives():
    p = _proposal(_row("C1", evidence=(
        EvidenceRef(path="pay.py", lines="1-2"),), quote="gateway.charge"))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals == {}


def test_a_quote_that_does_not_byte_verify_refuses_its_disposition():
    p = _proposal(_row("C1", evidence=(
        EvidenceRef(path="pay.py", lines="1-2"),), quote="gateway.refund"))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals["C1"][0] == "dropped_quote_unverified"
    assert out.unresolved_references == 1


def test_an_empty_quote_does_not_ground_trivially():
    """E-43 closed exactly this hole: "" in haystack is True."""
    p = _proposal(_row("C1", evidence=(
        EvidenceRef(path="pay.py", lines="1-2"),), quote="   "))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals["C1"][0] == "dropped_quote_empty"


def _context_with(cids: list[str]):
    from sdlc.assessment.discover.map import (
        CandidateContext, DiscoverContext, GraphSummary,
    )
    from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
    from sdlc.measurement import Measurement

    measured = Measurement.measured(1.0)
    candidates = tuple(
        CandidateContext(
            candidate_id=cid, name=f"name_{cid}", confidence=Confidence.HIGH,
            sources=(f"S3-{cid}",), source_rules=("s3_http_route",),
            members=(CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                     value="POST /pay", path="pay/api.py"),),
            member_paths=("pay/api.py",),
            cohesion=measured, coupling=measured, guardrail_only=False)
        for cid in cids)
    return DiscoverContext(
        candidates=candidates,
        graph=GraphSummary(
            parsed=1, unparsed=0, edges=1,
            unresolved_relative_rate=Measurement.measured(0.0)),
        collected=measured)


def test_a_refused_verdict_is_not_reported_as_an_omission():
    """P3-D1/DD7: "the model cited garbage" and "the model said nothing"
    must not converge on dropped_missing."""
    from sdlc.assessment.discover.apply import stamp

    context = _context_with(["C1"])
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="ghost.py"),)))
    out = verify_refs(p, {"ghost.py": None})
    stamped = stamp(context, out.proposal, refusals=out.refusals)

    row = stamped.dispositions[0]
    assert row.action is DiscoverAction.FLAG
    assert row.source is DispositionSource.DROPPED
    assert row.rule == "dropped_ref_unresolved"
    assert row.rule != "dropped_missing"

