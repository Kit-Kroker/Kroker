"""The review stage slice."""

from __future__ import annotations

import sys
import types

from .activities import ACTIVITIES
from .lenses import (
    GATING_LENSES,
    LensOutcome,
    LensPresence,
    backstop_admits,
    classify_lens,
    primary_admits,
)
from .models import DeepReviewReport, ReviewFinding, ReviewReport
from .step import run_adversary, run_deep_review, step

__all__ = [
    "ACTIVITIES",
    "DeepReviewReport",
    "GATING_LENSES",
    "LensOutcome",
    "LensPresence",
    "ReviewFinding",
    "ReviewReport",
    "backstop_admits",
    "classify_lens",
    "primary_admits",
    "run_adversary",
    "run_deep_review",
    "step",
]


class _StageModule(types.ModuleType):
    """Shadow-proof the `step` re-export (inbox card 2026-09-12-b0-lazy-step-export-shadowing).

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
