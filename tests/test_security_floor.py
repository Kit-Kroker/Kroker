from __future__ import annotations

import pathlib

import pytest

from sdlc.activities import SecurityScanInput, security_scan
from sdlc.measurement import CollectionState
from sdlc.models import SecurityReport


def test_security_report_requires_a_collection_state():
    """A report cannot be built without saying whether a scan happened."""
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        SecurityReport(critical=0)


def test_clean_scan_is_measured():
    r = SecurityReport(critical=0, state=CollectionState.MEASURED)
    assert r.findings == []
    assert r.state is CollectionState.MEASURED


@pytest.mark.asyncio
async def test_regex_scan_always_reports_measured(tmp_path: pathlib.Path):
    """The default path always collects, so this retrofit changes no live
    behavior -- the guard is installed before the semgrep path that would
    trip it."""
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.state is CollectionState.MEASURED


@pytest.mark.asyncio
async def test_security_scan_clean_worktree(tmp_path: pathlib.Path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical == 0


@pytest.mark.asyncio
async def test_security_scan_flags_hardcoded_secret(tmp_path: pathlib.Path):
    (tmp_path / "cfg.py").write_text(
        'AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLEKEY1234567890abcd"\n', encoding="utf-8"
    )
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical >= 1
    assert any(f.severity == "critical" for f in report.findings)


@pytest.mark.asyncio
async def test_security_scan_flags_eval_of_input(tmp_path: pathlib.Path):
    (tmp_path / "danger.py").write_text("def run(s):\n    return eval(s)\n", encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.critical >= 1


@pytest.mark.asyncio
async def test_security_scan_skips_the_provisioned_venv(tmp_path: pathlib.Path):
    """`_ensure_python_env` creates `.sdlc-venv` INSIDE the worktree, so by
    merge time the scan walks a full site-packages tree. Stdlib and vendored
    third-party code is dense with `eval(` and `shell=True`, so the ABSOLUTE
    security_no_critical check became unpassable for any Python case once QA
    had run (bench-todo-api-greenfield-1785444047: 14 critical findings, 14
    of 14 inside .sdlc-venv, 0 from produced code)."""
    vendored = tmp_path / ".sdlc-venv" / "Lib" / "site-packages" / "pygments"
    vendored.mkdir(parents=True)
    (vendored / "formatters.py").write_text(
        "def load(name):\n    return eval(name)\n", encoding="utf-8"
    )
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))

    assert report.critical == 0, report.findings


@pytest.mark.asyncio
async def test_security_scan_skips_vendored_dependency_trees(tmp_path: pathlib.Path):
    """Same reasoning for the conventions the produced project itself brings:
    a dependency's source is not the diff under review."""
    for vendor_dir in (".venv", "venv", "node_modules"):
        pkg = tmp_path / vendor_dir / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "index.js").write_text("module.exports = (s) => eval(s);\n", encoding="utf-8")

    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))

    assert report.critical == 0, report.findings


@pytest.mark.asyncio
async def test_security_scan_still_flags_produced_code_beside_a_venv(tmp_path: pathlib.Path):
    """Pruning must not turn the gate off — a real finding in the produced
    tree is still caught with a provisioned venv present."""
    vendored = tmp_path / ".sdlc-venv" / "Lib" / "site-packages"
    vendored.mkdir(parents=True)
    (vendored / "noise.py").write_text("eval('1')\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "danger.py").write_text(
        "def run(s):\n    return eval(s)\n", encoding="utf-8"
    )

    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))

    assert report.critical == 1
    assert report.findings[0].path.endswith("danger.py")


from sdlc.gate import CheckClass, build_check, evaluate_quality_gate


def test_security_check_blocks_when_critical_present():
    checks = [
        build_check("build_integration_green", True, CheckClass.ABSOLUTE),
        build_check(
            "security_no_critical", False, CheckClass.ABSOLUTE, detail="1 critical finding"
        ),
    ]
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_security_check_absolute_even_if_requested_advisory():
    # ABSOLUTE_FLOOR promotion: an override cannot wave it through.
    from sdlc.gate import GateOverride

    checks = [build_check("security_no_critical", False, CheckClass.ADVISORY)]
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="security_no_critical", approved_by="human", reason="yolo")],
    )
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_feature_workflow_builds_security_check():
    import pathlib

    src = pathlib.Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8")
    assert (
        'build_check(\n                "security_no_critical"' in src
        or '"security_no_critical"' in src
    ), "merge gate must build the security_no_critical check"
    assert "security_scan" in src, "merge gate must run the security_scan activity"
