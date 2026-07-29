# agents/research/exa_wrapper.py
import hashlib
import os
from pathlib import Path
from pydantic_ai_harness.exa import ExaSearch

async def get_page_intercepted(exa_client, url: str) -> str:
    """A standalone function or patched method to fetch via Exa and write to disk."""
    # We use Exa's get_contents directly as a helper to mirror what ExaSearch does
    response = exa_client.get_contents([url], text=True)
    if not response.results:
        return ""
    
    content = response.results[0].text
    
    # Intercept and write to SDLC_RUNS_ROOT
    runs_root = os.environ.get("SDLC_RUNS_ROOT", "/tmp/sdlc_runs")
    run_id = os.environ.get("SDLC_RUN_ID", "default-run")
    
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    out_path = Path(runs_root) / run_id / "research" / "pages" / f"{url_hash}.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    
    return content

class WrappedExaSearch(ExaSearch):
    """Subclass ExaSearch to override the get_page tool."""
    # The pydantic-ai-harness ExaSearch provides a `get_page` tool. We'll override it here if possible.
    # We will configure it properly in Task 2.
    pass
