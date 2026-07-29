# tests/test_exa_wrapper.py
import hashlib
import os
import pytest
from agents.research.exa_wrapper import get_wrapped_exa_search

@pytest.mark.asyncio
async def test_get_wrapped_exa_search(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUN_ID", "test-run-123")
    
    WrappedExaSearch = get_wrapped_exa_search()
    
    # If pydantic_ai_harness is missing, it returns DummyExaSearch
    if WrappedExaSearch.__name__ == 'DummyExaSearch':
        pytest.skip("pydantic_ai_harness not installed")
        
    class FakeTextResponse:
        text = "Hello World Exa"
        url = "https://example.com"
        title = "Example"
        published_date = None
        author = None
        highlights = None

    class FakeExaResponse:
        results = [FakeTextResponse()]

    class FakeExaClient:
        async def get_contents(self, urls, text):
            return FakeExaResponse()

    # The capability expects a client complying with ExaClient
    capability = WrappedExaSearch(client=FakeExaClient())
    toolset = capability.get_toolset()
    
    url = "https://example.com"
    result = await toolset.get_page(url)
    
    content = result.return_value
    assert "Hello World Exa" in content
    
    # Verify file is written
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    expected_path = tmp_path / "test-run-123" / "research" / "pages" / f"{url_hash}.txt"
    assert expected_path.exists()
    assert expected_path.read_text() == content
