# tests/test_exa_wrapper.py
import hashlib
import os
import pytest
from agents.research.exa_wrapper import get_page_intercepted

@pytest.mark.asyncio
async def test_get_page_intercepted(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    
    # Fake Exa response
    class FakeTextResponse:
        text = "Hello World Exa"
    
    class FakeExaResponse:
        results = [FakeTextResponse()]

    class FakeExaClient:
        def get_contents(self, urls, text):
            return FakeExaResponse()

    client = FakeExaClient()
    
    # We pretend run_id is injected into context or env
    monkeypatch.setenv("SDLC_RUN_ID", "test-run-123")
    
    url = "https://example.com"
    content = await get_page_intercepted(client, url)
    assert "Hello World Exa" in content
    
    # Verify file is written
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    expected_path = tmp_path / "test-run-123" / "research" / "pages" / f"{url_hash}.txt"
    assert expected_path.exists()
    assert expected_path.read_text() == "Hello World Exa"
