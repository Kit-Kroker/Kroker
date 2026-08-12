"""The scan signal memo (FR-103, FR-912, E-46 D10).

Filesystem I/O, so this is ACTIVITY-side code: a workflow must never call it.
Kept out of models.py and registry.py so those stay pure.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from ...measurement import CollectionState
from ...memoization import cache
from .models import ScanSignalId, SignalOutput
from .registry import SCAN_SIGNALS
from .rules import rules_sha

_log = logging.getLogger(__name__)


def _key(signal_id: ScanSignalId, tree_hash: str) -> str:
    return cache.signal_key(signal_id.value,
                            SCAN_SIGNALS[signal_id].version,
                            rules_sha(signal_id), tree_hash)


def load(signal_id: ScanSignalId, tree_hash: str) -> SignalOutput | None:
    """A cached output, or None on miss or unparseable content.

    Corrupt content is a MISS, never a crash: a truncated cache file must
    cost a recompute, not an assessment.
    """
    raw = cache.get(_key(signal_id, tree_hash))
    if raw is None:
        return None
    try:
        return SignalOutput.model_validate_json(raw)
    except ValidationError:
        _log.warning("scan memo for %s did not validate; recomputing",
                     signal_id.value)
        return None


def store(signal_id: ScanSignalId, tree_hash: str,
          out: SignalOutput) -> bool:
    """Cache `out` and report whether it was stored.

    ONLY a MEASURED result is stored. Memoizing a timed-out or uninterpretable
    signal would return that failure as a cache hit forever, which is worse
    than never caching at all.
    """
    if out.row.collected.state is not CollectionState.MEASURED:
        return False
    cache.put(_key(signal_id, tree_hash), out.model_dump_json())
    return True
