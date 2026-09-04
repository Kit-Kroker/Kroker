"""Activities for the clarify stage.

The clarify stage executes proposer agents via StageContext.run_role; cache
activities belong to memoization and question waiting is handled via signals in
StageContext.ask_and_wait. Clarify owns no worker-registered Temporal activities
directly, so ACTIVITIES is empty.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ACTIVITIES: list[Callable[..., Any]] = []
