"""Producer-side VCS models (FR-702).

Framework-free by design: no temporalio, no activity definitions — so
`workflows/models.py` can import `CodeArtifact` without dragging activity
code into agent-loader boot (spec D1/D5).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.models import ArtifactRef


class CodeArtifact(BaseModel):
    """ADR-3: one materialized code change, claim-checked (FR-702).

    Harness mode fills patch_ref (the FULL untruncated patch stored by
    get_task_diff); files/renames/stat are inline metadata (small).
    Propose mode (direct file writes, greenfield test files) would fill
    files as the artifact itself — typed per ADR-3, no producer yet.
    """

    files: list[str] = Field(default_factory=list)
    renames: list[list[str]] = Field(default_factory=list)
    stat: str = ""
    patch_ref: ArtifactRef | None = None
