from __future__ import annotations

from sdlc.gate import CheckClass, CheckResult
from sdlc.models import OpenQuestion
from sdlc.pending import (
    GateContext,
    MergeGatePending,
    StageGatePending,
    TaskEscalationPending,
    clarify_pending,
    gate_pending,
)


def _q(qid, ans=None):
    return OpenQuestion(id=qid, question=f"{qid}?", why_it_matters="w", suggested_answer="sugg")


def test_clarify_pending_skips_answered():
    qs = [_q("Q1"), _q("Q2"), _q("Q3")]
    out = clarify_pending(qs, {"Q2"})
    assert [p.key for p in out] == ["Q1", "Q3"]
    assert out[0].question == "Q1?" and out[0].suggested_answer == "sugg"


def test_gate_pending_merge_variant_carries_checks():
    ctx = GateContext(
        checks=[CheckResult(name="coverage", passed=False, classification=CheckClass.ADVISORY)],
        verdict="v",
    )
    p = gate_pending("merge", 1, ctx)
    assert isinstance(p, MergeGatePending)
    assert p.key == "merge#1" and p.checks[0].name == "coverage" and p.verdict == "v"


def test_gate_pending_task_variant_from_prefix():
    p = gate_pending("task:t7", 1, GateContext(analysis="unmet", attempts=3))
    assert isinstance(p, TaskEscalationPending)
    assert p.task_id == "t7" and p.analysis == "unmet" and p.attempts == 3
    assert p.key == "task:t7#1"


def test_gate_pending_defaults_to_stage_variant():
    p = gate_pending("architecture", 2, GateContext(spec_summary="s"))
    assert isinstance(p, StageGatePending)
    assert p.gate == "architecture" and p.round == 2 and p.spec_summary == "s"


def test_gate_pending_tolerates_missing_context():
    p = gate_pending("planning", 1, None)
    assert isinstance(p, StageGatePending) and p.spec_summary == ""
