"""Artifact and stage-internal models for the clarify stage (spec A §2).

Artifact models: ClarifiedRequirements, OpenQuestion.
Stage-internal types for the fan-out: ClarifyRoute, ProbeResult.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.models import (
    ArtifactRef,
    ClarificationDimension,
)


class OpenQuestion(BaseModel):
    id: str
    question: str
    why_it_matters: str
    suggested_answer: str | None = None
    answer: str | None = None  # filled by human (or auto)
    # E-85: additive only -- a pre-E-85 artifact must still validate.
    dimension: ClarificationDimension | None = None
    asked_by: str | None = None  # "supervisor" | "probe:C4"
    materiality: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = None  # repo path/symbol grounding it


class ClarifiedRequirements(BaseModel):
    summary: str
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    out_of_scope: list[str]
    open_questions: list[OpenQuestion]
    spec_ref: ArtifactRef | None = None
    # E-85: what actually ran, and what the cap cut. `dropped` is what makes
    # the cap honest -- without it, capping and being incurious are
    # indistinguishable in the record.
    dimensions_probed: list[ClarificationDimension] = Field(default_factory=list)
    dropped: list[OpenQuestion] = Field(default_factory=list)


class ClarifyRoute(BaseModel):
    """clarify_route's output: MAC's is_ambiguous() and select_domain() fused
    into one call. The supervisor authors the requirements body and its own
    C1/C2 questions, and NAMES the dimensions to probe -- it does not author
    the probes' questions (E-85 D2, mirroring agents/discover's "You judge;
    you do not author")."""

    summary: str
    functional_requirements: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    questions: list[OpenQuestion] = Field(default_factory=list)
    live_dimensions: list[ClarificationDimension] = Field(default_factory=list)


class ProbeResult(BaseModel):
    """One probe's answer. An empty `questions` list is valid and expected --
    it means is_ambiguous() returned 0 for this dimension. Abstaining is not
    a failure; a probe that never abstains is inventing work."""

    dimension: ClarificationDimension
    questions: list[OpenQuestion] = Field(default_factory=list)
