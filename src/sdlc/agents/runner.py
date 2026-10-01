"""The worker/replayer plugin Kroker runs (003, T031 mitigation).

Why this exists: pydantic-ai's ``TemporalDurability`` builds pydantic schemas
when it binds to an agent, and ``roles.py`` eagerly constructs all 16 durable
agents at import. Inside Temporal's workflow sandbox that import-plus-bind
exceeds the 2-second deadlock detector (TMPRL1101, first workflow task),
which fails workflow tasks — replay included (research.md R4(d); reproduced
on the migrated tree by ``tests/research`` and ``tests/replay``). The old
``TemporalAgent`` wrapper was fast enough to stay under the budget, so this
module became necessary with the capability migration.

The fix is the plan's sanctioned mitigation: pass ``sdlc.agents`` through
the sandbox instead of re-executing it there. The agents are module-level
constants constructed once, deterministically, before any workflow runs;
the sandbox gains nothing by re-executing them and pays the deadlock
detector for it. Everything else about the runner (isolation of workflow
code, pydantic passthroughs) is inherited from ``PydanticAIPlugin``
unchanged.

FR-021: this module lives under ``src/sdlc/agents/`` and is covered by the
sandbox-module pin in ``tests/durability/test_sandbox_module_marking.py``
(a new module here is a conscious decision recorded in that pin, and the
passthrough below is its marking).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.worker import WorkflowRunner
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

# Modules the workflow sandbox must NOT re-execute. `sdlc.agents` constructs
# the durable agents at import (roles.py); re-executing that construction
# inside a workflow task trips TMPRL1101 (see module docstring).
_PASSTHROUGH = ("sdlc.agents",)


def _warm_workflow_side_imports() -> None:
    """Import, on the HOST, the provider modules the workflow will need.

    TemporalDurability resolves model-id strings inside the workflow
    (FR-020d); the first resolution imports the provider SDK and builds its
    pydantic schemas (~1.9 s for the anthropic SDK, measured in the dev
    container). On the host that is a one-time boot cost; inside a workflow
    task it trips TMPRL1101. Every registry proposer model is
    anthropic:-prefixed today (only harness roles use zai, and harness roles
    are never durable agents) — but 004 forwards proposer overrides to any
    constructible provider, so a run with an ``openai:``/``google:`` override
    resolves that provider workflow-side (E4). Warm the openai and google
    provider modules too; a provider whose extra is absent stays cold and
    its first import inside a task is the override's own cost. Failure is
    swallowed per module: warm-up is an optimization, never a boot gate.
    """
    for module in ("anthropic", "openai", "google.genai"):
        try:
            importlib.import_module(module)
        except Exception:  # noqa: BLE001 -- boot must not depend on warm-up
            pass


class SdlcPydanticAIPlugin(PydanticAIPlugin):
    """PydanticAIPlugin with sdlc.agents passed through the workflow sandbox."""

    def __init__(self) -> None:
        super().__init__()
        _warm_workflow_side_imports()
        # The base plugin stores a (runner|None) -> runner callable that
        # installs its passthroughs on temporalio's default sandboxed runner;
        # wrap it so ours extends the same restrictions rather than replacing
        # them. Unsandboxed runners pass through the wrapper untouched. The
        # getattr deliberately hides the attribute from mypy: SimplePlugin's
        # workflow_runner is a parameter alias (value | callable) whose type
        # the pre-commit staged-file hook cannot resolve, and getattr returns
        # Any which the cast then anchors to the callable shape. noqa because
        # B009's auto-fix would restore the direct attribute read mypy
        # rejects in staged-file mode.
        base: Callable[[WorkflowRunner | None], WorkflowRunner] = cast(
            "Callable[[WorkflowRunner | None], WorkflowRunner]",
            getattr(self, "workflow_runner"),  # noqa: B009 -- see comment above
        )

        def _extended(runner: WorkflowRunner | None) -> WorkflowRunner:
            resolved = base(runner)
            if isinstance(resolved, SandboxedWorkflowRunner):
                resolved = replace(
                    resolved,
                    restrictions=resolved.restrictions.with_passthrough_modules(*_PASSTHROUGH),
                )
            return resolved

        self.workflow_runner = _extended
