"""Model-id helpers for proposer forwarding, validation and the zai route.

This module is the single home of the 004 model-resolution seam and the 005
zai route policy:

- ``single_retry_layer()`` — a model-id resolver capability factory whose
  provider factory sets the SDK client's retry count to 0, so the workflow
  engine's attempt budget is the only retry layer (FR-007..FR-009).
- ``zai_base_url()`` / ``ZAI_CODING_BASE_URL`` — the base-URL policy: a
  ``zai:`` model id is served on z.ai's coding endpoint (the subscription-
  covered one) unless ``ZAI_BASE_URL`` overrides it (005, FR-016, contract
  zai-route-contract.md C1-C2).
- ``resolve_model(model_id)`` / ``route_layer()`` — build a model (or a
  resolver capability) applying the URL policy only; SDK retries stay at
  their default (C4).
- ``validate_proposer_model(role, value)`` — offline ``provider:model``
  validation for proposer overrides (FR-004, FR-005).
- ``forwarded_model(cfg, role)`` — the one decision point for which model a
  role's call is forwarded under (FR-001, FR-002).

Contracts: .specify/specs/004-model-forwarding-single-retry/contracts/
model-resolution-contract.md (extended, not weakened) and
.specify/specs/005-native-zai-provider/contracts/zai-route-contract.md.
The base URL a built model uses is no longer always the SDK default: for
provider name ``zai`` it is the coding endpoint / ``ZAI_BASE_URL`` (005
A5); every other provider is exactly what the framework builds.

Provider SDK imports stay LAZY, inside functions: this module is imported by
workflow code, is passed through the Temporal sandbox wholesale with the rest
of ``sdlc.agents`` (SdlcPydanticAIPlugin), and must not pay provider import
cost — or trip the workflow deadlock detector — at module import time.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:  # annotation-only; runtime imports stay inside functions
    from pydantic_ai.capabilities import ResolveModelId
    from pydantic_ai.models import Model

    from ..core.models import PipelineConfig

ZAI_CODING_BASE_URL = "https://api.z.ai/api/coding/paas/v4"


def zai_base_url() -> str:
    """The base URL a zai provider is pointed at (005, contract C1-C2).

    ``ZAI_BASE_URL`` when set and non-blank, else the coding endpoint —
    the subscription-covered one; the provider's built-in default
    (``/api/paas/v4``) is NOT subscription-covered (GATE 1 Q2 probes).
    Unset, empty and whitespace-only all mean the default. The
    environment is read HERE, at call time — never baked at import — so
    providers built after an env change observe it.
    """
    override = os.environ.get("ZAI_BASE_URL", "").strip()
    return override or ZAI_CODING_BASE_URL


def _provider_for(name: str, *, single_retry: bool = False):
    """The one provider factory behind the seam (005 D1, R1).

    Builds the provider exactly as ``infer_provider`` does, then applies
    the route policy: for provider name ``zai`` the provider client's
    ``base_url`` is set to ``zai_base_url()`` — the SDK client's own
    setter, probe-verified to normalise the trailing slash and to be the
    client the model uses. Every other provider name is returned
    untouched. With ``single_retry`` the 004 retry-zeroing is applied on
    top (integer ``max_retries`` → 0); without it the SDK retry count is
    left at its default. No HTTP client is built; key lookup and the
    missing-key error stay the provider's own (C5-C6).
    """
    from pydantic_ai.providers import infer_provider

    provider = infer_provider(name)
    if name == "zai":
        client = getattr(provider, "client", None)
        if client is not None:
            client.base_url = zai_base_url()
    if single_retry:
        client = getattr(provider, "client", None)
        retries = getattr(client, "max_retries", None)
        if client is not None and isinstance(retries, int):
            client.max_retries = 0
    return provider


def resolve_model(model_id: str) -> Model:
    """Build a model applying the URL policy only (005, contract C4).

    ``infer_model(model_id, provider_factory=...)`` with the shared
    factory in its URL-only mode: a ``zai:`` id resolves to the coding
    endpoint / ``ZAI_BASE_URL``; SDK retries keep their default. For
    sites that hold a string and want a model (plan D2 sites 5-7).
    """
    from pydantic_ai.models import infer_model

    return infer_model(model_id, provider_factory=lambda name: _provider_for(name))


def route_layer() -> ResolveModelId[Any]:
    """A fresh model-id resolver capability applying ``resolve_model``
    (005, contract C4).

    One instance per agent. For sites that pass a model STRING to
    ``Agent(...)`` through a build function and must not construct the
    model eagerly themselves: URL policy only, SDK retries untouched.
    """
    from pydantic_ai.capabilities import ResolveModelId

    def _resolve(ctx: Any, model_id: str):
        return resolve_model(model_id)

    return ResolveModelId(_resolve)


def single_retry_layer() -> ResolveModelId[Any]:
    """A fresh model-id resolver capability that turns SDK retries off (T011).

    One instance per agent (``single_retry_layer()`` per construction site).
    The resolver builds any model-id string through the framework's normal
    chain — ``infer_model(id, provider_factory=...)`` — where the shared
    factory (``_provider_for(name, single_retry=True)``) constructs the
    provider exactly as ``infer_provider`` does, applies the 005 zai
    base-URL policy (for provider ``zai``: coding endpoint /
    ``ZAI_BASE_URL`` — the base URL is no longer always the SDK default,
    005 A5), and then sets the provider client's SDK retry count to 0 when
    the client exposes an integer ``max_retries`` (anthropic/openai style;
    a client with no such knob has opt-in-only retries and is left
    untouched). The workflow engine's attempt budget is then the only
    retry layer (FR-007..FR-009).

    Builds no HTTP client; credentials and timeouts stay the SDK's own
    defaults (FR-009). No import happens until first resolution.
    """
    from pydantic_ai.capabilities import ResolveModelId
    from pydantic_ai.models import infer_model

    def _resolve(ctx: Any, model_id: str):
        return infer_model(
            model_id, provider_factory=lambda name: _provider_for(name, single_retry=True)
        )

    return ResolveModelId(_resolve)


def validate_proposer_model(role: str, value: str) -> None:
    """Offline validation of a proposer override (T020, FR-004/FR-005, Q2).

    Accepts exactly ``provider:model`` with non-empty parts whose provider
    class the installed framework can resolve WITHOUT instantiation — no
    network, no credentials, no provider construction. Raises RegistryError
    naming the role, the offending string and the accepted form. The model
    name is not checked against any list (Q2). Harness roles are never
    passed here (their grammar is their own, FR-005).
    """
    from pydantic_ai.models import parse_model_id
    from pydantic_ai.providers import infer_provider_class

    from .loader import RegistryError  # lazy: loader imports this module

    def _reject(reason: str) -> NoReturn:
        raise RegistryError(
            f"role '{role}': '{value}' is not a valid proposer model id "
            f"({reason}); the accepted form is provider:model, e.g. "
            f"openai:gpt-5.2 (known provider, installed SDK)"
        )

    if value == "test":
        _reject("the literal 'test' resolves to TestModel, never a real provider")
    provider_name, model_name = parse_model_id(value)
    if provider_name is None:
        _reject("no provider part — that is the harness grammar, not provider:model")
    if not provider_name or not model_name:
        _reject("empty provider or model part")
    try:
        infer_provider_class(provider_name)
    except ValueError:
        _reject(f"unknown provider '{provider_name}'")
    except ImportError:
        _reject(f"provider '{provider_name}' is known but its SDK extra is not installed")


def forwarded_model(cfg: PipelineConfig, role: str) -> str | None:
    """The one decision point for which model a role's call is forwarded
    under (T028, FR-001/FR-002, contracts/model-resolution-contract.md).

    `role` is a registry role name (the key space of ``cfg.roles``). Returns
    the override string iff that role is overridden with a model that
    DIFFERS from its registry model; otherwise ``None`` (no override, or an
    override equal to the registry model — E1: both behave as today). Pure
    over its arguments; safe to call inside workflow code.
    """
    from .roles import REGISTRY

    rc = cfg.roles.get(role)
    if rc is None or rc.model is None:
        return None
    registry_model = REGISTRY[role].model if role in REGISTRY else None
    if registry_model is None or rc.model == registry_model:
        return None
    return rc.model
