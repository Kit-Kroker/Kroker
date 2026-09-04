"""Artifact models for the research stage (spec A §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.models import ArtifactRef, RoleUsage


class SubQuestion(BaseModel):
    id: str
    question: str


class ConsultedSource(BaseModel):
    """Judgment before label: assess the source, THEN attach a relevance tag."""

    url: str
    title: str = ""
    assessment: str = ""  # what this source is / is worth
    relevance: str = ""  # e.g. "high" / "peripheral"


class GroundedFinding(BaseModel):
    """quote BEFORE claim (spec §4): commit to a verbatim span actually in the
    fetched bytes, then state what it supports. The verifier (research/verify.py)
    asserts `quote` is a substring of the page fetched THIS run for `source_url`."""

    source_url: str
    quote: str  # verbatim span from bytes fetched this run
    claim: str
    sub_question_ids: list[str] = Field(default_factory=list)


class InferredFinding(BaseModel):
    """reasoning BEFORE claim. `fetched_at` is set only when the lead came from
    the corpus (a recalled lead honestly belongs here, never in grounded)."""

    reasoning: str
    claim: str
    based_on: list[str] = Field(default_factory=list)  # source urls / lead ids
    fetched_at: str | None = None


class Contradiction(BaseModel):
    topic: str
    positions: list[str] = Field(default_factory=list)
    assessment: str = ""
    unresolved: bool = True


class Gap(BaseModel):
    sub_question_id: str
    what_is_missing: str
    why_it_matters: str = ""


class ResearchBrief(BaseModel):
    """FR-107 grounded research brief. Field order is reasoning order (SGR):
    decompose -> gather -> what the bytes say -> what I concluded -> where
    sources disagree -> what I could not answer -> summary -> ref -> confidence.
    tests/test_research_models.py pins the order; a reorder is a regression."""

    sub_questions: list[SubQuestion] = Field(default_factory=list)
    sources_consulted: list[ConsultedSource] = Field(default_factory=list)
    grounded_findings: list[GroundedFinding] = Field(default_factory=list)
    inferred_findings: list[InferredFinding] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    summary: str = ""
    brief_ref: ArtifactRef | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ResearchPlan(BaseModel):
    """The planner's output, WITH its model spend.

    Carrying `usage` is why this type exists rather than a bare
    list[SubQuestion]: fan-out moves the model call activity-side, out of
    _run_role's reach, so an activity that calls a model must hand its usage
    back or the spend is silently lost (E-33 amendment, fan-out design §7)."""

    sub_questions: list[SubQuestion] = Field(default_factory=list)
    usage: RoleUsage = Field(default_factory=lambda: RoleUsage(role="research", model="unknown"))


class SubQuestionFinding(BaseModel):
    """One sub-question's result: its own partial ResearchBrief plus spend.

    `failed=True` means the sub-question exhausted its retries or hit a
    non-retryable error. Its siblings survive -- a partial answer from three
    of four sub-questions is worth far more than nothing -- and the merge
    turns this into a Gap so a short brief is explained rather than just
    short."""

    sub_question: SubQuestion
    brief: ResearchBrief = Field(default_factory=ResearchBrief)
    usage: RoleUsage = Field(default_factory=lambda: RoleUsage(role="research", model="unknown"))
    failed: bool = False
    error: str = ""
