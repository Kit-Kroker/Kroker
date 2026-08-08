"""FR-913 greedy one-to-one assignment (E-47a)."""
from sdlc.capability.matcher import Pair, assign


def test_single_pair_attaches():
    assert assign([Pair(0.9, "BC-001", "c0")]) == {"c0": "BC-001"}


def test_two_locals_cannot_both_claim_one_id():
    # The naive per-capability argmax would give BC-001 to both.
    got = assign([Pair(0.9, "BC-001", "c0"), Pair(0.8, "BC-001", "c1")])
    assert got == {"c0": "BC-001"}


def test_one_local_cannot_claim_two_ids():
    got = assign([Pair(0.9, "BC-001", "c0"), Pair(0.8, "BC-002", "c0")])
    assert got == {"c0": "BC-001"}


def test_strong_pair_wins_regardless_of_other_candidates():
    # Local stability: c0/BC-001 is the best pair and must survive whatever
    # else is present. This is the property Hungarian does NOT guarantee.
    got = assign([
        Pair(0.95, "BC-001", "c0"),
        Pair(0.94, "BC-001", "c1"),
        Pair(0.93, "BC-002", "c1"),
        Pair(0.10, "BC-002", "c0"),
    ])
    assert got["c0"] == "BC-001"
    assert got["c1"] == "BC-002"


def test_ties_break_on_bc_id_ascending():
    got = assign([Pair(0.7, "BC-002", "c0"), Pair(0.7, "BC-001", "c0")])
    assert got == {"c0": "BC-001"}


def test_ties_on_score_and_bc_id_break_on_local_key_ascending():
    got = assign([Pair(0.7, "BC-001", "c1"), Pair(0.7, "BC-001", "c0")])
    assert got == {"c0": "BC-001"}


def test_assignment_is_order_independent():
    pairs = [Pair(0.9, "BC-001", "c0"), Pair(0.8, "BC-002", "c1"),
             Pair(0.7, "BC-001", "c1")]
    assert assign(pairs) == assign(list(reversed(pairs)))


def test_no_pairs_yields_no_assignments():
    assert assign([]) == {}
