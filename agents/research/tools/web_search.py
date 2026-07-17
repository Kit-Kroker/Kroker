from pydantic_ai import RunContext

from sdlc.research.deps import ResearchDeps, charge
from sdlc.research.protocol import make_provider


async def web_search(ctx: RunContext[ResearchDeps], query: str,
                     max_results: int = 5) -> list[dict]:
    """Search the web for `query`. Charges one search against the per-run
    budget (raises when exhausted). Returns [{url, title, snippet}]."""
    charge(ctx.deps, search=1)
    provider = make_provider(ctx.deps.provider)
    hits = await provider.search(query, max_results)
    return [h.model_dump() for h in hits]
