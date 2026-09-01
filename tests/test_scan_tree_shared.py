"""E-84 D1/D5: one extraction path, and it runs without a triage."""

from __future__ import annotations

import inspect

from sdlc.workflows import scanning


def test_scan_tree_is_importable_and_triage_is_optional():
    sig = inspect.signature(scanning.scan_tree)
    assert list(sig.parameters) == ["repo_dir", "commit_sha", "triage"]
    assert sig.parameters["triage"].default is None


def test_the_assessment_phase_delegates_rather_than_duplicating():
    """D1: two copies of the fan-out would agree only by coincidence -- the
    reason fanout.py exists at all. _scan must call scan_tree, not re-run the
    waves itself."""
    from sdlc.workflows.assessment import AssessmentWorkflow

    src = inspect.getsource(AssessmentWorkflow._scan)
    assert "scan_tree(" in src
    assert "for wave in WAVES" not in src
