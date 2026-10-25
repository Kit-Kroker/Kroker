"""Analyze stage prompt generation and digest (spec A §5)."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from ...core.models import PipelineConfig

if TYPE_CHECKING:
    from .models import KeyedCriterion, TraceInventory


def analyst_prompt(criteria_lines: str, qa_lines: str, diff_stat: str, diff_patch: str) -> str:
    """Clean-context prompt for the Analyst role (FR-106)."""
    return (
        "Acceptance criteria (task_id in brackets):\n"
        + criteria_lines
        + "\nAggregate test output:\n"
        + qa_lines
        + f"\nIntegration diff stat:\n{diff_stat}"
        + f"\nIntegration diff:\n{diff_patch}"
    )


def _format_capped_inventory_lines(
    items: list[str],
    budget: int,
) -> tuple[list[str], int]:
    """Return the items that fit in budget with whole lines, and remaining items count."""
    chosen: list[str] = []
    used = 0
    for item in items:
        line_cost = len(item) + 1
        if used + line_cost > budget:
            break
        chosen.append(item)
        used += line_cost
    return chosen, len(items) - len(chosen)


def analyst_prompt_v2(
    criteria: list[KeyedCriterion],
    inventory: TraceInventory,
    task_order: list[str],
    qa_lines: str,
    diff_stat: str,
    diff_patch: str,
) -> str:
    """Clean-context prompt for the Analyst role under 017-analyze-evidence (contract C-1).

    The prompt grows by at most 150,000 characters across (a) changed_files and
    (b) tests (research D-3). Budget is halved (75k each) with unused carrying over,
    whole lines only, with a truncation note when cut. The tail from Aggregate test
    output onward is byte-identical to analyst_prompt.
    """
    sec1 = "Acceptance criteria (key, task_id, text):\n" + "\n".join(
        f"- [{c.key}] [{c.task_id}] {c.criterion}" for c in criteria
    )

    cost_a = sum(len(p) + 1 for p in inventory.changed_files)
    cost_b = sum(len(t) + 1 for t in inventory.tests)

    if cost_a + cost_b <= 150_000:
        budget_a = cost_a
        budget_b = cost_b
    elif cost_a < 75_000:
        budget_a = cost_a
        budget_b = 150_000 - cost_a
    elif cost_b < 75_000:
        budget_b = cost_b
        budget_a = 150_000 - cost_b
    else:
        budget_a = 75_000
        budget_b = 75_000

    sec2_lines = [f"Changed files ({len(inventory.changed_files)}):"]
    if inventory.truncated.get("changed_files"):
        sec2_lines.append("(inventory capped at 2,000 entries)")
    if cost_a <= budget_a:
        sec2_lines.extend(inventory.changed_files)
    else:
        chosen_a, rem_a = _format_capped_inventory_lines(inventory.changed_files, budget_a)
        sec2_lines.extend(chosen_a)
        sec2_lines.append(f"(... {rem_a} more not shown: prompt cap 150,000 characters)")
    sec2 = "\n".join(sec2_lines)

    sec3_lines = [f"Tests in the tree ({len(inventory.tests)}):"]
    if inventory.truncated.get("tests"):
        sec3_lines.append("(inventory capped at 2,000 entries)")
    if cost_b <= budget_b:
        sec3_lines.extend(inventory.tests)
    else:
        chosen_b, rem_b = _format_capped_inventory_lines(inventory.tests, budget_b)
        sec3_lines.extend(chosen_b)
        sec3_lines.append(f"(... {rem_b} more not shown: prompt cap 150,000 characters)")
    sec3 = "\n".join(sec3_lines)

    sec4_lines = ["Files changed per task:"]
    for tid in task_order:
        cnt = inventory.task_changed.get(tid)
        if cnt is None:
            sec4_lines.append(f"{tid}: unknown")
        else:
            sec4_lines.append(f"{tid}: {cnt} files changed")
    sec4 = "\n".join(sec4_lines)

    tail = (
        "\nAggregate test output:\n"
        + qa_lines
        + f"\nIntegration diff stat:\n{diff_stat}"
        + f"\nIntegration diff:\n{diff_patch}"
    )

    return "\n".join([sec1, sec2, sec3, sec4]) + tail


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5)."""
    h = hashlib.sha256()
    h.update(b"analyst_prompt_v1")
    rc = cfg.roles.get("analyze") or cfg.roles.get("analyst")
    if rc and rc.model:
        h.update(rc.model.encode("utf-8"))
    return f":analyze:{h.hexdigest()[:16]}"
