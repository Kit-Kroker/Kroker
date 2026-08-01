# agents/research/exa_wrapper.py
import logging

from pydantic_ai import RunContext

from sdlc.research.budget_store import charge_persisted
from sdlc.research.deps import ResearchDeps
from sdlc.research.verify import page_filename, pages_dir

logger = logging.getLogger(__name__)

def get_wrapped_exa_search():
    """Factory to lazily load and configure ExaSearch subclass."""
    try:
        from pydantic_ai_harness.exa import ExaSearch
        from pydantic_ai_harness.exa._toolset import ExaSearchToolset
        from pydantic_ai.messages import ToolReturn

        class WrappedExaSearchToolset(ExaSearchToolset):
            """Charges the run's persisted budget (Task 8: deps.charge()
            alone doesn't hold under TemporalAgent -- see budget_store.py)
            before each Exa call, and mirrors get_page's fetched text to the
            page cache the grounding verifier reads."""

            async def web_search(self, ctx: RunContext[ResearchDeps],
                                 query: str) -> ToolReturn[str]:
                await charge_persisted(ctx.deps, search=1)
                return await super().web_search(query)

            async def get_page(self, ctx: RunContext[ResearchDeps],
                               url: str) -> ToolReturn[str]:
                await charge_persisted(ctx.deps, fetch=1)
                result = await super().get_page(url)

                content = result.return_value
                if not isinstance(content, str):
                    content = str(content)

                try:
                    out_path = pages_dir(ctx.deps.run_id) / page_filename(url)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(content, encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to write intercept for {url}: {e}")

                return result

            async def deep_search(self, ctx: RunContext[ResearchDeps],
                                  question: str) -> ToolReturn[str]:
                await charge_persisted(ctx.deps, search=1)
                return await super().deep_search(question)

        class WrappedExaSearch(ExaSearch):
            """Subclass ExaSearch to route its tools through the budget-
            charging, page-caching WrappedExaSearchToolset."""
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
