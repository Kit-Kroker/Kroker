"""Model-id helpers for proposer forwarding, validation and the single retry layer.

This module is the single home of the 004 model-resolution seam:

- ``single_retry_layer()`` — a model-id resolver capability factory whose
  provider factory sets the SDK client's retry count to 0, so the workflow
  engine's attempt budget is the only retry layer (FR-007..FR-009).
- ``validate_proposer_model(role, value)`` — offline ``provider:model``
  validation for proposer overrides (FR-004, FR-005).
- ``forwarded_model(cfg, role)`` — the one decision point for which model a
  role's call is forwarded under (FR-001, FR-002).

Contract: .specify/specs/004-model-forwarding-single-retry/contracts/
model-resolution-contract.md.

Provider SDK imports stay LAZY, inside functions: this module is imported by
workflow code, is passed through the Temporal sandbox wholesale with the rest
of ``sdlc.agents`` (SdlcPydanticAIPlugin), and must not pay provider import
cost — or trip the workflow deadlock detector — at module import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # annotation-only; runtime imports stay inside functions
    from pydantic_ai.capabilities import ResolveModelId


def single_retry_layer() -> ResolveModelId[Any]:
    """A fresh model-id resolver capability that turns SDK retries off (T011).

    One instance per agent (``single_retry_layer()`` per construction site).
    The resolver builds any model-id string through the framework's normal
    chain — ``infer_model(id, provider_factory=...)`` — where the factory
    constructs the provider exactly as ``infer_provider`` does and then sets
    the provider client's SDK retry count to 0 when the client exposes an
    integer ``max_retries`` (anthropic/openai style; a client with no such
    knob has opt-in-only retries and is left untouched). The workflow
    engine's attempt budget is then the only retry layer (FR-007..FR-009).

    Builds no HTTP client; base URL, credentials and timeouts stay the
    SDK's own defaults (FR-009). No import happens until first resolution.
    """
    from pydantic_ai.capabilities import ResolveModelId
    from pydantic_ai.models import infer_model
    from pydantic_ai.providers import infer_provider

    def _single_layer_provider(name: str):
        provider = infer_provider(name)
        client = getattr(provider, "client", None)
        retries = getattr(client, "max_retries", None)
        if client is not None and isinstance(retries, int):
            client.max_retries = 0
        return provider

    def _resolve(ctx: Any, model_id: str):
        return infer_model(model_id, provider_factory=_single_layer_provider)

    return ResolveModelId(_resolve)
