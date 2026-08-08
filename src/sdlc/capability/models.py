"""FR-913 (E-47a): capability identity contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as triage/models.py
and measurement.py must not: a dependency here would appear as a reviewable
import.

OQ-6 is resolved by the shape of CapabilityIdentity: `bc_id` is a surrogate
key carried alongside the fingerprint that produced it, not a value derived
from the fingerprint. Nothing here computes an id from content.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ..measurement import Measurement


class SignalTier(str, Enum):
    """Ordered by cost-to-change. A signal a refactor can alter carelessly is
    weak evidence of identity, which is the entire weighting rationale."""
    CONTRACT = "contract"          # routes, CLI commands, tables, topics
    BEHAVIORAL = "behavioral"      # test names, owned entity names
    STRUCTURAL = "structural"      # exported symbol names
    LOCATIONAL = "locational"      # file paths, directory membership


# Provisional. Calibration targets (benchmarks/calibration.py), never
# inlined at a call site -- every consumer takes them as a parameter.
DEFAULT_TIER_WEIGHTS: dict[SignalTier, float] = {
    SignalTier.CONTRACT: 0.50,
    SignalTier.BEHAVIORAL: 0.25,
    SignalTier.STRUCTURAL: 0.15,
    SignalTier.LOCATIONAL: 0.10,
}

T_MATCH = 0.55      # at/above: attach the existing id
EPSILON = 0.05      # winner-runner_up below this: ambiguous_match advisory


class CapabilityFingerprint(BaseModel):
    """What one assessment observed for one capability.

    `collected` is a Measurement, not a bool: a fingerprint that could not be
    computed reports not_collected and is never scored, which is
    distinguishable from one that computed and found few members (FR-915).
    """
    tiers: dict[SignalTier, list[str]] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _canonicalize(self) -> "CapabilityFingerprint":
        # Sorted and deduped so equal observations hash and compare equal
        # regardless of discovery order (NFR-10 determinism).
        self.tiers = {t: sorted(set(self.tiers.get(t, []))) for t in SignalTier}
        return self


class IdentityStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    MERGED = "merged"


class RetiredReason(str, Enum):
    NOT_OBSERVED = "not_observed"   # no eligible pair this assessment
    ABSORBED = "absorbed"           # lost a merge to another id


class CapabilityIdentity(BaseModel):
    """The registry row. Long-lived; one per capability per project, forever.

    The fingerprint is stored, not just the id: matching assessment N needs
    what assessment N-1 observed. Retired rows keep theirs or they can never
    be revived.
    """
    bc_id: str
    project: str
    first_seen_run: str
    status: IdentityStatus = IdentityStatus.ACTIVE
    retired_reason: RetiredReason | None = None
    merged_into: str | None = None
    derived_from: str | None = None      # set when minted by a split
    fingerprint: CapabilityFingerprint

    @model_validator(mode="after")
    def _status_fields_agree(self) -> "CapabilityIdentity":
        if self.status is IdentityStatus.RETIRED:
            if self.retired_reason is None:
                raise ValueError(
                    "status=retired requires retired_reason -- a retirement "
                    "without a reason cannot be distinguished from a bug")
        elif self.retired_reason is not None:
            raise ValueError(
                f"retired_reason is set on status={self.status.value}")
        if self.status is IdentityStatus.MERGED:
            if self.merged_into is None:
                raise ValueError("status=merged requires merged_into")
        if self.merged_into == self.bc_id:
            raise ValueError(f"{self.bc_id} cannot be merged into itself")
        if self.derived_from == self.bc_id:
            raise ValueError(f"{self.bc_id} cannot be derived from itself")
        return self


class AttachMethod(str, Enum):
    FIRST_DISCOVERY = "first_discovery"
    MATCHED = "matched"
    FORCED_BY_CORRECTION = "forced_by_correction"


class AdvisoryKind(str, Enum):
    POSSIBLE_RENAME = "possible_rename"
    AMBIGUOUS_MATCH = "ambiguous_match"
    SPLIT = "split"
    IDENTITY_NOT_ASSESSED = "identity_not_assessed"


class Advisory(BaseModel):
    kind: AdvisoryKind
    detail: str
    local_key: str = ""
    related_bc_id: str | None = None
    score: float | None = None


class ProposedCapability(BaseModel):
    """One capability boundary proposed by discover (E-48), before it has an
    id. `local_key` is the caller's handle for this assessment only."""
    local_key: str
    fingerprint: CapabilityFingerprint


class IdentityAttachment(BaseModel):
    """The per-assessment join, carrying the evidence for why this id was
    used. `contributions` is the per-tier score breakdown -- it falls out of
    scoring rather than being assembled separately."""
    local_key: str
    bc_id: str
    method: AttachMethod
    match_score: float | None = None
    contributions: dict[SignalTier, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _score_matches_method(self) -> "IdentityAttachment":
        if self.method is AttachMethod.MATCHED:
            if self.match_score is None:
                raise ValueError("method=matched requires a match_score")
        elif self.match_score is not None:
            raise ValueError(
                f"match_score is set on method={self.method.value}; only a "
                f"matched attachment was scored")
        return self


class ResolutionResult(BaseModel):
    attachments: list[IdentityAttachment] = Field(default_factory=list)
    retired: list[str] = Field(default_factory=list)
    merged: dict[str, str] = Field(default_factory=dict)   # loser -> winner
    advisories: list[Advisory] = Field(default_factory=list)
