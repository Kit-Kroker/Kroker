"""Every stage package's `step` re-export must resolve to the function.

A direct import of `sdlc.stages.<stage>.step` binds the submodule as an
attribute of its parent package. Where the package re-exports the step
FUNCTION only lazily (TYPE_CHECKING + __getattr__), that attribute wins
and `stage.step(...)` dies with TypeError: 'module' object is not callable
— in real wiring only, which is why the fast tier alone never caught it
(found on the first post-B0 brownfield run, 2026-09-12).

Packages that keep the lazy re-export on purpose — an eager one sits on
the benchmarks.models <-> stages circular import or pulls temporalio into
light layers — shadow-proof it with a module-class property instead (see
the NOTE in their __init__.py). This file pins the property: even with
the submodule imported first, the package attribute stays the function.

020 T027: architecture and plan LEFT this set — their `step` composites
are deleted with FeatureWorkflow, so the package attribute is the
submodule on purpose. For them the pin is the opposite: the attribute is
a module and exports no callable `step`.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

# Mimic the worker's import order: benchmarks.models loads before any stage
# slice. (A cold stages-first import trips a pre-existing circular import
# between benchmarks.models and stages.clarify.step — this file tests the
# shadowing bug, not that cycle.)
import sdlc.benchmarks.models  # noqa: F401

STAGES = [
    "analyze",
    "clarify",
    "code",
    "context",
    "deploy",
    "intake",
    "merge",
    "research",
    "retro",
    "review",
]

# 020 T027: the composite is gone; the submodule IS the surface.
COMPOSITE_GONE = ["architecture", "plan"]


@pytest.mark.parametrize("stage", STAGES)
def test_step_is_the_function_even_when_the_submodule_is_imported_first(
    stage: str,
) -> None:
    package = importlib.import_module(f"sdlc.stages.{stage}")
    # Simulate any other slice importing the submodule directly first.
    importlib.import_module(f"sdlc.stages.{stage}.step")
    step = package.step
    assert callable(step), (
        f"sdlc.stages.{stage}.step resolved to {type(step).__name__}, "
        "not the step function — the lazy re-export was shadowed"
    )


@pytest.mark.parametrize("stage", COMPOSITE_GONE)
def test_the_composite_is_gone_and_the_submodule_is_the_surface(stage: str) -> None:
    package = importlib.import_module(f"sdlc.stages.{stage}")
    importlib.import_module(f"sdlc.stages.{stage}.step")
    step = package.step
    assert inspect.ismodule(step), (
        f"sdlc.stages.{stage}.step should be the submodule (the 020 T027 "
        f"deletion removed the composite function), got {type(step).__name__}"
    )
    assert not hasattr(step, "step") or not callable(getattr(step, "step", None)), (
        f"sdlc.stages.{stage}.step.step must not exist — the composite is deleted"
    )
    assert not hasattr(package, "_StageModule"), "the shadow-proof module class is deleted"


def test_context_build_map_is_the_function_even_when_shadowed() -> None:
    import sdlc.stages.context as context

    importlib.import_module("sdlc.stages.context.step")
    assert callable(context.build_map)
    assert inspect.iscoroutinefunction(context.step)
