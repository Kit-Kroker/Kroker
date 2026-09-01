"""Minimal env-gated Logfire slice (E-38 spec §6).

Gate: LOGFIRE_TOKEN present -> configure + instrument; absent -> every call
is a no-op (nullcontext), and logfire is never imported. Span attributes
must be metadata only — counts, durations, sizes, ids. NEVER transcript
payloads: the scrub-before-store invariant applies to telemetry too.
"""

from __future__ import annotations

import os
from contextlib import nullcontext

_ENABLED = bool(os.environ.get("LOGFIRE_TOKEN"))


def configure() -> bool:
    """Called once at worker boot. Returns True iff Logfire is live."""
    if not _ENABLED:
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
    if not _ENABLED:
        return nullcontext()
    try:
        import logfire
    except ImportError:
        return nullcontext()
    return logfire.span(name, **attrs)
