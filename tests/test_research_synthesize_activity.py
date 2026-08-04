"""synthesize_brief: deterministic merge + a model call confined to summary,
contradictions, and confidence.

The model MUST NOT author grounded findings. It would be caught by
verify_brief, but only by turning a normal run into a fail-closed stage
failure -- so the activity refuses the material rather than relying on the
verifier to catch it."""
import pytest
from pydantic_ai.models.test import TestModel

from sdlc.models import (ConsultedSource, GroundedFinding, ResearchBrief,
                         SubQuestion, SubQuestionFinding)
from sdlc.research.stage import (SynthesizeInput, _numbered_sources,
                                 synthesize_brief)


def _finding(sq_id: str, brief: ResearchBrief) -> SubQuestionFinding:
    return SubQuestionFinding(
        sub_question=SubQuestion(id=sq_id, question=f"q {sq_id}"), brief=brief)


def _two_findings() -> list[SubQuestionFinding]:
    a = ResearchBrief(
        sources_consulted=[ConsultedSource(url="https://a.example", title="A")],
        grounded_findings=[GroundedFinding(
            source_url="https://a.example", quote="qa", claim="claim A")])
    b = ResearchBrief(
        sources_consulted=[ConsultedSource(url="https://b.example", title="B")],
        grounded_findings=[GroundedFinding(
            source_url="https://b.example", quote="qb", claim="claim B")])
    return [_finding("sq-0", a), _finding("sq-1", b)]


def _inp() -> SynthesizeInput:
    return SynthesizeInput(idea_json='{"title": "x"}',
                           findings=_two_findings(), model="test-model")


def test_numbered_sources_are_one_based_and_stable():
    brief = ResearchBrief(sources_consulted=[
        ConsultedSource(url="https://a.example", title="A"),
        ConsultedSource(url="https://b.example", title="B")])
    text = _numbered_sources(brief)
    assert "[1]" in text and "https://a.example" in text
    assert "[2]" in text and "https://b.example" in text


@pytest.mark.asyncio
async def test_findings_and_sources_come_from_the_merge_not_the_model():
    out = await synthesize_brief(_inp(), _model=TestModel(custom_output_args={
        "summary": "combined", "confidence": 0.7, "contradictions": []}))
    assert {f.claim for f in out.grounded_findings} == {"claim A", "claim B"}
    assert len(out.sources_consulted) == 2


@pytest.mark.asyncio
async def test_the_model_writes_summary_and_confidence():
    out = await synthesize_brief(_inp(), _model=TestModel(custom_output_args={
        "summary": "combined answer", "confidence": 0.7,
        "contradictions": []}))
    assert out.summary == "combined answer"
    assert out.confidence == 0.7


@pytest.mark.asyncio
async def test_the_model_can_add_cross_sub_question_contradictions():
    out = await synthesize_brief(_inp(), _model=TestModel(custom_output_args={
        "summary": "s", "confidence": 0.5,
        "contradictions": [{"topic": "date", "positions": ["2026", "2027"],
                            "assessment": "A is better sourced",
                            "unresolved": True}]}))
    assert len(out.contradictions) == 1
    assert out.contradictions[0].topic == "date"


@pytest.mark.asyncio
async def test_synthesis_of_no_findings_is_an_empty_brief_without_a_model_call():
    out = await synthesize_brief(
        SynthesizeInput(idea_json="{}", findings=[], model="test-model"),
        _model=TestModel(custom_output_args={
            "summary": "should not be used", "confidence": 1.0,
            "contradictions": []}))
    assert out.summary == ""
    assert out.grounded_findings == []


@pytest.mark.asyncio
async def test_field_order_is_preserved():
    # tests/test_research_models.py pins SGR reasoning order; a merge that
    # rebuilt the model with reordered fields would be a regression.
    out = await synthesize_brief(_inp(), _model=TestModel(custom_output_args={
        "summary": "s", "confidence": 0.5, "contradictions": []}))
    assert list(out.model_dump().keys()) == list(
        ResearchBrief().model_dump().keys())


def test_synthesis_confidence_is_bound_to_the_unit_interval():
    # The brief is assembled via model_copy(update=...), which bypasses
    # validation, so ResearchBrief.confidence's ge/le is inert on the synthesis
    # path. The bound must live on _SynthesisOutput -- the boundary where
    # pydantic-ai validates the model's structured output. An out-of-range
    # value is rejected here, not silently landed in the brief.
    from pydantic import ValidationError

    from sdlc.research.stage import _SynthesisOutput

    with pytest.raises(ValidationError):
        _SynthesisOutput(confidence=42.0)
    assert _SynthesisOutput(confidence=0.7).confidence == 0.7
