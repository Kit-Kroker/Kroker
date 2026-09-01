"""E-45 D2: FR-903's admission rule, at both strictnesses.

The `policy` rows are the FUTURE-CONSUMER TRAP workflows/tidyup.py:87-97
documents: TidyUpWorkflow's after-triage auto-approves its own OFF readiness
gate, so TidyUpReport.after.override.approved_by == "policy" -- a machine
placeholder. E-42's rule would admit that tree to a Tier 2 audit.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.measurement import Measurement
from sdlc.triage.admission import admits
from sdlc.triage.models import (
    Readiness,
    ReadinessOverride,
    RepoTriage,
    Verdict,
)


def _triage(verdict: Verdict, approved_by: str | None = None) -> RepoTriage:
    ok = Measurement.measured(1.0)
    override = None
    if approved_by is not None:
        override = ReadinessOverride(
            approved_by=approved_by,
            reviewer="alice",
            reason="known",
            decided_at=datetime(2026, 8, 10, tzinfo=UTC),
            gate_round=1,
        )
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        readiness=Readiness(
            buildable=ok, runnable=ok, tests_present=ok, structure_discernible=ok, verdict=verdict
        ),
        override=override,
    )


@pytest.mark.parametrize(
    "verdict,approved_by,tier0,tier2",
    [
        (Verdict.READY, None, True, True),
        (Verdict.READY, "policy", True, True),
        (Verdict.NOT_READY, None, False, False),
        (Verdict.INDETERMINATE, None, False, False),
        (Verdict.NOT_READY, "policy", True, False),
        (Verdict.NOT_READY, "timeout", True, False),
        (Verdict.NOT_READY, "human", True, True),
        (Verdict.INDETERMINATE, "policy", True, False),
        (Verdict.INDETERMINATE, "human", True, True),
    ],
)
def test_admission_table(verdict, approved_by, tier0, tier2):
    t = _triage(verdict, approved_by)
    assert admits(t, require_human=False)[0] is tier0
    assert admits(t, require_human=True)[0] is tier2


def test_a_refusal_carries_its_reason():
    """The reason lands on the Assessment, so a refusal is legible without a
    Temporal replay."""
    ok, why = admits(_triage(Verdict.NOT_READY, "policy"), require_human=True)
    assert ok is False
    assert "policy" in why
    assert "not_ready" in why


def test_a_missing_override_says_so():
    ok, why = admits(_triage(Verdict.INDETERMINATE), require_human=True)
    assert ok is False
    assert "no override" in why


def test_reviewer_is_never_consulted():
    """`reviewer` is self-asserted (the gap FR-1004 closes). Only
    approved_by -- GateDecision.decided_by verbatim -- is trustworthy, so a
    named reviewer on a policy approval must not rescue it."""
    t = _triage(Verdict.NOT_READY, "policy")
    assert t.override.reviewer == "alice"
    assert admits(t, require_human=True)[0] is False


def test_tidyup_delegates_rather_than_restating():
    """backlog.admitted must not hold a second copy of the rule: two
    admission rules agree only by coincidence, which is the failure shape
    2026-07-16-registry-drives-every-role was written about."""
    import inspect

    from sdlc.tidyup import backlog

    assert "admits(" in inspect.getsource(backlog.admitted)
    assert "Verdict.READY" not in inspect.getsource(backlog.admitted)
    assert backlog.admitted(_triage(Verdict.NOT_READY, "policy")) is True
    assert backlog.admitted(_triage(Verdict.NOT_READY)) is False
