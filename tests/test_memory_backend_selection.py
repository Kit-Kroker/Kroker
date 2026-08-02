"""The API key must never reach a `RecallInput`/`RetainInput`: those are
serialized into Temporal workflow history, which is durable storage."""
from __future__ import annotations

import dataclasses

import pytest

from sdlc.memory import activities
from sdlc.memory.activities import RecallInput, RetainInput, _backend
from sdlc.memory.fake import FakeMemory


def test_fake_backend_is_the_default():
    assert isinstance(_backend("http://x", "fake"), FakeMemory)


def test_hindsight_backend_reads_tenant_and_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("SDLC_MEMORY_TENANT", "acme")
    monkeypatch.setenv("SDLC_MEMORY_API_KEY", "secret-token")
    mem = _backend("http://h.local", "hindsight")
    assert mem.tenant == "acme"
    assert mem.api_key == "secret-token"


def test_tenant_defaults_and_key_is_optional(monkeypatch):
    monkeypatch.delenv("SDLC_MEMORY_TENANT", raising=False)
    monkeypatch.delenv("SDLC_MEMORY_API_KEY", raising=False)
    mem = _backend("http://h.local", "hindsight")
    assert mem.tenant == "default"
    assert mem.api_key is None


@pytest.mark.parametrize("model", [RecallInput, RetainInput])
def test_activity_inputs_carry_no_credential_field(model):
    names = {f.name for f in dataclasses.fields(model)}
    assert not (names & {"api_key", "token", "authorization", "tenant"}), (
        f"{model.__name__} would write a credential into Temporal history")
