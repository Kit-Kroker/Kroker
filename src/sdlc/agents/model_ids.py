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
