"""T004 (plan T011): operator runtime seam.

RED until src/sdlc/operator/runtime.py exists.
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_import_loads_no_web_agent_or_worker_modules():
    probe = (
        "import sys, sdlc.operator.runtime; "
        "bad = [m for m in ('fastapi', 'starlette', 'pydantic_ai', "
        "'sdlc.worker', 'sdlc.workflows.graph') if m in sys.modules]; "
        "print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""


def test_operator_deps_binds_board_actor_and_starter():
    from sdlc.board.store import BoardStore
    from sdlc.operator import runtime

    poller = SimpleNamespace(_client_or_connect=None)
    deps = runtime.operator_deps(poller, "chat:local")

    assert deps.board is BoardStore
    assert deps.actor == "chat:local"
    assert callable(deps.starter)
    assert deps.poller is poller


@pytest.mark.asyncio
async def test_start_graph_calls_start_graph_run_with_graph_workflow(monkeypatch):
    from sdlc.operator import runtime
    from sdlc.task_queue import TASK_QUEUE

    calls: dict = {}

    async def fake_client_or_connect():
        return "CLIENT"

    async def fake_start_graph_run(client, run, run_input, **kwargs):
        calls["client"] = client
        calls["run"] = run
        calls["run_input"] = run_input
        calls.update(kwargs)
        return SimpleNamespace(id="wf-42")

    def fake_build_run_input(*args, **kwargs):
        return ("RUN_INPUT", args, kwargs)

    poller = SimpleNamespace(_client_or_connect=fake_client_or_connect)
    monkeypatch.setattr(runtime, "start_graph_run", fake_start_graph_run)
    monkeypatch.setattr(runtime, "build_run_input", fake_build_run_input, raising=False)

    returned = await runtime.start_graph(poller, "an idea", object(), "wf-42")

    assert returned == "wf-42"
    assert calls["client"] == "CLIENT"
    assert calls["run"] == "GraphWorkflow"
    assert calls["task_queue"] == TASK_QUEUE
    assert calls["id"] == "wf-42"


def test_graph_workflow_registered_name_is_graph_workflow():
    from temporalio.workflow import _Definition

    from sdlc.workflows.graph import GraphWorkflow

    assert _Definition.from_class(GraphWorkflow).name == "GraphWorkflow"
