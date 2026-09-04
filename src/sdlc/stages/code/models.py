"""Artifact models for the code stage (spec A §2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HandoffClaim(BaseModel):
    """One assertion about the work, carrying the evidence for it.
    Evidence-first, mirroring IntegrityFlag."""

    text: str
    evidence: str  # quote/reference from the scrubbed HarnessSession


class HandoffSummary(BaseModel):
    """FR-805: structured task-to-task handoff (intra-run continuity).

    Split by provenance: `files_touched` is computed from the materialized
    diff by the workflow, so no model can misreport it. The claim lists are
    extracted from the scrubbed session -- the diff cannot state WHY an
    approach was chosen or what was knowingly left undone.
    """

    task_id: str
    files_touched: list[str] = Field(default_factory=list)
    what_changed: list[HandoffClaim] = Field(default_factory=list)
    decisions_made: list[HandoffClaim] = Field(default_factory=list)
    open_concerns: list[HandoffClaim] = Field(default_factory=list)


class IntegrityFlag(BaseModel):
    """One anti-cheat observation drawn from the scrubbed transcript (E-39)."""

    kind: Literal["oracle_peeking", "hardcoded_answer", "test_gaming", "excessive_backtracking"]
    detail: str
    evidence: str  # a quote/reference from the scrubbed transcript
