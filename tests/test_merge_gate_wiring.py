import ast, pathlib, pytest

SRC = pathlib.Path("src/sdlc/workflows/feature.py")

def _fn(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name:
            return n
    raise AssertionError(f"function {name} not found")

@pytest.fixture(scope="module")
def feature_src():
    return SRC.read_text(encoding="utf-8")

@pytest.fixture(scope="module")
def feature_tree(feature_src):
    return ast.parse(feature_src)

def test_merge_stage_calls_evaluate_gate_before_merge_verdict(
        feature_tree, feature_src):
    """SC-5: the deterministic gate is a hard precondition. Its activity
    call must textually precede any t_merge_verdict.run call in run()."""
    run = _fn(feature_tree, "run")
    src = ast.get_source_segment(feature_src, run)
    assert src is not None
    g = src.find("evaluate_gate")
    v = src.find("t_merge_verdict")
    assert g != -1, "merge stage does not call evaluate_gate activity"
    # When MergeVerdict is unreachable (e.g. gate failed), v may be -1;
    # when it is present it MUST come after the gate.
    if v != -1:
        assert g < v, "MergeVerdict consulted before DeterministicQualityGate"

def test_merge_stage_terminates_on_absolute_failure(feature_src):
    """An absolute gate failure is terminal — the workflow must return
    before any human-gate wait or MergeVerdict consult."""
    needle = "absolute-gate-failed"
    assert needle in feature_src, (
        "merge stage must short-circuit on absolute gate failure "
        f"(looked for return marker containing {needle!r})")


from sdlc.gate import (
    CheckClass, GateOverride, build_check, evaluate_quality_gate,
)

def test_absolute_failure_blocks_despite_override():
    """SC-5: an absolute check failure cannot be waived by a human override."""
    checks = [build_check("build_integration_green", False,
                          CheckClass.ABSOLUTE, detail="tests red")]
    report = evaluate_quality_gate(
        checks, overrides=[GateOverride(check="build_integration_green",
                                        approved_by="human", reason="ship it")])
    assert not report.passed
    assert "build_integration_green" in report.blocking
    assert report.overridden == []

def test_advisory_failure_passes_with_audited_override():
    checks = [build_check("coverage_gate", False, CheckClass.ADVISORY)]
    report = evaluate_quality_gate(
        checks, overrides=[GateOverride(check="coverage_gate",
                                        approved_by="human", reason="accepted")])
    assert report.passed
    assert "coverage_gate" in report.overridden
