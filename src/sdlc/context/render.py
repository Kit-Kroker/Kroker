"""E-84 D12: the Architect's view of the map.

ARCHITECTURE.md:169-171 requires this in as many words -- high-volume
exploration "uses programmatic access -- tools that filter and extract --
rather than streaming the corpus through the context window" -- and FR-801
enforces a per-role context_budget_tokens at prompt assembly regardless.

Truncation is deterministic because an unstable rendering would make the
architect memo key unstable and NFR-10's reproducibility claim false. The
input is already totally sorted by project(); this only cuts.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..measurement import CollectionState, Measurement
from .models import CodebaseMap


def _section(title: str, rows: Sequence[str], collected: Measurement,
             limit: int) -> list[str]:
    if collected.state is not CollectionState.MEASURED:
        return [f"{title}: {collected.state.value} -- {collected.reason}"]
    if not rows:
        return [f"{title}: none found"]
    shown = list(rows[:limit])
    out = [f"{title} ({len(rows)}):"]
    out.extend(f"  - {r}" for r in shown)
    if len(rows) > limit:
        out.append(f"  … {len(rows) - limit} more")
    return out


def render_for_prompt(m: CodebaseMap, *, max_modules: int = 40,
                      max_contracts: int = 60,
                      max_hot_spots: int = 25) -> str:
    lines = [f"CodebaseMap at commit {m.commit_sha[:12]} "
             f"(tree {m.tree_hash[:12]})"]
    lines += _section(
        "modules",
        [f"{x.name} [{x.confidence.value}] "
         f"{', '.join(x.member_paths[:5])}" for x in m.modules],
        m.modules_collected, max_modules)
    lines += _section(
        "contracts",
        [f"{x.kind.value} {x.value} ({x.path}"
         f"{':' + str(x.line) if x.line else ''})" for x in m.contracts],
        m.contracts_collected, max_contracts)
    lines += _section(
        "hot spots",
        [f"{x.path} [{x.source}] {x.reason}" for x in m.hot_spots],
        m.hot_spots_collected, max_hot_spots)
    return "\n".join(lines)
