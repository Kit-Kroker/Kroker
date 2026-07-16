"""measure_coverage: deterministic diff-scoped Cobertura seam."""
import pathlib

import pytest

from sdlc.activities import CoverageInput, measure_coverage

COBERTURA = """<?xml version="1.0" ?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class filename="app/main.py" line-rate="0.80"/>
        <class filename="app/util.py" line-rate="0.40"/>
      </classes>
    </package>
  </packages>
</coverage>
"""


@pytest.mark.asyncio
async def test_no_artifact_means_unmeasured(tmp_path):
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.measured is False
    assert r.diff_pct is None


@pytest.mark.asyncio
async def test_diff_scoped_percentage_over_changed_files(tmp_path):
    (tmp_path / "coverage.xml").write_text(COBERTURA, encoding="utf-8")
    # Only app/main.py changed -> 80%, ignoring app/util.py's 40%.
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.measured is True
    assert r.diff_pct == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_no_changed_file_in_report_means_unmeasured(tmp_path):
    (tmp_path / "coverage.xml").write_text(COBERTURA, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["other/thing.py"]))
    assert r.measured is False


# billion-laughs: entity expansion DoS. defusedxml must refuse it and we must
# degrade to measured=False, never hang or raise. (coverage.xml is generated
# in an untrusted harness worktree — ARCHITECTURE.md §10.)
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE coverage [
  <!ENTITY a "aaaaaaaaaa">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<coverage><packages><package><classes>
  <class filename="app/main.py" line-rate="0.8">&c;</class>
</classes></package></packages></coverage>
"""


@pytest.mark.asyncio
async def test_malicious_xml_degrades_to_unmeasured(tmp_path):
    (tmp_path / "coverage.xml").write_text(BILLION_LAUGHS, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.measured is False
