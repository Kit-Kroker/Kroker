"""The constitution stage slice (FR-112).

Eager model exports only: `constitution.models` is imported by the
downstream steps (clarify/architecture/plan), so the package init must not
drag step.py — and with it agents.roles' registry load — into that chain.
`ACTIVITIES` re-exports lazily (the architecture/plan slice pattern); the
worker reaches it through STAGE_MODULES, which resolves the attribute after
boot. `step` the function stays on its submodule (`from
sdlc.stages.constitution.step import step`, the handler's import) — the
architecture/plan rule: a package attribute named `step` is shadowed by
the submodule the moment anyone imports it.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from .models import (
    Constitution,
    DraftOutput,
    DraftPrinciple,
    Principle,
    constitution_digest,
)

if TYPE_CHECKING:
    from .stage import draft_constitution  # noqa: F401 - re-exported lazily below

__all__ = [
    "ACTIVITIES",
    "Constitution",
    "DraftOutput",
    "DraftPrinciple",
    "Principle",
    "constitution_digest",
    "draft_constitution",
]


def __getattr__(name: str) -> Any:
    if name in ("ACTIVITIES", "draft_constitution"):
        mod = importlib.import_module(".stage", __package__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
