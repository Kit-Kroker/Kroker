"""Claim-check read paths (E-39 deep_review; 021 recall snapshots;
FR-702 diff read-back).

The ONLY reader of a stored HarnessSession. The store holds nothing but
SCRUBBED bytes (E-38 scrubs before put), so reading it is scrubbed-by-
construction; the kind assertion pins that this is a session, never some
other artifact. Byte-capped so a large transcript cannot blow the
proposer's context — the workflow appends the inline SessionDigest when a
read is truncated so aggregate signals survive.

load_diff (FR-702) is the only reader of a stored patch and the only
place the T3 cut happens: get_task_diff stored git's FULL output, so the
truncation marker is produced here, never at the source. Char-capped
(decode first, then slice) so a cut at a multi-byte codepoint cannot
raise.

read_recall_snapshot (021 FR-402) is the verified read-back of a
content-addressed recall snapshot: wrong kind or hash mismatch raises
ValueError, and unverified content is never returned.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel
from temporalio import activity

from ..core.models import (
    ArtifactRef,
)
from ..memory.models import RecallSnapshot
from ..memory.query_hash import SNAPSHOT_TAG
from .store import ref_to_path

DEEP_REVIEW_MAX_BYTES = 512 * 1024


class LoadSessionInput(BaseModel):
    ref: ArtifactRef


class LoadSessionResult(BaseModel):
    text: str
    truncated: bool


@activity.defn
async def load_session(inp: LoadSessionInput) -> LoadSessionResult:
    assert inp.ref.kind == "harness_session", (
        f"load_session reads only scrubbed harness sessions, got kind={inp.ref.kind!r}"
    )
    data = ref_to_path(inp.ref).read_bytes()
    truncated = len(data) > DEEP_REVIEW_MAX_BYTES
    text = data[:DEEP_REVIEW_MAX_BYTES].decode("utf-8", errors="replace")
    return LoadSessionResult(text=text, truncated=truncated)


DIFF_MAX_CHARS = 60_000


class LoadDiffInput(BaseModel):
    ref: ArtifactRef
    max_chars: int = DIFF_MAX_CHARS


@activity.defn
async def load_diff(inp: LoadDiffInput) -> LoadSessionResult:
    """Bounded read-back of a stored patch (FR-702). The source never cuts
    — get_task_diff claim-checked git's FULL output — so this is the only
    place the T3 marker appears. Character semantics: the full bytes decode
    first (``errors="replace"``), then the text is sliced at max_chars;
    exactly max_chars characters passes through clean (``<=``), one more
    appends ``\\n...[diff truncated, N chars omitted]`` with the exact
    omitted count."""
    assert inp.ref.kind == "diff", f"load_diff reads only diffs, got kind={inp.ref.kind!r}"
    full = ref_to_path(inp.ref).read_bytes().decode("utf-8", errors="replace")
    truncated = len(full) > inp.max_chars
    text = full[: inp.max_chars]
    if truncated:
        text += f"\n...[diff truncated, {len(full) - inp.max_chars} chars omitted]"
    return LoadSessionResult(text=text, truncated=truncated)


def read_recall_snapshot(ref: ArtifactRef) -> RecallSnapshot:
    """Verified read-back of a persisted recall snapshot (021 contract §2).

    A plain function, not an activity: workflow code never calls it (a
    stage's recall answer comes from recorded activity output, FR-009);
    operators and auditors do. Raises ValueError on a foreign kind or a
    content-hash mismatch, and rebuilds the snapshot from the canonical
    array only after the bytes verify."""
    if ref.kind != "recall_snapshot":
        raise ValueError(f"read_recall_snapshot reads only recall snapshots, got kind={ref.kind!r}")
    data = ref_to_path(ref).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != ref.sha256:
        raise ValueError(
            f"recall snapshot hash mismatch: file hashes to {digest}, ref says {ref.sha256}"
        )
    tag, bank, watermark, query_hash, items, degraded = json.loads(data)
    if tag != SNAPSHOT_TAG:
        raise ValueError(f"unknown recall snapshot tag {tag!r}, expected {SNAPSHOT_TAG!r}")
    return RecallSnapshot(
        query_hash=query_hash, bank=bank, watermark=watermark, items=items, degraded=degraded
    )
