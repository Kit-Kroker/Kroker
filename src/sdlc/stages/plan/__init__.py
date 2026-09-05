"""The plan stage slice."""

from __future__ import annotations

import importlib
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
