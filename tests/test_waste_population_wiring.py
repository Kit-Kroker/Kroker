"""_stage_record calls workflow.info(), so it cannot run outside a Temporal
context. Following tests/test_pending_wiring.py, assert the signature and
the call-site wiring from source instead of spinning up a server.

020 T026: the workflow-half source scan moved off feature.py (deleted) to
the graph side — workflows/build.py plus graph_nodes/postplan.py, where
the single `waste=WasteBag.from_digest(...)` site lives."""

from __future__ import annotations

import inspect
import pathlib

from sdlc.workflows.graph import GraphWorkflow

BUILD_SRC = pathlib.Path("src/sdlc/workflows/build.py")
POSTPLAN_SRC = pathlib.Path("src/sdlc/workflows/graph_nodes/postplan.py")
TASK_HOST_SRC = pathlib.Path("src/sdlc/workflows/task_host.py")
CODE_SRC = pathlib.Path("src/sdlc/stages/code/step.py")


class _Source:
    def read_text(self, encoding="utf-8") -> str:
        return (
            BUILD_SRC.read_text(encoding=encoding)
            + "\n"
            + POSTPLAN_SRC.read_text(encoding=encoding)
            + "\n"
            + TASK_HOST_SRC.read_text(encoding=encoding)
            + "\n"
            + CODE_SRC.read_text(encoding=encoding)
        )


SRC = _Source()


def test_stage_record_accepts_waste():
    sig = inspect.signature(GraphWorkflow._stage_record)
    assert "waste" in sig.parameters
    assert sig.parameters["waste"].default is None


def test_the_pipeline_imports_waste_bag():
    assert "WasteBag" in SRC.read_text(encoding="utf-8")


def test_code_stage_record_passes_the_session_digest():
    """The stage='code' record is the ONE site where a HarnessRunResult with
    a digest exists per task attempt."""
    src = SRC.read_text(encoding="utf-8")
    assert "waste=WasteBag.from_digest(run.session_digest)" in src


def test_only_one_call_site_passes_waste():
    """Proposer stages have no transcript; passing waste anywhere else would
    fabricate a measurement."""
    src = SRC.read_text(encoding="utf-8")
    assert src.count("waste=WasteBag.from_digest") == 1
