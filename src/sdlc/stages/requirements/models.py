"""Artifact models for the requirements stage (FR-113, spec §Design 1)."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field


class FunctionalRequirement(BaseModel):
    """One testable behavior a story promises."""

    id: str  # "FR-1", assigned by code, never by the model; global across the artifact
    text: str  # one normative sentence


class SuccessCriterion(BaseModel):
    """One observable check that tells the story shipped."""

    id: str  # "SC-1", assigned by code, never by the model; global across the artifact
    text: str  # one measurable sentence


class Story(BaseModel):
    """One user-facing slice: narrative, its requirements, its criteria."""

    id: str  # "US-1", assigned by code, never by the model
    narrative: str  # "As a …, I want …, so that …"
    functional: list[FunctionalRequirement]  # ≥1, enforced by verify
    success_criteria: list[SuccessCriterion]  # ≥0; the SC pin (≥1 overall) is artifact-level
    source_ref: str | None = None  # one repo-relative path — brownfield-required


class Requirements(BaseModel):
    """The frozen artifact clarify/architect/plan consume."""

    stories: list[Story]
    digest: str  # requirements_digest over the stories — memo seam; "" when empty
    drafted_by: Literal["agent", "empty"]  # "empty" = flag-off / nothing survived


class DraftStory(BaseModel):
    """A story as the agent drafted it — NO id (ids are code-assigned in
    verify; the `_PlannerOutput` precedent: the model proposes, code names)."""

    narrative: str
    functional: list[str]
    success_criteria: list[str]
    source_ref: str | None = None


class DraftOutput(BaseModel):
    """The drafter agent's output_type: raw proposals before validation."""

    stories: list[DraftStory] = Field(default_factory=list)


def requirements_digest(stories: list[Story]) -> str:
    """Canonical hash over sorted (narrative, sorted functional texts, sorted
    success-criterion texts) tuples: story order, text order, and ids drop
    out; content remains — same stories -> same digest -> downstream memo
    keys hit, reordered drops don't churn keys. `""` for an empty list is
    the wire-level sentinel (constitution's flag-off convention): a flag-off
    or fully-dropped requirements artifact must digest identically to no
    requirements stage at all."""
    if not stories:
        return ""
    tuples = sorted(
        (
            s.narrative,
            sorted(fr.text for fr in s.functional),
            sorted(sc.text for sc in s.success_criteria),
        )
        for s in stories
    )
    payload = json.dumps(tuples, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
