"""ResearchConfig gains fan-out bounds. The existing per-run caps are
REINTERPRETED as per-sub-question; max_run_cost_usd is the new run ceiling."""
from sdlc.models import ResearchConfig


def test_fan_out_defaults():
    cfg = ResearchConfig()
    assert cfg.max_sub_questions == 4
    assert cfg.max_run_cost_usd == 4.0
    assert cfg.max_refine_rounds == 1


def test_per_sub_question_caps_keep_their_values():
    # The NUMBERS are unchanged; only their meaning moved from per-run to
    # per-sub-question. Guards against a well-meaning "fix" that divides them.
    cfg = ResearchConfig()
    assert cfg.max_searches == 5
    assert cfg.max_fetches == 10
    assert cfg.max_cost_usd == 1.0
    assert cfg.max_requests == 40


def test_run_ceiling_covers_the_default_fan_out_width():
    cfg = ResearchConfig()
    assert cfg.max_run_cost_usd >= cfg.max_sub_questions * cfg.max_cost_usd
