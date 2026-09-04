"""The pipeline's vertical slices.

STAGE_MODULES is explicit and ordered, never auto-discovered: registration
must stay deterministic and greppable, and there must be exactly one place to
edit when a stage is added. Entries appear here as their slice migrates.

Rule: adding a module to STAGE_MODULES and deleting its worker.py import
are one edit, never two.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

    STAGE_MODULES: tuple[ModuleType, ...]


def __getattr__(name: str) -> Any:
    if name == "STAGE_MODULES":
        from . import analyze, clarify, context, intake, qa, research, retro, review

        return (clarify, intake, qa, retro, analyze, research, review, context)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return ["STAGE_MODULES"]
