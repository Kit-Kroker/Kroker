import importlib.util
from pathlib import Path

import pytest
from pydantic_ai import RunContext

from sdlc.research.deps import ResearchDeps

AGENTS_TOOLS = Path(__file__).resolve().parents[1] / "agents" / "research" / "tools"


def _load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"_tool_{name}", AGENTS_TOOLS / f"{name}.py")
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
    return ResearchDeps(
        run_id="r1", provider="fake", max_searches=2, max_fetches=2, max_cost_usd=1.0
    )


# web_search/fetch_page (and their budget-cap tests) were removed with them
# in favor of the Exa-backed toolset -- see tests/test_exa_wrapper.py for the
# charge_persisted-based coverage of web_search/get_page/deep_search now that
# they're the tools actually in the agent's toolset.


@pytest.mark.asyncio
async def test_read_repo_reads_in_root_file(deps, monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RESEARCH_REPO_ROOT", str(tmp_path))
    (tmp_path / "hello.txt").write_text("cats", encoding="utf-8")
    read_repo = _load_tool("read_repo")
    assert await read_repo(_ctx(deps), "hello.txt") == "cats"


@pytest.mark.asyncio
async def test_read_repo_missing_file_returns_string(deps, monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RESEARCH_REPO_ROOT", str(tmp_path))
    read_repo = _load_tool("read_repo")
    out = await read_repo(_ctx(deps), "nope.txt")
    assert out == "[no such file: nope.txt]"


@pytest.mark.asyncio
async def test_read_repo_out_of_root_returns_string_not_raises(deps, monkeypatch, tmp_path):
    """A path escaping the root must be REFUSED GRACEFULLY (a model-visible
    string), never raised. A raised ValueError becomes a Temporal
    ApplicationFailure that the tool-call activity retries with no cap — an
    infinite loop that hangs the whole run (observed on the cat-cafe smoke
    run: read_repo on an out-of-cwd greenfield repo, attempt 11 and climbing)."""
    monkeypatch.setenv("SDLC_RESEARCH_REPO_ROOT", str(tmp_path))
    read_repo = _load_tool("read_repo")
    out = await read_repo(_ctx(deps), "../../../etc/passwd")
    assert isinstance(out, str)
    # a bracketed refusal marker, not file contents — the escaping path is
    # refused before any read, so nothing from outside the root leaks through
    assert out == "[refusing to read outside the repo root: ../../../etc/passwd]"
