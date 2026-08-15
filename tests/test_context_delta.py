"""E-84 D7/D8/D9: three classes, opposite rules, no rescue by basename."""
from __future__ import annotations

import random

from sdlc.context.delta import DELTA_CHECK, check_delta, normalize_path
from sdlc.gate import CheckClass
from sdlc.models import BrownfieldDelta

TREE = frozenset({"src/payments/api.py", "src/payments/store.py",
                  "tests/test_api.py", "README.md"})


def test_a_grounded_delta_passes():
    got = check_delta(
        BrownfieldDelta(added=["src/payments/refund.py"],
                        modified=["src/payments/api.py"],
                        removed=["src/payments/store.py"]), TREE)
    assert got.passed is True
    assert got.name == DELTA_CHECK
    assert got.classification is CheckClass.ABSOLUTE


def test_modifying_a_file_that_does_not_exist_fails():
    got = check_delta(
        BrownfieldDelta(modified=["src/payments/ghost.py"]), TREE)
    assert got.passed is False
    assert "src/payments/ghost.py" in got.detail
    assert "modified" in got.detail


def test_removing_a_file_that_does_not_exist_fails():
    got = check_delta(BrownfieldDelta(removed=["nope.py"]), TREE)
    assert got.passed is False
    assert "removed" in got.detail


def test_adding_a_file_that_already_exists_fails():
    """D8: the contradiction is the same species and the check is free."""
    got = check_delta(BrownfieldDelta(added=["src/payments/api.py"]), TREE)
    assert got.passed is False
    assert "already exists" in got.detail


def test_a_missing_delta_fails_rather_than_passing_vacuously():
    """D7: ArchitectureSpec cannot see the mode, so the stage enforces it
    here -- and an absent delta must never read as a grounded one."""
    got = check_delta(None, TREE)
    assert got.passed is False
    assert "no delta" in got.detail.lower()


def test_an_empty_delta_fails():
    got = check_delta(BrownfieldDelta(), TREE)
    assert got.passed is False
    assert "names no files" in got.detail


def test_windows_separators_and_dot_slash_normalize():
    got = check_delta(
        BrownfieldDelta(modified=["src\\payments\\api.py",
                                  "./tests/test_api.py"]), TREE)
    assert got.passed is True


def test_a_basename_match_is_not_a_match():
    """D9: normalization aggressive enough to rescue a wrong path is
    normalization that launders fabrication into a pass. Pinned as a test so
    a future 'helpful' relaxation trips it."""
    got = check_delta(BrownfieldDelta(modified=["api.py"]), TREE)
    assert got.passed is False
    got = check_delta(BrownfieldDelta(modified=["other/payments/api.py"]),
                      TREE)
    assert got.passed is False


def test_normalize_leaves_a_clean_path_alone():
    assert normalize_path("src/payments/api.py") == "src/payments/api.py"
    assert normalize_path("/src/api.py") == "src/api.py"


def test_every_unresolvable_path_is_named_not_just_the_first():
    got = check_delta(
        BrownfieldDelta(modified=["a.py", "b.py"], removed=["c.py"]), TREE)
    for p in ("a.py", "b.py", "c.py"):
        assert p in got.detail


def test_the_detail_is_order_independent():
    """NFR-10: the same failure reads identically however the lists arrive,
    because the detail becomes re-prompt guidance and an unstable string
    would move the architect memo key."""
    paths = ["a.py", "b.py", "c.py", "d.py"]
    first = check_delta(BrownfieldDelta(modified=paths), TREE).detail
    for _ in range(5):
        shuffled = paths[:]
        random.shuffle(shuffled)
        assert check_delta(BrownfieldDelta(modified=shuffled),
                           TREE).detail == first
