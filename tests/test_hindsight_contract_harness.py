"""The harness that replaces hand-asserted mock paths. If this test can be
made to pass by a client calling an endpoint nobody serves, the harness is
broken and so is every test built on it."""
from __future__ import annotations

import httpx
import pytest

from sdlc.memory.hindsight_api import BANK_PATH, RECALL_PATH, RETAIN_PATH
from tests.fakes.hindsight_contract import ContractTransport, ContractViolation


@pytest.mark.asyncio
async def test_a_path_absent_from_the_schema_is_rejected():
    transport = ContractTransport(responses={})
    client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    with pytest.raises(ContractViolation, match="no path in the Hindsight"):
        await client.post("/v1/default/banks/b/recall-memories",
                          json={"query": "q"})


@pytest.mark.asyncio
async def test_a_documented_path_is_accepted_and_returns_the_canned_body():
    transport = ContractTransport(responses={("POST", RECALL_PATH): {"results": []}})
    client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    resp = await client.post(
        RECALL_PATH.format(tenant="default", bank="b"), json={"query": "q"})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


@pytest.mark.asyncio
async def test_a_request_body_violating_the_schema_is_rejected():
    # The bank PUT has no `type` constraint, so a list slides through it; the
    # retain endpoint's RetainRequest enforces `type: object` + `required:
    # [items]`, which is what a list where an object is required must hit.
    transport = ContractTransport(responses={("POST", RETAIN_PATH): {
        "success": True, "bank_id": "b", "items_count": 0, "async": False}})
    client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    with pytest.raises(ContractViolation, match="request body"):
        await client.post(RETAIN_PATH.format(tenant="default", bank="b"),
                          json=[1, 2, 3])
