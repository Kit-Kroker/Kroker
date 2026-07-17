from pydantic_ai import RunContext

from sdlc.research.deps import ResearchDeps, charge
from sdlc.research.protocol import make_provider
from sdlc.research.verify import page_filename, pages_dir


async def fetch_page(ctx: RunContext[ResearchDeps], url: str) -> dict:
    """Fetch `url` and persist its text to runs/<run_id>/research/pages so the
    verifier (Task 7) can verify quotes against bytes fetched THIS run. Charges
    one fetch against the budget. Returns {url, text}."""
    charge(ctx.deps, fetch=1)
    provider = make_provider(ctx.deps.provider)
    page = await provider.fetch(url)
    d = pages_dir(ctx.deps.run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / page_filename(url)).write_text(page.text, encoding="utf-8")
    return page.model_dump()
