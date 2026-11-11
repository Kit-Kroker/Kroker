"""Prompt rendering for the constitution stage (FR-112, plan Task 8).

The drafter's SYSTEM prompt lives in agents/constitution/instructions.md
under PROMPT_SHAS governance — NOT here. This module holds only the
DOWNSTREAM seam: the bounded block the post-constitution proposer stages
(clarify, architect, planner) render into their prompts. It lives in the
producer slice because the producer owns its artifacts — the same shape as
the context slice owning `render_for_prompt` for the codebase map.

Byte-identity (FR-010): a constitution with no principles (flag off, or
nothing survived freeze) renders to `""`, so a run that never saw a
constitution builds byte-identical prompts and memo keys to today.
Truncation is deterministic — whole lines while any fits, hard bound at
max_chars — because an unstable rendering would make the same constitution
prompt differently per call (render_for_prompt's rule).
"""

from __future__ import annotations

from .models import Constitution

_HEADER = "Constitution — governing principles:"
_ELLIPSIS = "\n…"


def _truncate(block: str, max_chars: int) -> str:
    """Clean deterministic cut: drop to the last whole line that fits inside
    the bound (marker included), so the result never exceeds max_chars."""
    cut = block[: max_chars - len(_ELLIPSIS)]
    last_nl = cut.rfind("\n")
    if last_nl > 0:
        cut = cut[:last_nl]
    return cut + _ELLIPSIS


def render_constitution(c: Constitution, *, max_chars: int = 2000) -> str:
    """The constitution as a bounded prompt block: a header line, then one
    line per principle carrying its id, normative and statement, with
    source_ref in brackets when present.

    `""` for a constitution with no principles — the flag-off/empty
    artifact must render to nothing (FR-010 byte-identity). Never longer
    than max_chars.
    """
    if not c.principles:
        return ""
    lines = [_HEADER]
    for p in c.principles:
        line = f"- {p.id} {p.normative} {p.statement}"
        if p.source_ref:
            line += f" [{p.source_ref}]"
        lines.append(line)
    block = "\n".join(lines)
    if len(block) <= max_chars:
        return block
    return _truncate(block, max_chars)
