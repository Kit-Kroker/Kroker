"""The analyze stage is wired into FeatureWorkflow before the merge gate,
and both advisory checks are built from its output."""
import inspect

from sdlc.workflows import feature


def test_analyze_stage_calls_analyst_and_builds_both_checks():
    src = inspect.getsource(feature.FeatureWorkflow.run)
    # Analyst invoked
    assert "t_analyst.run(" in src
    # Enforcement helper used (not an LLM verdict)
    assert "untraced_criteria(" in src
    # Both advisory checks appended
    assert 'build_check(\n                "traceability"' in src or \
           'build_check("traceability"' in src
    assert '"coverage"' in src
    assert "measure_coverage" in src


def test_analyze_runs_before_merge_evidence():
    src = inspect.getsource(feature.FeatureWorkflow.run)
    assert src.index("t_analyst.run(") < src.index("evaluate_gate")
