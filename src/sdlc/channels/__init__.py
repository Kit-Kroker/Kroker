"""Channel contract (E-6) — the adapter layer between the workflow's
structured pending decisions and any surface (CLI, notify, dashboard, MCP).

Not imported by the workflow: keeping delivery/render code out of the
sandbox preserves ADR-13 purity. Surfaces import from here; the workflow
imports only sdlc.pending.
"""
from __future__ import annotations

from .contract import (
    Channel, PushChannel, ReferenceChannel, RenderedDecision, Reply,
    SignalCall, default_render, default_translate,
)

__all__ = [
    "Channel", "PushChannel", "ReferenceChannel", "RenderedDecision",
    "Reply", "SignalCall", "default_render", "default_translate",
]
