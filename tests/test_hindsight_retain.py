from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import BANK_PATH, RETAIN_PATH
from sdlc.memory.hindsight_client import HindsightMemory
from sdlc.models import MemoryKind, RetainItem
from tests.fakes.hindsight_contract import ContractTransport

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


def _transport():
    return ContractTransport(
        responses={
            ("PUT", BANK_PATH): _BANK_RESPONSE,
            # The retain 200 response requires success/bank_id/items_count/async.
            ("POST", RETAIN_PATH): {
                "success": True,
                "bank_id": "b",
                "items_count": 1,
                "async": True,
            },
        }
    )


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local")
    mem._client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    return mem


def _sent(transport) -> dict:
    post = [r for r in transport.requests if r.method == "POST"][0]
    return json.loads(post.content)


def _item(**over) -> RetainItem:
    base = dict(
        kind=MemoryKind.STAGE_SUMMARY,
        bank="project:default",
        text="the clarifier settled the scope",
        metadata={"stage": "clarify", "run_id": "run-1"},
    )
    base.update(over)
    return RetainItem(**base)


@pytest.mark.asyncio
async def test_retain_sends_content_not_text():
    transport = _transport()
    await _client(transport).retain(_item())
    item = _sent(transport)["items"][0]
    assert item["content"] == "the clarifier settled the scope"
    assert "text" not in item


@pytest.mark.asyncio
async def test_promoted_metadata_becomes_tags_alongside_kind():
    transport = _transport()
    await _client(transport).retain(_item())
    tags = _sent(transport)["items"][0]["tags"]
    assert "kind:stage_summary" in tags
    assert "stage:clarify" in tags


@pytest.mark.asyncio
async def test_unbounded_metadata_keys_stay_out_of_tags():
    transport = _transport()
    await _client(transport).retain(_item())
    item = _sent(transport)["items"][0]
    assert not any(t.startswith("run_id:") for t in item["tags"])
    assert item["metadata"]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_retain_is_async_with_a_deterministic_operation_id():
    t1, t2 = _transport(), _transport()
    await _client(t1).retain(_item())
    await _client(t2).retain(_item())
    body1, body2 = _sent(t1), _sent(t2)
    assert body1["async"] is True
    assert body1["operation_id"] == body2["operation_id"]
    assert body1["items"][0]["document_id"] == body2["items"][0]["document_id"]


@pytest.mark.asyncio
async def test_different_text_gets_a_different_document_id():
    t1, t2 = _transport(), _transport()
    await _client(t1).retain(_item())
    await _client(t2).retain(_item(text="something else entirely"))
    assert _sent(t1)["items"][0]["document_id"] != _sent(t2)["items"][0]["document_id"]


@pytest.mark.asyncio
async def test_retain_stamps_a_worker_clock_timestamp():
    transport = _transport()
    await _client(transport).retain(_item())
    stamp = _sent(transport)["items"][0]["timestamp"]
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_retain_ensures_the_bank_first():
    transport = _transport()
    await _client(transport).retain(_item())
    assert transport.requests[0].method == "PUT"


@pytest.mark.asyncio
async def test_current_watermark_is_an_iso_timestamp_and_makes_no_request():
    transport = _transport()
    mem = _client(transport)
    wm = await mem.current_watermark("project:default")
    assert datetime.fromisoformat(wm.replace("Z", "+00:00")).tzinfo is not None
    assert transport.requests == []
