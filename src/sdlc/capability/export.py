"""FR-913 (E-47a): the client-facing identity export.

NOT a store. A hash cannot drive matching -- Jaccard needs the sets, and a
digest yields equality and nothing else -- so this file has no read path and
the board stays authoritative. It has three jobs:

  1. durable resolution of a delivered BC-NNN without our infrastructure;
  2. tamper-evidence -- the hash lets a client verify across engagements
     that the stored fingerprint is the one present at delivery;
  3. cheap change detection -- a differing hash means the shape moved.

Opt-in and off by default: writing into a client repository is a
trust-boundary decision, the same framing triage/advisories.py uses for an
outbound lookup.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path

from .models import CapabilityFingerprint, CapabilityIdentity, SignalTier

EXPORT_VERSION = 1


def fingerprint_sha256(fp: CapabilityFingerprint) -> str:
    """Stable digest over the canonical tier members and collection state.

    The model validator already sorted and deduped the members, so equal
    observations hash equal regardless of discovery order. The collection
    state is part of the digest: a MEASURED fingerprint and a NOT_COLLECTED
    one with identical tiers are not the same observation -- conflating them
    in the client-facing artifact is exactly the ambiguity measurement.py
    exists to prevent."""
    canonical = json.dumps(
        {
            "tiers": {t.value: fp.tiers.get(t, []) for t in SignalTier},
            "collected": fp.collected.state.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_export(project: str, rows: Sequence[CapabilityIdentity]) -> dict:
    """The payload. Retired and merged rows are included deliberately: a
    delivered document citing them must still resolve."""
    return {
        "version": EXPORT_VERSION,
        "project": project,
        "capabilities": [
            {
                "bc_id": r.bc_id,
                "status": r.status.value,
                "retired_reason": (r.retired_reason.value if r.retired_reason else None),
                "merged_into": r.merged_into,
                "derived_from": r.derived_from,
                "fingerprint_sha256": fingerprint_sha256(r.fingerprint),
            }
            for r in sorted(rows, key=lambda r: r.bc_id)
        ],
    }


def write_export(path: str | os.PathLike, project: str, rows: Sequence[CapabilityIdentity]) -> str:
    """Write the export, creating parents. Deterministic bytes: identical
    input yields an identical file, so a no-change assessment produces no
    diff in the client's repository."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(build_export(project, rows), indent=2, sort_keys=False, ensure_ascii=False)
    target.write_text(body + "\n", encoding="utf-8")
    return str(target)
