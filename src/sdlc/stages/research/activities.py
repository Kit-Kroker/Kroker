"""Research stage activities (spec A Â§5)."""

from __future__ import annotations

from typing import Any

from .stage import plan_research, research_subquestion, synthesize_brief
from .verify import verify_brief_activity

ACTIVITIES: list[Any] = [
    plan_research,
    research_subquestion,
    synthesize_brief,
    verify_brief_activity,
]

__all__ = [
    "ACTIVITIES",
    "plan_research",
    "research_subquestion",
    "synthesize_brief",
    "verify_brief_activity",
]
