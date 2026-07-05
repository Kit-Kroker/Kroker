from sdlc.agents.roles import ARCHITECT_PROMPT, PLAN_PROMPT


def test_architect_prompt_requests_confidence_score():
    assert "confidence" in ARCHITECT_PROMPT.lower()


def test_plan_prompt_requests_confidence_score():
    assert "confidence" in PLAN_PROMPT.lower()
