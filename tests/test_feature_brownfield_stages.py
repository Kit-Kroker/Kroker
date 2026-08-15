"""E-84 D3/D4/D6/D13: the brownfield branch, wired."""
from __future__ import annotations

import inspect

from sdlc.workflows.feature import FeatureWorkflow


def test_the_pipeline_reads_the_mode():
    """Before E-84, IdeaBrief.mode was written by three callers and read by
    nothing in src/sdlc/. That is the defect this task closes."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "ProjectMode.BROWNFIELD" in src or "classify(" in src


def test_context_runs_after_the_integration_branch_is_cut():
    """D4: the map must describe the tree the work is actually based on, so
    it pins integration.head_sha rather than the base branch's tip."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert src.index("setup_integration_branch") < src.index("_context(")


def test_seeded_runs_still_short_circuit_before_context():
    """D13: tidy-up children declare BROWNFIELD and have no Architect call to
    ground, so they must not pay for a map nothing reads (E-44 D1)."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert src.index("if seeded is not None") < src.index("_context(")
