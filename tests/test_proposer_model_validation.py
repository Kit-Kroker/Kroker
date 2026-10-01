"""validate_proposer_model: the accept/reject table in
contracts/proposer-override-validation.md (004 T016, FR-004/FR-005).

Offline by construction: the test deletes every provider credential it can
find and blocks socket creation around each call, so a validation that
sneaks in a network round-trip or a credential read fails here rather than
in CI.

RED on main: sdlc.agents.model_ids does not exist yet (004 T020 delivers
validate_proposer_model).
"""

from __future__ import annotations

import socket

import pytest

from sdlc.agents.loader import RegistryError

ACCEPTED = [
    "anthropic:glm-5.2",
    "anthropic:claude-sonnet-4-6",
    "openai:gpt-5.2",
    "google:gemini-3.5-flash",
]

REJECTED = [
    "openai/gpt-5.2",  # slash is the harness grammar, not provider:model
    "zai-coding-plan/glm-5.2",
    "glm-5.2",  # no provider part
    "anthropic:",  # empty model part
    ":glm-5.2",  # empty provider part
    "test",  # resolves to TestModel, never a real proposer
    "nosuch:model",  # no constructible provider class
    "groq:nope",  # provider class exists upstream, extra not installed here
]

_CREDENTIAL_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "EXA_API_KEY",
    "TAVILY_API_KEY",
]


class _NoSockets:
    """socket.socket stand-in that fails loudly: validation is offline."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("validate_proposer_model made a network call (FR-005)")


@pytest.fixture
def offline(monkeypatch):
    for var in _CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(socket, "socket", _NoSockets)
    # sdlc.agents.model_ids is 004's new module; importing inside the tests
    # makes the missing-module failure a per-test RED, not a collection error.
    from sdlc.agents.model_ids import validate_proposer_model

    return validate_proposer_model


@pytest.mark.parametrize("value", ACCEPTED)
def test_accepts_valid_provider_model_ids(offline, value):
    offline("architect", value)  # raises nothing


@pytest.mark.parametrize("value", REJECTED)
def test_rejects_invalid_ids_naming_role_string_and_form(offline, value):
    with pytest.raises(RegistryError, match=r"provider:model") as excinfo:
        offline("architect", value)
    message = str(excinfo.value)
    assert "architect" in message, f"message must name the role: {message!r}"
    assert value in message, f"message must name the offending string: {message!r}"
