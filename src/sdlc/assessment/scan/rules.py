"""D10: rules_sha -- the memo term that makes a stale cache impossible.

A hand-maintained `version: int` invalidates only when someone remembers to
bump it, and two of E-46's signals share a rule module while three consume
another signal's output. Hashing the real bytes is PROMPT_SHAS' existing
answer to exactly this, and it removes the forgot-to-bump hazard for all
thirteen signals rather than only the ones that share a module.

Pure of temporalio; reads module source from disk, so it is called from
ACTIVITY code, never from a workflow.
"""

from __future__ import annotations

import hashlib
import importlib.util

from .models import ScanSignalId
from .registry import SCAN_SIGNALS


def module_sha(dotted: str) -> str:
    """sha256 of a module's source bytes, by dotted path.

    Uses find_spec rather than importing: hashing must not execute the
    module, and a signal module's import side effects are none of this
    function's business.
    """
    spec = importlib.util.find_spec(dotted)
    if spec is None or not spec.origin:
        raise RuntimeError(
            f"cannot locate module {dotted!r} to hash -- the registry names "
            f"it, so a missing module is registry drift, not a cache miss"
        )
    with open(spec.origin, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def rules_sha(signal_id: ScanSignalId) -> str:
    """Hash of everything whose bytes change this signal's output: its own
    module, its declared rule_modules, and -- transitively -- the modules of
    every signal it consumes.

    Sorted before hashing, so traversal order cannot change the key.
    """
    seen: set[ScanSignalId] = set()
    modules: set[str] = set()

    def walk(sid: ScanSignalId) -> None:
        if sid in seen:
            return
        seen.add(sid)
        spec = SCAN_SIGNALS[sid]
        modules.add(spec.module)
        modules.update(spec.rule_modules)
        for upstream in spec.consumes:
            walk(upstream)

    walk(signal_id)
    payload = "|".join(f"{m}:{module_sha(m)}" for m in sorted(modules))
    return hashlib.sha256(payload.encode()).hexdigest()
