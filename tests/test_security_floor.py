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
