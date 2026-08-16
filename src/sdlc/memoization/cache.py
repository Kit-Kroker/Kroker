"""Content-addressed activity cache — the ADR-5 memoization module.
Local filesystem, hash-named files (no new infra): same content in, same
content out, regardless of which run asked."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def _cache_root() -> Path:
    default = os.path.join(tempfile.gettempdir(), "sdlc", "memo_cache")
    return Path(os.environ.get("SDLC_MEMOIZATION_CACHE_ROOT", default))


def content_key(stage: str, input_json: str, prompt_sha: str, model_id: str,
                upstream_recall_ref: str) -> str:
    """Pure function of its arguments — safe to call from workflow code."""
    payload = "|".join([stage, input_json, prompt_sha, model_id,
                        upstream_recall_ref])
    return hashlib.sha256(payload.encode()).hexdigest()


def signal_key(signal_id: str, version: int, rules_sha: str,
               tree_hash: str) -> str:
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
    return path.read_text(encoding="utf-8")


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


def discover_key(project: str, tree_hash: str, context_digest: str,
                 identity_registry_version: int, prompt_sha: str,
                 model_id: str) -> str:
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
    payload = "|".join(["discover", project, tree_hash, context_digest,
                        str(identity_registry_version), prompt_sha, model_id])
    return hashlib.sha256(payload.encode()).hexdigest()


def risk_key(project: str, tree_hash: str, map_digest: str, rules_sha: str,
             prompt_sha: str, model_id: str) -> str:
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
    payload = "|".join(["risk", project, tree_hash, map_digest, rules_sha,
                        prompt_sha, model_id])
    return hashlib.sha256(payload.encode()).hexdigest()

