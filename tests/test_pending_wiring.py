from __future__ import annotations

import pathlib

from sdlc.pending import StageGatePending
from sdlc.workflows.feature import FeatureWorkflow

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_new_workflow_has_empty_pending_registry():
    wf = FeatureWorkflow()
    assert wf.pending_decisions() == []


def test_pending_decisions_query_returns_registry_values():
    wf = FeatureWorkflow()
    p = StageGatePending(key="architecture#1", gate="architecture", round=1,
                         spec_summary="x")
    wf._pending[p.key] = p
    assert wf.pending_decisions() == [p]


def test_gate_accepts_context_param():
    import inspect
    sig = inspect.signature(FeatureWorkflow._gate)
    assert "context" in sig.parameters


def test_feature_source_wires_pending_population():
    src = SRC.read_text(encoding="utf-8")
    # the query exists and is registered
    assert "def pending_decisions(" in src
    # clarify wait and gate wait both populate the registry
    assert "clarify_pending(" in src
    assert "gate_pending(" in src
    assert "self._pending" in src
    # gate population is cleared on resolution
    assert "self._pending.pop(" in src
