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
