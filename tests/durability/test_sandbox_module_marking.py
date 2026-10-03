"""FR-021 sandbox-marking guard for src/sdlc/agents/ (T045).

The known trap: a NEW module under src/sdlc/agents/ is imported by a
workflow INSIDE the Temporal sandbox, which re-executes it — pydantic
classes get defined a second time under a mangled module and cross-boundary
validation dies with `ValidationError ... input_type == <class name>`. The
mitigation is sandbox marking (passthrough), and this file pins the two
halves of that decision: the module set under src/sdlc/agents/ stays at
its pinned, consciously-marked membership, and the worker's sandbox really
does pass pydantic_ai through (which keeps TemporalDurability's own classes
single-defined while roles.py imports them at module level inside
workflows).

NOT red-first: this guards the current correct state and must be green
immediately. A new module (e.g. src/sdlc/agents/durability.py) must update
the pin in the same change that creates it.
"""

from pathlib import Path

from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.workflows.crew import CrewTaskWorkflow
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow

# tests/durability/ -> repo root, two levels up.
_AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "sdlc" / "agents"

# The sandbox-marking decision, frozen: every module that lives here is
# either executed inside workflows knowingly (loader/roles/settings are
# imported by workflow code and are safe under the pydantic_ai passthrough)
# or is package glue. `runner` (T031 mitigation) is PASSED THROUGH the
# sandbox wholesale by SdlcPydanticAIPlugin together with the rest of
# sdlc.agents, so it never sandbox-executes at all. Adding a module without
# editing this set is exactly the un-marked-module defect FR-021 guards
# against.
_PINNED_MODULES = {
    "__init__",
    "loader",
    "model_ids",
    "payload_guard",
    "roles",
    "runner",
    "settings",
}


def test_no_unpinned_modules_under_agents():
    """Every .py module directly under src/sdlc/agents/ is accounted for by
    the pin: a new file appearing here means a new sandbox-executed module
    whose marking nobody decided."""
    found = {p.stem for p in _AGENTS_DIR.glob("*.py")}
    assert found == _PINNED_MODULES, (
        f"src/sdlc/agents/ module set changed: new {sorted(found - _PINNED_MODULES)}, "
        f"removed {sorted(_PINNED_MODULES - found)}. A new module under src/sdlc/agents/ "
        "is imported inside the workflow sandbox and must be marked for it "
        "(pydantic class duplication trap) — make that decision and update "
        "_PINNED_MODULES in the same change."
    )


def test_workflow_runner_still_passes_through_pydantic_ai():
    """The replayer's worker config (same construction as the production
    worker effect) sandboxes workflows AND passes pydantic_ai through — the
    mechanism that keeps roles.py's module-level
    pydantic_ai.durable_exec.temporal import from duplicating classes
    inside the sandbox — and sdlc.agents through (T031's deadlock
    mitigation: roles.py's eager agent construction must not re-execute
    inside a workflow task, TMPRL1101)."""
    config = Replayer(
        workflows=[FeatureWorkflow, DeploymentWorkflow, CrewTaskWorkflow],
        data_converter=pydantic_data_converter,
        plugins=[SdlcPydanticAIPlugin()],
    ).config(active_config=True)

    runner = config["workflow_runner"]
    assert isinstance(runner, SandboxedWorkflowRunner)
    assert "pydantic_ai" in runner.restrictions.passthrough_modules
    assert "sdlc.agents" in runner.restrictions.passthrough_modules
