"""Minimal env-gated Logfire slice (E-38 spec §6).

Gate: LOGFIRE_TOKEN present -> configure + instrument; absent -> every call
is a no-op (nullcontext), and logfire is never imported. Span attributes
must be metadata only — counts, durations, sizes, ids. NEVER transcript
payloads: the scrub-before-store invariant applies to telemetry too.
"""

from __future__ import annotations

import os
from contextlib import nullcontext


def _is_enabled() -> bool:
    """Read the gate at call time, never at import.

    This module is imported inside the workflow sandbox, where imports are
    recorded replay commands. A module-level env read makes the import
    itself carry a result that can differ between the original execution
    and a replay after the worker restarted with a different environment
    (token added/removed between boots) — exactly the non-determinism that
    poisoned R1 mid-run (TMPRL1100, retro phase-3 incident Ф3-1). Call-time
    reads keep the import side-effect-free; where the value matters the
    caller is worker/activity context, not workflow code.
    """
    return bool(os.environ.get("LOGFIRE_TOKEN"))


def configure() -> bool:
    """Called once at worker boot. Returns True iff Logfire is live."""
    if not _is_enabled():
        return False
    try:
        import logfire  # lazy: optional dependency, only needed when gated on
    except ImportError:
        return False
    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
    return True


def span(name: str, **attrs):
    """Context manager: logfire.span when enabled, else nullcontext."""
    if not _is_enabled():
        return nullcontext()
    try:
        import logfire
    except ImportError:
        return nullcontext()
    return logfire.span(name, **attrs)
