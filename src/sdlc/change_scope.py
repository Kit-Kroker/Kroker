"""DS3 (diff-scoped merge gates): two-point multiset difference.

A finding's identity is (tool, rule, path, normalized source line) — never a
line number, which moves whenever anything above it changes. Multiset, not
set: a second identical finding in one file is introduced. Base paths are
mapped through the change's renames before comparison.

Pure: standard library only. The qa and merge slices both consume it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import TypeVar

T = TypeVar("T")

# (tool, rule, path, line). Callers return components already normalized with
# normalize_path / normalize_line.
FindingKey = tuple[str, str, str, str]


def normalize_path(path: str) -> str:
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def normalize_line(text: str) -> str:
    return " ".join(text.split())


def rename_map(renames: Sequence[Sequence[str]]) -> dict[str, str]:
    return {normalize_path(old): normalize_path(new) for old, new in renames}


def delta(
    base: Sequence[T],
    head: Sequence[T],
    key: Callable[[T], FindingKey],
    renames: Mapping[str, str],
) -> tuple[list[T], int, int]:
    """Return (introduced head items, pre-existing count, resolved count)."""

    def base_key(item: T) -> FindingKey:
        tool, rule, path, line = key(item)
        return (tool, rule, renames.get(path, path), line)

    base_counts = Counter(base_key(b) for b in base)
    by_key: dict[FindingKey, list[T]] = {}
    for h in head:
        by_key.setdefault(key(h), []).append(h)

    introduced: list[T] = []
    preexisting = 0
    for k in sorted(by_key):
        items = sorted(by_key[k], key=repr)
        kept = min(len(items), base_counts.get(k, 0))
        preexisting += kept
        introduced.extend(items[kept:])
    resolved = sum(max(0, n - len(by_key.get(k, []))) for k, n in base_counts.items())
    return introduced, preexisting, resolved
