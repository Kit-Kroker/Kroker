"""Crew activities (E-88 §1). Everything that touches the filesystem, a git
worktree, or a model lives here; the workflow stays deterministic and does
none of it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

from .models import MAX_NOTE_BYTES, RoundNote
from .worktree import orchestration_dir, prepare_orchestration, round_dir

# 4x the note cap: enough headroom for JSON overhead, small enough that a
# runaway file is refused before it is parsed.
MAX_ROUND_FILE_BYTES = 4 * MAX_NOTE_BYTES


class CrewProtocolError(RuntimeError):
    """A round file exists but is not what the protocol says it is. Distinct
    from a MISSING file, which is a diagnosis the workflow classifies."""


@dataclass
class PrepareCrewInput:
    worktree: str
    layout: str
    brief: str


@activity.defn
async def prepare_crew(inp: PrepareCrewInput) -> str:
    """Create the orchestration tree, exclude it from git, write the brief."""
    d = prepare_orchestration(inp.worktree, inp.layout)
    (d / "brief.md").write_text(inp.brief, encoding="utf-8")
    return str(d)


@dataclass
class ReadRoundInput:
    worktree: str
    layout: str
    round: int
    deliverable_path: str


@dataclass
class RoundReading:
    deliverable_path: str | None
    note_summary: str
    missing: bool


def _resolve_in_round(worktree: str, layout: str, rnd: int,
                      rel: str) -> Path:
    """Resolve a model-supplied relative path and prove it stayed inside the
    round directory. Rejected, never sanitised."""
    base = round_dir(worktree, layout, rnd).resolve()
    target = (base / rel).resolve()
    if not target.is_relative_to(base):
        raise CrewProtocolError(
            f"deliverable {rel!r} resolves outside the round directory "
            f"{base}")
    return target


@activity.defn
async def read_round(inp: ReadRoundInput) -> RoundReading:
    path = _resolve_in_round(inp.worktree, inp.layout, inp.round,
                             inp.deliverable_path)
    if not path.is_file():
        # The agent exited without running the protocol: crash, refusal, or
        # it left the skill. The workflow decides what that means.
        return RoundReading(deliverable_path=None, note_summary="",
                            missing=True)
    size = path.stat().st_size
    if size > MAX_ROUND_FILE_BYTES:
        raise CrewProtocolError(
            f"{path.name} is too large: {size} bytes exceeds "
            f"{MAX_ROUND_FILE_BYTES}")
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CrewProtocolError(f"{path.name} is not valid JSON: {e}") from e
    if not isinstance(payload, dict):
        raise CrewProtocolError(f"{path.name} must contain a JSON object")
    schema = payload.get("schema")
    if schema != "notes-v1":
        raise CrewProtocolError(
            f"{path.name} declares schema {schema!r}; only 'notes-v1' is "
            f"understood, and an unknown schema is an error rather than a "
            f"best-effort parse")
    note = RoundNote(**payload)
    summary = "\n".join(
        [note.what_changed, note.why, note.verification, note.left_undone]
    ).strip()
    return RoundReading(deliverable_path=str(path), note_summary=summary,
                        missing=False)
