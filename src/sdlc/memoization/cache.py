"""Content-addressed activity cache — the ADR-5 memoization module.
Local filesystem, hash-named files (no new infra): same content in, same
content out, regardless of which run asked — within one checkout. The
default root is namespaced per checkout (bug memo-cache-root): keys are
pure content with no checkout term, so a shared root would let a run
consume an entry some OTHER checkout's run wrote, making outcomes depend
on machine history instead of this checkout's own prior runs."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def _checkout_root() -> Path:
    """The directory this process is running a checkout of: the nearest
    ancestor of the CWD holding `.git` (a directory for a plain clone, a
    file for a linked worktree — both count, and the WORKING-TREE path is
    the identity, never the shared gitdir, or worktrees would collide with
    the primary checkout they link to). Outside any repo, the resolved CWD
    itself: hermetic, and never the bare process CWD."""
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _cache_root() -> Path:
    # Blank is unset, not a root: os.environ.get treats "" as a set value,
    # and Path("") is ".", which would scatter <key>.json files into
    # whatever directory is current.
    override = os.environ.get("SDLC_MEMOIZATION_CACHE_ROOT")
    if override:
        return Path(override)
    identity = hashlib.sha256(str(_checkout_root()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "sdlc" / "memo_cache" / identity


def content_key(
    stage: str, input_json: str, prompt_sha: str, model_id: str, upstream_recall_ref: str
) -> str:
    """Pure function of its arguments — safe to call from workflow code."""
    payload = "|".join([stage, input_json, prompt_sha, model_id, upstream_recall_ref])
    return hashlib.sha256(payload.encode()).hexdigest()


def signal_key(signal_id: str, version: int, rules_sha: str, tree_hash: str) -> str:
    """Memo key for one deterministic scan signal (E-46 D10).

    A sibling of content_key rather than a call into it: content_key requires
    prompt_sha and model_id, and passing "" for them would make "no model was
    involved" indistinguishable from a bug that dropped the model id -- in the
    one place where a silently wrong value serves stale results indefinitely.

    tree_hash, not commit_sha: two commits can share a tree (amend, rebase,
    cherry-pick) and a commit-keyed cache would miss on all of them.
    """
    payload = "|".join(["scan", signal_id, str(version), rules_sha, tree_hash])
    return hashlib.sha256(payload.encode()).hexdigest()


def get(key: str) -> str | None:
    path = _cache_root() / f"{key}.json"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # %TEMP% is shared machine space that anything may corrupt: a
        # crashed writer, an unrelated tool, a directory squatting on the
        # entry path. An entry that cannot be read is a miss — a memo may
        # cost a recompute, it may never cost the run (scan/memo.py's
        # rule, applied at the one layer that can keep every memo honest).
        return None


def put(key: str, payload_json: str) -> None:
    root = _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{key}.json").write_text(payload_json, encoding="utf-8")


# E-48 P2-D6. With no proposer there is no prompt and no model, and "" is
# exactly what signal_key's docstring refuses: it would make "no model was
# involved" indistinguishable from a bug that dropped the model id, in the one
# place where a silently wrong value serves stale results indefinitely. A
# baseline-only map and a proposer map therefore never share a key.
NO_PROPOSER = "no-proposer"


def discover_key(
    project: str,
    tree_hash: str,
    context_digest: str,
    identity_registry_version: int,
    prompt_sha: str,
    model_id: str,
) -> str:
    """Memo key for the whole discover phase (E-48 DD10).

    A sibling of content_key and signal_key rather than a call into either,
    for signal_key's reason: content_key has no slot for a registry version,
    and reusing upstream_recall_ref for one would put a load-bearing term in a
    field named for something else.

    `identity_registry_version` is FR-103's amendment from E-47a and is what
    makes skipping the lock on a hit safe -- if the registry moved, the key
    moved, so a hit implies the stored map's ids are still the registry's. It
    is deliberately coarse: any identity write invalidates the whole map for
    that project, and the map is a single artifact with no per-capability
    memoization to preserve.
    """
    payload = "|".join(
        [
            "discover",
            project,
            tree_hash,
            context_digest,
            str(identity_registry_version),
            prompt_sha,
            model_id,
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def risk_key(
    project: str, tree_hash: str, map_digest: str, rules_sha: str, prompt_sha: str, model_id: str
) -> str:
    """Memo key for the whole assess phase (E-49).

    A sibling of discover_key for signal_key's reason. `map_digest` rather
    than a restatement of the CapabilityMap's own key terms: the map already
    folds identity_registry_version (E-47a's FR-103 amendment), so digesting
    it inherits that term instead of maintaining a second copy of the list.

    `prompt_sha` and `model_id` carry the explicit NO_PROPOSER sentinel when
    no proposer ran, never "" -- which signal_key's docstring refuses, because
    it makes "no model was involved" indistinguishable from a bug that dropped
    the model id, in the one place where a silently wrong value serves stale
    results indefinitely.
    """
    payload = "|".join(["risk", project, tree_hash, map_digest, rules_sha, prompt_sha, model_id])
    return hashlib.sha256(payload.encode()).hexdigest()
