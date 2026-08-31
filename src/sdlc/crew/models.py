"""Round evidence and crew results (E-88 §1/§2).

Everything a model wrote is untrusted: schemas are exact, sizes are capped,
and a value that fails to parse is an error rather than a best-effort guess.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import ArtifactRef, HarnessKind, HarnessRunResult

NOTE_SCHEMA = "notes-v1"
# A note records decisions the diff cannot state. A model that inflates it is
# drowning the activity's payload, not documenting harder.
MAX_NOTE_BYTES = 64_000


class RoundNote(BaseModel):
    """The lead's round deliverable. The WORK is the diff, in git; this is
    what the diff cannot say."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: Literal["notes-v1"] = Field(alias="schema")
    what_changed: str = Field(max_length=MAX_NOTE_BYTES)
    why: str = Field(max_length=MAX_NOTE_BYTES)
    verification: str = Field(max_length=MAX_NOTE_BYTES)
    left_undone: str = Field(default="", max_length=MAX_NOTE_BYTES)


class RoundAdvisory(BaseModel):
    """The critic's response to the lead's round. Prose, because its consumer
    is the next round's brief and the reader is a model."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: Literal["advisor-v1"] = Field(alias="schema")
    assessment: str = Field(max_length=MAX_NOTE_BYTES)
    risks: str = Field(default="", max_length=MAX_NOTE_BYTES)
    suggestions: str = Field(default="", max_length=MAX_NOTE_BYTES)


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocker", "major", "minor"]
    where: str = Field(max_length=1_000)
    what: str = Field(max_length=MAX_NOTE_BYTES)


class RoundReview(BaseModel):
    """A verdict plus its evidence. `verdict` is a closed set because it
    drives a control decision -- a free string would let a model invent an
    outcome the workflow has no branch for."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: Literal["review-v1"] = Field(alias="schema")
    verdict: Literal["approve", "needs_work"]
    findings: list[ReviewFinding] = Field(default_factory=list,
                                          max_length=100)


class TurnBeat(BaseModel):
    """What a turn's heartbeat carries so a retry can resume rather than
    restart (spec §3). Crosses the Temporal boundary as a plain dict."""
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    round: int = 1
    phase: str = "streaming"
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class TurnRecord(BaseModel):
    """One agent turn, keyed by (role, round, attempt) so abandoned attempts
    stay countable."""
    model_config = ConfigDict(extra="forbid")

    role: str
    round: int
    attempt: int
    harness: HarnessKind
    model: str
    session_id: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_window: int | None = None
    exit_code: int | None = None
    # True when neither the heartbeat nor the error carried a reading. The
    # budget is then knowably short rather than silently understated.
    cost_incomplete: bool = False


class RoundRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int
    turns: list[TurnRecord] = Field(default_factory=list)
    deliverable_path: str | None = None
    verdict: str | None = None
    # What round N+1's brief carries forward. Stored on the record so a
    # replay reconstructs the brief from history rather than from the disk
    # state of a worktree that has moved on.
    critique: str = ""
    note_summary: str = ""

    def cost_usd(self) -> float | None:
        """Every attempt, abandoned ones included. None when any attempt's
        cost is unknown -- a partial sum would read as a complete one."""
        if any(t.cost_incomplete for t in self.turns):
            return None
        vals = [t.cost_usd for t in self.turns]
        if any(v is None for v in vals):
            return None
        return sum(vals)


class CrewRunResult(BaseModel):
    """What CrewTaskWorkflow returns. `run` is the shared contract the
    factory already consumes; the rest is crew-specific and additive."""
    model_config = ConfigDict(extra="forbid")

    run: HarnessRunResult
    sessions: dict[str, str] = Field(default_factory=dict)
    session_refs: list[ArtifactRef] = Field(default_factory=list)
    rounds: list[RoundRecord] = Field(default_factory=list)
