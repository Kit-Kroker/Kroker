from __future__ import annotations

from pydantic import TypeAdapter

from sdlc.gate import CheckClass, CheckResult
from sdlc.pending import (
    ClarifyPending,
    GateContext,
    MergeGatePending,
    PendingDecision,
    StageGatePending,
    TaskEscalationPending,
)

_ADAPTER = TypeAdapter(list[PendingDecision])


def test_variants_construct_with_defaults():
    c = ClarifyPending(key="Q1", question="OIDC or SAML?", why_it_matters="auth")
    assert c.kind == "clarify" and c.suggested_answer is None
    m = MergeGatePending(key="merge#1", gate="merge", round=1)
    assert m.kind == "merge_gate" and m.checks == [] and m.verdict is None


def test_discriminated_union_round_trip_preserves_subclass_fields():
    items: list[PendingDecision] = [
        ClarifyPending(key="Q1", question="q", why_it_matters="w", suggested_answer="s"),
        StageGatePending(
            key="architecture#1", gate="architecture", round=1, spec_summary="the spec"
        ),
        TaskEscalationPending(
            key="task:t1#1", gate="task:t1", round=1, task_id="t1", analysis="unmet", attempts=3
        ),
        MergeGatePending(
            key="merge#1",
            gate="merge",
            round=1,
            checks=[
                CheckResult(name="lint_clean", passed=False, classification=CheckClass.ABSOLUTE)
            ],
            verdict="advisory",
        ),
    ]
    wire = _ADAPTER.dump_json(items)
    back = _ADAPTER.validate_json(wire)
    assert back == items
    # subclass-specific field survived the wire, not just the base fields
    assert isinstance(back[3], MergeGatePending)
    assert back[3].checks[0].name == "lint_clean"


def test_gate_context_defaults_are_empty():
    ctx = GateContext()
    assert ctx.checks == [] and ctx.spec_summary is None and ctx.attempts is None
