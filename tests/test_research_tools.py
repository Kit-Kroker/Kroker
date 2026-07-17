import importlib.util
from pathlib import Path

import pytest
from pydantic_ai import RunContext

from sdlc.research.deps import Budget, BudgetExceeded, ResearchDeps

AGENTS_TOOLS = Path(__file__).resolve().parents[1] / "agents" / "research" / "tools"


def _load_tool(name: str):
    spec = importlib.util.spec_from_file_location(
        f"_tool_{name}", AGENTS_TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def _ctx(deps: ResearchDeps) -> RunContext:
    # A minimal RunContext carrying deps is enough for these tools; the tools
    # only read ctx.deps.
    return RunContext(deps=deps, model=None, usage=None, prompt=None)  # type: ignore[arg-type]


@pytest.fixture
def deps(monkeypatch, tmp_path):
    corpus = Path(__file__).resolve().parent / "fakes" / "research_corpus"
    monkeypatch.setenv("SDLC_RESEARCH_FAKE_CORPUS", str(corpus))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return ResearchDeps(run_id="r1", provider="fake", max_searches=2,
                        max_fetches=2, max_cost_usd=1.0)


@pytest.mark.asyncio
async def test_web_search_returns_hits_and_charges_budget(deps):
    web_search = _load_tool("web_search")
    hits = await web_search(_ctx(deps), "retry library", max_results=5)
    assert hits and hits[0]["url"]
    assert deps.budget.searches == 1


@pytest.mark.asyncio
async def test_fetch_page_writes_the_page_and_charges_budget(deps):
    from sdlc.research.verify import page_filename, pages_dir
    fetch_page = _load_tool("fetch_page")
    url = "https://docs.example.com/retrylib"
    page = await fetch_page(_ctx(deps), url)
    assert "handles retries natively" in page["text"]
    written = pages_dir("r1") / page_filename(url)
    assert written.is_file()
    assert deps.budget.fetches == 1


@pytest.mark.asyncio
async def test_search_budget_cap_raises(deps):
    web_search = _load_tool("web_search")
    await web_search(_ctx(deps), "retry", max_results=1)
    await web_search(_ctx(deps), "retry", max_results=1)
    with pytest.raises(BudgetExceeded):
        await web_search(_ctx(deps), "retry", max_results=1)


@pytest.mark.asyncio
async def test_fetch_budget_cap_raises(deps):
    fetch_page = _load_tool("fetch_page")
    await fetch_page(_ctx(deps), "https://docs.example.com/retrylib")
    await fetch_page(_ctx(deps), "https://docs.example.com/httpx")
    with pytest.raises(BudgetExceeded):
        await fetch_page(_ctx(deps), "https://docs.example.com/retrylib")
