"""FR-913 client-facing identity export (E-47a)."""

import json

from sdlc.capability.export import (
    build_export,
    fingerprint_sha256,
    write_export,
)
from sdlc.capability.models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    RetiredReason,
    SignalTier,
)
from sdlc.measurement import Measurement


def _fp(*contract) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(contract)}, collected=Measurement.measured(1.0)
    )


def _identity(bc_id, fp, **kw):
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0", fingerprint=fp, **kw)


def test_hash_is_stable_across_member_order():
    assert fingerprint_sha256(_fp("POST /a", "POST /b")) == fingerprint_sha256(
        _fp("POST /b", "POST /a")
    )


def test_hash_changes_when_a_member_changes():
    assert fingerprint_sha256(_fp("POST /a")) != fingerprint_sha256(_fp("POST /b"))


def test_hash_distinguishes_identical_tiers_by_collection_state():
    # The digest hashed only the tier members, so a MEASURED fingerprint and
    # a NOT_COLLECTED one with identical tiers collided -- the exact
    # conflation measurement.py exists to prevent, reappearing in the
    # client-facing artifact. "Same hash means nothing changed" cannot hold
    # when "measured and empty" is indistinguishable from "we could not
    # measure."
    tiers = {SignalTier.CONTRACT: ["POST /a"]}
    measured = CapabilityFingerprint(tiers=tiers, collected=Measurement.measured(1.0))
    uncollected = CapabilityFingerprint(
        tiers=tiers, collected=Measurement.not_collected("parse fail")
    )
    assert fingerprint_sha256(measured) != fingerprint_sha256(uncollected)


def test_export_carries_no_raw_fingerprint_members():
    payload = build_export("p", [_identity("BC-001", _fp("POST /secret"))])
    assert "POST /secret" not in json.dumps(payload)


def test_export_entries_are_sorted_by_bc_id():
    payload = build_export(
        "p", [_identity("BC-002", _fp("POST /b")), _identity("BC-001", _fp("POST /a"))]
    )
    assert [e["bc_id"] for e in payload["capabilities"]] == ["BC-001", "BC-002"]


def test_export_records_status_and_merge_target():
    payload = build_export(
        "p",
        [_identity("BC-001", _fp("POST /a"), status=IdentityStatus.MERGED, merged_into="BC-002")],
    )
    entry = payload["capabilities"][0]
    assert entry["status"] == "merged" and entry["merged_into"] == "BC-002"


def test_retired_entries_are_exported_so_delivered_refs_resolve():
    payload = build_export(
        "p",
        [
            _identity(
                "BC-001",
                _fp("POST /a"),
                status=IdentityStatus.RETIRED,
                retired_reason=RetiredReason.NOT_OBSERVED,
            )
        ],
    )
    assert payload["capabilities"][0]["status"] == "retired"


def test_write_export_is_deterministic(tmp_path):
    rows = [_identity("BC-001", _fp("POST /a"))]
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    write_export(first, "p", rows)
    write_export(second, "p", rows)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_write_export_creates_parent_directories(tmp_path):
    target = tmp_path / ".sdlc" / "capabilities.json"
    write_export(target, "p", [_identity("BC-001", _fp("POST /a"))])
    assert json.loads(target.read_text(encoding="utf-8"))["project"] == "p"
