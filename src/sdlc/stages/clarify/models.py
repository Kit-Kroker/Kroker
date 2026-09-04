"""Stage-internal types for the clarify fan-out.

Neither type is persisted and neither reaches a human: merge folds them into
ClarifiedRequirements, which is the only artifact the stage emits.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.models import (
    ClarificationDimension,
)
from ...models import (
    OpenQuestion,
)


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
