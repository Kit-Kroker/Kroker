"""FR-913 (E-48 DD3): MemberKind -> SignalTier, total, and deliberately not
CONTRACT_KINDS."""

from __future__ import annotations

import random

from sdlc.assessment.discover.models import CONTRACT_KINDS
from sdlc.assessment.discover.tiers import MEMBER_TIERS, group_by_tier
from sdlc.assessment.scan.models import CandidateMember, MemberKind
from sdlc.capability.models import SignalTier


def test_every_member_kind_has_a_tier():
    """D13: the mapping is TOTAL. Adding a kind to the enum must fail here
    rather than silently landing in no tier."""
    assert set(MEMBER_TIERS) == set(MemberKind)


def test_contract_tier_and_contract_kinds_differ_by_exactly_db_table():
    """E-47c D4's warning, made checkable in both directions.

    A table is contract-tier IDENTITY evidence (a table name survives a
    refactor that renames every symbol) but it is NOT an operation -- an
    operation is something the system DOES, and a table is something it HAS.
    Deriving either set from the other would be wrong.
    """
    tier_contract = {k for k, t in MEMBER_TIERS.items() if t is SignalTier.CONTRACT}
    assert tier_contract - CONTRACT_KINDS == {MemberKind.DB_TABLE}
    assert CONTRACT_KINDS - tier_contract == set()


def test_entity_name_belongs_to_neither_set():
    """The other half of the same point: ENTITY_NAME reads as contract-ish
    vocabulary, but it is behavioral identity evidence and not an operation.
    The two vocabularies classify on different axes."""
    assert MEMBER_TIERS[MemberKind.ENTITY_NAME] is SignalTier.BEHAVIORAL
    assert MemberKind.ENTITY_NAME not in CONTRACT_KINDS


def test_group_by_tier_carries_every_tier_including_empty_ones():
    """An absent key and an empty list are different claims, and only one of
    them is true -- AttributionReport._counts_agree_with_files' rule."""
    grouped = group_by_tier(
        [
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay"),
        ]
    )
    assert set(grouped) == set(SignalTier)
    assert grouped[SignalTier.CONTRACT] == ["POST /pay"]
    assert grouped[SignalTier.BEHAVIORAL] == []


def test_group_by_tier_is_sorted_and_deduped():
    grouped = group_by_tier(
        [
            CandidateMember(kind=MemberKind.DB_TABLE, value="orders"),
            CandidateMember(kind=MemberKind.DB_TABLE, value="accounts"),
            CandidateMember(kind=MemberKind.DB_TABLE, value="orders", path="other.py"),
        ]
    )
    assert grouped[SignalTier.CONTRACT] == ["accounts", "orders"]


def test_group_by_tier_is_order_independent():
    """NFR-10: discovery order must not reach the artifact."""
    members = [
        CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /a"),
        CandidateMember(kind=MemberKind.TEST_NAME, value="test_b"),
        CandidateMember(kind=MemberKind.FILE_PATH, value="c.py"),
        CandidateMember(kind=MemberKind.EXPORTED_SYMBOL, value="d"),
    ]
    first = group_by_tier(members)
    for _ in range(5):
        shuffled = members[:]
        random.shuffle(shuffled)
        assert group_by_tier(shuffled) == first
