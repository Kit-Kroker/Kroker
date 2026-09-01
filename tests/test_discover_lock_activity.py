# tests/test_discover_lock_activity.py
"""FR-913 (E-48 D4/DD5): the lock is identity resolution, and it fails
closed."""

from __future__ import annotations

import pytest

from sdlc.assessment.activities import DiscoverLockInput, discover_lock
from sdlc.capability.models import (
    AttachMethod,
    CapabilityFingerprint,
    ProposedCapability,
    SignalTier,
)
from sdlc.capability.store import BoardIdentityStore
from sdlc.measurement import Measurement

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    return tmp_path / "board.sqlite3"


def _fp(*routes) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(routes)},
        collected=Measurement.measured(float(len(routes))),
    )


def _proposed(local_key="C-01", *routes) -> ProposedCapability:
    return ProposedCapability(local_key=local_key, fingerprint=_fp(*(routes or ("POST /pay",))))


async def test_the_lock_mints_ids_and_persists_them():
    out = await discover_lock(
        DiscoverLockInput(
            project="acme",
            run_id="run-1",
            proposed=[_proposed("C-01"), _proposed("C-02", "GET /orders")],
        )
    )
    assert {a.local_key for a in out.attachments} == {"C-01", "C-02"}
    assert all(a.method is AttachMethod.FIRST_DISCOVERY for a in out.attachments)

    store = BoardIdentityStore()
    try:
        rows = store.load("acme")
    finally:
        store.close()
    assert {r.bc_id for r in rows} == {a.bc_id for a in out.attachments}
    assert all(r.first_seen_run == "run-1" for r in rows)


async def test_a_second_lock_on_the_same_fingerprints_reattaches():
    """E-47a's central guarantee: an id clients cite does not move because
    the assessment ran again."""
    first = await discover_lock(
        DiscoverLockInput(project="acme", run_id="run-1", proposed=[_proposed("C-01")])
    )
    second = await discover_lock(
        DiscoverLockInput(project="acme", run_id="run-2", proposed=[_proposed("C-01")])
    )
    assert second.attachments[0].bc_id == first.attachments[0].bc_id
    assert second.attachments[0].method is AttachMethod.MATCHED


async def test_the_lock_returns_the_new_registry_version():
    """The memo's store-side key term (P2-D3)."""
    out = await discover_lock(
        DiscoverLockInput(project="acme", run_id="run-1", proposed=[_proposed("C-01")])
    )
    assert out.registry_version == 1


async def test_an_empty_proposal_does_not_move_the_registry_version():
    """P2-D7: apply() bumps the version and writes one audit event per row.
    With no rows it would bump the version and record nothing, invalidating
    every project memo for a write that did not happen."""
    out = await discover_lock(DiscoverLockInput(project="acme", run_id="run-1", proposed=[]))
    assert out.attachments == []
    assert out.registry_version == 0


async def test_an_unreachable_store_raises_rather_than_degrading(tmp_path, monkeypatch):
    """DD9 and E-47a's fail-closed rule: proceeding produces a complete,
    plausible-looking map in which every id is wrong. The phase must report
    not_collected, which means this activity raises."""
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path))
    # The contract under test is "raises at all", whatever the store's
    # failure mode; naming one exception type would weaken it.
    with pytest.raises(Exception):  # noqa: B017
        await discover_lock(
            DiscoverLockInput(project="acme", run_id="run-1", proposed=[_proposed("C-01")])
        )
