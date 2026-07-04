"""load_case_assets activity: reads rubric files into {stage: text}.

File I/O lives in the activity; the workflow passes only serializable args.
Missing files are skipped (that stage just won't be judged) rather than
crashing the run.
"""
import asyncio

from sdlc.benchmarks.judge import load_case_assets


def test_load_case_assets_reads_two_rubric_files(tmp_path):
    (tmp_path / "rubric-architect.md").write_text("arch rubric body", encoding="utf-8")
    (tmp_path / "rubric-clarifier.md").write_text("clar rubric body", encoding="utf-8")
    rubric_files = {
        "architect": str(tmp_path / "rubric-architect.md"),
        "clarifier": str(tmp_path / "rubric-clarifier.md"),
    }
    out = asyncio.run(load_case_assets("ignored", rubric_files))
    assert out == {"architect": "arch rubric body",
                   "clarifier": "clar rubric body"}


def test_load_case_assets_skips_missing_file(tmp_path):
    present = tmp_path / "rubric-architect.md"
    present.write_text("arch body", encoding="utf-8")
    rubric_files = {
        "architect": str(present),
        "clarifier": str(tmp_path / "does-not-exist.md"),
    }
    out = asyncio.run(load_case_assets("ignored", rubric_files))
    # missing stage absent, present stage read; no exception raised
    assert set(out) == {"architect"}
    assert out["architect"] == "arch body"


def test_load_case_assets_returns_empty_when_no_files(tmp_path):
    out = asyncio.run(load_case_assets("ignored", {}))
    assert out == {}
