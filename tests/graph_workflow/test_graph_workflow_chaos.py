"""Chaos + edge-case characterization for E-74 Task 19 (GraphWorkflow + boot).

RED until ``sdlc.workflows.graph.GraphWorkflow`` and
``sdlc.worker.graph_boot_problems`` exist: every test fetches them through
``_graph()`` / ``_boot()``, so each test fails on its own with an ImportError
-- the plan's expected RED reason -- while the file still collects.

Pins the edge behaviour the task specifies:
- an INVALID graph (from_graph raises InvalidGraph) becomes ApplicationError
  "invalid graph: ..." with non_retryable=True; the raise happens BEFORE the
  first workflow-context call, so it is tested on a bare instance
- a NON-EXECUTABLE graph (executable() problems) becomes ApplicationError
  "graph not executable: <problems joined>" with non_retryable=True
- a stored_failure in the dispatcher outcome is RE-RAISED unchanged (not
  wrapped, not an ApplicationError) and retro never runs (U9); a healthy
  completed run DOES run retro and returns "completed:"
- the memory watermark truth table: memory enabled with no preset watermark
  captures once via the capture_watermark activity and threads the captured
  value into the dispatcher's facts; a watermark preset in cfg.memory wins
  WITHOUT an activity call; memory disabled captures nothing (facts carry
  the host's None default). The workflow module-global is faked so run()
  completes outside Temporal; the dispatcher is a stub returning a
  completed outcome
- graph_boot_problems: healthy boot is empty; a MISSING handler, an
  UNEXPECTED extra handler and check_node_types problems all surface
- a bare GraphWorkflow answers run_state() and run_summary() with None
"""

from __future__ import annotations

import asyncio
from types import MappingProxyType, SimpleNamespace

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.core.models import PipelineConfig
from sdlc.graph import NODE_TYPES, PipelineGraph
from sdlc.graph.router import RouterState
from sdlc.memory.activities import WatermarkInput, capture_watermark
from sdlc.workflows.graph_catalog import NOT_EXECUTABLE, SHIPPED, ExecutableProblem
from sdlc.workflows.graph_dispatch import DispatchOutcome
from sdlc.workflows.graph_nodes import HANDLERS
from sdlc.workflows.models import GraphRunInput
from tests.fakes.canned import greenfield_idea
from tests.graph.fixtures.registries import roles


def _graph():
    from sdlc.workflows.graph import GraphWorkflow

    return GraphWorkflow


def _graph_module():
    import sdlc.workflows.graph as graph_module

    return graph_module


def _boot():
    from sdlc.worker import graph_boot_problems

    return graph_boot_problems


def _patch_dispatcher(monkeypatch, gm, *, stored=None):
    """GraphDispatcher stub recording its kwargs; run() yields a completed outcome."""
    instances: list[dict] = []

    class _Stub:
        def __init__(self, **kw):
            self.kw = kw
            instances.append(kw)

        async def run(self):
            return DispatchOutcome(
                state=RouterState(nodes={}, outcome="completed"),
                terminal_result=None,
                last_sink_result=None,
                budget_halted=False,
                stored_failure=stored,
            )

    monkeypatch.setattr(gm, "GraphDispatcher", _Stub)
    return instances


def _patch_workflow_module(monkeypatch, gm, *, activity=None):
    """Replace graph.py's workflow global so run() completes outside Temporal."""
    calls: list[tuple[object, object]] = []

    async def default_activity(fn, arg, **kw):
        calls.append((fn, arg))
        return "captured-wm"

    fake = SimpleNamespace(
        now=lambda: "t0",
        info=lambda: SimpleNamespace(workflow_id="wf-42"),
        execute_activity=activity or default_activity,
    )
    monkeypatch.setattr(gm, "workflow", fake)
    return calls


def _no_retro(rec):
    async def retro(cfg, idea, result):
        rec.append(result)

    return retro


def _inp(graph=None, cfg=None):
    return GraphRunInput(
        idea=greenfield_idea(),
        cfg=cfg or PipelineConfig(),
        graph=graph or SHIPPED["default"],
        roles=dict(roles()),
    )


# ---- run(): invalid and non-executable graphs ----------------------------------


def test_run_rejects_an_invalid_graph_as_non_retryable():
    bad = PipelineGraph(schema_version=1, nodes=[{"id": "x", "type": "nope"}], edges=[])

    with pytest.raises(ApplicationError) as err:
        asyncio.run(_graph()().run(_inp(graph=bad)))

    assert err.value.non_retryable is True
    assert err.value.message.startswith("invalid graph:")


def test_run_rejects_a_non_executable_graph_as_non_retryable(monkeypatch):
    gm = _graph_module()
    monkeypatch.setattr(
        gm,
        "executable",
        lambda g, h: (
            ExecutableProblem(code="no_handler", node="x", message="no handler for node type 'x'"),
        ),
    )

    with pytest.raises(ApplicationError) as err:
        asyncio.run(_graph()().run(_inp()))

    assert err.value.non_retryable is True
    assert err.value.message == "graph not executable: no handler for node type 'x'"


# ---- run(): a stored failure is re-raised, retro skipped -------------------------


def test_run_reraises_a_stored_failure_directly_and_skips_retro(monkeypatch):
    gm = _graph_module()
    boom = RuntimeError("unrouted failure")
    _patch_workflow_module(monkeypatch, gm)
    _patch_dispatcher(monkeypatch, gm, stored=boom)
    monkeypatch.setattr(gm, "executable", lambda g, h: ())
    wf = _graph()()
    retro_calls: list[str] = []
    wf._retro = _no_retro(retro_calls)

    with pytest.raises(RuntimeError) as err:
        asyncio.run(wf.run(_inp()))

    assert err.value is boom  # the ORIGINAL exception, not an ApplicationError
    assert not isinstance(err.value, ApplicationError)
    assert retro_calls == []  # U9: a crashed run never runs retro


# ---- run(): the memory watermark truth table --------------------------------------


def test_watermark_is_captured_when_memory_is_enabled(monkeypatch):
    gm = _graph_module()
    cfg = PipelineConfig()
    cfg.memory.enabled = True
    calls = _patch_workflow_module(monkeypatch, gm)
    instances = _patch_dispatcher(monkeypatch, gm)
    wf = _graph()()
    retro_calls: list[str] = []
    wf._retro = _no_retro(retro_calls)

    result = asyncio.run(wf.run(_inp(cfg=cfg)))

    assert [(fn, arg.bank, arg.backend) for fn, arg in calls] == [
        (capture_watermark, "project:default", cfg.memory.backend)
    ]
    assert isinstance(calls[0][1], WatermarkInput)
    assert instances[0]["facts"].memory_watermark == "captured-wm"
    assert instances[0]["facts"].run_id == "wf-42"
    assert result == "completed:"  # completed with no sinks: the empty suffix
    assert retro_calls == ["completed:"]  # a healthy run DOES run retro


def test_watermark_preset_in_cfg_skips_the_capture(monkeypatch):
    gm = _graph_module()

    async def no_activity(fn, arg, **kw):
        raise AssertionError("no capture when cfg.memory.watermark is preset")

    cfg = PipelineConfig()
    cfg.memory.enabled = True
    cfg.memory.watermark = "wm-x"
    _patch_workflow_module(monkeypatch, gm, activity=no_activity)
    instances = _patch_dispatcher(monkeypatch, gm)
    wf = _graph()()
    wf._retro = _no_retro([])

    asyncio.run(wf.run(_inp(cfg=cfg)))

    assert instances[0]["facts"].memory_watermark == "wm-x"


def test_watermark_is_skipped_when_memory_is_disabled(monkeypatch):
    gm = _graph_module()

    async def no_activity(fn, arg, **kw):
        raise AssertionError("no capture when memory is disabled")

    cfg = PipelineConfig()  # memory.enabled defaults to False
    _patch_workflow_module(monkeypatch, gm, activity=no_activity)
    instances = _patch_dispatcher(monkeypatch, gm)
    wf = _graph()()
    wf._retro = _no_retro([])

    asyncio.run(wf.run(_inp(cfg=cfg)))

    assert instances[0]["facts"].memory_watermark is None  # the host default


# ---- worker boot checks ------------------------------------------------------------


def test_boot_checks_are_healthy():
    assert _boot()() == []


def test_boot_flags_a_missing_handler(monkeypatch):
    boot = _boot()
    import sdlc.workflows.graph_nodes as gn_module

    reduced = {k: v for k, v in HANDLERS.items() if k != "deploy"}
    monkeypatch.setattr(gn_module, "HANDLERS", MappingProxyType(reduced))
    covered = sorted({*reduced, *NOT_EXECUTABLE})

    problems = boot()

    assert problems == [
        f"handler coverage mismatch: registry {sorted(NODE_TYPES)} vs handled {covered}"
    ]


def test_boot_flags_an_unexpected_extra_handler(monkeypatch):
    boot = _boot()
    import sdlc.workflows.graph_nodes as gn_module

    extra = {**HANDLERS, "ghost.type": lambda nc, act, cfg: None}
    monkeypatch.setattr(gn_module, "HANDLERS", MappingProxyType(extra))
    covered = sorted({*extra, *NOT_EXECUTABLE})

    problems = boot()

    assert problems == [
        f"handler coverage mismatch: registry {sorted(NODE_TYPES)} vs handled {covered}"
    ]


def test_boot_surfaces_check_node_types_problems(monkeypatch):
    boot = _boot()
    import sdlc.graph.node_types as nt_module

    monkeypatch.setattr(nt_module, "check_node_types", lambda registry=None: ["boom problem"])

    assert boot() == ["boom problem"]


# ---- bare instance queries -----------------------------------------------------------


def test_bare_instance_queries_return_none():
    wf = _graph()()

    assert wf.run_state() is None
    assert wf.run_summary() is None
