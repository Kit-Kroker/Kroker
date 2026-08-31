"""Crew activities (E-88 §1). Everything that touches the filesystem, a git
worktree, or a model lives here; the workflow stays deterministic and does
none of it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from temporalio import activity
from temporalio.exceptions import ApplicationError

from ..artifacts.capture import capture_session
from ..harness.adapters import HARNESSES, HarnessRequest
from ..models import HarnessKind, HarnessRunResult, ToolGrant
from .models import MAX_NOTE_BYTES, RoundNote, TurnBeat, TurnRecord
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


# The error type a workflow matches on to tell "the agent produced a bad
# result" from "the worker died". Only the latter deserves a retry.
AGENT_FAILURE = "crew_agent_failure"


@dataclass
class CrewTurnInput:
    worktree: str
    layout: str
    role: str
    harness: HarnessKind
    model: str
    prompt: str
    round: int
    attempt: int
    turn_timeout_s: int
    task_id: str
    session_id: str | None = None
    containment_enabled: bool = False
    containment_policy_path: str | None = None
    containment_strict: bool = False
    grants: list[ToolGrant] = field(default_factory=list)


@dataclass
class CrewTurnOutput:
    run: HarnessRunResult
    record: TurnRecord


def _resume_target(inp: CrewTurnInput) -> str | None:
    """The session to continue. A retried attempt prefers what the previous
    attempt heartbeated: the CLI printed its session id seconds into the run
    (adapters.py:127), so even a turn that died mid-stream leaves us able to
    continue rather than re-pay the whole context (spec §3)."""
    try:
        details = activity.info().heartbeat_details
    except RuntimeError:                       # outside an activity, in tests
        details = ()
    if details:
        beat = TurnBeat(**details[-1])
        if beat.session_id:
            return beat.session_id
    return inp.session_id


@activity.defn
async def run_crew_turn(inp: CrewTurnInput) -> CrewTurnOutput:
    harness = HARNESSES[inp.harness]
    session_id = _resume_target(inp)
    req = HarnessRequest(prompt=inp.prompt, cwd=inp.worktree,
                         model=inp.model, session_id=session_id,
                         timeout_s=inp.turn_timeout_s)

    seen = TurnBeat(session_id=session_id, round=inp.round)

    def _beat(payload=None) -> None:
        """Heartbeat with the details a retry needs. The harness calls this
        as it streams; we enrich rather than replace, so the session id
        survives even when a later beat carries no payload."""
        if isinstance(payload, dict):
            for k, v in payload.items():
                if v is not None and hasattr(seen, k):
                    setattr(seen, k, v)
        try:
            activity.heartbeat(seen.model_dump())
        except RuntimeError:                   # outside an activity, in tests
            pass

    result = await harness.run(req, heartbeat=_beat)
    result.denials = harness.normalise_denials(result._raw_stdout)
    result.deferred = harness.normalise_deferral(result._raw_stdout)

    # E-38/ADR-16, per TURN. Raw stdout rides a PrivateAttr and is scrubbed
    # here; a real transcript per agent per round is the thing E-87's single
    # synthetic journal was standing in for. Best-effort, exactly as
    # run_coding_task treats it: losing the RECORD must not fail the turn.
    try:
        run_id = activity.info().workflow_run_id
    except RuntimeError:                       # outside an activity, in tests
        run_id = "local"
    try:
        ref, digest = capture_session(
            harness, result._raw_stdout, run_id=run_id,
            task_id=f"{inp.task_id}-{inp.role}-r{inp.round}",
            attempt=inp.attempt)
        result.session_ref = ref
        result.session_digest = digest
    except Exception:                          # noqa: BLE001
        pass

    record = TurnRecord(
        role=inp.role, round=inp.round, attempt=inp.attempt,
        harness=inp.harness, model=inp.model,
        session_id=result.session_id or session_id,
        cost_usd=result.cost_usd, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        context_window=result.context_window, exit_code=result.exit_code,
        cost_incomplete=result.cost_usd is None)

    # A suspended tool call is NOT a failure: the workflow must see it, gate
    # it, and resume. Only a genuine non-zero exit is an agent-level failure.
    if result.exit_code != 0 and result.deferred is None:
        raise ApplicationError(
            f"crew turn failed: role={inp.role} round={inp.round} "
            f"exit_code={result.exit_code}",
            record.model_dump(mode="json"),
            type=AGENT_FAILURE, non_retryable=True)

    return CrewTurnOutput(run=result, record=record)
