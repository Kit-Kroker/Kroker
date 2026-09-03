"""E-84 contracts. Pure -- Pydantic, measurement, and assessment models only.

BrownfieldDelta is deliberately NOT here: it is a field of ArchitectureSpec, so
it lives in root models.py. Siting it here would invert the dependency
direction (D2) and open the cycle models.py -> context -> assessment -> triage
-> models.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from ..assessment.scan.models import Confidence, MemberKind
from ..core.models import (
    ProjectMode,
)
from ..measurement import CollectionState, Measurement


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


class MapModule(BaseModel):
    """One S5-merged candidate, as the Architect sees it."""

    model_config = {"frozen": True}
    name: str
    member_paths: tuple[str, ...] = ()
    confidence: Confidence


class MapContract(BaseModel):
    """One externally-reachable member: a route, a command, a topic."""

    model_config = {"frozen": True}
    kind: MemberKind
    value: str
    path: str
    line: int | None = None


class HotSpot(BaseModel):
    """A place the Architect should look before proposing a change.

    `source` is what keeps partial collection inspectable: when QS3 ran and
    QS2 did not, the hot spots that exist say which signal produced them
    rather than presenting as a complete set.
    """

    model_config = {"frozen": True}
    path: str
    source: Literal["testability", "coverage"]
    reason: str
    metric: Measurement


class CodebaseMap(BaseModel):
    """FR-102's stage 2 artifact: modules, contracts and hot spots extracted
    from the tree at a pinned commit.

    Deliberately does NOT carry the tree's path list. The delta resolves
    against git activity-side (D8) because a large repository's full listing
    would bloat every run's history against ADR-10 and push this past the
    Architect's context_budget_tokens (FR-801).
    """

    tree_hash: str
    commit_sha: str
    modules: tuple[MapModule, ...] = ()
    contracts: tuple[MapContract, ...] = ()
    hot_spots: tuple[HotSpot, ...] = ()
    modules_collected: Measurement
    contracts_collected: Measurement
    hot_spots_collected: Measurement
    collected: Measurement

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> CodebaseMap:
        if self.collected.state is not CollectionState.MEASURED:
            if self.modules or self.contracts or self.hot_spots:
                raise ValueError(
                    f"collected={self.collected.state.value} carries no "
                    f"payload, but modules/contracts/hot_spots are present "
                    f"-- a context stage that did not collect has nothing to "
                    f"show (FR-915)"
                )
        return self
