"""Shared validators library (FR-205): pure checks, evidence schemas, plus
the tree-reading activity.

The pure functions import eagerly -- workflow code can take them from here
or from `sdlc.validators.pure` directly -- and so do the evidence schemas
(evidence.py, the ADR-24 handoff): plain Pydantic, nothing behind them.
ACTIVITIES is a lazy export (PEP 562): its home, activities.py, imports
temporalio at top level, so fetching it only when a registration site asks
keeps `import sdlc.validators.pure` free of temporalio (the purity pin in
tests/validators/test_pure.py).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from .evidence import (
    AssertionEvidence,
    Coverage,
    Finding,
)
from .pure import (
    covers_all,
    dag_acyclic,
    deps_resolve,
    ids_unique,
    path_like_tokens,
    task_size,
    validate_task_graph,
)

if TYPE_CHECKING:
    from .activities import ACTIVITIES

__all__ = [
    "ACTIVITIES",
    "AssertionEvidence",
    "Coverage",
    "Finding",
    "covers_all",
    "dag_acyclic",
    "deps_resolve",
    "ids_unique",
    "path_like_tokens",
    "task_size",
    "validate_task_graph",
]


def __getattr__(name: str) -> Any:
    if name == "ACTIVITIES":
        mod = importlib.import_module(".activities", __package__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
