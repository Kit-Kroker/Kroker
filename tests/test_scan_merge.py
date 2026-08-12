"""S5 -- the merge. Two rules and no more (D9), and a confidence that is
derived from distinct SOURCES, never from the depth of one (D8)."""
from __future__ import annotations

from sdlc.assessment.scan.merge import CANDIDATE_BAND, merge
from sdlc.assessment.scan.models import (
    CandidateMember, Confidence, MemberKind, ScanSignalId, SourceCandidate,
)
from sdlc.measurement import CollectionState, Measurement

MEASURED = {s: Measurement.measured(1.0)
            for s in (ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3,
                      ScanSignalId.S4)}


def _sc(signal: ScanSignalId, slug: str, name: str,
        members: list[CandidateMember] | None = None) -> SourceCandidate:
    return SourceCandidate(
        signal=signal, local_id=f"{signal.value}-{slug}", name=name,
        rule="r", detail="d", confidence_contribution=Confidence.LOW,
        members=members or [CandidateMember(kind=MemberKind.PACKAGE_PATH,
                                            value=f"src/{slug}")])


def test_three_sources_on_one_name_merge_to_high():
    out = merge([_sc(ScanSignalId.S1, "payments", "payments"),
                 _sc(ScanSignalId.S3, "payment", "PaymentController"),
                 _sc(ScanSignalId.S4, "pay", "Payments")], MEASURED)
    assert len(out.candidates) == 1
    assert out.candidates[0].confidence is Confidence.HIGH
    assert len(out.candidates[0].sources) == 3


def test_two_sources_are_medium_and_one_is_low():
    two = merge([_sc(ScanSignalId.S1, "orders", "orders"),
                 _sc(ScanSignalId.S3, "order", "OrderService")], MEASURED)
    assert two.candidates[0].confidence is Confidence.MEDIUM
    one = merge([_sc(ScanSignalId.S1, "orders", "orders")], MEASURED)
    assert one.candidates[0].confidence is Confidence.LOW


def test_two_candidates_from_the_SAME_signal_do_not_corroborate():
    """D8: distinct SIGNALS, not distinct candidates -- two S1 groupings are
    one source's opinion twice."""
    out = merge([_sc(ScanSignalId.S1, "payments", "payments"),
                 _sc(ScanSignalId.S1, "payment", "Payment")], MEASURED)
    assert len(out.candidates) == 1
    assert out.candidates[0].confidence is Confidence.LOW


def test_overlapping_members_under_different_names_are_not_collapsed():
    """D9 rule 2, ported verbatim: emit both, flag each. /discover decides
    MERGE vs SPLIT -- S5 never has to be right, only never silently wrong."""
    shared = CandidateMember(kind=MemberKind.FILE_PATH,
                             value="src/billing/core.py")
    out = merge([_sc(ScanSignalId.S1, "payments", "payments", [shared]),
                 _sc(ScanSignalId.S3, "refund", "Refunds", [shared])],
                MEASURED)
    assert len(out.candidates) == 2
    ids = {c.candidate_id for c in out.candidates}
    for c in out.candidates:
        assert c.possible_duplicate_of == sorted(ids - {c.candidate_id})


def test_non_overlapping_candidates_carry_no_duplicate_flag():
    out = merge([_sc(ScanSignalId.S1, "payments", "payments"),
                 _sc(ScanSignalId.S3, "orders", "Orders")], MEASURED)
    assert all(c.possible_duplicate_of == [] for c in out.candidates)


def test_candidate_ids_are_assigned_in_sorted_order_and_zero_padded():
    out = merge([_sc(ScanSignalId.S1, "orders", "orders"),
                 _sc(ScanSignalId.S3, "billing", "Billing")], MEASURED)
    assert [c.candidate_id for c in out.candidates] == ["C-01", "C-02"]
    # The display name is one a SOURCE used ("Billing"), never one this
    # function invented by title-casing the normalized key.
    assert [c.name for c in out.candidates] == ["Billing", "orders"]


def test_a_candidate_id_is_not_a_capability_id():
    """BC-NNN is E-47a's surrogate key, allocated after discover. Minting one
    here would put capability identity two phases early."""
    out = merge([_sc(ScanSignalId.S1, "orders", "orders")], MEASURED)
    assert not out.candidates[0].candidate_id.startswith("BC-")


def test_members_from_every_source_reach_the_merged_candidate():
    a = CandidateMember(kind=MemberKind.PACKAGE_PATH, value="src/payments")
    b = CandidateMember(kind=MemberKind.HTTP_ROUTE,
                        value="POST /api/payments", path="src/api.py", line=4)
    out = merge([_sc(ScanSignalId.S1, "payments", "payments", [a]),
                 _sc(ScanSignalId.S3, "payment", "PaymentController", [b])],
                MEASURED)
    assert set(out.candidates[0].members) == {a, b}


def test_no_sources_from_signals_that_all_failed_is_a_gap():
    """FR-915: merging nothing because there was nothing to merge is not a
    measured zero."""
    nc = Measurement.not_collected("S3 activity failed")
    out = merge([], {ScanSignalId.S1: nc, ScanSignalId.S3: nc})
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert "S1" in out.collected.reason and "S3" in out.collected.reason
    assert out.candidates == []


def test_no_sources_from_signals_that_measured_is_a_real_zero():
    out = merge([], MEASURED)
    assert out.collected.state is CollectionState.MEASURED
    assert out.collected.value == 0.0


def test_the_candidate_band_is_a_constant_not_a_gate():
    """D11: BrownKit hard-gates on 15-25; ported as advisory, because a
    40-file Next.js app legitimately has four capabilities."""
    assert CANDIDATE_BAND == (15, 25)
    out = merge([_sc(ScanSignalId.S1, "orders", "orders")], MEASURED)
    assert out.collected.state is CollectionState.MEASURED   # not a failure


def test_output_is_order_independent():
    args = [_sc(ScanSignalId.S1, "payments", "payments"),
            _sc(ScanSignalId.S3, "payment", "PaymentController"),
            _sc(ScanSignalId.S4, "orders", "Orders")]
    a = merge(args, MEASURED)
    b = merge(list(reversed(args)), MEASURED)
    assert a.model_dump_json() == b.model_dump_json()
