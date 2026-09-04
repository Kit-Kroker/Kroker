from pydantic_ai import RunContext

from sdlc.memory.activities import _backend
from sdlc.stages.research.deps import ResearchDeps


async def recall_leads(
    ctx: RunContext[ResearchDeps], query: str, max_results: int = 5
) -> list[str]:
    """Recall prior research findings from the corpus as LEADS — never as truth.
    Watermark-pinned, filtered to stage=research. A recalled lead placed in
    grounded_findings fails the verifier's source-never-fetched check by
    construction (spec finding 5); to promote a lead, re-fetch it."""
    backend = _backend(ctx.deps.memory_base_url, ctx.deps.memory_backend)
    snap = await backend.recall(
        ctx.deps.memory_bank, query, {"stage": "research"}, ctx.deps.memory_watermark
    )
    return snap.items[:max_results]
