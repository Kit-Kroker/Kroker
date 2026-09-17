"""E-74 §8.1: every new start goes to GraphWorkflow; queries see both types."""

from __future__ import annotations

import inspect
from pathlib import Path

from sdlc import cli
from sdlc.channels import inbox
from sdlc.dashboard import fleet

ROOT = Path(__file__).resolve().parents[2]


def test_cli_start_builds_a_graph_run_input_and_starts_graph_workflow():
    src = inspect.getsource(cli.main)
    assert "build_run_input(" in src
    assert "GraphWorkflow.run" in src
    assert "FeatureWorkflow.run" not in src  # cli.py:635 keeps an unrelated prose mention


def test_dashboard_starter_starts_graph_workflow():
    src = (ROOT / "interfaces" / "dashboard" / "api" / "main.py").read_text(encoding="utf-8")
    assert "GraphWorkflow.run" in src and "build_run_input(" in src
    assert "FeatureWorkflow" not in src


def test_open_run_queries_include_both_types():
    assert "GraphWorkflow" in inspect.getsource(inbox.list_open_run_ids)
    assert "GraphWorkflow" in inspect.getsource(inbox)


def test_closed_run_queries_keep_both_types_permanently():
    for query in (fleet._CLOSED_QUERY, fleet._CLOSED_QUERY_UNORDERED):
        assert "WorkflowType='FeatureWorkflow'" in query and "WorkflowType='GraphWorkflow'" in query
