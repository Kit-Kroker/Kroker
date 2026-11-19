"""VCS-side artifact models (FR-702, ADR-3).

Framework-free by design: only pydantic and `core` imports, so the agent
loader can import these at boot without dragging activity definitions
(temporalio) or workflows in with them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.models import ArtifactRef

__all__ = [
    "CodeArtifact",
]


class CodeArtifact(BaseModel):
    """ADR-3: one materialized code change, claim-checked (FR-702)."""

    files: list[str] = Field(default_factory=list)
    renames: list[list[str]] = Field(default_factory=list)
    stat: str = ""
    patch_ref: ArtifactRef | None = None
