# tests/test_discover_guard.py
"""E-48 DD8: past a 0.10 fabrication rate, too many references failed to
resolve for the surviving ones to be evidence."""

from sdlc.assessment.discover.apply import (
    ApplyResult,
    LockedCandidate,
    StampedProposal,
    build_map,
)
from sdlc.assessment.discover.map import (
    CITATION_GUARD_MAX_UNRESOLVED,
    CandidateDisposition,
    DiscoverAction,
    DiscoverProposal,
    DispositionSource,
    guard_tripped,
)
from sdlc.assessment.discover.verify import RefVerification
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement


def _verification(total: int, unresolved: int) -> RefVerification:
    return RefVerification(
        proposal=DiscoverProposal(), total_references=total, unresolved_references=unresolved
    )


def test_the_threshold_matches_e47bs_dead_guard():
    """Same value for the same reason -- two guards that drift apart are two
    unexplained numbers."""
    from sdlc.assessment.discover.models import DEAD_GUARD_MAX_UNRESOLVED

    assert CITATION_GUARD_MAX_UNRESOLVED == DEAD_GUARD_MAX_UNRESOLVED


def test_a_clean_proposal_does_not_trip():
    assert guard_tripped(_verification(20, 0)) == ""


def test_exactly_at_the_threshold_does_not_trip():
    """PAST 0.10, not at it -- the boundary belongs to the passing side."""
    assert guard_tripped(_verification(20, 2)) == ""


def test_past_the_threshold_trips_and_names_both_terms():
    reason = guard_tripped(_verification(20, 3))
    assert reason != ""
    assert "3" in reason and "20" in reason


def test_no_references_never_trips():
    """P3-D2: a proposer that cited nothing fabricated nothing. Unevidenced is
    a different complaint and not this guard's."""
    assert guard_tripped(_verification(0, 0)) == ""


def test_total_references_reaches_the_map():
    """The number a customer would need to audit the guard's arithmetic must
    be on the artifact, not only in the workflow's history."""
    measured = Measurement.measured(1.0)
    disp = CandidateDisposition(
        candidate_id="C-01",
        action=DiscoverAction.CONFIRM,
        source=DispositionSource.BASELINE,
        rule="baseline_confirm",
    )
    locked = LockedCandidate(
        local_key="C-01",
        name="payments",
        confidence=Confidence.HIGH,
        members=(
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py"),
        ),
        member_paths=("pay/api.py",),
        cohesion=measured,
        coupling=measured,
        disposition=disp,
    )
    applied = ApplyResult(locked=(locked,), stamped=StampedProposal(dispositions=(disp,)))
    bc_of = {"C-01": "BC-001"}
    cap_map = build_map(applied, bc_of, total_references=7)
    assert cap_map.total_references == 7
