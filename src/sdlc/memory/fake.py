"""In-memory Memory implementation — unit-test/CI double, no Hindsight
container required."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..models import RecallSnapshot, RetainItem
from .protocol import Memory
from .query_hash import recall_query_hash


@dataclass
class _Entry:
    text: str
    metadata: dict[str, str]
    version: int


@dataclass
class FakeMemory(Memory):
    """The per-bank entry count IS the watermark: recalling against an
    earlier watermark reproduces an earlier recall even after later
    retains land — the freeze semantics ADR-5 relies on."""

    _entries: dict[str, list[_Entry]] = field(default_factory=lambda: defaultdict(list))

    async def current_watermark(self, bank: str) -> str:
        return str(len(self._entries[bank]))

    async def retain(self, item: RetainItem) -> None:
        bank_entries = self._entries[item.bank]
        bank_entries.append(
            _Entry(text=item.text, metadata=item.metadata, version=len(bank_entries) + 1)
        )

    async def recall(
        self, bank: str, query: str, filters: dict[str, str], watermark: str | None
    ) -> RecallSnapshot:
        cutoff = int(watermark) if watermark is not None else len(self._entries[bank])
        matches = [
            e.text
            for e in self._entries[bank]
            if e.version <= cutoff and all(e.metadata.get(k) == v for k, v in filters.items())
        ]
        query_hash = recall_query_hash(bank, query, filters, str(cutoff))
        return RecallSnapshot(
            query_hash=query_hash, bank=bank, watermark=str(cutoff), items=matches[-10:]
        )

    async def reflect(self, bank: str) -> None:
        return None
