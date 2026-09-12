"""The architecture stage slice."""

from __future__ import annotations

import importlib
import sys
import types
from typing import TYPE_CHECKING, Any

from .models import ArchitectureDecision, ArchitectureSpec, ValidationContract

# NOTE: `step` stays a lazy re-export, unlike intake/clarify/code. An eager
# `from .step import step` sits on the pre-existing benchmarks.models <->
# stages circular import (plan.models imports this package, and
# architecture.step imports clarify, which imports benchmarks.models), so it
# only survives today's worker import order, not a cold one. Laziness alone
# is shadowable (the first direct `stages.architecture.step` import binds
# the MODULE over the re-exported FUNCTION) — _StageModule below closes
# that class.

if TYPE_CHECKING:
    from .activities import ACTIVITIES
    from .prompts import prompt_digest
    from .step import step

__all__ = [
    "ACTIVITIES",
    "ArchitectureDecision",
    "ArchitectureSpec",
    "ValidationContract",
    "prompt_digest",
    "step",
]


def __getattr__(name: str) -> Any:
    if name == "ACTIVITIES":
        mod = importlib.import_module(".activities", __package__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    if name == "step":
        mod = importlib.import_module(".step", __package__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    if name == "prompt_digest":
        mod = importlib.import_module(".prompts", __package__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)


class _StageModule(types.ModuleType):
    """Shadow-proof the lazy `step` re-export (see the NOTE above).

    A data descriptor on the module class outranks any instance-dict write,
    so the import machinery's `setattr(package, "step", <submodule>)` is
    absorbed and reads always resolve to the function.
    """

    @property
    def step(self):
        from .step import step as _fn

        return _fn

    @step.setter
    def step(self, _shadowed):  # absorbs the machinery's module binding
        pass


sys.modules[__name__].__class__ = _StageModule
