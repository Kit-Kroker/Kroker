"""The assess phase memo (FR-103, FR-916, E-49).

Filesystem I/O, so this is ACTIVITY-side code: a workflow must never call it.
Kept out of build.py so that module stays pure -- discover/memo.py's shape
and scan/memo.py's reason.
"""
from __future__ import annotations

import hashlib
import logging

from pydantic import ValidationError

from ..discover.map import CapabilityMap
from ...measurement import CollectionState
from ...memoization import cache
from .models import UnifiedRiskMap

_log = logging.getLogger(__name__)


def map_digest(cmap: CapabilityMap) -> str:
    """A content hash over the serialized CapabilityMap.

    Pydantic emits fields in declaration order, so this does not depend on
    construction order (NFR-10) -- and the map's own producers already assert
    their rows sorted.
    """
    return hashlib.sha256(
        cmap.model_dump_json().encode("utf-8")).hexdigest()


def load(*, project: str, tree_hash: str, map_digest: str,
         rules_sha: str) -> UnifiedRiskMap | None:
    """A cached map, or None on miss or unparseable content.

    Corrupt content is a MISS, never a crash: a truncated cache file must
    cost a recompute, not an assessment (scan/memo.py's rule).
    """
    raw = cache.get(cache.risk_key(project, tree_hash, map_digest, rules_sha))
    if raw is None:
        return None
    try:
        return UnifiedRiskMap.model_validate_json(raw)
    except ValidationError:
        _log.warning("risk memo for %s did not validate; recomputing",
                     project)
        return None


def store(*, project: str, tree_hash: str, map_digest: str, rules_sha: str,
          out: UnifiedRiskMap) -> bool:
    """Cache `out` and report whether it was stored.

    ONLY a MEASURED map is stored -- scan/memo.py's rule 1. A transient
    upstream failure must not freeze a permanently missing score into the
    cache.
    """
    if out.collected.state is not CollectionState.MEASURED:
        return False
    cache.put(cache.risk_key(project, tree_hash, map_digest, rules_sha),
              out.model_dump_json())
    return True
