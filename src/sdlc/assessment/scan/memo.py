"""The scan signal memo (FR-103, FR-912, E-46 D10).

Filesystem I/O, so this is ACTIVITY-side code: a workflow must never call it.
Kept out of models.py and registry.py so those stay pure.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from ...measurement import CollectionState
from ...memoization import cache
from .models import ScanSignalId, ScanUpstream, SignalOutput
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


def store(signal_id: ScanSignalId, tree_hash: str, out: SignalOutput,
          upstream: ScanUpstream | None = None) -> bool:
    """Cache `out` and report whether it was stored.

    Three rules, all of them the same rule: never serve a failure forever.

    1. ONLY a MEASURED result is stored. Memoizing a timed-out or
       uninterpretable signal returns that failure as a cache hit forever.
    2. A signal that CONSUMES another must pass that signal's `upstream`, and
       is not stored when any consumed signal did not collect (P3-D5). SS1 can
       report MEASURED -- a TLS count -- while input_validation is
       not_collected because S3 degraded; caching that serves a permanently
       missing category against a healthy S3 on an unchanged tree.
    3. Forgetting the argument raises rather than silently reinstating the
       hazard. In production the activity's own try/except turns that into a
       degraded signal; in CI it is a failing test.
    """
    consumes = SCAN_SIGNALS[signal_id].consumes
    if consumes and upstream is None:
        raise ValueError(
            f"{signal_id.value} consumes {[c.value for c in consumes]} but "
            f"store() was called without its upstream -- a consuming signal's "
            f"output is only cacheable when its inputs collected (P3-D5)")
    if out.row.collected.state is not CollectionState.MEASURED:
        return False
    if upstream is not None and not all(
            upstream.measured(c) for c in consumes):
        return False
    cache.put(_key(signal_id, tree_hash), out.model_dump_json())
    return True
