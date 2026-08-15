# tests/test_capability_rows.py
"""FR-913 (E-48 P2-D4): a ResolutionResult becomes the rows store.apply()
persists."""
from __future__ import annotations

from sdlc.capability.models import (
    Advisory, AdvisoryKind, AttachMethod, CapabilityFingerprint,
    CapabilityIdentity, IdentityAttachment, IdentityStatus, ResolutionResult,
    RetiredReason, SignalTier,
)
from sdlc.capability.rows import identity_rows
from sdlc.measurement import Measurement


def _fp(*routes) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(routes)},
        collected=Measurement.measured(float(len(routes))))


def _stored(bc_id="BC-001", status=IdentityStatus.ACTIVE, **kw):
    base = dict(bc_id=bc_id, project="acme", first_seen_run="run-1",
                status=status, fingerprint=_fp("GET /old"))
    return CapabilityIdentity(**(base | kw))


def _matched(local_key="C-01", bc_id="BC-001"):
    return IdentityAttachment(local_key=local_key, bc_id=bc_id,
                              method=AttachMethod.MATCHED, match_score=0.9)


def _new(local_key="C-01", bc_id="BC-007"):
    return IdentityAttachment(local_key=local_key, bc_id=bc_id,
                              method=AttachMethod.FIRST_DISCOVERY)


def test_a_first_discovery_mints_an_active_row_stamped_with_this_run():
    rows = identity_rows("acme", "run-9",
                         ResolutionResult(attachments=[_new()]),
                         {"C-01": _fp("POST /pay")}, [])
    assert len(rows) == 1
    assert rows[0].bc_id == "BC-007"
    assert rows[0].project == "acme"
    assert rows[0].first_seen_run == "run-9"
    assert rows[0].status is IdentityStatus.ACTIVE
    assert rows[0].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /pay"]


def test_a_matched_row_keeps_first_seen_run_and_refreshes_the_fingerprint():
    """Refreshing is what keeps the id attached across a slow drift: next
    run matches against what THIS run observed, not what run 1 did."""
    rows = identity_rows("acme", "run-9",
                         ResolutionResult(attachments=[_matched()]),
                         {"C-01": _fp("POST /pay")}, [_stored()])
    assert rows[0].first_seen_run == "run-1"
    assert rows[0].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /pay"]


def test_a_matched_retired_row_is_revived():
    """E-47a: retired rows ARE match candidates, and a scan that matches one
    is re-attachment to the same capability, not reuse by a different one."""
    stored = _stored(status=IdentityStatus.RETIRED,
                     retired_reason=RetiredReason.NOT_OBSERVED)
    rows = identity_rows("acme", "run-9",
                         ResolutionResult(attachments=[_matched()]),
                         {"C-01": _fp("POST /pay")}, [stored])
    assert rows[0].status is IdentityStatus.ACTIVE
    assert rows[0].retired_reason is None


def test_an_unobserved_row_is_retired_with_its_reason():
    rows = identity_rows(
        "acme", "run-9",
        ResolutionResult(attachments=[_new(bc_id="BC-007")],
                         retired=["BC-001"]),
        {"C-01": _fp("POST /pay")}, [_stored()])
    retired = next(r for r in rows if r.bc_id == "BC-001")
    assert retired.status is IdentityStatus.RETIRED
    assert retired.retired_reason is RetiredReason.NOT_OBSERVED


def test_a_merge_loser_points_at_its_winner_and_carries_no_retired_reason():
    """P2-D9: CapabilityIdentity forbids a retired_reason on a MERGED row, so
    RetiredReason.ABSORBED gains no producer here -- it stays reserved and
    unemitted, like OwnershipVerb.TRACKS. This is corrections._absorb's
    exact shape."""
    rows = identity_rows(
        "acme", "run-9",
        ResolutionResult(attachments=[_matched(bc_id="BC-002")],
                         merged={"BC-001": "BC-002"}),
        {"C-01": _fp("POST /pay")},
        [_stored("BC-001"), _stored("BC-002")])
    loser = next(r for r in rows if r.bc_id == "BC-001")
    assert loser.status is IdentityStatus.MERGED
    assert loser.merged_into == "BC-002"
    assert loser.retired_reason is None


def test_a_split_advisory_sets_derived_from():
    """resolve() files a SPLIT advisory when a new id was minted because a
    stronger match claimed the id it also matched. derived_from is where
    that provenance lands."""
    result = ResolutionResult(
        attachments=[_matched(bc_id="BC-001"),
                     _new(local_key="C-02", bc_id="BC-007")],
        advisories=[Advisory(kind=AdvisoryKind.SPLIT, local_key="C-02",
                             related_bc_id="BC-001", score=0.7,
                             detail="claimed by a stronger match")])
    rows = identity_rows("acme", "run-9", result,
                         {"C-01": _fp("POST /pay"), "C-02": _fp("GET /pay")},
                         [_stored()])
    minted = next(r for r in rows if r.bc_id == "BC-007")
    assert minted.derived_from == "BC-001"


def test_rows_are_sorted_by_bc_id():
    """store.apply() writes one audit event per row, so the order is
    observable and must not depend on attachment order (NFR-10)."""
    result = ResolutionResult(attachments=[
        _new(local_key="C-02", bc_id="BC-009"),
        _new(local_key="C-01", bc_id="BC-003")])
    rows = identity_rows("acme", "run-9", result,
                         {"C-01": _fp("a"), "C-02": _fp("b")}, [])
    assert [r.bc_id for r in rows] == ["BC-003", "BC-009"]


def test_an_id_absent_from_the_registry_is_skipped_not_fabricated():
    """A retired or merged id with no stored row cannot be written: there is
    no fingerprint or first_seen_run to carry, and inventing them would put a
    fabricated row in the registry clients cite."""
    rows = identity_rows("acme", "run-9",
                         ResolutionResult(retired=["BC-404"],
                                          merged={"BC-405": "BC-001"}),
                         {}, [])
    assert rows == []
