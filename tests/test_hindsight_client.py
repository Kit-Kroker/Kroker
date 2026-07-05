import httpx
import pytest

from sdlc.memory.hindsight_client import HindsightMemory
from sdlc.models import MemoryKind, RetainItem


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_recall_posts_query_and_parses_snapshot():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/banks/project:x/recall"
        return httpx.Response(200, json={
            "query_hash": "abc123", "watermark": "5",
            "items": ["memory item one"],
        })

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    snap = await client.recall("project:x", "q", {}, None)
    assert snap.query_hash == "abc123"
    assert snap.watermark == "5"
    assert snap.items == ["memory item one"]


@pytest.mark.asyncio
async def test_retain_posts_kind_text_metadata():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={})

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    await client.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="project:x",
                                   text="t", metadata={}))
    assert seen["path"] == "/v1/banks/project:x/retain"


@pytest.mark.asyncio
async def test_current_watermark_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/banks/project:x/watermark"
        return httpx.Response(200, json={"watermark": "9"})

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    wm = await client.current_watermark("project:x")
    assert wm == "9"


@pytest.mark.asyncio
async def test_recall_raises_on_http_error_so_the_activity_can_degrade():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = HindsightMemory(base_url="http://hindsight.local")
    client._client = httpx.AsyncClient(base_url="http://hindsight.local",
                                       transport=_transport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await client.recall("project:x", "q", {}, None)
