import os
from pathlib import Path

from pydantic_ai import RunContext

from sdlc.research.deps import ResearchDeps


async def read_repo(ctx: RunContext[ResearchDeps], path: str) -> str:
    """Read a text file from the project repo to ground research in the code
    that exists. Rooted at $SDLC_RESEARCH_REPO_ROOT (default cwd); path
    traversal outside the root is refused. NOT charged against the search/fetch
    budget — local reads are free and bounded by the model's own restraint."""
    root = Path(os.environ.get("SDLC_RESEARCH_REPO_ROOT", ".")).resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"refusing to read outside the repo root: {path}")
    if not target.is_file():
        return f"[no such file: {path}]"
    return target.read_text(encoding="utf-8", errors="replace")
