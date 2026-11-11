"""Memory models and contracts (spec A §2.2).

Owned by the horizontal memory package.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from ..core.models import ArtifactRef
from .query_hash import recall_snapshot_hash


class MemoryKind(StrEnum):
    STAGE_SUMMARY = "stage_summary"
    GOTCHA = "gotcha"
    GATE_FEEDBACK = "gate_feedback"
    RESEARCH_FINDING = "research_finding"  # verified grounded findings only
    RUN_SUMMARY = "run_summary"  # retro-stage per-run summary (E-32)


class RecallSnapshot(BaseModel):
    """A stage-level recall answer, content-addressed (021 FR-402).

    `query_hash` is the identity of the *question* (memory.query_hash);
    `snapshot_hash` is the sha256 of the canonical *answer* bytes — bank,
    watermark, query_hash, ordered items, degraded flag — derived by the
    validator whenever it is empty and `query_hash or degraded`, so every
    backend path, test stub and replayed pre-021 history yields the same
    hash from one definition. `ref` points at the persisted artifact when
    the recall activity stored one; `persist_failed=True` marks a snapshot
    degraded to empty items by a persistence failure (FR-008: memory I/O
    never blocks the pipeline). The disabled shape (`query_hash=""`,
    not degraded) keeps `snapshot_hash=""` — memory-off runs stay
    byte-identical to pre-021 (FR-007)."""

    query_hash: str
    bank: str
    watermark: str
    items: list[str] = Field(default_factory=list)
    degraded: bool = False
    snapshot_hash: str = ""
    ref: ArtifactRef | None = None
    persist_failed: bool = False

    @model_validator(mode="after")
    def _fill_snapshot_hash(self) -> RecallSnapshot:
        if not self.snapshot_hash and (self.query_hash or self.degraded):
            self.snapshot_hash = recall_snapshot_hash(
                self.bank, self.watermark, self.query_hash, self.items, self.degraded
            )
        return self


class RetainItem(BaseModel):
    kind: MemoryKind
    bank: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)
