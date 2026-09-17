"""E-74 §5.7: GraphWorkflow exposes FeatureWorkflow's HITL surface by the same names."""

from __future__ import annotations

import ast
from pathlib import Path

from temporalio.workflow import _Definition

from sdlc.worker import graph_boot_problems
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.gates import GateHost
from sdlc.workflows.graph import GraphWorkflow
from sdlc.workflows.run_host import RunHost


def test_graph_workflow_serves_the_same_queries_and_signals():
    g = _Definition.must_from_class(GraphWorkflow)
    f = _Definition.must_from_class(FeatureWorkflow)
    # Parity is a superset (E-75 §4.2): GraphWorkflow serves every HITL
    # surface FeatureWorkflow does, plus graph-only queries (graph_view).
    assert set(f.queries) <= set(g.queries)
    assert set(g.signals) == set(f.signals)


def test_run_host_precedes_gate_host():
    mro = GraphWorkflow.__mro__
    assert mro.index(RunHost) < mro.index(GateHost)


def test_bare_instance_run_state_is_none():
    assert GraphWorkflow().run_state() is None


def test_boot_checks_are_healthy():
    assert graph_boot_problems() == []


def test_worker_registers_both_pipeline_workflows():
    src = (Path(__file__).resolve().parents[2] / "src" / "sdlc" / "worker.py").read_text(
        encoding="utf-8"
    )
    names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    assert {"FeatureWorkflow", "GraphWorkflow", "graph_boot_problems"} <= names
