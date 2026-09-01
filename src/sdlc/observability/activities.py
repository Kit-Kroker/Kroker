"""Retro export activity (E-32). Owns the filesystem + env reads the workflow
must not do. Path resolution here (SDLC_EXPORT_ROOT) mirrors how
setup_integration_branch resolves the worktree root inside an activity."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

from ..models import RunSummary
from .export import render_events_jsonl, render_report_html
from .trace import RunEvent


class RunExportInput(BaseModel):
    run_id: str
    summary: RunSummary
    trace: list[RunEvent] = Field(default_factory=list)


@activity.defn
async def export_run_artifacts(inp: RunExportInput) -> str:
    root = Path(os.environ.get("SDLC_EXPORT_ROOT", "./runs"))
    run_dir = root / inp.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text(render_events_jsonl(inp.trace), encoding="utf-8")
    (run_dir / "report.html").write_text(render_report_html(inp.summary), encoding="utf-8")
    # summary.json is RunSummary as DATA. report.html above is a lossy
    # human view of the same object; the SC rollup needs the structure.
    (run_dir / "summary.json").write_text(inp.summary.model_dump_json(indent=2), encoding="utf-8")
    return str(run_dir)
