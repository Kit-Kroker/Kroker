from __future__ import annotations

import pathlib

import pytest

from sdlc.activities import SecurityScanInput, security_scan
from sdlc.models import SecurityReport


def test_security_report_defaults_clean():
    r = SecurityReport(critical=0)
    assert r.findings == []
    assert r.critical == 0


@pytest.mark.asyncio
async def test_security_scan_clean_worktree(tmp_path: pathlib.Path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n",
                                     encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical == 0


@pytest.mark.asyncio
async def test_security_scan_flags_hardcoded_secret(tmp_path: pathlib.Path):
    (tmp_path / "cfg.py").write_text(
        'AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLEKEY1234567890abcd"\n',
        encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical >= 1
    assert any(f.severity == "critical" for f in report.findings)


@pytest.mark.asyncio
async def test_security_scan_flags_eval_of_input(tmp_path: pathlib.Path):
    (tmp_path / "danger.py").write_text(
        "def run(s):\n    return eval(s)\n", encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical >= 1


from sdlc.gate import CheckClass, build_check, evaluate_quality_gate


def test_security_check_blocks_when_critical_present():
    checks = [
        build_check("build_integration_green", True, CheckClass.ABSOLUTE),
        build_check("security_no_critical", False, CheckClass.ABSOLUTE,
                    detail="1 critical finding"),
    ]
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_security_check_absolute_even_if_requested_advisory():
    # ABSOLUTE_FLOOR promotion: an override cannot wave it through.
    from sdlc.gate import GateOverride
    checks = [build_check("security_no_critical", False, CheckClass.ADVISORY)]
    report = evaluate_quality_gate(
        checks, overrides=[GateOverride(check="security_no_critical",
                                        approved_by="human", reason="yolo")])
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_feature_workflow_builds_security_check():
    import pathlib
    src = pathlib.Path("src/sdlc/workflows/feature.py").read_text(
        encoding="utf-8")
    assert 'build_check(\n                "security_no_critical"' in src \
        or '"security_no_critical"' in src, \
        "merge gate must build the security_no_critical check"
    assert "security_scan" in src, \
        "merge gate must run the security_scan activity"
