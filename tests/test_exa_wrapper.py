# tests/test_exa_wrapper.py
import hashlib
import json

import pytest
from pydantic_ai import RunContext

from agents.research.exa_wrapper import get_wrapped_exa_search
from sdlc.research.budget_store import budget_path
from sdlc.research.deps import BudgetExceeded, ResearchDeps


def _ctx(deps: ResearchDeps) -> RunContext:
    # A minimal RunContext carrying deps is enough here; the wrapped tools
    # only read ctx.deps (mirrors tests/test_research_tools.py's helper).
    return RunContext(deps=deps, model=None, usage=None, prompt=None)  # type: ignore[arg-type]


def _deps(run_id: str = "r1", max_fetches: int = 5, max_searches: int = 5) -> ResearchDeps:
    return ResearchDeps(
        run_id=run_id,
        provider="tavily",
        max_searches=max_searches,
        max_fetches=max_fetches,
        max_cost_usd=10.0,
    )


class FakePageResult:
    text = "Hello World Exa"
    url = "https://example.com"
    title = "Example"
    published_date = None
    author = None
    highlights = None


class FakeSearchResult:
    def __init__(self, url: str = "https://example.com/a", title: str = "A"):
        self.url = url
        self.title = title
        self.published_date = None
        self.author = None
        self.highlights = ["a highlight"]


class FakeOutput:
    content = "synthesized answer"
    grounding: list = []


class FakeSearchResponse:
    def __init__(self, results=None, output=None):
        self.results = results if results is not None else [FakeSearchResult()]
        self.output = output


class FakeExaClient:
    def __init__(self):
        self.get_contents_calls = 0
        self.search_calls = 0

    async def get_contents(self, urls, text):
        self.get_contents_calls += 1
        return FakeSearchResponse(results=[FakePageResult()])

    async def search(self, query, **kwargs):
        self.search_calls += 1
        if kwargs.get("type") == "deep":
            return FakeSearchResponse(results=[FakeSearchResult()], output=FakeOutput())
        return FakeSearchResponse()


def _wrapped_search_or_skip(**kwargs):
    WrappedExaSearch = get_wrapped_exa_search()
    if WrappedExaSearch.__name__ == "DummyExaSearch":
        pytest.skip("pydantic_ai_harness not installed")
    client = FakeExaClient()
    capability = WrappedExaSearch(client=client, **kwargs)
    return capability.get_toolset(), client


@pytest.mark.asyncio
async def test_get_page_writes_the_page_under_ctx_deps_run_id(tmp_path, monkeypatch):
    # SDLC_RUN_ID is never set in production (feature.py never sets it) --
    # the page cache path must come from ctx.deps.run_id, not that env var.
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    monkeypatch.delenv("SDLC_RUN_ID", raising=False)
    toolset, client = _wrapped_search_or_skip()

    url = "https://example.com"
    result = await toolset.get_page(_ctx(_deps("run-xyz")), url)

    content = result.return_value
    assert "Hello World Exa" in content
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    expected_path = tmp_path / "run-xyz" / "research" / "pages" / f"{url_hash}.txt"
    assert expected_path.exists()
    assert expected_path.read_text() == content


@pytest.mark.asyncio
async def test_get_page_charges_fetch_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    toolset, client = _wrapped_search_or_skip()

    await toolset.get_page(_ctx(_deps("run-a")), "https://example.com/1")
    await toolset.get_page(_ctx(_deps("run-a")), "https://example.com/2")

    assert json.loads(budget_path("run-a").read_text())["fetches"] == 2
    assert client.get_contents_calls == 2


@pytest.mark.asyncio
async def test_get_page_raises_and_skips_the_call_when_fetch_budget_exhausted(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    toolset, client = _wrapped_search_or_skip()

    await toolset.get_page(_ctx(_deps("run-b", max_fetches=1)), "https://example.com/1")
    with pytest.raises(BudgetExceeded):
        await toolset.get_page(_ctx(_deps("run-b", max_fetches=1)), "https://example.com/2")

    # Charge-before-work: the exhausted call never reaches the Exa client.
    assert client.get_contents_calls == 1


@pytest.mark.asyncio
async def test_web_search_charges_search_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    toolset, client = _wrapped_search_or_skip()

    await toolset.web_search(_ctx(_deps("run-c")), "some query")

    assert json.loads(budget_path("run-c").read_text())["searches"] == 1
    assert client.search_calls == 1


@pytest.mark.asyncio
async def test_web_search_raises_and_skips_the_call_when_search_budget_exhausted(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    toolset, client = _wrapped_search_or_skip()

    await toolset.web_search(_ctx(_deps("run-d", max_searches=1)), "q1")
    with pytest.raises(BudgetExceeded):
        await toolset.web_search(_ctx(_deps("run-d", max_searches=1)), "q2")

    assert client.search_calls == 1


@pytest.mark.asyncio
async def test_deep_search_charges_search_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    toolset, client = _wrapped_search_or_skip(include_deep_search=True)

    await toolset.deep_search(_ctx(_deps("run-e")), "some question")

    assert json.loads(budget_path("run-e").read_text())["searches"] == 1
    assert client.search_calls == 1
