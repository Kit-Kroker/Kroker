"""Memory backend abstraction. All access happens in activities
(memory/activities.py) — workflow code never imports this directly."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import RecallSnapshot, RetainItem


class Memory(ABC):
    @abstractmethod
    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot: ...

    @abstractmethod
    async def retain(self, item: RetainItem) -> None: ...

    @abstractmethod
    async def reflect(self, bank: str) -> None: ...

    @abstractmethod
    async def current_watermark(self, bank: str) -> str: ...
