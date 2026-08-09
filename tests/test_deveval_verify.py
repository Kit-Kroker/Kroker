"""E-79 spec section 7: an imported case whose gold implementation cannot
pass its own oracle is broken, and must be caught at import rather than in a
benchmark run."""
from pathlib import Path

import pytest

from sdlc.benchmarks.importers.deveval import convert_repo
from sdlc.benchmarks.importers.verify import VerifyResult, verify_case

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_calc"


@pytest.mark.slow
def test_verify_case_green_on_a_faithful_import(tmp_path):
    convert_repo(FIXTURE, tmp_path, judge_model="google:gemini-3.5-flash")
    result = verify_case(tmp_path / "deveval-mini-calc")
    assert isinstance(result, VerifyResult)
    assert result.ok, result.output


@pytest.mark.slow
def test_verify_case_red_when_the_reference_is_broken(tmp_path):
    """The gate must discriminate, not merely run."""
    convert_repo(FIXTURE, tmp_path, judge_model="google:gemini-3.5-flash")
    calc = tmp_path / "deveval-mini-calc" / "reference" / "calc.py"
    calc.write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
    result = verify_case(tmp_path / "deveval-mini-calc")
    assert not result.ok
    assert "test_add_positive" in result.output


@pytest.mark.slow
def test_verify_case_reports_a_missing_reference(tmp_path):
    convert_repo(FIXTURE, tmp_path, judge_model="google:gemini-3.5-flash")
    import shutil
    shutil.rmtree(tmp_path / "deveval-mini-calc" / "reference")
    result = verify_case(tmp_path / "deveval-mini-calc")
    assert not result.ok
    assert "reference" in result.output
