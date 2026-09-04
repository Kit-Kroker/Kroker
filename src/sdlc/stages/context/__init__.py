"""The context stage slice."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from .models import BrownfieldDelta

if TYPE_CHECKING:
    from .activities import (
        ACTIVITIES,
        DeltaCheckInput,
        RepoProbeInput,
        check_brownfield_delta,
        classify_repo,
    )
    from .prompts import prompt_digest
    from .step import build_map, step

__all__ = [
    "ACTIVITIES",
    "BrownfieldDelta",
    "DeltaCheckInput",
    "RepoProbeInput",
    "build_map",
    "check_brownfield_delta",
    "classify_repo",
    "prompt_digest",
    "step",
]


def __getattr__(name: str) -> Any:
    if name in (
        "ACTIVITIES",
        "DeltaCheckInput",
        "RepoProbeInput",
        "check_brownfield_delta",
        "classify_repo",
    ):
        mod = importlib.import_module(".activities", __package__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    if name in ("step", "build_map"):
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
