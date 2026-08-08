"""FR-913 (E-47a): audited identity corrections.

Modelled field-for-field on gate.py's GateOverride -- approved_by, reason,
and the operation. `approved_by` is retained as a calibration signal, the
same role it plays for a gate override: every correction is labelled ground
truth saying the matcher scored a pair at X and a human disagreed.

Application follows E-78's pattern (FR-1302): mutate the row, append one
event with actor and operation. A purely event-sourced fold would be more
elegant; a second persistence model inside one SQLite file would be worse.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .models import (
    CapabilityFingerprint, CapabilityIdentity, IdentityStatus, SignalTier,
)
from .store import CapabilityIdentityStore


class CorrectionOp(str, Enum):
    MERGE = "merge"          # two ids are one capability
    SPLIT = "split"          # one id should have been two
    REATTACH = "reattach"    # a new id is really an existing capability


class IdentityCorrection(BaseModel):
    operation: CorrectionOp
    approved_by: str
    reason: str
    source_bc_id: str
    target_bc_id: str | None = None
    # SPLIT only: the members moving to the new id. Richer input than the
    # other two operations need, because no scored evidence exists for a
    # partition the matcher did not make.
    partition: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _audited(self) -> "IdentityCorrection":
        if not self.approved_by.strip():
            raise ValueError(
                "approved_by is required -- an unattributed override is not "
                "an audited one")
        if not self.reason.strip():
            raise ValueError("reason is required")
        return self


def apply_correction(store: CapabilityIdentityStore, project: str,
                     correction: IdentityCorrection) -> int:
    """Apply one correction. Returns the resulting registry_version.

    Idempotent by TARGET-STATE check, not by dedupe key: humans retry CLI
    invocations in ways Temporal activities do not, so re-issuing a
    correction that already holds is a no-op returning the current version.
    """
    version = store.registry_version(project)
    rows = {r.bc_id: r for r in store.load(project)}

    source = rows.get(correction.source_bc_id)
    if source is None:
        raise ValueError(
            f"unknown capability '{correction.source_bc_id}' in project "
            f"'{project}'")

    if correction.operation is CorrectionOp.SPLIT:
        changed = _split(source, correction, store.allocator(project))
    else:
        changed = _absorb(source, correction, rows)

    if changed is None:            # already in the target state
        return version

    return store.apply(project, changed, expected_version=version,
                       actor=correction.approved_by,
                       operation=correction.operation.value)


def _absorb(source: CapabilityIdentity, correction: IdentityCorrection,
            rows: dict[str, CapabilityIdentity]
            ) -> list[CapabilityIdentity] | None:
    """MERGE and REATTACH are the same write: the source is absorbed into the
    target, and the target inherits the source's fingerprint.

    Inheriting the fingerprint is what makes the correction stick. Point the
    ids at each other without it and the next assessment scores the
    refactored capability against the target's stale fingerprint, misses
    threshold again, and mints another new id.
    """
    if correction.target_bc_id is None:
        raise ValueError(
            f"operation={correction.operation.value} requires target_bc_id")
    target = rows.get(correction.target_bc_id)
    if target is None:
        raise ValueError(
            f"unknown capability '{correction.target_bc_id}'")

    if target.status is not IdentityStatus.ACTIVE:
        # A non-active target is either MERGED (absorbing into it would build
        # a cycle, and the inheriting row is excluded from matching so the
        # fingerprint inheritance is silently discarded) or RETIRED. Neither
        # is recoverable from the CLI. Name the live head so the operator can
        # re-issue against it.
        head = _live_head(target.bc_id, rows)
        suffix = (f" (live head is '{head}'; re-issue with --into {head})"
                  if head != target.bc_id else "")
        raise ValueError(
            f"cannot {correction.operation.value} into "
            f"'{target.bc_id}': it is {target.status.value}{suffix}")

    if (source.status is IdentityStatus.MERGED
            and source.merged_into == target.bc_id):
        return None

    absorbed = source.model_copy(update={
        "status": IdentityStatus.MERGED,
        "retired_reason": None,
        "merged_into": target.bc_id})
    survivor = target.model_copy(update={"fingerprint": source.fingerprint})
    return [absorbed, survivor]


def _live_head(bc_id: str, rows: dict[str, CapabilityIdentity]) -> str:
    """Follow merged_into to the active row, to name it in an error message.

    A MERGED row's merged_into points at a row that was ACTIVE at merge time
    (the guard above enforces it for every new write), so in a well-formed
    registry the walk terminates in one step. The `seen` set is defensive: a
    registry damaged before that guard existed could carry a cycle, and
    looping inside an error path would be its own bug.
    """
    seen: set[str] = set()
    cur = bc_id
    while cur in rows and cur not in seen:
        seen.add(cur)
        row = rows[cur]
        if row.status is IdentityStatus.MERGED and row.merged_into:
            cur = row.merged_into
        else:
            return cur
    return bc_id


def _split(source: CapabilityIdentity, correction: IdentityCorrection,
           allocate) -> list[CapabilityIdentity]:
    """Move the named members onto a freshly minted id. Members are matched
    across every tier, so a caller need not say which tier each belongs to."""
    if not correction.partition:
        raise ValueError("operation=split requires a non-empty partition")

    moving = set(correction.partition)
    kept: dict[SignalTier, list[str]] = {}
    taken: dict[SignalTier, list[str]] = {}
    for tier in SignalTier:
        members = source.fingerprint.tiers.get(tier, [])
        kept[tier] = [m for m in members if m not in moving]
        taken[tier] = [m for m in members if m in moving]

    if not any(taken.values()):
        raise ValueError(
            f"partition {sorted(moving)} matched no member of "
            f"{source.bc_id}; nothing to split out")

    new_id = allocate()
    minted = CapabilityIdentity(
        bc_id=new_id, project=source.project,
        first_seen_run=source.first_seen_run,
        status=IdentityStatus.ACTIVE, derived_from=source.bc_id,
        fingerprint=CapabilityFingerprint(
            tiers=taken, collected=source.fingerprint.collected))
    remaining = source.model_copy(update={
        "fingerprint": CapabilityFingerprint(
            tiers=kept, collected=source.fingerprint.collected)})
    return [remaining, minted]
