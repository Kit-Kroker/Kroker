"""Artifact models for the constitution stage (FR-112, spec §Design 1)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field


class Principle(BaseModel):
    """One governing principle, frozen into the artifact the crew obeys."""

    id: str  # "CP-1", assigned by code, never by the model
    statement: str  # one normative sentence
    normative: Literal["MUST", "SHOULD"]
    rationale: str  # why it exists, one sentence
    source_ref: str | None = None  # "AGENTS.md#L17" / "pyproject.toml" — brownfield-required


class Constitution(BaseModel):
    """The frozen artifact clarify/architect/plan consume."""

    principles: list[Principle]  # ≥1, unique ids, enforced by verify
    digest: str  # constitution_digest over the principles — memo seam
    drafted_by: Literal["agent", "empty"]  # "empty" = flag-off / nothing survived


class DraftPrinciple(BaseModel):
    """A principle as the agent drafted it — NO id (ids are code-assigned in
    verify; the `_PlannerOutput` precedent: the model proposes, code names)."""

    statement: str
    normative: Literal["MUST", "SHOULD"]
    rationale: str
    source_ref: str | None = None


class DraftOutput(BaseModel):
    """The drafter agent's output_type: raw proposals before validation."""

    principles: list[DraftPrinciple] = Field(default_factory=list)


def constitution_digest(principles: Sequence[Principle | DraftPrinciple]) -> str:
    """Canonical hash over sorted (statement, normative) pairs: prose, ordering,
    and ids drop out; content remains — same principles -> same digest ->
    downstream memo keys hit. `""` for an empty list is the wire-level sentinel
    (research's ungrounded-brief convention): a flag-off or fully-dropped
    constitution must digest identically to no constitution stage at all."""
    if not principles:
        return ""
    pairs = sorted((p.statement, p.normative) for p in principles)
    payload = json.dumps(pairs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
