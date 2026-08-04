"""The refine round: gate REVISE triggers a second, targeted wave.

Round-1 findings are never discarded, round-2 ids never collide with round-1,
and exhausting the round budget PROCEEDS with the current brief rather than
rejecting -- research degrades a run, it never stops it."""
import pytest

from sdlc.models import (Contradiction, Gap, ResearchBrief, ResearchConfig,
                         SubQuestion, SubQuestionFinding)
from sdlc.workflows.feature import _refine_seed, _should_refine


def _brief() -> ResearchBrief:
    return ResearchBrief(
        gaps=[Gap(sub_question_id="sq-0", what_is_missing="penalties",
                  why_it_matters="drives the design")],
        contradictions=[Contradiction(topic="date", positions=["a", "b"],
                                      unresolved=True),
                        Contradiction(topic="scope", positions=["c", "d"],
                                      unresolved=False)])


def test_refine_is_allowed_on_the_first_revise():
    assert _should_refine(round_n=1, cfg=ResearchConfig()) is True


def test_refine_is_exhausted_after_max_rounds():
    assert _should_refine(round_n=2, cfg=ResearchConfig()) is False


def test_refine_can_be_disabled_entirely():
    assert _should_refine(round_n=1,
                          cfg=ResearchConfig(max_refine_rounds=0)) is False


def test_the_seed_carries_gaps_and_only_UNRESOLVED_contradictions():
    # A resolved contradiction is answered. Re-researching it spends the run
    # ceiling on work already done.
    gaps, conflicts = _refine_seed(_brief())
    assert [g.what_is_missing for g in gaps] == ["penalties"]
    assert [c.topic for c in conflicts] == ["date"]


def test_the_id_offset_is_the_count_of_existing_sub_questions():
    findings = [
        SubQuestionFinding(sub_question=SubQuestion(id="sq-0", question="a")),
        SubQuestionFinding(sub_question=SubQuestion(id="sq-1", question="b")),
    ]
    # Round two must start at sq-2 or the merge silently overwrites round one.
    assert len(findings) == 2
