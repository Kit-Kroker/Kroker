"""Memory models and contracts (spec A §2.2).

Owned by the horizontal memory package.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import (
    BaseModel,
    Field,
)


class MemoryKind(StrEnum):
    STAGE_SUMMARY = "stage_summary"
    GOTCHA = "gotcha"
    GATE_FEEDBACK = "gate_feedback"
    RESEARCH_FINDING = "research_finding"  # verified grounded findings only
    RUN_SUMMARY = "run_summary"  # retro-stage per-run summary (E-32)


class RecallSnapshot(BaseModel):
    """Persisted, hashed recall result — FR-402: a declared stage input,
    never a live side-channel. `degraded=True` means the backend was
    unreachable; the pipeline proceeds with an empty snapshot rather than
    blocking on memory."""

    query_hash: str
    bank: str
    watermark: str
    items: list[str] = Field(default_factory=list)
    degraded: bool = False


class RetainItem(BaseModel):
    kind: MemoryKind
    bank: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)
