"""C8: lens-absence tombstones -- the pure layer.

A lens that did not run must be constructible only as an absence, never as
an approval. These tests pin the classifier's truth table (spec 3.2), the
model invariant (spec 3.1), and the two admission predicates as exact
transcriptions of shipped behaviour (spec 3.4).
"""

import pytest
from pydantic import ValidationError

from sdlc.stages.review.lenses import (
    GATING_LENSES,
    LensOutcome,
    LensPresence,
    backstop_admits,
    classify_lens,
    primary_admits,
)
from sdlc.stages.review.models import ReviewFinding, ReviewReport


def _approving() -> ReviewReport:
    return ReviewReport(approve=True)


def _rejecting_blocking() -> ReviewReport:
    """`blocking_findings` is a DERIVED property on ReviewReport -- it filters
    `findings` to severity critical/high. It cannot be passed to the
    constructor; drive it through severity."""
    return ReviewReport(
        approve=False,
        findings=[ReviewFinding(assertion="a1", severity="high", detail="broken")],
    )


def _rejecting_non_blocking() -> ReviewReport:
    return ReviewReport(
        approve=False,
        findings=[ReviewFinding(assertion="a1", severity="low", detail="nit")],
    )


def test_gating_lenses_holds_exactly_the_two_gating_lenses():
    """deep_review is FILTERED -- it gates nothing, so its absence cannot be
    read as approval and it is deliberately not graded."""
    assert GATING_LENSES == frozenset({"reviewer", "adversary"})


@pytest.mark.parametrize(
    "enabled,agent_present,reached,report,expected",
    [
        # flag off wins over everything -- the operator's declaration is the
        # truthful cause; path geometry and wiring are moot.
        (False, True, True, None, LensPresence.DECLARED_ABSENT),
        (False, False, False, None, LensPresence.DECLARED_ABSENT),
        # a missing agent on an enabled lens is a real misconfiguration, and
        # it is observable whether or not the run site was reached.
        (True, False, True, None, LensPresence.UNDECLARED_ABSENT),
        (True, False, False, None, LensPresence.UNDECLARED_ABSENT),
        # enabled, wired, never reached -- routine pipeline geometry (A1).
        (True, True, False, None, LensPresence.NOT_REACHED),
        # enabled, wired, reached, nothing came back -- the wiring broke.
        (True, True, True, None, LensPresence.UNDECLARED_ABSENT),
    ],
)
def test_classify_lens_truth_table(enabled, agent_present, reached, report, expected):
    outcome = classify_lens(
        "adversary",
        enabled=enabled,
        agent_present=agent_present,
        reached=reached,
        report=report,
    )
    assert outcome.presence is expected
    assert outcome.approved is None
    assert outcome.reason, "every absent state must carry a reason"


def test_classify_lens_present_carries_the_report_facts():
    outcome = classify_lens(
        "reviewer", enabled=True, agent_present=True, reached=True, report=_rejecting_blocking()
    )
    assert outcome.presence is LensPresence.PRESENT
    assert outcome.approved is False
    assert outcome.has_blocking_findings is True


def test_classify_lens_rejects_an_unreached_report():
    """reached=False with a report is incoherent -- refuse it rather than
    silently normalizing it into PRESENT."""
    with pytest.raises(ValueError):
        classify_lens(
            "adversary", enabled=True, agent_present=True, reached=False, report=_approving()
        )


@pytest.mark.parametrize(
    "presence",
    [
        LensPresence.DECLARED_ABSENT,
        LensPresence.NOT_REACHED,
        LensPresence.UNDECLARED_ABSENT,
    ],
)
def test_absent_outcome_cannot_claim_approval(presence):
    """The whole point of the row: absence is unconstructible as approval."""
    with pytest.raises(ValidationError):
        LensOutcome(lens="adversary", presence=presence, approved=True, reason="whatever")


@pytest.mark.parametrize(
    "presence",
    [
        LensPresence.DECLARED_ABSENT,
        LensPresence.NOT_REACHED,
        LensPresence.UNDECLARED_ABSENT,
    ],
)
def test_absent_outcome_requires_a_reason(presence):
    with pytest.raises(ValidationError):
        LensOutcome(lens="adversary", presence=presence)


def test_present_outcome_requires_an_approved_verdict():
    with pytest.raises(ValidationError):
        LensOutcome(lens="reviewer", presence=LensPresence.PRESENT)


@pytest.mark.parametrize(
    "report,admits",
    [
        (_approving(), True),
        (_rejecting_blocking(), False),
        # The F2 cell: a PRESENT primary rejecting with NO blocking findings
        # still fails, exactly as code/step.py:798 does today. Do not
        # harmonize this with backstop_admits.
        (_rejecting_non_blocking(), False),
    ],
)
def test_primary_admits_present_cells(report, admits):
    outcome = classify_lens(
        "reviewer", enabled=True, agent_present=True, reached=True, report=report
    )
    assert primary_admits(outcome) is admits


@pytest.mark.parametrize(
    "presence",
    [
        LensPresence.DECLARED_ABSENT,
        LensPresence.NOT_REACHED,
        LensPresence.UNDECLARED_ABSENT,
    ],
)
def test_both_predicates_admit_every_absent_state(presence):
    """Ruling OQ1: the task layer is non-blocking in every presence state.
    The tombstone changes what absence SAYS, never what the task layer DOES."""
    outcome = LensOutcome(lens="adversary", presence=presence, reason="because")
    assert primary_admits(outcome) is True
    assert backstop_admits(outcome) is True


@pytest.mark.parametrize(
    "report,admits",
    [
        (_approving(), True),
        (_rejecting_blocking(), False),
        # transcribes code/step.py:813's `or not adversary.blocking_findings`
        (_rejecting_non_blocking(), True),
    ],
)
def test_backstop_admits_present_cells(report, admits):
    outcome = classify_lens(
        "adversary", enabled=True, agent_present=True, reached=True, report=report
    )
    assert backstop_admits(outcome) is admits
