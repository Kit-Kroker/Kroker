from __future__ import annotations

import json

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import BANK_PATH, RECALL_LIMIT_FIELD, RECALL_PATH
from sdlc.memory.hindsight_client import RECALL_KEEP, HindsightMemory
from tests.fakes.hindsight_contract import ContractTransport

_BANK_RESPONSE = {
    "bank_id": "b", "name": "b", "mission": "",
    "disposition": {"skepticism": 3, "literalism": 3, "empathy": 3},
}


@pytest.fixture(autouse=True)
def _clean():
    hc._clear_bank_cache()
    hc._clear_client_cache()
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


def _result(text: str, mentioned_at: str) -> dict:
    return {"id": f"m-{text[:6]}", "text": text, "type": "world",
            "mentioned_at": mentioned_at, "tags": [], "entities": [],
            "document_id": "d1", "chunk_id": "c1",
            "scores": {"final": 0.9}}


def _transport(results):
    return ContractTransport(responses={
        ("PUT", BANK_PATH): _BANK_RESPONSE,
        ("POST", RECALL_PATH): {"results": results},
    })


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local")
    mem._client = httpx.AsyncClient(base_url="http://h.local",
                                    transport=transport)
    return mem


def _sent(transport) -> dict:
    post = [r for r in transport.requests if r.method == "POST"][0]
    return json.loads(post.content)


@pytest.mark.asyncio
async def test_recall_reads_results_not_items():
    transport = _transport([_result("a gotcha worth knowing",
                                    "2026-08-01T00:00:00+00:00")])
    snap = await _client(transport).recall("project:default", "q", {}, None)
    assert snap.items == ["a gotcha worth knowing"]


@pytest.mark.asyncio
async def test_filters_become_strict_tag_matches():
    transport = _transport([])
    await _client(transport).recall("project:default", "q",
                                    {"stage": "clarify"}, None)
    body = _sent(transport)
    assert body["tags"] == ["stage:clarify"]
    assert body["tags_match"] == "all_strict"


@pytest.mark.asyncio
async def test_empty_filters_send_no_tag_keys_at_all():
    transport = _transport([])
    await _client(transport).recall("project:default", "q", {}, None)
    body = _sent(transport)
    assert "tags" not in body
    assert "tags_match" not in body


@pytest.mark.asyncio
async def test_an_unfilterable_filter_key_raises_rather_than_returning_everything():
    transport = _transport([])
    with pytest.raises(ValueError, match="run_id"):
        await _client(transport).recall("project:default", "q",
                                        {"run_id": "run-1"}, None)


@pytest.mark.asyncio
async def test_results_after_the_watermark_are_dropped():
    transport = _transport([
        _result("before the freeze", "2026-08-01T00:00:00+00:00"),
        _result("after the freeze", "2026-08-03T00:00:00+00:00"),
    ])
    snap = await _client(transport).recall(
        "project:default", "q", {}, "2026-08-02T00:00:00+00:00")
    assert snap.items == ["before the freeze"]


@pytest.mark.asyncio
async def test_a_result_without_a_timestamp_is_dropped_when_pinned():
    bad = _result("undateable", "2026-08-01T00:00:00+00:00")
    del bad["mentioned_at"]
    transport = _transport([bad])
    snap = await _client(transport).recall(
        "project:default", "q", {}, "2026-08-02T00:00:00+00:00")
    assert snap.items == []


@pytest.mark.asyncio
async def test_a_result_without_a_timestamp_survives_when_unpinned():
    bad = _result("undateable", "2026-08-01T00:00:00+00:00")
    del bad["mentioned_at"]
    snap = await _client(_transport([bad])).recall(
        "project:default", "q", {}, None)
    assert snap.items == ["undateable"]


@pytest.mark.asyncio
async def test_recall_over_fetches_so_the_cutoff_does_not_starve_the_snapshot():
    transport = _transport([])
    await _client(transport).recall("project:default", "q", {}, None)
    # max_tokens bounds by token count, not results; assert it is generous
    # enough that the watermark cutoff can discard without starving the
    # snapshot. (RECALL_LIMIT_FIELD is max_tokens, not a result count.)
    assert _sent(transport)[RECALL_LIMIT_FIELD] >= 4096


@pytest.mark.asyncio
async def test_snapshot_is_truncated_to_the_keep_size():
    results = [_result(f"memory {i}", "2026-08-01T00:00:00+00:00")
               for i in range(RECALL_KEEP + 5)]
    snap = await _client(_transport(results)).recall(
        "project:default", "q", {}, None)
    assert len(snap.items) == RECALL_KEEP


@pytest.mark.asyncio
async def test_snapshot_carries_the_pinned_watermark_and_a_query_hash():
    snap = await _client(_transport([])).recall(
        "project:default", "q", {}, "2026-08-02T00:00:00+00:00")
    assert snap.watermark == "2026-08-02T00:00:00+00:00"
    assert snap.bank == "project:default"
    assert len(snap.query_hash) == 64
    assert snap.degraded is False
