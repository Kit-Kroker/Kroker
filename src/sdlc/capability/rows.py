# src/sdlc/capability/rows.py
"""FR-913 (E-48 P2-D4): a ResolutionResult becomes the rows to persist.

Pure -- fingerprints and attachments in, registry rows out. No I/O and no
temporalio, the tier matcher.py occupies.

Separate from matcher.py deliberately: resolve() answers "which id belongs to
this boundary", and this answers "what does the registry look like
afterwards". They are different questions with different failure modes, and
E-54's incremental re-assessment is the second caller of both. Two copies of
this mapping would agree only by coincidence.

RetiredReason.ABSORBED gains no producer here (P2-D9): resolve() reports
absorption as `merged`, and CapabilityIdentity._status_fields_agree forbids a
retired_reason on a MERGED row. The value stays reserved and unemitted, like
OwnershipVerb.TRACKS -- recorded as a deliberate deferral rather than given a
synthetic trigger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import (
    AdvisoryKind,
    AttachMethod,
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    ResolutionResult,
    RetiredReason,
)


def identity_rows(
    project: str,
    run_id: str,
    result: ResolutionResult,
    fingerprints: Mapping[str, CapabilityFingerprint],
    registry: Sequence[CapabilityIdentity],
) -> list[CapabilityIdentity]:
    """Every row this assessment changes, sorted by bc_id.

    `fingerprints` is local_key -> what THIS assessment observed. A missing
    key is a KeyError rather than a skip: resolve() attaches every proposed
    capability, so a caller that lost one has a bug, and writing the row
    without its fingerprint would leave the next assessment matching against
    nothing.

    A retired or merged id with no stored row is skipped, not fabricated: it
    has no fingerprint and no first_seen_run to carry, and inventing them
    would put a made-up row in the registry clients cite.
    """
    stored = {r.bc_id: r for r in registry}
    split_source = {
        a.local_key: a.related_bc_id
        for a in result.advisories
        if a.kind is AdvisoryKind.SPLIT and a.related_bc_id
    }
    rows: dict[str, CapabilityIdentity] = {}

    for attachment in result.attachments:
        fingerprint = fingerprints[attachment.local_key]
        prior = stored.get(attachment.bc_id)
        if prior is None or attachment.method is AttachMethod.FIRST_DISCOVERY:
            rows[attachment.bc_id] = CapabilityIdentity(
                bc_id=attachment.bc_id,
                project=project,
                first_seen_run=run_id,
                status=IdentityStatus.ACTIVE,
                derived_from=split_source.get(attachment.local_key),
                fingerprint=fingerprint,
            )
            continue
        # A MATCHED row keeps its first_seen_run and its provenance, and
        # refreshes what it looked like: next assessment matches against what
        # THIS one observed, which is what keeps an id attached across a slow
        # drift. A matched RETIRED row is revived -- E-47a's rule that a scan
        # matching a retired id is re-attachment, not reuse.
        rows[attachment.bc_id] = prior.model_copy(
            update={
                "status": IdentityStatus.ACTIVE,
                "retired_reason": None,
                "fingerprint": fingerprint,
            }
        )

    for bc_id in result.retired:
        prior = stored.get(bc_id)
        if prior is None:
            continue
        rows[bc_id] = prior.model_copy(
            update={
                "status": IdentityStatus.RETIRED,
                "retired_reason": RetiredReason.NOT_OBSERVED,
                "merged_into": None,
            }
        )

    for loser, winner in result.merged.items():
        prior = stored.get(loser)
        if prior is None:
            continue
        rows[loser] = prior.model_copy(
            update={"status": IdentityStatus.MERGED, "retired_reason": None, "merged_into": winner}
        )

    return [rows[bc_id] for bc_id in sorted(rows)]
