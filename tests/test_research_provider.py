import pytest

from sdlc.research.protocol import SearchProvider, make_provider


@pytest.fixture(autouse=True)
def _corpus(monkeypatch):
    from pathlib import Path

    corpus = Path(__file__).resolve().parent / "fakes" / "research_corpus"
    monkeypatch.setenv("SDLC_RESEARCH_FAKE_CORPUS", str(corpus))


@pytest.mark.asyncio
async def test_fake_provider_searches_and_fetches_the_canned_corpus():
    provider: SearchProvider = make_provider("fake")
    hits = await provider.search("retry library", max_results=5)
    assert hits, "canned corpus should answer the seeded query"
    page = await provider.fetch(hits[0].url)
    assert page.url == hits[0].url
    assert page.text.strip()


@pytest.mark.asyncio
async def test_make_provider_rejects_unknown_name():
    with pytest.raises(ValueError):
        make_provider("nope")
