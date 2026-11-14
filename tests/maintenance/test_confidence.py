"""The R8 confidence-floor table (023a T011, RED).

Authorship note: both QA seats are quota-blocked until 23:50; this file is
executor-written under the degradation ruling — every case is a row of the
R8 table (research.md §R8) or a direct consequence of it.

Subject: ``sdlc.maintenance.confidence.confidence_floor`` — does not exist
yet (T012 implements). Table:

    fix class   ceiling   subtract                                        floor at
    MECHANICAL  0.95      0.15 if not reproduced, 0.20/reopen, 0.05/action>1  0
    JUDGEMENT   0.6       same                                            0
    STRUCTURAL  0.0       —                                               0
"""

from __future__ import annotations

import pytest

from sdlc.maintenance.confidence import confidence_floor
from sdlc.triage.models import FixClass, TriageFinding

from tests.maintenance.conftest import env_file_findings


def _mechanical() -> TriageFinding:
    return env_file_findings()[1]  # env_file_tracked: MECHANICAL


def _judgement() -> TriageFinding:
    return env_file_findings()[0]  # secret_committed: JUDGEMENT


def _structural() -> TriageFinding:
    return TriageFinding(
        signal="scaffold",
        rule="no_package_layout",
        severity="medium",
        detail="fixture",
        fix_class=FixClass.STRUCTURAL,
    )


# --- ceilings ------------------------------------------------------------- #


def test_mechanical_ceiling_is_095():
    v = confidence_floor(_mechanical(), reproduced=True, reopens=0, n_actions=1)
    assert v == pytest.approx(0.95)


def test_judgement_ceiling_is_06():
    v = confidence_floor(_judgement(), reproduced=True, reopens=0, n_actions=1)
    assert v == pytest.approx(0.6)


def test_structural_is_zero_no_matter_what():
    assert confidence_floor(_structural(), reproduced=True, reopens=0, n_actions=1) == 0.0
    assert confidence_floor(_structural(), reproduced=False, reopens=5, n_actions=9) == 0.0


# --- subtractions ---------------------------------------------------------- #


def test_not_reproduced_subtracts_015():
    v = confidence_floor(_mechanical(), reproduced=False, reopens=0, n_actions=1)
    assert v == pytest.approx(0.95 - 0.15)
    v2 = confidence_floor(_judgement(), reproduced=False, reopens=0, n_actions=1)
    assert v2 == pytest.approx(0.6 - 0.15)


@pytest.mark.parametrize("reopens,expected", [(0, 0.95), (1, 0.75), (2, 0.55), (3, 0.35)])
def test_each_reopen_subtracts_02(reopens, expected):
    v = confidence_floor(_mechanical(), reproduced=True, reopens=reopens, n_actions=1)
    assert v == pytest.approx(expected)


@pytest.mark.parametrize("n_actions,expected", [(1, 0.95), (2, 0.90), (5, 0.75), (6, 0.70)])
def test_each_action_beyond_one_subtracts_005(n_actions, expected):
    v = confidence_floor(_mechanical(), reproduced=True, reopens=0, n_actions=n_actions)
    assert v == pytest.approx(expected)


def test_all_subtractions_stack():
    v = confidence_floor(_mechanical(), reproduced=False, reopens=1, n_actions=3)
    assert v == pytest.approx(0.95 - 0.15 - 0.20 - 0.10)


# --- floored at zero -------------------------------------------------------- #


def test_never_below_zero():
    v = confidence_floor(_judgement(), reproduced=False, reopens=3, n_actions=6)
    # 0.6 - 0.15 - 0.6 - 0.25 = -0.4 -> floored
    assert v == 0.0


# --- purity ---------------------------------------------------------------- #


def test_pure_repeated_calls_are_equal_and_finding_unmutated():
    f = _mechanical()
    before = f.model_dump()
    a = confidence_floor(f, reproduced=True, reopens=1, n_actions=2)
    b = confidence_floor(f, reproduced=True, reopens=1, n_actions=2)
    assert a == b
    assert f.model_dump() == before


def test_effective_is_min_of_self_and_floor():
    # FR-010: effective confidence is the lower of the proposer's self-rating
    # and this code-computed floor.
    floor = confidence_floor(_judgement(), reproduced=True, reopens=0, n_actions=1)
    assert floor == pytest.approx(0.6)
    assert min(0.2, floor) == 0.2  # self below the floor: self wins
    assert min(0.99, floor) == pytest.approx(0.6)  # self above: the floor caps
