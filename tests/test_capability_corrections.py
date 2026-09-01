"""FR-913 audited identity corrections (E-47a)."""

import pytest

from sdlc.capability.corrections import (
    CorrectionOp,
    IdentityCorrection,
    apply_correction,
)
from sdlc.capability.models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    RetiredReason,
    SignalTier,
)
from sdlc.capability.store import BoardIdentityStore
from sdlc.measurement import Measurement


@pytest.fixture()
def store(tmp_path):
    s = BoardIdentityStore(db=tmp_path / "board.sqlite3")
    yield s
    s.close()


def _fp(*contract) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(contract)}, collected=Measurement.measured(1.0)
    )


def _seed(store, *rows):
    store.apply("p", rows, expected_version=store.registry_version("p"))


def _identity(bc_id, fp, **kw):
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0", fingerprint=fp, **kw)


def _by_id(store):
    return {r.bc_id: r for r in store.load("p")}


def _correction(op, source, target=None, partition=None):
    return IdentityCorrection(
        operation=op,
        approved_by="maks",
        reason="reviewed by hand",
        source_bc_id=source,
        target_bc_id=target,
        partition=partition or [],
    )


def test_merge_retires_the_source_into_the_target(store):
    _seed(
        store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /a", "POST /b"))
    )
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    rows = _by_id(store)
    assert rows["BC-001"].status is IdentityStatus.MERGED
    assert rows["BC-001"].merged_into == "BC-002"
    assert rows["BC-002"].status is IdentityStatus.ACTIVE


def test_merge_overwrites_the_survivors_fingerprint(store):
    # Without this the next assessment scores against stale data, misses
    # threshold again, and the human corrects the same thing every run.
    _seed(store, _identity("BC-001", _fp("POST /new")), _identity("BC-002", _fp("POST /old")))
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    assert _by_id(store)["BC-002"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /new"]


def test_reattach_moves_the_fingerprint_onto_the_existing_id(store):
    _seed(
        store,
        _identity("BC-003", _fp("POST /login")),
        _identity("BC-012", _fp("POST /login", "POST /session")),
    )
    apply_correction(store, "p", _correction(CorrectionOp.REATTACH, "BC-012", "BC-003"))
    rows = _by_id(store)
    assert rows["BC-012"].status is IdentityStatus.MERGED
    assert rows["BC-012"].merged_into == "BC-003"
    assert rows["BC-003"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /login", "POST /session"]


def test_split_mints_a_new_id_carrying_the_supplied_partition(store):
    _seed(store, _identity("BC-001", _fp("POST /a", "POST /b")))
    apply_correction(store, "p", _correction(CorrectionOp.SPLIT, "BC-001", partition=["POST /b"]))
    rows = _by_id(store)
    assert rows["BC-002"].derived_from == "BC-001"
    assert rows["BC-002"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /b"]
    # The source keeps everything not moved out.
    assert rows["BC-001"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /a"]


def test_split_requires_a_partition(store):
    _seed(store, _identity("BC-001", _fp("POST /a")))
    with pytest.raises(ValueError, match="partition"):
        apply_correction(store, "p", _correction(CorrectionOp.SPLIT, "BC-001"))


def test_merge_requires_a_target(store):
    _seed(store, _identity("BC-001", _fp("POST /a")))
    with pytest.raises(ValueError, match="target_bc_id"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001"))


def test_correction_requires_an_approver_and_a_reason():
    with pytest.raises(ValueError, match="approved_by"):
        IdentityCorrection(
            operation=CorrectionOp.MERGE,
            approved_by="  ",
            reason="r",
            source_bc_id="BC-001",
            target_bc_id="BC-002",
        )
    with pytest.raises(ValueError, match="reason"):
        IdentityCorrection(
            operation=CorrectionOp.MERGE,
            approved_by="maks",
            reason=" ",
            source_bc_id="BC-001",
            target_bc_id="BC-002",
        )


def test_merge_is_idempotent_by_target_state(store):
    _seed(store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /a")))
    c = _correction(CorrectionOp.MERGE, "BC-001", "BC-002")
    first = apply_correction(store, "p", c)
    second = apply_correction(store, "p", c)
    assert second == first  # no-op: version does not move
    assert _by_id(store)["BC-001"].merged_into == "BC-002"


def test_unknown_source_raises(store):
    with pytest.raises(ValueError, match="BC-404"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-404", "BC-001"))


def test_correction_bumps_the_registry_version(store):
    _seed(store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /a")))
    before = store.registry_version("p")
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    assert store.registry_version("p") == before + 1


# --- review #1: a merge must never target a non-active row --------------


def test_reversed_merge_cannot_create_a_cycle(store):
    # The operator-recovery case: merge the wrong direction, then try to
    # reverse it. Without the guard, BC-002 -> BC-001 makes both rows MERGED
    # into each other, so resolve() has no candidate and mints a new id on
    # every assessment forever; a client walking merged_into loops infinitely.
    _seed(store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /b")))
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    with pytest.raises(ValueError):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-002", "BC-001"))
    rows = _by_id(store)
    assert rows["BC-002"].status is IdentityStatus.ACTIVE
    assert rows["BC-001"].merged_into == "BC-002"


def test_merge_into_a_merged_target_names_the_live_head(store):
    # The silent-discard variant: BC-001 is merged, so it is excluded from
    # matching. Absorbing BC-003 into it would discard the fingerprint
    # inheritance that makes a correction stick. Reject and point at the head.
    _seed(
        store,
        _identity("BC-001", _fp("POST /a")),
        _identity("BC-002", _fp("POST /b")),
        _identity("BC-003", _fp("POST /c")),
    )
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    with pytest.raises(ValueError, match="BC-002"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-003", "BC-001"))


def test_merge_head_follows_a_transitive_chain(store):
    # BC-001 -> BC-002 -> BC-003. Naming BC-003 (the active head), not BC-002,
    # is what tells the operator where to retarget.
    _seed(
        store,
        _identity("BC-001", _fp("POST /a")),
        _identity("BC-002", _fp("POST /b")),
        _identity("BC-003", _fp("POST /c")),
        _identity("BC-004", _fp("POST /d")),
    )
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-002", "BC-003"))
    with pytest.raises(ValueError, match="BC-003"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-004", "BC-001"))


def test_merge_into_a_retired_target_is_rejected(store):
    _seed(
        store,
        _identity(
            "BC-001",
            _fp("POST /a"),
            status=IdentityStatus.RETIRED,
            retired_reason=RetiredReason.NOT_OBSERVED,
        ),
        _identity("BC-002", _fp("POST /b")),
    )
    with pytest.raises(ValueError, match="retired"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-002", "BC-001"))


# --- review #2: the correction reason must be retained, not discarded ----


def test_correction_reason_is_recorded_in_the_event(store):
    # corrections.py says reason "is retained as a calibration signal" and
    # _audited rejects a blank one. apply() was writing row.status.value into
    # event.detail and dropping the reason entirely -- validated, required,
    # thrown away. The detail column is where it belongs.
    _seed(store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /b")))
    apply_correction(
        store,
        "p",
        IdentityCorrection(
            operation=CorrectionOp.MERGE,
            approved_by="maks",
            reason="THE HUMAN JUSTIFICATION",
            source_bc_id="BC-001",
            target_bc_id="BC-002",
        ),
    )
    detail = store._conn.execute(
        "SELECT detail FROM capability_event WHERE bc_id = ? "
        "AND operation = ? ORDER BY id DESC LIMIT 1",
        ("BC-001", "merge"),
    ).fetchone()[0]
    assert "THE HUMAN JUSTIFICATION" in detail


# --- review #5: a self-merge is a no-op that lies about success ----------


def test_self_merge_is_rejected_and_does_not_bump_version(store):
    # merge --from BC-001 --into BC-001 returned exit 0, bumped the version,
    # and wrote a spurious 'merged' event while the row was unchanged (the
    # survivor overwrites the absorbed row in the same transaction). The
    # invalid self-merge object existed in memory and survived only by write
    # ordering. Reject it outright instead.
    _seed(store, _identity("BC-001", _fp("POST /a")))
    before = store.registry_version("p")
    with pytest.raises(ValueError, match="itself"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-001"))
    assert store.registry_version("p") == before


def test_self_reattach_is_rejected(store):
    _seed(store, _identity("BC-001", _fp("POST /a")))
    with pytest.raises(ValueError, match="itself"):
        apply_correction(store, "p", _correction(CorrectionOp.REATTACH, "BC-001", "BC-001"))


# --- review #6: a split must not empty the source nor swallow a typo -----


def test_split_that_empties_the_source_is_rejected(store):
    # Naming every member in the partition left BC-001 as an empty husk: no
    # shared tier can ever match again (score() returns None), and its export
    # digest is identical to every other empty fingerprint.
    _seed(store, _identity("BC-001", _fp("POST /a", "POST /b")))
    with pytest.raises(ValueError, match="husk"):
        apply_correction(
            store, "p", _correction(CorrectionOp.SPLIT, "BC-001", partition=["POST /a", "POST /b"])
        )


def test_split_with_a_non_matching_member_is_rejected(store):
    # A typo in one --member would otherwise move the matching members and
    # report success, silently dropping the typo'd entry.
    _seed(store, _identity("BC-001", _fp("POST /a", "POST /b")))
    with pytest.raises(ValueError, match="not present"):
        apply_correction(
            store, "p", _correction(CorrectionOp.SPLIT, "BC-001", partition=["POST /a", "TYPO"])
        )
