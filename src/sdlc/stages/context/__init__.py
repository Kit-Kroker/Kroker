"""The context stage slice."""

from __future__ import annotations

import importlib
import sys
import types
from typing import TYPE_CHECKING, Any

from .models import BrownfieldDelta

# NOTE: `step`/`build_map` stay lazy re-exports, unlike intake/clarify/code —
# an eager one would pull `temporalio` into light layers that import this
# package without wanting a framework (workflows.scanning ->
# test_operator_layering). Laziness alone is shadowable: the first direct
# import of `stages.context.step` makes the import machinery bind the MODULE
# over the re-exported FUNCTION, and `context.step(...)` then dies with
# "module object is not callable" (first post-B0 brownfield run, 2026-09-12).
# _StageModule below closes that class: the properties always resolve to the
# functions and absorb the machinery's shadowing write.

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


class _StageModule(types.ModuleType):
    """Shadow-proof the lazy `step`/`build_map` re-exports.

    A data descriptor on the module class outranks any instance-dict write,
    so the import machinery's `setattr(package, "step", <submodule>)` is
    absorbed by the setters and reads always resolve to the functions.
    """

    @property
    def step(self):
        from .step import step as _fn

        return _fn

    @step.setter
    def step(self, _shadowed):  # absorbs the machinery's module binding
        pass

    @property
    def build_map(self):
        from .step import build_map as _fn

        return _fn

    @build_map.setter
    def build_map(self, _shadowed):  # absorbs the machinery's module binding
        pass


sys.modules[__name__].__class__ = _StageModule
