# tests/test_crew_fs_activities.py
"""E-88 §2. read_round is where untrusted model output stops being a file
and becomes typed data -- or a protocol violation."""

from __future__ import annotations

import json
import subprocess

import pytest

from sdlc.crew.activities import (
    PrepareCrewInput,
    ReadRoundInput,
    prepare_crew,
    read_round,
)
from sdlc.crew.worktree import orchestration_dir, round_dir

pytestmark = pytest.mark.asyncio

GOOD = {
    "schema": "notes-v1",
    "what_changed": "added greet()",
    "why": "the brief asked",
    "verification": "pytest passed",
    "left_undone": "",
}


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


async def test_prepare_writes_the_brief_where_the_skill_looks(tmp_path):
    repo = _repo(tmp_path)
    await prepare_crew(PrepareCrewInput(worktree=str(repo), layout="code", brief="do the thing"))
    brief = orchestration_dir(repo, "code") / "brief.md"
    assert brief.read_text(encoding="utf-8") == "do the thing"


async def test_read_round_returns_the_note_summary(tmp_path):
    repo = _repo(tmp_path)
    await prepare_crew(PrepareCrewInput(worktree=str(repo), layout="code", brief="b"))
    d = round_dir(repo, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(json.dumps(GOOD), encoding="utf-8")
    out = await read_round(
        ReadRoundInput(worktree=str(repo), layout="code", round=1, deliverable_path="notes.md")
    )
    assert out.missing is False
    assert "greet()" in out.note_summary


async def test_read_round_reports_a_missing_deliverable_rather_than_raising(tmp_path):
    """spec §2: 'the agent exited without running the protocol' is a
    DIAGNOSIS the workflow classifies, not an activity crash."""
    repo = _repo(tmp_path)
    await prepare_crew(PrepareCrewInput(worktree=str(repo), layout="code", brief="b"))
    round_dir(repo, "code", 1).mkdir(parents=True)
    out = await read_round(
        ReadRoundInput(worktree=str(repo), layout="code", round=1, deliverable_path="notes.md")
    )
    assert out.missing is True


async def test_read_round_turns_a_bad_deliverable_schema_into_critique(tmp_path):
    """An unknown schema in the deliverable is agent misbehavior the next
    round's brief must correct -- a violation, not an activity crash."""
    repo = _repo(tmp_path)
    d = round_dir(repo, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(json.dumps({**GOOD, "schema": "notes-v2"}), encoding="utf-8")
    out = await read_round(
        ReadRoundInput(worktree=str(repo), layout="code", round=1, deliverable_path="notes.md")
    )
    assert out.missing is False
    assert "notes-v2" in out.critique
    assert "PROTOCOL VIOLATIONS" in out.critique


async def test_read_round_turns_a_prose_advisor_into_critique(tmp_path):
    """Regression (T06 run, 2026-09-21): the critic wrote advisor.md as a
    Markdown review instead of advisor-v1 JSON and the crew died on it. The
    violation must reach the next round's brief as corrective critique."""
    repo = _repo(tmp_path)
    d = round_dir(repo, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(json.dumps(GOOD), encoding="utf-8")
    (d / "advisor.md").write_text(
        "# Advisor review -- round 1\n\n**Land the direction.**\n", encoding="utf-8"
    )
    out = await read_round(
        ReadRoundInput(worktree=str(repo), layout="code", round=1, deliverable_path="notes.md")
    )
    assert out.missing is False
    assert "greet()" in out.note_summary  # the valid deliverable still reads
    assert "advisor.md" in out.critique
    assert "PROTOCOL VIOLATIONS" in out.critique
    assert out.verdict is None  # review.json absent -> no verdict


async def test_read_round_rejects_a_path_escaping_the_round_directory(tmp_path):
    repo = _repo(tmp_path)
    round_dir(repo, "code", 1).mkdir(parents=True)
    with pytest.raises(Exception, match="round directory"):
        await read_round(
            ReadRoundInput(
                worktree=str(repo),
                layout="code",
                round=1,
                deliverable_path="../../../../etc/passwd",
            )
        )


async def test_read_round_caps_the_file_size(tmp_path):
    """A model cannot drown the activity's payload by inflating its note."""
    repo = _repo(tmp_path)
    d = round_dir(repo, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text("x" * 400_000, encoding="utf-8")
    with pytest.raises(Exception, match="too large"):
        await read_round(
            ReadRoundInput(worktree=str(repo), layout="code", round=1, deliverable_path="notes.md")
        )
