"""Context stage step execution (spec A §3.3).

Stage 2 context (E-84) maps a brownfield codebase at a pinned commit SHA:
runs the thirteen static scan signals over the tree (shared with assessment),
projects the signals into a CodebaseMap, and validates that collection measured.
Pure deterministic scan fan-out with no LLM proposer role.
"""

from __future__ import annotations

from ...context.models import CodebaseMap
from ...context.project import project
from ...core.context import StageContext
from ...core.models import IdeaBrief, PipelineConfig, ProjectMode
from ...measurement import CollectionState
from ...workflows.scanning import scan_tree


async def build_map(repo_path: str, commit_sha: str) -> CodebaseMap:
    """Stage 2 (E-84). The same thirteen signals the audit tier runs, over
    the same memo, with no triage (D1/D5).

    Nothing here executes the repository's code: every signal reads blob
    bytes at the pinned commit (NFR-9).
    """
    out = await scan_tree(repo_path, commit_sha, None)
    if out.scan is None:
        return CodebaseMap(
            tree_hash=out.tree_hash or "",
            commit_sha=commit_sha,
            modules_collected=out.result.collected,
            contracts_collected=out.result.collected,
            hot_spots_collected=out.result.collected,
            collected=out.result.collected,
        )
    return project(out.scan, out.tree_hash, commit_sha)


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief,
    repo_path: str,
    commit_sha: str,
) -> CodebaseMap | str | None:
    """Execute the context stage for brownfield features.

    Returns:
    - None if idea.mode is not ProjectMode.BROWNFIELD (greenfield bypasses context).
    - Rejection string 'rejected:context (<reason>)' if collection was not MEASURED.
    - CodebaseMap if collection succeeded.
    """
    if idea.mode is not ProjectMode.BROWNFIELD:
        return None

    ctx.stage("mapping", "context")
    codebase_map = await build_map(repo_path, commit_sha)
    if codebase_map.collected.state is not CollectionState.MEASURED:
        # D6: proceeding would silently drop the delta check exactly
        # when the ground is weakest -- the shape of the
        # malformed-SARIF-reads-as-clean hole (FR-915).
        return f"rejected:context ({codebase_map.collected.reason})"
    return codebase_map


__all__ = ["build_map", "step"]
