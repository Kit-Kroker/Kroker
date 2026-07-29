# agents/research/exa_wrapper.py
import hashlib
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def get_wrapped_exa_search():
    """Factory to lazily load and configure ExaSearch subclass."""
    try:
        from pydantic_ai_harness.exa import ExaSearch
        from pydantic_ai_harness.exa._toolset import ExaSearchToolset
        from pydantic_ai.messages import ToolReturn
        
        class WrappedExaSearchToolset(ExaSearchToolset):
            async def get_page(self, url: str) -> ToolReturn[str]:
                # Call base
                result = await super().get_page(url)
                
                content = result.return_value
                if not isinstance(content, str):
                    content = str(content)
                    
                try:
                    # Intercept and write to SDLC_RUNS_ROOT
                    runs_root = os.environ.get("SDLC_RUNS_ROOT", "/tmp/sdlc_runs")
                    run_id = os.environ.get("SDLC_RUN_ID", "default-run")
                    
                    url_hash = hashlib.sha256(url.encode()).hexdigest()
                    out_path = Path(runs_root) / run_id / "research" / "pages" / f"{url_hash}.txt"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(content, encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to write intercept for {url}: {e}")
                
                return result

        class WrappedExaSearch(ExaSearch):
            """Subclass ExaSearch to override the get_page tool."""
            def get_toolset(self):
                return WrappedExaSearchToolset(
                    client=self.client,
                    num_results=self.num_results,
                    max_text_chars=self.max_text_chars,
                    include_deep_search=self.include_deep_search,
                    include_domains=self.include_domains,
                    exclude_domains=self.exclude_domains,
                    text_summary=self.text_summary,
                )
                
        return WrappedExaSearch
    except ImportError:
        class DummyExaSearch:
            def __init__(self, **kwargs):
                pass
        return DummyExaSearch
