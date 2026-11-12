"""The requirements stage slice (FR-113).

Eager exports none: `requirements.models` is imported by the downstream
step (clarify) as a submodule, so the package init drags nothing heavy into
that chain. `ACTIVITIES` re-exports lazily (the constitution slice
pattern); the worker reaches it through STAGE_MODULES, which resolves the
attribute after boot. `step` the function stays on its submodule (the
architecture/plan rule: a package attribute named `step` is shadowed by
the submodule the moment anyone imports it).
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["ACTIVITIES", "draft_requirements"]


def __getattr__(name: str) -> Any:
    if name in ("ACTIVITIES", "draft_requirements"):
        mod = importlib.import_module(".stage", __package__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
