from __future__ import annotations

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import BANK_PATH
from sdlc.memory.hindsight_client import HindsightMemory, _bank_id
from tests.fakes.hindsight_contract import ContractTransport

# The bank PUT 200 response requires bank_id/name/disposition/mission
# (disposition itself requires skepticism/literalism/empathy). The plan's
# placeholder {} was a guess that the contract transport correctly rejects.
_BANK_RESPONSE = {
    "bank_id": "b",
    "name": "b",
    "mission": "",
    "disposition": {"skepticism": 3, "literalism": 3, "empathy": 3},
}


@pytest.fixture(autouse=True)
def _clean():
    hc._clear_bank_cache()
    hc._clear_client_cache()
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local", tenant="default")
    mem._client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    return mem


def test_bank_ids_are_reduced_to_url_safe_segments():
    assert _bank_id("project:default") == "project-default"
    assert _bank_id("org") == "org"


def test_distinct_banks_stay_distinct_after_sanitising():
    assert _bank_id("project:a") != _bank_id("project:b")


@pytest.mark.asyncio
async def test_ensure_bank_puts_the_bank():
    transport = ContractTransport(responses={("PUT", BANK_PATH): _BANK_RESPONSE})
    mem = _client(transport)
    await mem.ensure_bank("project:default")
    assert transport.requests[0].method == "PUT"
    assert transport.requests[0].url.path.endswith("/banks/project-default")


@pytest.mark.asyncio
async def test_ensure_bank_is_called_once_per_bank():
    transport = ContractTransport(responses={("PUT", BANK_PATH): _BANK_RESPONSE})
    mem = _client(transport)
    await mem.ensure_bank("org")
    await mem.ensure_bank("org")
    assert len(transport.requests) == 1


def test_api_key_becomes_a_bearer_header():
    mem = HindsightMemory(base_url="http://h.local", api_key="tok")
    assert mem._client.headers["authorization"] == "Bearer tok"


def test_no_authorization_header_without_a_key():
    mem = HindsightMemory(base_url="http://h.local")
    assert "authorization" not in mem._client.headers


def test_instances_with_the_same_config_share_one_httpx_client():
    """_backend() builds a fresh HindsightMemory on every activity
    invocation; an AsyncClient per instance that is never closed is a socket
    leak under load."""
    a = HindsightMemory(base_url="http://h.local", tenant="default")
    b = HindsightMemory(base_url="http://h.local", tenant="default")
    assert a._client is b._client


def test_different_tenants_do_not_share_a_client():
    a = HindsightMemory(base_url="http://h.local", tenant="one")
    b = HindsightMemory(base_url="http://h.local", tenant="two")
    assert a._client is not b._client
