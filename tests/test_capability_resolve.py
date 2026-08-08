"""FR-913 identity resolution (E-47a)."""
import itertools

from sdlc.capability.matcher import resolve
from sdlc.capability.models import (
    AdvisoryKind, AttachMethod, CapabilityFingerprint, CapabilityIdentity,
    IdentityStatus, ProposedCapability, RetiredReason, SignalTier,
)
from sdlc.measurement import Measurement


def _fp(collected=True, **tiers) -> CapabilityFingerprint:
    m = (Measurement.measured(1.0) if collected
         else Measurement.not_collected("parse failure"))
    return CapabilityFingerprint(
        tiers={SignalTier(k): v for k, v in tiers.items()}, collected=m)


def _identity(bc_id, fp, status=IdentityStatus.ACTIVE, reason=None):
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0",
                              status=status, retired_reason=reason,
                              fingerprint=fp)


def _allocator(start=900):
    counter = itertools.count(start)
    return lambda: f"BC-{next(counter):03d}"


def _kinds(result):
    return {a.kind for a in result.advisories}


def test_empty_registry_is_all_first_discovery_with_no_advisories():
    proposed = [ProposedCapability(local_key="c0", fingerprint=_fp(contract=["POST /a"])),
                ProposedCapability(local_key="c1", fingerprint=_fp(contract=["POST /b"]))]
    r = resolve(proposed, [], allocate=_allocator())
    assert [a.method for a in r.attachments] == [
        AttachMethod.FIRST_DISCOVERY, AttachMethod.FIRST_DISCOVERY]
    assert all(a.match_score is None for a in r.attachments)
    assert r.advisories == []


def test_unchanged_capability_keeps_its_id():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=fp)],
                [_identity("BC-001", fp)], allocate=_allocator())
    assert r.attachments[0].bc_id == "BC-001"
    assert r.attachments[0].method is AttachMethod.MATCHED
    assert r.attachments[0].match_score == 1.0


def test_attachment_records_per_tier_contributions_as_evidence():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=fp)],
                [_identity("BC-001", fp)], allocate=_allocator())
    contrib = r.attachments[0].contributions
    assert contrib[SignalTier.CONTRACT] == 1.0
    assert contrib[SignalTier.STRUCTURAL] == 1.0


def test_heavy_internal_refactor_keeps_the_id():
    stored = _fp(contract=["POST /login"], structural=["OldAuth"],
                 locational=["old/auth.py"])
    now = _fp(contract=["POST /login"], structural=["NewIdentity"],
              locational=["pkg/new/identity.py"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=now)],
                [_identity("BC-001", stored)], allocate=_allocator())
    assert r.attachments[0].bc_id == "BC-001"


def test_unrelated_capability_gets_a_new_id_and_a_rename_advisory():
    stored = _fp(contract=["POST /login"], structural=["Auth"])
    now = _fp(contract=["GET /reports"], structural=["Reporting"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=now)],
                [_identity("BC-001", stored)], allocate=_allocator())
    assert r.attachments[0].bc_id == "BC-900"
    assert AdvisoryKind.POSSIBLE_RENAME in _kinds(r)
    near = next(a for a in r.advisories
                if a.kind is AdvisoryKind.POSSIBLE_RENAME)
    assert near.related_bc_id == "BC-001" and near.score is not None


def test_uncomputable_fingerprint_gets_new_id_and_is_not_scored():
    stored = _fp(contract=["POST /login"])
    now = _fp(collected=False, contract=["POST /login"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=now)],
                [_identity("BC-001", stored)], allocate=_allocator())
    assert r.attachments[0].bc_id == "BC-900"
    assert r.attachments[0].match_score is None
    assert AdvisoryKind.IDENTITY_NOT_ASSESSED in _kinds(r)


def test_detected_split_keeps_the_id_on_the_stronger_half():
    stored = _fp(contract=["POST /login", "POST /logout"],
                 structural=["Auth"])
    strong = _fp(contract=["POST /login", "POST /logout"],
                 structural=["Auth"])
    weak = _fp(contract=["POST /login"], structural=["Auth"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=strong),
                 ProposedCapability(local_key="c1", fingerprint=weak)],
                [_identity("BC-001", stored)], allocate=_allocator())
    bykey = {a.local_key: a for a in r.attachments}
    assert bykey["c0"].bc_id == "BC-001"
    assert bykey["c1"].bc_id == "BC-900"
    assert AdvisoryKind.SPLIT in _kinds(r)


def test_detected_merge_marks_the_loser_merged_into_the_winner():
    a = _fp(contract=["POST /login"], structural=["Auth"])
    b = _fp(contract=["POST /login"], structural=["Auth", "Session"])
    now = _fp(contract=["POST /login"], structural=["Auth", "Session"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=now)],
                [_identity("BC-001", a), _identity("BC-002", b)],
                allocate=_allocator())
    winner = r.attachments[0].bc_id
    assert winner == "BC-002"
    assert r.merged == {"BC-001": "BC-002"}
    assert r.retired == []


def test_vanished_capability_is_retired_not_merged():
    stored = _fp(contract=["POST /legacy"], structural=["Legacy"])
    now = _fp(contract=["GET /reports"], structural=["Reporting"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=now)],
                [_identity("BC-001", stored)], allocate=_allocator())
    assert r.retired == ["BC-001"]
    assert r.merged == {}


def test_retired_capability_revives_when_it_reappears():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    stored = _identity("BC-001", fp, status=IdentityStatus.RETIRED,
                       reason=RetiredReason.NOT_OBSERVED)
    r = resolve([ProposedCapability(local_key="c0", fingerprint=fp)],
                [stored], allocate=_allocator())
    assert r.attachments[0].bc_id == "BC-001"
    assert r.retired == []


def test_merged_rows_are_never_matched_against():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    dead = CapabilityIdentity(bc_id="BC-001", project="p", first_seen_run="r0",
                              status=IdentityStatus.MERGED,
                              merged_into="BC-002", fingerprint=fp)
    r = resolve([ProposedCapability(local_key="c0", fingerprint=fp)],
                [dead], allocate=_allocator())
    assert r.attachments[0].bc_id == "BC-900"


def test_near_tie_emits_ambiguous_match():
    now = _fp(contract=["POST /a", "POST /b"], structural=["X"])
    one = _fp(contract=["POST /a", "POST /b"], structural=["X"])
    two = _fp(contract=["POST /a", "POST /b"], structural=["X", "Y"])
    r = resolve([ProposedCapability(local_key="c0", fingerprint=now)],
                [_identity("BC-001", one), _identity("BC-002", two)],
                allocate=_allocator(), epsilon=0.9)
    assert AdvisoryKind.AMBIGUOUS_MATCH in _kinds(r)


def test_resolution_is_deterministic_across_input_order():
    fps = {k: _fp(contract=[f"POST /{k}"], structural=[k.upper()])
           for k in ("a", "b", "c")}
    registry = [_identity(f"BC-00{i}", fps[k])
                for i, k in enumerate(("a", "b", "c"), start=1)]
    proposed = [ProposedCapability(local_key=k, fingerprint=fps[k])
                for k in ("a", "b", "c")]
    first = resolve(proposed, registry, allocate=_allocator())
    second = resolve(list(reversed(proposed)), list(reversed(registry)),
                     allocate=_allocator())
    assert ({(a.local_key, a.bc_id) for a in first.attachments}
            == {(a.local_key, a.bc_id) for a in second.attachments})
