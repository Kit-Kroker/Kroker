"""VCS-side artifact models (FR-702, ADR-3).

Framework-free by design: only pydantic and `core` imports, so the agent
loader can import these at boot without dragging activity definitions
(temporalio) or workflows in with them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.models import ArtifactRef

__all__ = [
    "CodeArtifact",
    "as_code_artifact",
]


class CodeArtifact(BaseModel):
    """ADR-3: one materialized code change, claim-checked (FR-702)."""

    files: list[str] = Field(default_factory=list)
    renames: list[list[str]] = Field(default_factory=list)
    stat: str = ""
    patch_ref: ArtifactRef | None = None


def as_code_artifact(value: CodeArtifact | dict[str, Any]) -> CodeArtifact:
    """The ONE decode shim for FR-702 diff results (final review, Minor 2).

    A workflow-side call site receives whatever the history's payload
    converter decoded: a live run answers a ``CodeArtifact``; a replayed
    pre-claim-check history (or a fake pinned to the old shape) answers a
    plain dict. The dict validates in place — metadata kept, the legacy
    inline ``patch`` key dropped by extra-ignore, ``patch_ref=None`` — so
    no read-back is ever scheduled for it and the legacy patch text is
    never trusted back on the wire. A ``CodeArtifact`` passes through
    unchanged; anything else is a wire-shape error and raises.
    """
    if isinstance(value, CodeArtifact):
        return value
    if isinstance(value, dict):
        return CodeArtifact.model_validate(value)
    raise TypeError(f"expected CodeArtifact or dict, got {type(value).__name__}")
