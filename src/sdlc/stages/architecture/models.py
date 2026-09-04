"""Artifact models for the architecture stage (spec A §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ...core.models import ArtifactRef
from ..context.models import BrownfieldDelta


class ArchitectureDecision(BaseModel):
    id: str
    decision: str
    rationale: str
    alternatives_considered: list[str] = Field(default_factory=list)


class ArchitectureSpec(BaseModel):
    overview: str
    decisions: list[ArchitectureDecision]
    affected_modules: list[str] = Field(default_factory=list)  # brownfield
    new_components: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    spec_ref: ArtifactRef | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301
    delta: BrownfieldDelta | None = None  # E-84, brownfield

    @model_validator(mode="after")
    def _affected_modules_follow_the_delta(self) -> ArchitectureSpec:
        """E-84 D7: one authority for what changed.

        `affected_modules` predates the typed delta and is documented as the
        delta in docs/schemas/agents-schema.html. When a delta is present it is the
        authority and this field is derived from it; when it is absent
        (greenfield, and the seeded specs tidyup/backlog.py:103 and the
        benchmark fixtures write) the field is left exactly as given.
        """
        if self.delta is not None:
            derived = sorted(set(self.delta.modified) | set(self.delta.removed))
            if list(self.affected_modules) != derived:
                self.affected_modules = derived
        return self


class ValidationContract(BaseModel):
    """FR-803: machine-checkable 'done', frozen at planning, before code.

    QA and reviewers validate against this — never against the
    implementation or the worker's narrative.
    """

    task_id: str
    assertions: list[str]  # human-readable, test-mappable
    test_commands: list[str] = Field(default_factory=list)
    lint_commands: list[str] = Field(default_factory=list)
    stack: str = ""  # e.g. "TypeScript/Node.js, npm
    # workspaces" — copied verbatim
    # from the architecture decision;
    # a hard constraint, not a soft
    # acceptance criterion
    frozen: bool = True  # set at plan gate; immutable after
