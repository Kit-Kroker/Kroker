"""The proposer payload guard (007): one limit, checked per model request.

A proposer model request whose input exceeds the workflow engine's payload
cap leaves the run open forever — the worker retries the failing workflow
task in a hot loop and no stage failure path ever runs (research R1). This
module is the fix: a capability attached to every durable proposer agent
that measures each workflow-scheduled model request BEFORE it is scheduled
and, above the limit, raises the repo's existing non-retryable failure
(``ApplicationError``) in place of scheduling it. Each call site then takes
the failure path it already has.

Design: .specify/specs/007-bounded-proposer-prompts/plan.md D1. The
capability overrides only ``wrap_model_request``: outside a workflow it is
inert (E9 — agents run inside activities behave exactly as today), and the
patch marker is consulted only on the failing branch, so an under-limit run
issues no new command and stays replay-identical (R5, FR-006/FR-007).

This module lives under ``sdlc.agents``, which
``SdlcPydanticAIPlugin`` passes through the Temporal workflow sandbox
wholesale (``agents/runner.py``), so it needs no sandbox marking of its own;
module-level ``pydantic_ai`` and ``temporalio`` imports are the established
pattern here (``roles.py``). No provider SDK is imported, nothing is
logged (call sites already do), and the capability holds no per-run state.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from pydantic_ai.capabilities.abstract import (
    AbstractCapability,
    WrapModelRequestHandler,
    leaf_capabilities,
)
from pydantic_ai.capabilities.wrapper import WrapperCapability
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models import ModelRequestParameters
from temporalio import workflow
from temporalio.exceptions import ApplicationError

if TYPE_CHECKING:  # annotation-only; the runtime import stays above
    from pydantic_ai import RunContext
    from pydantic_ai.messages import ModelMessage, ModelResponse
    from pydantic_ai.models import ModelRequestContext
    from pydantic_ai.settings import ModelSettings

# 1 MiB. Measured against the engine's own caps (research R1): a single
# encoded payload over 2,097,152 bytes hangs the run (workflow task fails
# with PAYLOADS_TOO_LARGE, ~15 retries/s, run stays RUNNING), and all
# commands in one workflow task share a 4,194,304-byte message limit. The
# 1 MiB choice leaves 1 MiB for the parts the measure does not count
# (serialized run context, deps, payload envelope) and keeps three
# parallel requests at the limit inside the aggregate cap (research R4).
# A code constant by GATE 1/2 ruling, one value for every role and model.
PROPOSER_PAYLOAD_LIMIT_BYTES = 1_048_576

# A wire name: it appears in recorded workflow histories as the patch
# marker id. Never rename it once shipped — a renamed id makes a replayed
# over-limit history diverge (R5).
GUARD_PATCH_ID = "007-proposer-payload-guard"

OVERSIZE_ERROR_TYPE = "ProposerPayloadTooLarge"

# Built once: the request-parameters adapter mirrors what the payload
# converter serializes for the activity input (research R3, exact to the
# byte).
_PARAMS_ADAPTER: TypeAdapter[ModelRequestParameters] = TypeAdapter(ModelRequestParameters)


def payload_size(
    messages: list[ModelMessage],
    model_request_parameters: ModelRequestParameters | None,
    model_settings: ModelSettings | None,
) -> int:
    """Serialized bytes of what one model request carries across the
    workflow-to-activity boundary: the message list plus the request
    parameters plus the model settings (spec A8).

    The same pydantic encoders the payload converter uses, so the number is
    the size, not an estimate (R3); equal inputs give equal sizes, which is
    what replay determinism needs (FR-006). Empty settings count as ``{}``.
    Pure: no I/O, no workflow calls.
    """
    size = len(ModelMessagesTypeAdapter.dump_json(messages))
    if model_request_parameters is not None:
        size += len(_PARAMS_ADAPTER.dump_json(model_request_parameters))
    size += len(json.dumps(model_settings or {}).encode("utf-8"))
    return size


class ProposerPayloadGuard(AbstractCapability[Any]):
    """Fail a workflow-scheduled model request over the limit, before it is
    scheduled (FR-001..FR-003).

    Steps, in order (plan D1 — the order of step 3's two conditions is part
    of the wire contract): outside a workflow, pass through untouched (E9);
    measure the request; over the limit AND the patch marker present, raise
    the non-retryable ``ApplicationError`` of type
    ``ProposerPayloadTooLarge``; otherwise pass through. ``patched`` is
    evaluated only after the size test is true, so an under-limit run
    records no marker and schedules exactly the commands it always did
    (R5), and a replayed pre-007 history that recorded an over-limit
    success steps aside and replays as recorded (E4).
    """

    async def wrap_model_request(
        self,
        ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        if not workflow.in_workflow():
            return await handler(request_context)

        size = payload_size(
            request_context.messages,
            request_context.model_request_parameters,
            request_context.model_settings,
        )
        if size > PROPOSER_PAYLOAD_LIMIT_BYTES and workflow.patched(GUARD_PATCH_ID):
            agent = getattr(ctx, "agent", None)
            name = getattr(agent, "name", None) or "unknown"
            raise ApplicationError(
                f"agent '{name}': proposer payload {size} bytes exceeds the "
                f"{PROPOSER_PAYLOAD_LIMIT_BYTES}-byte limit "
                "(007; the request was NOT sent)",
                type=OVERSIZE_ERROR_TYPE,
                non_retryable=True,
            )
        return await handler(request_context)


def payload_guard() -> ProposerPayloadGuard:
    """A fresh guard instance, one per agent (like ``single_retry_layer()``)."""
    return ProposerPayloadGuard()


def has_payload_guard(agent: Any) -> bool:
    """Whether ``agent`` carries a :class:`ProposerPayloadGuard`.

    The same traversal ``TemporalDurability.from_agent`` uses: walk the
    agent's capability leaves and unwrap wrapper capabilities. Objects
    without a ``root_capability`` (test stubs) answer False.
    """
    root = getattr(agent, "root_capability", None)
    if root is None:
        return False
    for capability in leaf_capabilities(root):
        while isinstance(capability, WrapperCapability):
            capability = capability.wrapped
        if isinstance(capability, ProposerPayloadGuard):
            return True
    return False
