"""FR-913 identity persistence (E-47a)."""
import pytest

from sdlc.capability.models import (
    CapabilityFingerprint, CapabilityIdentity, IdentityStatus, RetiredReason,
    SignalTier,
)
from sdlc.capability.store import (
    BoardIdentityStore, IdentityConflictError,
)
from sdlc.measurement import Measurement


@pytest.fixture()
def store(tmp_path):
    s = BoardIdentityStore(db=tmp_path / "board.sqlite3")
    yield s
    s.close()


def _fp(**tiers) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier(k): v for k, v in tiers.items()},
        collected=Measurement.measured(1.0))


def _identity(bc_id, **kw) -> CapabilityIdentity:
    kw.setdefault("fingerprint", _fp(contract=[f"POST /{bc_id}"]))
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0",
                              **kw)


def test_empty_project_loads_empty_at_version_zero(store):
    assert store.load("p") == []
    assert store.registry_version("p") == 0


def test_apply_round_trips_an_identity(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    (got,) = store.load("p")
    assert got.bc_id == "BC-001"
    assert got.fingerprint.tiers[SignalTier.CONTRACT] == ["POST /BC-001"]


def test_apply_bumps_registry_version(store):
    assert store.apply("p", [_identity("BC-001")], expected_version=0) == 1
    assert store.apply("p", [_identity("BC-002")], expected_version=1) == 2


def test_stale_expected_version_conflicts(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    with pytest.raises(IdentityConflictError):
        store.apply("p", [_identity("BC-002")], expected_version=0)


def test_apply_upserts_an_existing_row(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    store.apply("p", [_identity("BC-001", status=IdentityStatus.RETIRED,
                                retired_reason=RetiredReason.NOT_OBSERVED)],
                expected_version=1)
    (got,) = store.load("p")
    assert got.status is IdentityStatus.RETIRED
    assert got.retired_reason is RetiredReason.NOT_OBSERVED


def test_projects_are_isolated(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    assert store.load("other") == []
    assert store.registry_version("other") == 0


def test_allocator_is_monotonic_and_never_reuses(store):
    alloc = store.allocator("p")
    assert [alloc(), alloc()] == ["BC-001", "BC-002"]
    store.apply("p", [_identity("BC-001"), _identity("BC-002")],
                expected_version=0)
    assert store.allocator("p")() == "BC-003"


def test_allocator_skips_retired_ids(store):
    store.apply("p", [_identity("BC-001", status=IdentityStatus.RETIRED,
                                retired_reason=RetiredReason.NOT_OBSERVED)],
                expected_version=0)
    # Never reuse: BC-001 is retired, not free.
    assert store.allocator("p")() == "BC-002"


def test_load_returns_rows_sorted_by_bc_id(store):
    store.apply("p", [_identity("BC-003"), _identity("BC-001"),
                      _identity("BC-002")], expected_version=0)
    assert [r.bc_id for r in store.load("p")] == ["BC-001", "BC-002", "BC-003"]


def test_reopening_the_same_db_sees_prior_state(tmp_path):
    db = tmp_path / "board.sqlite3"
    first = BoardIdentityStore(db=db)
    first.apply("p", [_identity("BC-001")], expected_version=0)
    first.close()
    second = BoardIdentityStore(db=db)
    assert [r.bc_id for r in second.load("p")] == ["BC-001"]
    assert second.registry_version("p") == 1
    second.close()
