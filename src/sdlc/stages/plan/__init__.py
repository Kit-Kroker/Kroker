"""The plan stage slice."""

from __future__ import annotations

import importlib
import sys
import types
from typing import TYPE_CHECKING, Any

from .models import (
    DevTask,
    ImplementationPlan,
    PlanDeviation,
    PlanDrift,
    compute_plan_drift,
)

if TYPE_CHECKING:
    from .activities import ACTIVITIES
    from .prompts import prompt_digest
    from .step import step

# NOTE: `step` stays a lazy re-export here, unlike intake/clarify/code.
# An eager `from .step import step` lands inside the pre-existing
# benchmarks.models <-> stages circular import (benchmarks.models:22 imports
# this package for PlanDrift), which only works today because benchmarks
# completes before any stage slice loads. Laziness alone is shadowable (the
# first direct `stages.plan.step` import binds the MODULE over the
# re-exported FUNCTION) — _StageModule below closes that class.

__all__ = [
    "ACTIVITIES",
    "DevTask",
    "ImplementationPlan",
    "PlanDeviation",
    "PlanDrift",
    "compute_plan_drift",
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
