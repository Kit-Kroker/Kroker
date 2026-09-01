"""FR-913 capability identity contracts (E-47a)."""

import pytest
from pydantic import ValidationError

from sdlc.capability.models import (
    DEFAULT_TIER_WEIGHTS,
    Advisory,
    AdvisoryKind,
    AttachMethod,
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityAttachment,
    IdentityStatus,
    ProposedCapability,
    ResolutionResult,
    RetiredReason,
    SignalTier,
)
from sdlc.measurement import Measurement


def _fp(**tiers) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier(k): v for k, v in tiers.items()}, collected=Measurement.measured(1.0)
    )


def test_fingerprint_sorts_and_dedupes_tier_members():
    fp = _fp(contract=["POST /b", "POST /a", "POST /b"])
    assert fp.tiers[SignalTier.CONTRACT] == ["POST /a", "POST /b"]


def test_fingerprint_absent_tiers_default_to_empty():
    fp = _fp(contract=["POST /a"])
    assert fp.tiers[SignalTier.BEHAVIORAL] == []
    assert fp.tiers[SignalTier.LOCATIONAL] == []


def test_default_weights_cover_every_tier_and_sum_to_one():
    assert set(DEFAULT_TIER_WEIGHTS) == set(SignalTier)
    assert sum(DEFAULT_TIER_WEIGHTS.values()) == pytest.approx(1.0)


def test_retired_identity_requires_a_reason():
    with pytest.raises(ValidationError, match="retired_reason"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.RETIRED,
            fingerprint=_fp(contract=["a"]),
        )


def test_active_identity_must_not_carry_a_retired_reason():
    with pytest.raises(ValidationError, match="retired_reason"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.ACTIVE,
            retired_reason=RetiredReason.NOT_OBSERVED,
            fingerprint=_fp(contract=["a"]),
        )


def test_merged_identity_requires_merged_into():
    with pytest.raises(ValidationError, match="merged_into"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.MERGED,
            fingerprint=_fp(contract=["a"]),
        )


def test_merged_into_must_not_be_self():
    with pytest.raises(ValidationError, match="itself"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.MERGED,
            merged_into="BC-001",
            fingerprint=_fp(contract=["a"]),
        )


def test_first_discovery_attachment_carries_no_score():
    with pytest.raises(ValidationError, match="match_score"):
        IdentityAttachment(
            local_key="c0", bc_id="BC-001", method=AttachMethod.FIRST_DISCOVERY, match_score=0.9
        )


def test_matched_attachment_requires_a_score():
    with pytest.raises(ValidationError, match="match_score"):
        IdentityAttachment(local_key="c0", bc_id="BC-001", method=AttachMethod.MATCHED)


def test_resolution_result_defaults_are_empty():
    r = ResolutionResult()
    assert r.attachments == [] and r.retired == [] and r.advisories == []


def test_advisory_carries_kind_and_detail():
    a = Advisory(
        kind=AdvisoryKind.POSSIBLE_RENAME, detail="near miss", related_bc_id="BC-002", score=0.51
    )
    assert a.kind is AdvisoryKind.POSSIBLE_RENAME


def test_proposed_capability_pairs_local_key_with_fingerprint():
    p = ProposedCapability(local_key="c0", fingerprint=_fp(contract=["a"]))
    assert p.local_key == "c0"
