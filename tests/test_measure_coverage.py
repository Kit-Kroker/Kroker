"""measure_coverage: deterministic diff-scoped Cobertura seam."""
import pytest

from sdlc.activities import CoverageInput, measure_coverage
from sdlc.measurement import CollectionState

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
async def test_no_artifact_means_not_collected(tmp_path):
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.NOT_COLLECTED
    assert r.coverage.value is None
    assert "coverage.xml" in r.coverage.reason


@pytest.mark.asyncio
async def test_diff_scoped_percentage_over_changed_files(tmp_path):
    (tmp_path / "coverage.xml").write_text(COBERTURA, encoding="utf-8")
    # Only app/main.py changed -> 80%, ignoring app/util.py's 40%.
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.MEASURED
    assert r.coverage.value == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_no_changed_file_in_report_means_unmeasured(tmp_path):
    (tmp_path / "coverage.xml").write_text(COBERTURA, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["other/thing.py"]))
    assert r.coverage.state is CollectionState.NOT_COLLECTED


# billion-laughs: entity expansion DoS. defusedxml must refuse it and we must
# degrade to not collected, never hang or raise. (coverage.xml is generated
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
    assert r.coverage.state is CollectionState.NOT_COLLECTED


UNRELATED_SUFFIX_MATCH = """<?xml version="1.0" ?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class filename="main.py" line-rate="0.9"/>
      </classes>
    </package>
  </packages>
</coverage>
"""


@pytest.mark.asyncio
async def test_suffix_match_without_path_boundary_is_rejected(tmp_path):
    """A bare 'main.py' entry must not match 'app/domain.py' just because the
    changed path happens to end with the same trailing characters — that is
    not a path-boundary-safe suffix match and would attribute another file's
    coverage to a file that was never touched."""
    (tmp_path / "coverage.xml").write_text(UNRELATED_SUFFIX_MATCH, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/domain.py"]))
    assert r.coverage.state is CollectionState.NOT_COLLECTED


@pytest.mark.asyncio
async def test_non_finite_line_rate_degrades_safely(tmp_path):
    """A hostile or corrupt coverage.xml can carry a non-finite line-rate
    (nan/inf). nan must not silently propagate into a measured value (where
    `nan >= threshold` is always False, i.e. a fabricated advisory failure),
    and the class must simply be skipped rather than counted. The file parsed
    and the changed file was present — an attempt produced uninterpretable
    output, which is `unknown`, not `not_collected`."""
    xml = """<?xml version="1.0" ?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class filename="app/main.py" line-rate="nan"/>
      </classes>
    </package>
  </packages>
</coverage>
"""
    (tmp_path / "coverage.xml").write_text(xml, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.UNKNOWN


@pytest.mark.asyncio
async def test_infinite_line_rate_is_skipped(tmp_path):
    """An overflowing literal ('1e400') parses to inf, which the isfinite
    guard skips rather than clamps — so the only class is dropped and the
    seam reports nothing measured instead of a fabricated 100%. The file
    parsed and the changed file was present — an attempt produced
    uninterpretable output, which is `unknown`, not `not_collected`."""
    xml = """<?xml version="1.0" ?>
<coverage>
  <packages>
    <package name="app">
      <classes>
        <class filename="app/main.py" line-rate="1e400"/>
      </classes>
    </package>
  </packages>
</coverage>
"""
    (tmp_path / "coverage.xml").write_text(xml, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.UNKNOWN


@pytest.mark.asyncio
async def test_malformed_xml_degrades_to_unmeasured(tmp_path):
    """A truncated/malformed (not malicious) coverage.xml must hit the
    DET.ParseError branch and degrade to not collected rather than raise."""
    (tmp_path / "coverage.xml").write_text(
        "<coverage><packages><package>", encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.NOT_COLLECTED


@pytest.mark.asyncio
async def test_a_measured_zero_is_distinguishable_from_no_measurement(tmp_path):
    """The defect this retrofit exists to fix: 0% coverage on a changed file
    must not look like a coverage run that never happened."""
    zero = """<?xml version="1.0" ?>
<coverage><packages><package name="app"><classes>
  <class filename="app/main.py" line-rate="0.0"/>
</classes></package></packages></coverage>
"""
    (tmp_path / "coverage.xml").write_text(zero, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.MEASURED
    assert r.coverage.value == pytest.approx(0.0)
