from datetime import UTC, datetime

import pytest

from sdlc.core.models import (
    RunSummary,
)
from sdlc.observability.activities import RunExportInput, export_run_artifacts
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_export_writes_both_files_under_export_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    summary = RunSummary(
        run_id="run-xyz",
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T0,
        ended_at=T0,
        duration_s=0.0,
    )
    trace = [RunEvent(seq=0, at=T0, kind=RunEventKind.RUN_FINISHED)]
    out = await export_run_artifacts(RunExportInput(run_id="run-xyz", summary=summary, trace=trace))
    run_dir = tmp_path / "run-xyz"
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "report.html").exists()
    assert "run-xyz" in (run_dir / "report.html").read_text(encoding="utf-8")
    assert out == str(run_dir)


@pytest.mark.asyncio
async def test_export_writes_summary_json_as_data(tmp_path, monkeypatch):
    """report.html is lossy; the SC rollup needs RunSummary as data."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    summary = RunSummary(
        run_id="run-abc",
        mode="greenfield",
        outcome="deployed:http://pr/1",
        terminal_stage="deploy",
        started_at=T0,
        ended_at=T0,
        duration_s=0.0,
    )
    await export_run_artifacts(
        RunExportInput(
            run_id="run-abc",
            summary=summary,
            trace=[RunEvent(seq=0, at=T0, kind=RunEventKind.RUN_FINISHED)],
        )
    )
    p = tmp_path / "run-abc" / "summary.json"
    assert p.exists()
    again = RunSummary.model_validate_json(p.read_text(encoding="utf-8"))
    assert again.run_id == "run-abc"
    assert again.outcome == "deployed:http://pr/1"


@pytest.mark.asyncio
async def test_unset_export_root_defaults_to_runs_pipeline(tmp_path, monkeypatch):
    """Layout contract: an unset SDLC_EXPORT_ROOT lands pipeline exports in
    runs/pipeline/, never beside benchmarks/ or ops/ in runs/."""
    monkeypatch.delenv("SDLC_EXPORT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    summary = RunSummary(
        run_id="run-def",
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T0,
        ended_at=T0,
        duration_s=0.0,
    )
    await export_run_artifacts(
        RunExportInput(
            run_id="run-def",
            summary=summary,
            trace=[RunEvent(seq=0, at=T0, kind=RunEventKind.RUN_FINISHED)],
        )
    )
    assert (tmp_path / "runs" / "pipeline" / "run-def" / "summary.json").exists()


def test_demo_export_root_matches_the_activity_default(tmp_path, monkeypatch):
    """demo/run.py mirrors the activity's root resolution; the two literals
    must not drift apart."""
    monkeypatch.delenv("SDLC_EXPORT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    from pathlib import Path

    from sdlc.demo.run import export_root

    assert export_root() == Path("runs") / "pipeline"
