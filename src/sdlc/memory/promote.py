"""Cross-project gotcha promotion grouping (E-25).

Pure logic, no I/O: the nightly reflect job recalls gotchas per project bank
and promotes the ones that recur across projects into the `org` bank. Prior
art (agent-architecture plan) rules what belongs there: the org bank holds
only *stack knowledge* recurring in 2+ projects; project-specific facts stay
project-side. Task 3 wraps this in a Temporal activity. Recall-window cap:
only each bank's most recently recalled gotchas are considered (the recall
window — `RECALL_KEEP = 10` in hindsight_client.py, `[-10:]` in the fake),
so a gotcha outside that window is never considered; revisit when a real
bank hits the cap.

Spec: docs/superpowers/specs/2026-11-19-org-bank-promotion-design.md
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from .models import MemoryKind, RetainItem

GOTCHA_QUERY = "recurring cross-project gotchas and stack knowledge"


def normalize_gotcha(text: str) -> str:
    """Canonical grouping key: lowercase, punctuation -> space, collapse, strip.

    One pass handles both the non-alphanumeric strip and the whitespace
    collapse: every run of non-`[a-z0-9]` characters becomes a single space.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def promotions(
    items_by_bank: Mapping[str, Sequence[str]], *, org_bank: str, min_projects: int = 2
) -> list[RetainItem]:
    """Group gotchas by normalized text; groups spanning enough banks promote.

    Deterministic: groups are keyed by `normalize_gotcha(text)`, the
    representative is the lexicographically smallest raw text in the group,
    `promoted_from` lists banks sorted, and the result is sorted by `text`.
    """
    # normalized text -> (distinct banks holding it, raw texts seen)
    groups: dict[str, tuple[set[str], list[str]]] = {}
    for bank, items in items_by_bank.items():
        for text in items:
            banks, raws = groups.setdefault(normalize_gotcha(text), (set(), []))
            banks.add(bank)
            raws.append(text)

    return sorted(
        (
            RetainItem(
                kind=MemoryKind.GOTCHA,
                bank=org_bank,
                text=min(raws),
                metadata={"promoted_from": ",".join(sorted(banks))},
            )
            for banks, raws in groups.values()
            if len(banks) >= min_projects
        ),
        key=lambda item: item.text,
    )
