"""Pure prompt composition for the proposer roles.

Extracted verbatim from FeatureWorkflow's inline expressions so that the
production pipeline and the eval fixture generator build the same string
from the same code. Divergence is now a code change, not silent rot.

No I/O, no imports beyond typing: this module is imported inside
feature.py's `workflow.unsafe.imports_passed_through()` block and must
stay deterministic and sandbox-safe.

Every function here is pinned byte-for-byte by
tests/test_prompts_characterization.py. Changing an output string changes
the prompt the pipeline sends AND invalidates the memoization content_key
-- treat it as a behavior change, never a tidy-up.
"""

from __future__ import annotations

from collections.abc import Sequence


def _memory_block(items: Sequence[str]) -> str:
    """feature.py:1894-1895, :2041-2042 -- shared by clarify and planner."""
    if not items:
        return ""
    return "\nRelevant memory:\n- " + "\n- ".join(items)


def _frozen_contract_block(assertions: Sequence[str]) -> str:
    """feature.py:1404, :1415 -- shared by qa and reviewer."""
    return "Frozen contract assertions:\n- " + "\n- ".join(assertions)


def planner_prompt(arch_json: str, memory: Sequence[str], guidance: str | None) -> str:
    """feature.py:2040-2044."""
    return (
        arch_json
        + _memory_block(memory)
        + (f"\nRevision guidance from reviewer:\n{guidance}" if guidance else "")
    )


def qa_prompt(assertions: Sequence[str], qa_raw_json: str, diff_stat: str, diff_patch: str) -> str:
    """feature.py:1404-1407."""
    return (
        _frozen_contract_block(assertions)
        + f"\nTest results: {qa_raw_json}"
        + f"\nDiff stat:\n{diff_stat}"
        + f"\nDiff:\n{diff_patch}"
    )


def reviewer_prompt(assertions: Sequence[str], qa_raw_json: str, diff_patch: str) -> str:
    """feature.py:1415-1417. NOTE: no `Diff stat:` block -- qa gets one and
    reviewer does not. Preserved from the original; see design doc 4.1."""
    return (
        _frozen_contract_block(assertions)
        + f"\nTest results: {qa_raw_json}"
        + f"\nDiff:\n{diff_patch}"
    )


def analyst_prompt(criteria_lines: str, qa_lines: str, diff_stat: str, diff_patch: str) -> str:
    """feature.py:2192-2195."""
    return (
        "Acceptance criteria (task_id in brackets):\n"
        + criteria_lines
        + "\nAggregate test output:\n"
        + qa_lines
        + f"\nIntegration diff stat:\n{diff_stat}"
        + f"\nIntegration diff:\n{diff_patch}"
    )


def merge_verdict_prompt(task_results: Sequence[dict]) -> str:
    """feature.py:2361-2362. The f-string interpolates the LIST, so Python's
    repr of list-of-dicts is what reaches the model. Do not "fix" this to
    JSON -- it would change the prompt."""
    return (
        f"Advisory only — the deterministic gate already passed. Task results: {list(task_results)}"
    )
