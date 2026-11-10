"""E-74 §5.7, re-cast 020 T026: GraphWorkflow's HITL surface as a frozen name set.

FeatureWorkflow is deleted (020 T025). The surface is pinned by exact name
sets, so any addition or removal is a deliberate change to this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

from temporalio.workflow import _Definition

from sdlc.worker import graph_boot_problems
from sdlc.workflows.gates import GateHost
from sdlc.workflows.graph import GraphWorkflow
from sdlc.workflows.run_host import RunHost


def test_graph_workflow_serves_the_frozen_hitl_surface():
    g = _Definition.must_from_class(GraphWorkflow)
    assert set(g.queries) == {
        "graph_view",
        "pending_decisions",
        "pending_gate",
        "run_state",
        "run_summary",
        "status",
    }
    assert set(g.signals) == {"answer_question", "submit_gate_decision"}


def test_run_host_precedes_gate_host():
    mro = GraphWorkflow.__mro__
    assert mro.index(RunHost) < mro.index(GateHost)


def test_bare_instance_run_state_is_none():
    assert GraphWorkflow().run_state() is None


def test_boot_checks_are_healthy():
    assert graph_boot_problems() == []


def test_worker_registers_the_graph_pipeline_workflow():
    src = (Path(__file__).resolve().parents[2] / "src" / "sdlc" / "worker.py").read_text(
        encoding="utf-8"
    )
    names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    assert {"GraphWorkflow", "graph_boot_problems"} <= names
