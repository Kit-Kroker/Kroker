"""plan_research: decomposition becomes workflow-owned state.

The planner runs against TestModel -- no network, no live model. Width is a
HARD SLICE: measured behaviour is that planners return the top of any range
they are given, so the config value decides the width, not the question."""

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.research.stage import PlanInput, _plan_prompt
from sdlc.research.stage import _plan_research_impl as plan_research
from sdlc.stages.research.models import (
    Contradiction,
    Gap,
    ResearchPlan,
)


def _inp(**kw) -> PlanInput:
    base = dict(idea_json='{"title": "add rate limiting"}', max_sub_questions=4, model="test-model")
    base.update(kw)
    return PlanInput(**base)


def test_plan_prompt_contains_the_idea():
    assert "rate limiting" in _plan_prompt(_inp())


def test_plan_prompt_asks_for_the_configured_width():
    assert "4" in _plan_prompt(_inp(max_sub_questions=4))


def test_plan_prompt_without_a_refine_seed_mentions_no_guidance():
    prompt = _plan_prompt(_inp())
    assert "Focus specifically on" not in prompt


def test_plan_prompt_with_a_refine_seed_carries_guidance_gaps_and_conflicts():
    prompt = _plan_prompt(
        _inp(
            guidance="dig into the enforcement timeline",
            gaps=[
                Gap(
                    sub_question_id="sq-0",
                    what_is_missing="penalty amounts",
                    why_it_matters="drives the design",
                )
            ],
            contradictions=[
                Contradiction(topic="effective date", positions=["2026", "2027"], unresolved=True)
            ],
        )
    )
    assert "Focus specifically on" in prompt
    assert "enforcement timeline" in prompt
    assert "penalty amounts" in prompt
    assert "effective date" in prompt


@pytest.mark.asyncio
async def test_plan_research_returns_sub_questions_with_stable_ids():
    plan = await plan_research(
        _inp(), _model=TestModel(custom_output_args={"sub_questions": ["a?", "b?", "c?"]})
    )
    assert isinstance(plan, ResearchPlan)
    assert [s.id for s in plan.sub_questions] == ["sq-0", "sq-1", "sq-2"]
    assert [s.question for s in plan.sub_questions] == ["a?", "b?", "c?"]


@pytest.mark.asyncio
async def test_plan_research_slices_to_max_sub_questions():
    # The planner over-returns. The SLICE is what bounds the fan-out, not the
    # prompt -- trusting the model here is how a 4-wide stage becomes 9-wide.
    plan = await plan_research(
        _inp(max_sub_questions=2),
        _model=TestModel(custom_output_args={"sub_questions": ["a?", "b?", "c?", "d?", "e?"]}),
    )
    assert len(plan.sub_questions) == 2


@pytest.mark.asyncio
async def test_plan_research_applies_the_id_offset_for_refine_rounds():
    # Round-2 ids must never collide with round-1 ids, or findings from the
    # two rounds overwrite each other in the merge.
    plan = await plan_research(
        _inp(id_offset=4), _model=TestModel(custom_output_args={"sub_questions": ["a?", "b?"]})
    )
    assert [s.id for s in plan.sub_questions] == ["sq-4", "sq-5"]


@pytest.mark.asyncio
async def test_plan_research_drops_blank_sub_questions():
    plan = await plan_research(
        _inp(), _model=TestModel(custom_output_args={"sub_questions": ["a?", "   ", "", "b?"]})
    )
    assert [s.question for s in plan.sub_questions] == ["a?", "b?"]


@pytest.mark.asyncio
async def test_plan_research_falls_back_to_the_whole_idea_when_empty():
    # A planner that returns nothing must degrade to today's behaviour -- one
    # sub-question covering the whole idea -- never to an empty fan-out.
    plan = await plan_research(_inp(), _model=TestModel(custom_output_args={"sub_questions": []}))
    assert len(plan.sub_questions) == 1
    assert plan.sub_questions[0].id == "sq-0"


@pytest.mark.asyncio
async def test_plan_research_carries_usage():
    plan = await plan_research(
        _inp(), _model=TestModel(custom_output_args={"sub_questions": ["a?"]})
    )
    assert plan.usage.role == "research"
    assert plan.usage.calls == 1
