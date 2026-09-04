"""The research stage slice (spec A §3.3)."""

from __future__ import annotations

from .activities import ACTIVITIES
from .models import (
    ConsultedSource,
    Contradiction,
    Gap,
    GroundedFinding,
    InferredFinding,
    ResearchBrief,
    ResearchPlan,
    SubQuestion,
    SubQuestionFinding,
)
from .step import ResearchOutcome, step

__all__ = [
    "ACTIVITIES",
    "ConsultedSource",
    "Contradiction",
    "Gap",
    "GroundedFinding",
    "InferredFinding",
    "ResearchBrief",
    "ResearchOutcome",
    "ResearchPlan",
    "SubQuestion",
    "SubQuestionFinding",
    "step",
]
