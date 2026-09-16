"""Regression for SG-5: ``sdlc.stages.review.step`` must stay a callable function.

``review/__init__.py`` exports the ``step`` coroutine from the submodule
``sdlc/stages/review/step.py`` -- and the submodule stays importable. The
replay import chain (importing ``sdlc.stages.code.step``, then running a
recorded history through the sandboxed temporal ``Replayer``) re-resolves the
workflow-local ``from ..review.step import ...`` imports (code/step.py 507 et
al); the import system then binds the SUBMODULE onto the parent package,
clobbering the function export. Any later
``from sdlc.stages.review import step`` binds a module, and calling it raises
``TypeError: 'module' object is not callable``.

Probed (fresh interpreter): a plain package import, ``import
sdlc.stages.code.step``, a ``from sdlc.stages.review.step import step`` and
``importlib.import_module("sdlc.stages.review.step")`` all leave the function
intact -- only the sandboxed replay reproduces the clobber. So every test
here runs the real trigger chain, and reads the attribute THROUGH the package
at assertion time: a module-level ``from sdlc.stages.review import step``
would bind the function before the clobber and pass for the wrong reason.

Replay SUCCESS is not this file's business (SG-2 owns that in
tests/replay/test_feature_replay.py) -- the replay is only the trigger; the
assertions below pin the shadowing invariant.
"""

from __future__ import annotations

import importlib
import inspect

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer

import sdlc.stages.review as review_pkg
from sdlc.workflows.crew import CrewTaskWorkflow
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from tests.replay.harness import load_history


def _replay_chain() -> Replayer:
    return Replayer(
        workflows=[FeatureWorkflow, DeploymentWorkflow, CrewTaskWorkflow],
        data_converter=pydantic_data_converter,
        plugins=[PydanticAIPlugin()],
    )


async def _replay_greenfield_happy() -> None:
    """The SG-5 trigger: import the code.step module, then replay one full
    recorded FeatureWorkflow history through the production-shaped (sandboxed)
    Replayer -- the same recipe tests/replay/test_feature_replay.py uses."""
    import sdlc.stages.code.step  # noqa: F401  (the step.py:507 chain)

    await _replay_chain().replay_workflow(load_history("greenfield_happy"))


@pytest.mark.asyncio
async def test_review_step_stays_callable_after_code_step_import_and_replay():
    await _replay_greenfield_happy()

    current = review_pkg.step
    assert inspect.isfunction(current), (
        f"sdlc.stages.review.step was clobbered to {type(current).__name__}"
    )
    assert current.__module__ == "sdlc.stages.review.step"


@pytest.mark.asyncio
async def test_inspect_signature_works_on_review_step_after_replay():
    await _replay_greenfield_happy()

    current = review_pkg.step
    assert inspect.isfunction(current), (
        f"sdlc.stages.review.step was clobbered to {type(current).__name__}"
    )

    signature = inspect.signature(current)
    assert list(signature.parameters) == [
        "ctx",
        "cfg",
        "task",
        "contract",
        "diff",
        "worktree",
        "reviewer_agent",
        "adversary_agent",
        "deep_review_agent",
        "qa_raw",
        "reviewer_model",
        "attempt",
        "started",
        "run",
    ]
    kinds = {name: param.kind for name, param in signature.parameters.items()}
    assert kinds["ctx"] == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(kind == inspect.Parameter.KEYWORD_ONLY for kind in list(kinds.values())[1:])


@pytest.mark.asyncio
async def test_function_export_and_submodule_import_coexist_after_replay():
    await _replay_greenfield_happy()

    submodule = importlib.import_module("sdlc.stages.review.step")
    current = review_pkg.step

    assert inspect.isfunction(current), (
        f"sdlc.stages.review.step was clobbered to {type(current).__name__}"
    )
    # the function LIVES in that submodule: both identities coexist
    assert current is submodule.step
    assert current.__module__ == submodule.__name__ == "sdlc.stages.review.step"
