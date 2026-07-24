"""Claim-check read path for the deep_review lens (E-39).

The ONLY reader of a stored HarnessSession. The store holds nothing but
SCRUBBED bytes (E-38 scrubs before put), so reading it is scrubbed-by-
construction; the kind assertion pins that this is a session, never some
other artifact. Byte-capped so a large transcript cannot blow the
proposer's context — the workflow appends the inline SessionDigest when a
read is truncated so aggregate signals survive.
"""
from __future__ import annotations

from pydantic import BaseModel
from temporalio import activity

from ..models import ArtifactRef
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
        f"load_session reads only scrubbed harness sessions, got "
        f"kind={inp.ref.kind!r}")
    data = ref_to_path(inp.ref).read_bytes()
    truncated = len(data) > DEEP_REVIEW_MAX_BYTES
    text = data[:DEEP_REVIEW_MAX_BYTES].decode("utf-8", errors="replace")
    return LoadSessionResult(text=text, truncated=truncated)
