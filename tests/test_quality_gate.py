from sdlc.gate import (
    CheckClass, GateOverride, build_check, evaluate_quality_gate,
)


def test_absolute_failure_blocks_unconditionally():
    checks = [build_check("lint", False, CheckClass.ABSOLUTE)]
    rep = evaluate_quality_gate(checks, overrides=[
        GateOverride(check="lint", approved_by="alice", reason="whatever")])
    assert rep.passed is False
    assert "lint" in rep.blocking          # override ignored for absolute
    assert rep.overridden == []


def test_advisory_failure_blocks_without_override():
    rep = evaluate_quality_gate([build_check("coverage", False, CheckClass.ADVISORY)])
    assert rep.passed is False
    assert "coverage" in rep.blocking


def test_advisory_failure_passes_with_override():
    checks = [build_check("coverage", False, CheckClass.ADVISORY)]
    rep = evaluate_quality_gate(checks, overrides=[
        GateOverride(check="coverage", approved_by="alice", reason="legacy gap")])
    assert rep.passed is True
    assert rep.overridden == ["coverage"]
    assert rep.blocking == []


def test_security_floor_cannot_be_demoted():
    c = build_check("security_no_critical", False, CheckClass.ADVISORY)
    assert c.classification is CheckClass.ABSOLUTE
    rep = evaluate_quality_gate([c], overrides=[
        GateOverride(check="security_no_critical", approved_by="alice",
                     reason="yolo")])
    assert rep.passed is False


def test_all_pass_is_clean():
    checks = [build_check("lint", True, CheckClass.ABSOLUTE),
              build_check("coverage", True, CheckClass.ADVISORY)]
    rep = evaluate_quality_gate(checks)
    assert rep.passed is True
    assert rep.blocking == []
