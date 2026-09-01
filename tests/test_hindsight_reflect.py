from __future__ import annotations

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import (
    BANK_PATH,
    CONSOLIDATE_PATH,
    OPERATION_PATH,
)
from sdlc.memory.hindsight_client import ConsolidationFailed, HindsightMemory
from tests.fakes.hindsight_contract import ContractTransport

_BANK_RESPONSE = {
    "bank_id": "b",
    "name": "b",
    "mission": "",
    "disposition": {"skepticism": 3, "literalism": 3, "empathy": 3},
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    hc._clear_bank_cache()
    hc._clear_client_cache()
    # Never actually sleep in unit tests.
    monkeypatch.setattr(hc, "POLL_INTERVAL_S", 0.0)
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


def _transport(op_status: str):
    return ContractTransport(
        responses={
            ("PUT", BANK_PATH): _BANK_RESPONSE,
            ("POST", CONSOLIDATE_PATH): {"operation_id": "op-1"},
            # Operation status schema requires operation_id + status (not id/type).
            ("GET", OPERATION_PATH): {"operation_id": "op-1", "status": op_status},
        }
    )


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local")
    mem._client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    return mem


@pytest.mark.asyncio
async def test_reflect_triggers_consolidation_not_the_qa_endpoint():
    transport = _transport("completed")
    await _client(transport).reflect("project:default")
    posted = [r for r in transport.requests if r.method == "POST"][0]
    assert "consolidate" in posted.url.path
    assert not posted.url.path.endswith("/reflect")


@pytest.mark.asyncio
async def test_reflect_polls_the_operation_to_completion():
    transport = _transport("completed")
    await _client(transport).reflect("project:default")
    assert any(r.method == "GET" and "op-1" in r.url.path for r in transport.requests)


@pytest.mark.asyncio
async def test_a_failed_consolidation_raises():
    with pytest.raises(ConsolidationFailed, match="failed"):
        await _client(_transport("failed")).reflect("project:default")


@pytest.mark.asyncio
async def test_a_cancelled_consolidation_raises():
    with pytest.raises(ConsolidationFailed):
        await _client(_transport("cancelled")).reflect("project:default")


@pytest.mark.asyncio
async def test_polling_gives_up_rather_than_hanging_past_the_activity_budget(monkeypatch):
    monkeypatch.setattr(hc, "POLL_DEADLINE_S", 0.0)
    with pytest.raises(ConsolidationFailed, match="did not finish"):
        await _client(_transport("processing")).reflect("project:default")


@pytest.mark.asyncio
async def test_a_consolidation_response_without_operation_id_skips_polling():
    """Hindsight's schema requires operation_id on every consolidate response,
    so this path cannot fire against the real API. It is defensive against a
    proxy stripping the field or an API change; tested with a plain
    MockTransport because the contract transport correctly rejects a body
    missing the required operation_id."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "PUT":
            return httpx.Response(200, json=_BANK_RESPONSE)
        return httpx.Response(200, json={})  # no operation_id

    mem = HindsightMemory(base_url="http://h.local")
    mem._client = httpx.AsyncClient(
        base_url="http://h.local", transport=httpx.MockTransport(handler)
    )
    await mem.reflect("project:default")
    assert not any(r.method == "GET" for r in requests)
