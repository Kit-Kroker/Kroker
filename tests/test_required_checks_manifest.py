"""C3: the gate fails closed on a required check it was never handed.

`evaluate_quality_gate` used to judge only the checks it received, so a
required check that was absent from the list was invisible and the run went
quietly green. These tests pin the manifest, the synthesis, the echo into
`GateReport.checks`, and the floor re-assertion that close that hole.
"""

import ast
import pathlib

from sdlc.gate import (
    ABSOLUTE_FLOOR,
    MERGE_REQUIRED_CHECKS,
    CheckClass,
    CheckResult,
    GateOverride,
    build_check,
    evaluate_quality_gate,
)

MERGE_STEP = pathlib.Path("src/sdlc/stages/merge/step.py")


def test_missing_absolute_check_blocks_and_ignores_its_override(required_checks):
    checks = [c for c in required_checks() if c.name != "lint_clean"]
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="lint_clean", approved_by="alice", reason="ship it")],
    )
    assert report.passed is False
    assert "lint_clean" in report.blocking
    assert report.overridden == []


def test_missing_advisory_check_blocks_without_an_override(required_checks):
    checks = [c for c in required_checks() if c.name != "coverage"]
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "coverage" in report.blocking


def test_missing_advisory_check_is_waivable_by_an_audited_override(required_checks):
    checks = [c for c in required_checks() if c.name != "coverage"]
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="coverage", approved_by="alice", reason="legacy gap")],
    )
    assert report.passed is True
    assert report.overridden == ["coverage"]
    assert report.blocking == []


def test_a_typo_in_a_required_name_blocks_instead_of_passing_quietly(required_checks):
    """The typo'd check is inert; the real name synthesizes and blocks. This is
    the sharpest demonstration of what C3 buys."""
    checks = [c for c in required_checks() if c.name != "security_no_critical"]
    checks.append(build_check("security_no_crtical", True, CheckClass.ABSOLUTE))
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_an_empty_checks_list_synthesizes_every_required_name():
    report = evaluate_quality_gate([])
    assert report.passed is False
    assert sorted(report.blocking) == sorted(MERGE_REQUIRED_CHECKS)


def test_synthesized_checks_are_echoed_in_the_report(required_checks):
    """merge/step.py:321-325 and :353-357 split absolute from advisory by
    iterating report.checks. A synthesized name that never lands there
    misroutes into the human escalation path."""
    checks = [c for c in required_checks() if c.name != "security_scan_collected"]
    report = evaluate_quality_gate(checks)
    echoed = [c for c in report.checks if c.name == "security_scan_collected"]
    assert len(echoed) == 1
    assert echoed[0].passed is False
    assert echoed[0].classification is CheckClass.ABSOLUTE
    assert "MISCONFIGURED" in echoed[0].detail


def test_evaluating_twice_neither_mutates_nor_duplicates(required_checks):
    """merge/step.py evaluates once clean (:316-318) and again with overrides
    (:378-380), passing the same list object both times."""
    checks = [c for c in required_checks() if c.name != "coverage"]
    before = [c.name for c in checks]
    first = evaluate_quality_gate(checks)
    # The caller's list is never mutated: nothing appended, nothing replaced.
    # (Identity of the elements is deliberately not asserted — _normalized
    # returns new objects for floor names.)
    assert [c.name for c in checks] == before
    second = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="coverage", approved_by="alice", reason="waived")],
    )
    assert [c.name for c in second.checks].count("coverage") == 1
    assert first.blocking == ["coverage"]
    assert second.passed is True


def test_a_directly_constructed_floor_check_cannot_be_demoted(required_checks):
    """build_check forces the floor at construction; a raw CheckResult skips
    it. The re-assertion must reach the echoed list too, or merge/step.py
    routes a demoted absolute into the human-waivable advisory split."""
    checks = [c for c in required_checks() if c.name != "security_no_critical"]
    checks.append(
        CheckResult(
            name="security_no_critical",
            passed=False,
            classification=CheckClass.ADVISORY,
            detail="1 critical finding",
        )
    )
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="security_no_critical", approved_by="alice", reason="yolo")],
    )
    assert report.passed is False
    assert "security_no_critical" in report.blocking
    assert report.overridden == []
    echoed = next(c for c in report.checks if c.name == "security_no_critical")
    assert echoed.classification is CheckClass.ABSOLUTE


def test_every_floor_name_is_required_and_absolute():
    for name in ABSOLUTE_FLOOR:
        assert name in MERGE_REQUIRED_CHECKS
        assert MERGE_REQUIRED_CHECKS[name] is CheckClass.ABSOLUTE


def test_the_manifest_pins_the_checks_the_merge_step_builds():
    """Source needle: the manifest is the merge gate's production contract.

    Deliberately does NOT use the required_checks fixture — the fixture is
    built from the manifest, so it cannot be the census of the manifest.
    """
    tree = ast.parse(MERGE_STEP.read_text(encoding="utf-8"))
    built = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_check"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert built == set(MERGE_REQUIRED_CHECKS)
