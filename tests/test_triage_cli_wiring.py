"""E-42 section 8: the operator path. approve/reject/status need NO changes --
channels/transport.py resolves signals and queries BY NAME and imports nothing
workflow-specific, so the gate surface GateHost gave TriageWorkflow is already
reachable. This test is that claim, checked rather than asserted."""
from __future__ import annotations

import pathlib

from sdlc.workflows.gates import GateHost
from sdlc.workflows.triage import TriageWorkflow


def test_triage_workflow_has_the_hitl_surface():
    for name in ("submit_gate_decision", "status", "pending_decisions",
                 "pending_gate"):
        assert hasattr(TriageWorkflow, name), name
    assert issubclass(TriageWorkflow, GateHost)


def test_transport_stays_workflow_agnostic():
    src = pathlib.Path("src/sdlc/channels/transport.py").read_text(
        encoding="utf-8")
    # The docstring names FeatureWorkflow by way of explaining the invariant
    # ("Nothing here imports FeatureWorkflow"); the assertion is about IMPORTS,
    # not prose. Check only the import lines.
    import_lines = "\n".join(
        l for l in src.splitlines()
        if l.strip().startswith(("import ", "from ")))
    assert "FeatureWorkflow" not in import_lines
    assert "TriageWorkflow" not in import_lines


def test_worker_registers_the_triage_workflow_and_pin_activity():
    src = pathlib.Path("src/sdlc/worker.py").read_text(encoding="utf-8")
    assert "TriageWorkflow" in src
    assert "triage_resolve_commit" in src


def test_cli_exposes_the_triage_verb():
    src = pathlib.Path("src/sdlc/cli.py").read_text(encoding="utf-8")
    assert '"triage"' in src or "'triage'" in src
    assert "--no-build-probe" in src
