"""FR-913 audited identity corrections (E-47a)."""
import pytest

from sdlc.capability.corrections import (
    CorrectionOp, IdentityCorrection, apply_correction,
)
from sdlc.capability.models import (
    CapabilityFingerprint, CapabilityIdentity, IdentityStatus, RetiredReason,
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
        tiers={SignalTier.CONTRACT: list(contract)},
        collected=Measurement.measured(1.0))


def _seed(store, *rows):
    store.apply("p", rows, expected_version=store.registry_version("p"))


def _identity(bc_id, fp, **kw):
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0",
                              fingerprint=fp, **kw)


def _by_id(store):
    return {r.bc_id: r for r in store.load("p")}


def _correction(op, source, target=None, partition=None):
    return IdentityCorrection(
        operation=op, approved_by="maks", reason="reviewed by hand",
        source_bc_id=source, target_bc_id=target, partition=partition or [])


def test_merge_retires_the_source_into_the_target(store):
    _seed(store, _identity("BC-001", _fp("POST /a")),
          _identity("BC-002", _fp("POST /a", "POST /b")))
    apply_correction(store, "p", _correction(
        CorrectionOp.MERGE, "BC-001", "BC-002"))
    rows = _by_id(store)
    assert rows["BC-001"].status is IdentityStatus.MERGED
    assert rows["BC-001"].merged_into == "BC-002"
    assert rows["BC-002"].status is IdentityStatus.ACTIVE


def test_merge_overwrites_the_survivors_fingerprint(store):
    # Without this the next assessment scores against stale data, misses
    # threshold again, and the human corrects the same thing every run.
    _seed(store, _identity("BC-001", _fp("POST /new")),
          _identity("BC-002", _fp("POST /old")))
    apply_correction(store, "p", _correction(
        CorrectionOp.MERGE, "BC-001", "BC-002"))
    assert _by_id(store)["BC-002"].fingerprint.tiers[
        SignalTier.CONTRACT] == ["POST /new"]


def test_reattach_moves_the_fingerprint_onto_the_existing_id(store):
    _seed(store, _identity("BC-003", _fp("POST /login")),
          _identity("BC-012", _fp("POST /login", "POST /session")))
    apply_correction(store, "p", _correction(
        CorrectionOp.REATTACH, "BC-012", "BC-003"))
    rows = _by_id(store)
    assert rows["BC-012"].status is IdentityStatus.MERGED
    assert rows["BC-012"].merged_into == "BC-003"
    assert rows["BC-003"].fingerprint.tiers[SignalTier.CONTRACT] == [
        "POST /login", "POST /session"]


def test_split_mints_a_new_id_carrying_the_supplied_partition(store):
    _seed(store, _identity("BC-001", _fp("POST /a", "POST /b")))
    apply_correction(store, "p", _correction(
        CorrectionOp.SPLIT, "BC-001", partition=["POST /b"]))
    rows = _by_id(store)
    assert rows["BC-002"].derived_from == "BC-001"
    assert rows["BC-002"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /b"]
    # The source keeps everything not moved out.
    assert rows["BC-001"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /a"]


def test_split_requires_a_partition(store):
    _seed(store, _identity("BC-001", _fp("POST /a")))
    with pytest.raises(ValueError, match="partition"):
        apply_correction(store, "p", _correction(
            CorrectionOp.SPLIT, "BC-001"))


def test_merge_requires_a_target(store):
    _seed(store, _identity("BC-001", _fp("POST /a")))
    with pytest.raises(ValueError, match="target_bc_id"):
        apply_correction(store, "p", _correction(
            CorrectionOp.MERGE, "BC-001"))


def test_correction_requires_an_approver_and_a_reason():
    with pytest.raises(ValueError, match="approved_by"):
        IdentityCorrection(operation=CorrectionOp.MERGE, approved_by="  ",
                           reason="r", source_bc_id="BC-001",
                           target_bc_id="BC-002")
    with pytest.raises(ValueError, match="reason"):
        IdentityCorrection(operation=CorrectionOp.MERGE, approved_by="maks",
                           reason=" ", source_bc_id="BC-001",
                           target_bc_id="BC-002")


def test_merge_is_idempotent_by_target_state(store):
    _seed(store, _identity("BC-001", _fp("POST /a")),
          _identity("BC-002", _fp("POST /a")))
    c = _correction(CorrectionOp.MERGE, "BC-001", "BC-002")
    first = apply_correction(store, "p", c)
    second = apply_correction(store, "p", c)
    assert second == first          # no-op: version does not move
    assert _by_id(store)["BC-001"].merged_into == "BC-002"


def test_unknown_source_raises(store):
    with pytest.raises(ValueError, match="BC-404"):
        apply_correction(store, "p", _correction(
            CorrectionOp.MERGE, "BC-404", "BC-001"))


def test_correction_bumps_the_registry_version(store):
    _seed(store, _identity("BC-001", _fp("POST /a")),
          _identity("BC-002", _fp("POST /a")))
    before = store.registry_version("p")
    apply_correction(store, "p", _correction(
        CorrectionOp.MERGE, "BC-001", "BC-002"))
    assert store.registry_version("p") == before + 1
