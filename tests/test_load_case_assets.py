"""load_case_assets activity: reads rubric files into {stage: text}.

File I/O lives in the activity; the workflow passes only serializable args.
A registered rubric file that is missing raises a non-retryable
ApplicationError typed MissingCaseAsset naming the key and the path -- the
run stops before spending any model budget (012 contract §1.4), it never
silently leaves a stage unjudged.
"""

import asyncio

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.benchmarks.judge import load_case_assets


def test_load_case_assets_reads_two_rubric_files(tmp_path):
    (tmp_path / "rubric-architect.md").write_text("arch rubric body", encoding="utf-8")
    (tmp_path / "rubric-clarifier.md").write_text("clar rubric body", encoding="utf-8")
    rubric_files = {
        "architect": str(tmp_path / "rubric-architect.md"),
        "clarifier": str(tmp_path / "rubric-clarifier.md"),
    }
    out = asyncio.run(load_case_assets("ignored", rubric_files))
    assert out == {"architect": "arch rubric body", "clarifier": "clar rubric body"}


def test_load_case_assets_missing_registered_file_raises(tmp_path):
    """012 contract §1.4: a registered file that does not exist fails the
    activity loudly — non-retryable MissingCaseAsset naming key and path."""
    present = tmp_path / "rubric-architect.md"
    present.write_text("arch body", encoding="utf-8")
    missing = tmp_path / "does-not-exist.md"
    rubric_files = {
        "architect": str(present),
        "clarifier": str(missing),
    }
    with pytest.raises(ApplicationError) as excinfo:
        asyncio.run(load_case_assets("ignored", rubric_files))
    exc = excinfo.value
    assert exc.type == "MissingCaseAsset"
    assert exc.non_retryable is True
    assert "clarifier" in str(exc), "the error must name the registered map key"
    assert str(missing) in str(exc), "the error must name the missing path"


def test_load_case_assets_returns_empty_when_no_files(tmp_path):
    out = asyncio.run(load_case_assets("ignored", {}))
    assert out == {}
