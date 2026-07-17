from sdlc.agents.roles import _STAGE_PROMPTS

ARCHITECT_PROMPT = _STAGE_PROMPTS["architect"]
PLAN_PROMPT = _STAGE_PROMPTS["plan"]


def test_architect_prompt_requests_confidence_score():
    assert "confidence" in ARCHITECT_PROMPT.lower()


def test_plan_prompt_requests_confidence_score():
    assert "confidence" in PLAN_PROMPT.lower()
