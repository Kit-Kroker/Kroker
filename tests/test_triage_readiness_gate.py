"""FR-903 (E-42 section 7): the gate that stands between a triaged repo and
Tier 2, and the override that records a decision to proceed anyway."""
from __future__ import annotations

import datetime as dt

from sdlc.measurement import Measurement
from sdlc.models import GateDecision, GateOutcome
from sdlc.triage.models import (
    Readiness, RepoTriage, TriageFinding, FixClass, SignalResult, Verdict,
)
from sdlc.workflows.triage import _readiness_summary, override_from


def _triage(verdict=Verdict.NOT_READY) -> RepoTriage:
    return RepoTriage(
        repo_dir="/r", commit_sha="a" * 40,
        readiness=Readiness(
            buildable=Measurement.measured(0.0),
            runnable=Measurement.measured(0.0),
            tests_present=Measurement.measured(0.0),
            structure_discernible=Measurement.measured(1.0),
            verdict=verdict),
        signals=[SignalResult(
            signal="secrets", version=2,
            collected=Measurement.measured(1.0),
            findings=[TriageFinding(
                signal="secrets", rule="committed_env", severity="critical",
                detail="tracked .env", path=".env",
                fix_class=FixClass.JUDGEMENT)])])


def test_summary_names_the_verdict_and_the_blocking_dimensions():
    s = _readiness_summary(_triage())
    assert "not_ready" in s
    assert "buildable" in s and "runnable" in s and "tests_present" in s
    # A dimension that passed is not listed as blocking.
    assert "structure_discernible" not in s


def test_summary_counts_findings_by_severity():
    assert "critical: 1" in _readiness_summary(_triage())


def test_summary_is_ascii():
    """The Windows console cannot print non-ASCII."""
    _readiness_summary(_triage()).encode("ascii")


def test_override_records_decided_by_verbatim():
    """All three approval classes record an override -- one rule, no special
    cases -- and 'policy'/'timeout' stay legible as non-human."""
    for who in ("human", "policy", "timeout"):
        d = GateDecision(gate="readiness", round=1,
                         outcome=GateOutcome.APPROVE, decided_by=who,
                         comments="ship it",
                         decided_at=dt.datetime(2026, 8, 8,
                                                tzinfo=dt.timezone.utc))
        o = override_from(d)
        assert o.approved_by == who
        assert o.reason == "ship it"
        assert o.gate_round == 1


def test_override_carries_the_reviewer_when_present():
    d = GateDecision(gate="readiness", round=1, outcome=GateOutcome.APPROVE,
                     decided_by="human", reviewer="alice", comments="ok",
                     decided_at=dt.datetime(2026, 8, 8,
                                            tzinfo=dt.timezone.utc))
    assert override_from(d).reviewer == "alice"


def test_override_from_a_rejection_is_none():
    d = GateDecision(gate="readiness", round=1, outcome=GateOutcome.REJECT,
                     decided_by="human")
    assert override_from(d) is None


def test_override_from_a_revise_is_none():
    """REVISE is not an approval -- GateDecision.approved is APPROVE-only."""
    d = GateDecision(gate="readiness", round=1, outcome=GateOutcome.REVISE,
                     decided_by="human")
    assert override_from(d) is None
