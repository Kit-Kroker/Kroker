# src/sdlc/assessment/discover/memo.py
"""The discover phase memo (FR-103, FR-913, E-48 DD10).

Filesystem I/O, so this is ACTIVITY-side code: a workflow must never call it.
Kept out of map.py and apply.py so those stay pure -- scan/memo.py's shape and
scan/memo.py's reason.

The memo is over the WHOLE phase: a hit returns the stored CapabilityMap and
steps 3-8 are skipped entirely, including the lock. That is safe precisely
because identity_registry_version is a key term.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from ...measurement import CollectionState
from ...memoization import cache
from .map import CapabilityMap

_log = logging.getLogger(__name__)


def load(*, project: str, tree_hash: str, context_digest: str,
         registry_version: int, prompt_sha: str,
         model: str) -> CapabilityMap | None:
    """A cached map, or None on miss or unparseable content.

    Corrupt content is a MISS, never a crash: a truncated cache file must cost
    a recompute, not an assessment (scan/memo.py's rule).
    """
    raw = cache.get(cache.discover_key(project, tree_hash, context_digest,
                                       registry_version, prompt_sha, model))
    if raw is None:
        return None
    try:
        return CapabilityMap.model_validate_json(raw)
    except ValidationError:
        _log.warning("discover memo for %s did not validate; recomputing",
                     project)
        return None


def store(*, project: str, tree_hash: str, context_digest: str,
          registry_version: int, prompt_sha: str, model: str,
          out: CapabilityMap) -> bool:
    """Cache `out` and report whether it was stored.

    Three guards, all of them the same rule (scan/memo.py's rules 1 and 2):
    never serve a failure forever.

    1. ONLY a MEASURED map is stored.
    2. A map with any degraded sub-report (attribution, decomposition,
       ownership) is NOT stored -- a transient finalize blip or git timeout
       must not freeze a permanently missing report into the cache.
    """
    if out.collected.state is not CollectionState.MEASURED:
        return False
    if out.attribution is not None and (
            out.attribution.coverage.state is not CollectionState.MEASURED):
        return False
    if out.decomposition is not None and (
            out.decomposition.collected.state is not CollectionState.MEASURED):
        return False
    if out.ownership is not None and (
            out.ownership.collected.state is not CollectionState.MEASURED):
        return False
    cache.put(cache.discover_key(project, tree_hash, context_digest,
                                 registry_version, prompt_sha, model),
              out.model_dump_json())
    return True
