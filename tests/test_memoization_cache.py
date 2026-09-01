import pytest

from sdlc.memoization import cache
from sdlc.memoization.activities import CacheGetInput, CachePutInput, cache_get, cache_put
from sdlc.memoization.cache import content_key


@pytest.fixture(autouse=True)
def _isolated_cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))
    yield


def test_content_key_is_deterministic():
    a = content_key("clarify", '{"title":"x"}', "sha1", "model", "wm1")
    b = content_key("clarify", '{"title":"x"}', "sha1", "model", "wm1")
    assert a == b


def test_content_key_changes_with_any_input():
    base = content_key("clarify", '{"title":"x"}', "sha1", "model", "wm1")
    assert base != content_key("architect", '{"title":"x"}', "sha1", "model", "wm1")
    assert base != content_key("clarify", '{"title":"y"}', "sha1", "model", "wm1")
    assert base != content_key("clarify", '{"title":"x"}', "sha2", "model", "wm1")
    assert base != content_key("clarify", '{"title":"x"}', "sha1", "model2", "wm1")
    assert base != content_key("clarify", '{"title":"x"}', "sha1", "model", "wm2")


def test_cache_miss_returns_none():
    assert cache.get("nonexistent-key") is None


def test_cache_put_then_get_round_trips():
    cache.put("k1", '{"a": 1}')
    assert cache.get("k1") == '{"a": 1}'


def test_cache_get_is_a_temporal_activity():
    assert getattr(cache_get, "__temporal_activity_definition", None) is not None


@pytest.mark.asyncio
async def test_cache_activities_round_trip():
    await cache_put(CachePutInput(key="k2", payload_json='{"b": 2}'))
    result = await cache_get(CacheGetInput(key="k2"))
    assert result == '{"b": 2}'
