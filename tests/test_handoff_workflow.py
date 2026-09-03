"""Handoff content reaches the NEXT task's prompt -- and no validator."""

from sdlc.models import HandoffClaim, HandoffSummary
from sdlc.workflows.task_host import _handoff_notes


def _claim(text):
    return HandoffClaim(text=text, evidence="model_turn")


def test_notes_carry_all_three_claim_lists():
    h = HandoffSummary(
        task_id="t1",
        files_touched=["src/app.py"],
        what_changed=[_claim("added /health")],
        decisions_made=[_claim("chose cookie sessions over JWT")],
        open_concerns=[_claim("empty-list case not handled")],
    )
    notes = "\n".join(_handoff_notes([h]))
    assert "added /health" in notes
    assert "chose cookie sessions over JWT" in notes
    assert "empty-list case not handled" in notes


def test_notes_never_leak_evidence_quotes():
    """Evidence is for the cross-check and the record, not the next prompt."""
    h = HandoffSummary(
        task_id="t1",
        what_changed=[HandoffClaim(text="added /health", evidence="SECRET-TRANSCRIPT-QUOTE")],
    )
    assert "SECRET-TRANSCRIPT-QUOTE" not in "\n".join(_handoff_notes([h]))


def test_empty_handoff_produces_no_notes():
    assert _handoff_notes([HandoffSummary(task_id="t1")]) == []


def test_only_last_five_handoffs_are_carried():
    hs = [HandoffSummary(task_id=f"t{i}", what_changed=[_claim(f"c{i}")]) for i in range(8)]
    notes = "\n".join(_handoff_notes(hs))
    assert "c0" not in notes
    assert "c7" in notes
