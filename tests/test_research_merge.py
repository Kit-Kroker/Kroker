"""Deterministic merge of partial briefs. Pure -- no model, no I/O.

The dedupe rule is load-bearing in BOTH directions: corroboration (same claim,
different sources) is the most valuable thing fan-out produces and must
survive; exact duplicate triples must NOT, because brief_digest hashes
(source_url, claim) pairs as a LIST, so a duplicate changes the digest and
silently degrades clarify's memo hit rate."""

from sdlc.research.merge import merge_briefs
from sdlc.research.verify import brief_digest
from sdlc.stages.research.models import (
    ConsultedSource,
    Contradiction,
    GroundedFinding,
    InferredFinding,
    ResearchBrief,
    SubQuestion,
    SubQuestionFinding,
)


def _finding(sq_id: str, brief: ResearchBrief, **kw) -> SubQuestionFinding:
    return SubQuestionFinding(
        sub_question=SubQuestion(id=sq_id, question=f"q for {sq_id}"), brief=brief, **kw
    )


def test_merge_of_nothing_is_an_empty_brief():
    assert merge_briefs([]) == ResearchBrief()


def test_sub_questions_are_unioned_in_order():
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief()),
            _finding("sq-1", ResearchBrief()),
        ]
    )
    assert [s.id for s in merged.sub_questions] == ["sq-0", "sq-1"]


def test_corroboration_is_preserved_same_claim_different_sources():
    a = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://a.example", quote="q1", claim="X is true")
        ]
    )
    b = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://b.example", quote="q2", claim="X is true")
        ]
    )
    merged = merge_briefs([_finding("sq-0", a), _finding("sq-1", b)])
    assert len(merged.grounded_findings) == 2, "corroboration was collapsed"


def test_exact_duplicate_triples_are_deduped():
    g = GroundedFinding(source_url="https://a.example", quote="q", claim="X")
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(grounded_findings=[g])),
            _finding("sq-1", ResearchBrief(grounded_findings=[g.model_copy()])),
        ]
    )
    assert len(merged.grounded_findings) == 1


def test_digest_is_stable_when_two_sub_questions_report_the_same_triple():
    g = GroundedFinding(source_url="https://a.example", quote="q", claim="X")
    one = merge_briefs([_finding("sq-0", ResearchBrief(grounded_findings=[g]))])
    two = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(grounded_findings=[g])),
            _finding("sq-1", ResearchBrief(grounded_findings=[g.model_copy()])),
        ]
    )
    assert brief_digest(one) == brief_digest(two)


def test_sources_are_deduped_by_url_first_seen_wins():
    a = ResearchBrief(
        sources_consulted=[ConsultedSource(url="https://a.example", title="A", relevance="high")]
    )
    b = ResearchBrief(
        sources_consulted=[
            ConsultedSource(url="https://a.example", title="A again", relevance="peripheral")
        ]
    )
    merged = merge_briefs([_finding("sq-0", a), _finding("sq-1", b)])
    assert len(merged.sources_consulted) == 1
    assert merged.sources_consulted[0].relevance == "high"


def test_inferred_findings_and_gaps_concatenate():
    a = ResearchBrief(inferred_findings=[InferredFinding(reasoning="r1", claim="c1")])
    b = ResearchBrief(inferred_findings=[InferredFinding(reasoning="r2", claim="c2")])
    merged = merge_briefs([_finding("sq-0", a), _finding("sq-1", b)])
    assert len(merged.inferred_findings) == 2


def test_within_sub_question_contradictions_carry_through():
    a = ResearchBrief(
        contradictions=[Contradiction(topic="t", positions=["p1", "p2"], unresolved=True)]
    )
    merged = merge_briefs([_finding("sq-0", a)])
    assert len(merged.contradictions) == 1
    assert merged.contradictions[0].topic == "t"


def test_a_failed_sub_question_becomes_a_gap():
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(), failed=True, error="RefusalError: declined"),
        ]
    )
    assert len(merged.gaps) == 1
    assert merged.gaps[0].sub_question_id == "sq-0"
    assert "declined" in merged.gaps[0].why_it_matters


def test_a_failed_sub_question_does_not_stop_its_siblings():
    ok = ResearchBrief(
        grounded_findings=[GroundedFinding(source_url="https://a.example", quote="q", claim="X")]
    )
    merged = merge_briefs(
        [
            _finding("sq-0", ResearchBrief(), failed=True, error="boom"),
            _finding("sq-1", ok),
        ]
    )
    assert len(merged.grounded_findings) == 1
    assert len(merged.gaps) == 1


def test_merge_leaves_summary_and_confidence_for_synthesis():
    a = ResearchBrief(summary="partial summary", confidence=0.9)
    merged = merge_briefs([_finding("sq-0", a)])
    assert merged.summary == ""
    assert merged.confidence == 0.0
