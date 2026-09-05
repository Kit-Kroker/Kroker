"""The analyze stage is wired into FeatureWorkflow before the merge gate,
and both advisory checks are built from its output."""

import inspect
import pathlib

from sdlc.workflows import feature

MERGE_SRC = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")


def test_analyze_stage_calls_analyst_and_builds_both_checks():
    src = inspect.getsource(feature.FeatureWorkflow._build_and_merge)
    # Analyst invoked
    assert "t_analyst," in src
    # Enforcement helper used (not an LLM verdict)
    assert "untraced_criteria(" in src
    # Both advisory checks built in merge stage
    assert "build_check(" in MERGE_SRC and '"traceability"' in MERGE_SRC
    assert '"coverage"' in MERGE_SRC
    assert "measure_coverage" in MERGE_SRC


def test_analyze_runs_before_merge_evidence():
    src = inspect.getsource(feature.FeatureWorkflow._build_and_merge)
    assert src.index("t_analyst,") < src.index("merge.step")
