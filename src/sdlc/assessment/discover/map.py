"""FR-913 (E-48): the discover phase's contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as discover/models.py
and capability/models.py must not.

Separate from discover/models.py deliberately (DD2): that module holds E-47b/c's
SUB-MECHANISM reports (attribution, decomposition, ownership) and is already
387 lines. This one holds the PHASE artifact and the proposer's interface.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ..scan.models import EvidenceRef


class DiscoverAction(str, Enum):
    """Clause D2. One verdict per candidate."""
    CONFIRM = "confirm"
    SPLIT = "split"
    MERGE = "merge"
    DE_SCOPE = "de_scope"
    FLAG = "flag"


class DispositionSource(str, Enum):
    """Who decided, and it is never the model's to claim (DD7).

    DROPPED and BASELINE must not converge: "a model decided this and cited
    something that does not exist" is evidence about the candidate, while "no
    model ran" is not. This is unbuilt_signal vs failed_signal, whose docstring
    states the rule -- "the reason strings must not converge".
    """
    BASELINE = "baseline"      # code's rule; no proposer consulted
    PROPOSER = "proposer"      # the model decided and its refs resolved
    DROPPED = "dropped"        # the model decided; verification refused it


class SplitPartition(BaseModel):
    """One side of a SPLIT. `member_values` must be a subset of the
    candidate's own members -- enforced at apply time (plan 2), where the
    candidate is in scope."""
    model_config = {"frozen": True}
    name: str
    member_values: tuple[str, ...]

    @model_validator(mode="after")
    def _member_values_are_sorted(self) -> "SplitPartition":
        if list(self.member_values) != sorted(set(self.member_values)):
            raise ValueError(
                f"member_values {self.member_values} are not sorted and "
                f"deduped -- discovery order must not reach the artifact")
        return self


class ProposedDisposition(BaseModel):
    """What the MODEL returns.

    Carries no `source` and no `rule`: provenance is code's to stamp (DD1).
    A model able to set `source` could label a hallucinated verdict as a
    code-computed baseline, which is exactly the laundering DD7 forbids.
    """
    candidate_id: str
    action: DiscoverAction
    rationale: str
    merge_into: str | None = None
    partitions: tuple[SplitPartition, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class DiscoverProposal(BaseModel):
    """The proposer's output_type. Dispositions and nothing else (DD1)."""
    dispositions: list[ProposedDisposition] = Field(default_factory=list)


class CandidateDisposition(BaseModel):
    """A disposition after code has stamped its provenance."""
    model_config = {"frozen": True}
    candidate_id: str
    action: DiscoverAction
    source: DispositionSource
    rule: str
    rationale: str = ""
    merge_into: str | None = None
    partitions: tuple[SplitPartition, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _merge_names_a_target(self) -> "CandidateDisposition":
        if (self.action is DiscoverAction.MERGE) != (self.merge_into is not None):
            raise ValueError(
                f"merge_into is set IFF action is merge -- got "
                f"action={self.action.value} merge_into={self.merge_into}")
        return self

    @model_validator(mode="after")
    def _split_partitions_the_candidate(self) -> "CandidateDisposition":
        if self.action is DiscoverAction.SPLIT:
            if len(self.partitions) < 2:
                raise ValueError(
                    f"action=split needs at least two partitions, got "
                    f"{len(self.partitions)} -- a split into one is a confirm")
        elif self.partitions:
            raise ValueError(
                f"action={self.action.value} must not carry partitions")
        return self

    @model_validator(mode="after")
    def _a_proposer_verdict_carries_its_reasoning(self) -> "CandidateDisposition":
        if (self.source is DispositionSource.PROPOSER
                and not self.rationale.strip()):
            raise ValueError(
                "source=proposer requires a rationale -- a baseline's rule IS "
                "its rationale, but an unexplained model verdict is "
                "unreviewable")
        return self
