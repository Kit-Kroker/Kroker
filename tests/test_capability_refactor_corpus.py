"""FR-913 mechanical refactor corpus (E-47a).

Ground truth generated rather than hand-labelled: apply a KNOWN refactor to a
fingerprint and assert identity survives (or does not). This is what
calibrates T_MATCH and DEFAULT_TIER_WEIGHTS before the first client
repository, and it directly falsifies the Contract-tier weighting claim -- if
renaming every symbol broke identity while changing one route did not, the
weighting would be wrong.
"""
import itertools

import pytest

from sdlc.capability.matcher import resolve
from sdlc.capability.models import (
    CapabilityFingerprint, CapabilityIdentity, ProposedCapability, SignalTier,
)
from sdlc.measurement import Measurement

BASE = {
    SignalTier.CONTRACT: ["POST /auth/login", "POST /auth/logout",
                          "table:users", "table:sessions"],
    SignalTier.BEHAVIORAL: ["test_login_succeeds", "test_logout_clears",
                            "entity:User", "entity:Session"],
    SignalTier.STRUCTURAL: ["AuthService", "SessionStore", "TokenCodec"],
    SignalTier.LOCATIONAL: ["src/auth/service.py", "src/auth/session.py"],
}


def _fp(tiers) -> CapabilityFingerprint:
    return CapabilityFingerprint(tiers=dict(tiers),
                                 collected=Measurement.measured(1.0))


def _mutate(**overrides):
    tiers = dict(BASE)
    tiers.update(overrides)
    return _fp(tiers)


def _resolves_to_same_id(after: CapabilityFingerprint) -> bool:
    stored = CapabilityIdentity(bc_id="BC-001", project="p",
                                first_seen_run="r0", fingerprint=_fp(BASE))
    counter = itertools.count(900)
    result = resolve(
        [ProposedCapability(local_key="c0", fingerprint=after)],
        [stored], allocate=lambda: f"BC-{next(counter)}")
    return result.attachments[0].bc_id == "BC-001"


# --- refactors identity MUST survive ------------------------------------

SURVIVES = {
    "move_every_file": {
        SignalTier.LOCATIONAL: ["pkg/identity/svc.py", "pkg/identity/sess.py"],
    },
    "rename_every_symbol": {
        SignalTier.STRUCTURAL: ["IdentityService", "SessionRepository",
                                "JwtCodec"],
    },
    "move_and_rename_together": {
        SignalTier.STRUCTURAL: ["IdentityService", "SessionRepository",
                                "JwtCodec"],
        SignalTier.LOCATIONAL: ["pkg/identity/svc.py", "pkg/identity/sess.py"],
    },
    "extract_a_module": {
        SignalTier.STRUCTURAL: ["AuthService", "SessionStore", "TokenCodec",
                                "TokenRotation", "ClockSkew"],
        SignalTier.LOCATIONAL: ["src/auth/service.py", "src/auth/session.py",
                                "src/auth/rotation.py"],
    },
    "add_one_endpoint": {
        SignalTier.CONTRACT: ["POST /auth/login", "POST /auth/logout",
                              "POST /auth/refresh", "table:users",
                              "table:sessions"],
    },
    "rename_a_test": {
        SignalTier.BEHAVIORAL: ["test_login_returns_token",
                                "test_logout_clears", "entity:User",
                                "entity:Session"],
    },
}


@pytest.mark.parametrize("name", sorted(SURVIVES))
def test_identity_survives_internal_refactor(name):
    assert _resolves_to_same_id(_mutate(**SURVIVES[name])), (
        f"{name} broke identity; the tier weighting is not doing its job")


# --- changes identity MUST NOT survive ----------------------------------

BREAKS = {
    "different_capability_entirely": {
        SignalTier.CONTRACT: ["GET /reports/monthly", "table:invoices"],
        SignalTier.BEHAVIORAL: ["test_monthly_totals", "entity:Invoice"],
        SignalTier.STRUCTURAL: ["ReportBuilder", "InvoiceQuery"],
        SignalTier.LOCATIONAL: ["src/reports/monthly.py"],
    },
    "whole_contract_replaced_and_internals_too": {
        SignalTier.CONTRACT: ["POST /v2/identity", "table:principals"],
        SignalTier.BEHAVIORAL: ["test_principal_created", "entity:Principal"],
        SignalTier.STRUCTURAL: ["PrincipalService"],
        SignalTier.LOCATIONAL: ["src/principal/service.py"],
    },
}


@pytest.mark.parametrize("name", sorted(BREAKS))
def test_unrelated_capability_does_not_inherit_the_id(name):
    assert not _resolves_to_same_id(_mutate(**BREAKS[name])), (
        f"{name} wrongly inherited BC-001; T_MATCH is too permissive")


def test_contract_tier_outweighs_all_internal_tiers_combined():
    """The Section 2 claim, stated as an executable assertion: preserving the
    contract while changing every internal signal must beat changing the
    contract while preserving every internal signal."""
    internals_changed = _mutate(**{
        SignalTier.STRUCTURAL: ["Xx", "Yy", "Zz"],
        SignalTier.LOCATIONAL: ["a/b.py", "c/d.py"],
        SignalTier.BEHAVIORAL: ["test_q", "test_r", "entity:Q", "entity:R"],
    })
    contract_changed = _mutate(**{
        SignalTier.CONTRACT: ["GET /other", "table:other"],
    })
    assert _resolves_to_same_id(internals_changed)
    assert not _resolves_to_same_id(contract_changed)
