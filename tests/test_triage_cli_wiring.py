"""E-42 section 8: the operator path. approve/reject/status need NO changes --
channels/transport.py resolves signals and queries BY NAME and imports nothing
workflow-specific, so the gate surface GateHost gave TriageWorkflow is already
reachable. This test is that claim, checked rather than asserted."""

from __future__ import annotations

import datetime as dt
import pathlib

from sdlc.workflows.gates import GateHost
from sdlc.workflows.triage import TriageWorkflow


def test_triage_workflow_has_the_hitl_surface():
    for name in ("submit_gate_decision", "status", "pending_decisions", "pending_gate"):
        assert hasattr(TriageWorkflow, name), name
    assert issubclass(TriageWorkflow, GateHost)


def test_transport_stays_workflow_agnostic():
    src = pathlib.Path("src/sdlc/channels/transport.py").read_text(encoding="utf-8")
    # The docstring names FeatureWorkflow by way of explaining the invariant
    # ("Nothing here imports FeatureWorkflow"); the assertion is about IMPORTS,
    # not prose. Check only the import lines.
    import_lines = "\n".join(
        line for line in src.splitlines() if line.strip().startswith(("import ", "from "))
    )
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


def test_triage_workflow_id_is_distinct_per_run():
    """Review fix. Temporal refuses to start a workflow whose id is already
    RUNNING, so a bare `triage-<slug>` meant a triage parked on the readiness
    gate blocked the next triage of that repository -- and E-44's
    assess -> fix -> re-triage loop is the first thing that would hit it."""
    from sdlc.cli import triage_workflow_id

    a = triage_workflow_id(
        "/srv/checkouts/MyRepo", dt.datetime(2026, 8, 9, 10, 15, 0, tzinfo=dt.UTC)
    )
    b = triage_workflow_id(
        "/srv/checkouts/MyRepo", dt.datetime(2026, 8, 9, 10, 16, 0, tzinfo=dt.UTC)
    )
    assert a != b
    assert a == "triage-myrepo-20260809T101500Z"
    # Still names the repository: an operator reading `sdlc inbox` must be able
    # to tell which triage is waiting on them.
    assert a.startswith("triage-myrepo-")


def test_triage_show_queries_by_method_not_by_name():
    """Review fix (critical). A string query carries no result type, so the
    converter returns a dict and `.model_dump_json()` is an AttributeError --
    which is what `sdlc triage show` did on every invocation.

    A source-text check, deliberately: nothing drives cli.py's main() under a
    live server, so this is what actually guards the CLI against the regression.
    test_triage_workflow_e2e.py::test_the_cli_show_path_renders_json pins the
    underlying temporalio behaviour that makes the idiom necessary.
    """
    src = pathlib.Path("src/sdlc/cli.py").read_text(encoding="utf-8")
    assert 'handle.query("triage")' not in src
    assert "handle.query(TriageWorkflow.triage)" in src
