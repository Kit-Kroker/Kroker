"""Prompt rendering for the requirements stage (FR-113, plan Task 7).

The product drafter's SYSTEM prompt lives in
agents/product/instructions.md under PROMPT_SHAS governance — NOT here.
This module holds only the DOWNSTREAM seam: the bounded block clarify
renders into its prompt. It lives in the producer slice because the
producer owns its artifacts — the same shape as the constitution slice
owning `render_constitution` and the context slice owning
`render_for_prompt` for the codebase map.

Byte-identity (FR-010): a requirements artifact with no stories (flag
off, or nothing survived the freeze) renders to `""`, so a run that
never saw a requirements draft builds byte-identical prompts and memo
keys to today. Truncation is deterministic — whole lines while any
fits, hard bound at max_chars — because an unstable rendering would
make the same artifact prompt differently per call
(render_constitution's rule, which took it from render_for_prompt).
"""

from __future__ import annotations

from .models import Requirements

_HEADER = "Requirements — drafted user stories:"
_ELLIPSIS = "\n…"


def _truncate(block: str, max_chars: int) -> str:
    """Clean deterministic cut: drop to the last whole line that fits inside
    the bound (marker included), so the result never exceeds max_chars."""
    cut = block[: max_chars - len(_ELLIPSIS)]
    last_nl = cut.rfind("\n")
    if last_nl > 0:
        cut = cut[:last_nl]
    return cut + _ELLIPSIS


def render_requirements(c: Requirements, *, max_chars: int = 2000) -> str:
    """The requirements artifact as a bounded prompt block: a header line,
    then one line per story carrying its id and narrative (source_ref in
    brackets when present), with the story's FR and SC lines nested
    beneath it.

    `""` for an artifact with no stories — the flag-off/empty artifact
    must render to nothing (FR-010 byte-identity). Never longer than
    max_chars.
    """
    if not c.stories:
        return ""
    lines = [_HEADER]
    for s in c.stories:
        line = f"- {s.id} {s.narrative}"
        if s.source_ref:
            line += f" [{s.source_ref}]"
        lines.append(line)
        lines.extend(f"  - {fr.id} {fr.text}" for fr in s.functional)
        lines.extend(f"  - {sc.id} {sc.text}" for sc in s.success_criteria)
    block = "\n".join(lines)
    if len(block) <= max_chars:
        return block
    return _truncate(block, max_chars)
