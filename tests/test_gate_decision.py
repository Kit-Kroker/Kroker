from sdlc.models import GateDecision, GateOutcome, gate_key


def test_approve_outcome_sets_approved_property():
    d = GateDecision(gate="architecture", outcome=GateOutcome.APPROVE, decided_by="human")
    assert d.approved is True
    assert d.round == 1


def test_revise_and_reject_are_not_approved():
    revise = GateDecision(
        gate="architecture",
        outcome=GateOutcome.REVISE,
        decided_by="human",
        guidance="tighten scope",
    )
    reject = GateDecision(gate="architecture", outcome=GateOutcome.REJECT, decided_by="human")
    assert revise.approved is False
    assert reject.approved is False
    assert revise.guidance == "tighten scope"


def test_gate_key_is_round_scoped():
    assert gate_key("architecture", 1) == "architecture#1"
    assert gate_key("architecture", 2) == "architecture#2"
