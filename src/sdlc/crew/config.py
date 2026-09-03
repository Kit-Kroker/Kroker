"""Declarative shape of a crew (E-88 §5).

Two artifacts, not one: a role answers "what is this agent", and is reused
across layouts; a layout answers "which roles are assembled and by what
rules". Merging them would duplicate every non-lead role per layout and
produce two descriptions of one role that drift apart.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core.models import (
    HarnessKind,
)


class CrewRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str  # filled from the filename
    harness: HarnessKind
    model: str  # passed to the CLI verbatim
    # "writes" means REPOSITORY files. Every role writes its own protocol
    # files under the orchestration dir; only the lead may touch the repo,
    # or the diff stops being attributable (spec §1).
    writes: bool = False
    skill: str
    superpowers: list[str] = Field(default_factory=list)


class Rounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max: int = 1
    require_reviewer_approval: bool = False


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_clock_s: int
    # NOT herdr's pane_idle_timeout_s. One TURN's deadline, which becomes the
    # activity's start_to_close_timeout. Safe to set aggressively only because
    # a round's work is checkpoint-committed (spec §4).
    turn_timeout_s: int
    cost_usd: float


class Deliverable(BaseModel):
    """Where the lead writes its output, RELATIVE TO THE ROUND DIRECTORY.

    Round-relative because a round is the unit that gets retried: a
    layout-relative path would have round 2 overwrite round 1's evidence.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: str
    schema_name: str = Field(alias="schema")


class CrewLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: str
    lead: str
    crew: list[str]
    rounds: Rounds = Field(default_factory=Rounds)
    deliverable: Deliverable
    limits: Limits

    @model_validator(mode="after")
    def _lead_is_on_the_crew(self) -> CrewLayout:
        if self.lead not in self.crew:
            raise ValueError(
                f"layout {self.layout!r}: lead {self.lead!r} is not in crew {self.crew}"
            )
        return self

    def roles(self) -> list[str]:
        """Every role this layout instantiates, lead first."""
        return [self.lead] + [r for r in self.crew if r != self.lead]
