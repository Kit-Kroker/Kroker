"""Policy unit tests for the 005 zai route (FR-016, contract C1-C4).

The zai route policy lives in ``sdlc.agents.model_ids``: for provider name
``zai`` the provider's client is pointed at ``ZAI_BASE_URL`` when set and
non-blank, otherwise at the coding endpoint (the subscription-covered one),
and the environment is read when the provider is BUILT, never at module
import (C2). ``single_retry_layer()`` keeps its 004 behaviour on top of the
URL policy — SDK retries zeroed, the engine budget the only retry layer
(C3, FR-006). ``resolve_model()``/``route_layer()`` apply the URL policy
only and leave the SDK's retry count alone (C4). The policy unit tests
(T006) construct no HTTP (C5); the T009 wire-evidence section below adds
local stub-server runs against the SAME policy surface.

T009 wire evidence (contract "Observable evidence"): with ``ZAI_BASE_URL``
pointed at the local counting stub, one plain (non-durable) agent call —
both through the ``route_layer()`` resolver capability and through a
pre-built ``resolve_model()`` instance — makes exactly ONE HTTP request,
on a path ending ``/chat/completions`` under the stub base. That is the
proof the ``client.base_url`` assignment reaches the wire: a red here is
SG-5, not a missing implementation. With ``ZAI_BASE_URL`` unset the model
builds against the coding endpoint and no network call is made.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models import infer_model
from pydantic_ai.providers import infer_provider

from sdlc.agents.model_ids import (
    ZAI_CODING_BASE_URL,
    resolve_model,
    route_layer,
    single_retry_layer,
    zai_base_url,
)

from ._http_stub import ProviderStub

_ZAI_ID = "zai:glm-5.3"
_GATEWAY = "https://gateway.example.com/zai"


def _url(base_url: object) -> str:
    """A client base URL as a string, without the trailing slash the
    OpenAI-style client normalises onto every URL (probe: assigning
    ``.../paas/v4`` reads back ``.../paas/v4/``)."""
    return str(base_url).rstrip("/")


def _sdk_default_max_retries() -> int:
    """What the framework's own zai provider builds — the value "left at
    the SDK default" must equal (2 on the installed openai SDK)."""
    return infer_provider("zai").client.max_retries  # type: ignore[no-any-return]


# --- C1: zai_base_url() default, blank and override forms -------------------


def test_coding_endpoint_constant_is_the_subscription_covered_url():
    # The whole point of 005: the DEFAULT endpoint (api/paas/v4) is not
    # subscription-covered; the coding endpoint is what the registry's zai
    # proposers must reach (GATE 1 Q2 probes; spec E2).
    assert ZAI_CODING_BASE_URL == "https://api.z.ai/api/coding/paas/v4"


def test_zai_base_url_defaults_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ZAI_BASE_URL", raising=False)
    assert zai_base_url() == ZAI_CODING_BASE_URL


@pytest.mark.parametrize("blank", ["", "   ", "\t \n"])
def test_zai_base_url_treats_blank_and_whitespace_overrides_as_unset(
    monkeypatch: pytest.MonkeyPatch, blank: str
):
    monkeypatch.setenv("ZAI_BASE_URL", blank)
    assert zai_base_url() == ZAI_CODING_BASE_URL


def test_zai_base_url_honours_a_non_blank_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ZAI_BASE_URL", _GATEWAY)
    assert zai_base_url() == _GATEWAY


# --- C4: resolve_model() routes the URL, never the retry count --------------


def test_resolve_model_routes_zai_to_the_coding_endpoint():
    model = resolve_model(_ZAI_ID)
    assert _url(model.client.base_url) == ZAI_CODING_BASE_URL, (
        f"resolve_model({_ZAI_ID!r}) left the client on "
        f"{_url(model.client.base_url)!r}; the policy must point it at the "
        f"coding endpoint (C1, C4; contract zai-route-contract.md)"
    )


def test_resolve_model_leaves_sdk_retries_at_the_default():
    model = resolve_model(_ZAI_ID)
    assert model.client.max_retries == _sdk_default_max_retries(), (
        f"resolve_model({_ZAI_ID!r}) changed the client's max_retries to "
        f"{model.client.max_retries!r}; C4 leaves the SDK default "
        f"({_sdk_default_max_retries()}) untouched — zeroing retries is "
        f"single_retry_layer()'s job alone (C3)"
    )


# --- C1+C3: single_retry_layer() adds retry-zeroing on top of the URL -------


def test_single_retry_layer_routes_zai_to_the_coding_endpoint():
    capability = single_retry_layer()
    model = capability.resolver(None, _ZAI_ID)  # type: ignore[arg-type]
    # The resolver is ctx-independent (it builds through infer_model with a
    # provider_factory; contract C1/C3), so None stands in for the framework's
    # ModelResolutionContext here.
    assert _url(model.client.base_url) == ZAI_CODING_BASE_URL, (
        f"single_retry_layer() resolved {_ZAI_ID!r} to "
        f"{_url(model.client.base_url)!r}; the single retry layer must apply "
        f"the same URL policy (C1, C3)"
    )


def test_single_retry_layer_zeroes_sdk_retries_for_zai():
    capability = single_retry_layer()
    model = capability.resolver(None, _ZAI_ID)  # type: ignore[arg-type]
    assert model.client.max_retries == 0, (
        f"single_retry_layer() resolved {_ZAI_ID!r} with max_retries="
        f"{model.client.max_retries!r}; the engine's attempt budget must be "
        f"the only retry layer (C3, FR-006, 004 contract unchanged)"
    )


# --- C1: a non-zai provider is untouched by the URL policy ------------------


def test_resolve_model_leaves_non_zai_providers_on_their_own_base_url():
    routed = resolve_model("openai:gpt-5.2")
    reference = infer_model("openai:gpt-5.2")  # the plain framework path
    assert _url(routed.client.base_url) == _url(reference.client.base_url), (
        "the URL policy moved a non-zai provider off its own base URL; C1 "
        "applies to provider name zai only"
    )
    assert _url(routed.client.base_url) != ZAI_CODING_BASE_URL, (
        "an openai model must not point at the zai coding endpoint"
    )


def test_route_layer_applies_the_url_policy_with_sdk_retries_intact():
    capability = route_layer()
    model = capability.resolver(None, _ZAI_ID)  # type: ignore[arg-type]
    assert _url(model.client.base_url) == ZAI_CODING_BASE_URL
    assert model.client.max_retries == _sdk_default_max_retries(), (
        "route_layer() must behave as resolve_model(): URL policy only, the "
        "SDK retry count left at its default (C4)"
    )


# --- C2: the environment is read when the provider is built -----------------


def test_zai_base_url_env_is_read_at_call_time_not_at_import(
    monkeypatch: pytest.MonkeyPatch,
):
    # pytest imports this module (and sdlc.agents.model_ids with it) before
    # test bodies run, so setting the variable here is strictly AFTER import:
    # a value baked in at import time cannot be observed by this test (C2).
    monkeypatch.setenv("ZAI_BASE_URL", _GATEWAY)
    assert zai_base_url() == _GATEWAY


def test_providers_built_after_an_env_change_observe_it(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ZAI_BASE_URL", raising=False)
    before = resolve_model(_ZAI_ID)
    assert _url(before.client.base_url) == ZAI_CODING_BASE_URL
    monkeypatch.setenv("ZAI_BASE_URL", _GATEWAY)
    after = resolve_model(_ZAI_ID)
    assert _url(after.client.base_url) == _GATEWAY, (
        "a ZAI_BASE_URL set after earlier resolutions must reach providers "
        "built afterwards; the policy is caching the default (C2)"
    )


# --- T009: wire evidence on the local counting stub -------------------------
#
# The policy unit tests above read the client object; these run a real
# request against the local stub to prove the client.base_url assignment
# reaches the wire (contract "Observable evidence", SG-5's tripwire). The
# models are built INSIDE the stub/env context — C2 means the URL the
# provider gets is the one ZAI_BASE_URL has when IT is built.


def _one_wire_call(
    build: Callable[[], Agent[Any, Any]], monkeypatch: pytest.MonkeyPatch
) -> tuple[str, int, list[str]]:
    """Build the agent against the ok-mode stub and run one sync call;
    returns (output, request count, observed request paths)."""
    with ProviderStub(mode="always_ok") as stub:
        monkeypatch.setenv("ZAI_BASE_URL", stub.base_url)
        output = build().run_sync("Say ok.").output
        paths = [path for path, _ in stub.requests]
        return output, stub.count, paths


def test_route_layer_agent_reaches_the_stub_chat_completions_path(
    monkeypatch: pytest.MonkeyPatch,
):
    output, count, paths = _one_wire_call(
        lambda: Agent(_ZAI_ID, capabilities=[route_layer()]), monkeypatch
    )
    assert output == "ok", "the ok-mode stub must serve the agent call"
    assert count == 1, (
        f"one plain agent call over route_layer() made {count} HTTP "
        f"requests; the URL policy adds no calls and the SDK must not stack "
        f"retries beneath a served request (T009, contract C4)"
    )
    assert paths and paths[0].endswith("/chat/completions"), (
        f"observed paths {paths!r}; the zai request must land on "
        f"/chat/completions under the stub base (T009)"
    )


def test_resolve_model_instance_agent_reaches_the_stub_chat_completions_path(
    monkeypatch: pytest.MonkeyPatch,
):
    output, count, paths = _one_wire_call(lambda: Agent(resolve_model(_ZAI_ID)), monkeypatch)
    assert output == "ok", "the ok-mode stub must serve the agent call"
    assert count == 1, (
        f"one plain agent call over a pre-built resolve_model() instance "
        f"made {count} HTTP requests (T009, contract C4)"
    )
    assert paths and paths[0].endswith("/chat/completions"), (
        f"observed paths {paths!r}; the zai request must land on "
        f"/chat/completions under the stub base (T009)"
    )


def test_unset_zai_base_url_builds_the_model_without_any_network_call(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ZAI_BASE_URL", raising=False)
    with ProviderStub(mode="always_ok") as stub:
        model = resolve_model(_ZAI_ID)
        assert _url(model.client.base_url) == ZAI_CODING_BASE_URL, (
            "with ZAI_BASE_URL unset the built model must sit on the coding "
            "endpoint (C1) — build only, the agent is never run here"
        )
        assert stub.count == 0, (
            f"building a model made {stub.count} HTTP requests; resolution "
            f"must not touch the network (T009, C5)"
        )
