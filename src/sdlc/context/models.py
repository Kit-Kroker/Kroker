"""E-84 contracts. Pure -- Pydantic, measurement, and assessment models only.

BrownfieldDelta is deliberately NOT here: it is a field of ArchitectureSpec, so
it lives in root models.py. Siting it here would invert the dependency
direction (D2) and open the cycle models.py -> context -> assessment -> triage
-> models.py.
"""
from __future__ import annotations

from pydantic import BaseModel

from ..models import ProjectMode


class RepoObservation(BaseModel):
    """What stage 0's activity saw. Facts only -- the verdict is classify's.

    `source_file_count` counts SOURCE_EXTENSIONS blobs, the same definition
    E-47b's coverage denominator uses: intake decides a repository is mappable
    and the scan decides what it can map, so two definitions of "has code"
    would let a repository pass intake and then produce an empty map.
    """
    is_git_repo: bool
    base_branch_resolves: bool
    commit_sha: str = ""
    source_file_count: int = 0
    reason: str = ""


class IntakeVerdict(BaseModel):
    """Stage 0's output. `mode` is what was DECLARED -- intake verifies a
    declaration, it never reclassifies behind the operator's back."""
    mode: ProjectMode
    ok: bool
    warning: str = ""
    reason: str = ""
