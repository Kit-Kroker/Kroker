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
from .config import CrewLayout, CrewRole
from .models import MAX_NOTE_BYTES, RoundNote, TurnBeat, TurnRecord
from .worktree import (
    ORCH_ROOT, orchestration_dir, prepare_orchestration, round_dir,
)

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

# The turn refused to run because containment could not be established the
# way the run asked for it: an unresolvable policy, a harness with no layer
# (ADR-17), or strict mode against unenforceable rules. Always a config
# error, so always non-retryable -- a retry spends money to learn the same
# thing.
CREW_CONTAINMENT_REFUSED = "crew_containment_refused"

# ADR-6 guard (spec §5, finding 5): a crew run whose lead's model never
# entered check_adr6_families must not start.
CREW_MODEL_UNRESOLVED = "crew_model_unresolved"


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
    # Repository writes, not protocol writes: every role writes its own
    # files under the orchestration dir. Only the lead may touch the repo,
    # or the diff stops being attributable (spec §1).
    writes: bool = False
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
    # Imported inside the function, following load_crew below: sdlc.activities
    # pulls in the whole activity surface, and crew.activities is imported by
    # feature.py under workflow.unsafe.imports_passed_through. Shared rather
    # than duplicated because ADR-17's fail-closed ladder must have exactly
    # one implementation.
    from ..activities import _resolve_containment
    from ..harness.containment import ContainmentError

    harness = HARNESSES[inp.harness]
    # The activity is the only actor that knows the round, so it owns the
    # round dir: the agent must not have to mkdir to follow the protocol,
    # and a dir nobody created would read as EXIT_PROTOCOL_VIOLATION.
    round_dir(inp.worktree, inp.layout, inp.round).mkdir(
        parents=True, exist_ok=True)
    session_id = _resume_target(inp)
    # A non-lead role reads the repository (cwd) and writes only the
    # protocol tree (write_root). The lead gets None -- a write_root would
    # fence it out of the repository, which is its whole job.
    write_root = (None if inp.writes
                  else str(orchestration_dir(inp.worktree, inp.layout)))
    req = HarnessRequest(prompt=inp.prompt, cwd=inp.worktree,
                         model=inp.model, session_id=session_id,
                         timeout_s=inp.turn_timeout_s,
                         write_root=write_root)
    try:
        _, report = _resolve_containment(harness, inp, req)
    except ContainmentError as e:
        raise ApplicationError(f"crew turn for role {inp.role!r}: {e}",
                               type=CREW_CONTAINMENT_REFUSED,
                               non_retryable=True) from e

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
    result.containment = report
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


@dataclass
class CheckpointInput:
    worktree: str
    round: int
    exit_code: int


@activity.defn
async def checkpoint_round(inp: CheckpointInput) -> str | None:
    """Close a round with a commit. Per ROUND rather than per task: it is
    the resume point a restart resets to, and it is why a turn timeout no
    longer discards the work already in the worktree (spec §2/§4).

    `_git` is imported from sdlc.activities rather than reimplemented: it
    carries the safe.directory bypass that mounted volumes and container
    users need, and two copies of that would drift.
    """
    from ..activities import _git

    # Pathspec-scoped add: the exclusion is LOCAL to this one command -- no
    # common-dir state, no races between parallel tasks, nothing written
    # into the user's repository. (info/exclude lives in the git COMMON
    # dir, so a linked worktree cannot have a private exclude file.)
    add = _git(["add", "-A", "--", ".", f":(exclude){ORCH_ROOT}"],
               inp.worktree)
    if (add.returncode != 0
            and "ignored by one of your .gitignore files" in add.stderr):
        # The target repo (or a stale COMMON-dir info/exclude left by an
        # older run) already ignores ORCH_ROOT itself. Naming an
        # already-ignored path in ANY pathspec -- exclude clause included --
        # makes git refuse the whole `add` with this error unless `-f`
        # (confirmed empirically: identical repo, only difference is a
        # pre-existing ignore rule for the same path). Since the path is
        # already known-ignored, a plain `-A` (no exclude pathspec at all)
        # reaches the same end state through git's default ignore handling,
        # without re-triggering the conflict.
        add = _git(["add", "-A", "--", "."], inp.worktree)
    if add.returncode != 0:
        # Surface git's actual diagnostic instead of a bare
        # CalledProcessError that loses stderr when Temporal serializes it.
        detail = add.stderr.strip() or add.stdout.strip()
        hint = ""
        if "not a git repository" in detail:
            hint = (" (the worktree was a repository when this crew started; "
                    "the agent likely deleted or reinitialized it)")
        raise RuntimeError(f"git add failed in {inp.worktree}: "
                           f"{detail}{hint}")
    commit = _git(
        ["commit", "-m", f"sdlc crew checkpoint round {inp.round} "
                         f"(exit={inp.exit_code})", "--allow-empty"],
        inp.worktree)
    if commit.returncode != 0:
        return None
    return _git(["rev-parse", "HEAD"], inp.worktree).stdout.strip()


@dataclass
class LoadCrewInput:
    layout: str
    lead_harness: HarnessKind | None = None
    lead_model: str | None = None


@dataclass
class LoadedCrew:
    layout: CrewLayout
    roles: list[CrewRole]
    # The LEAD's SKILL.md (a one-role crew runs one skill): the round
    # protocol the workflow renders into every round brief. Without it the
    # skill is boot-validated and then dropped, and nothing tells the agent
    # to write its notes.md.
    protocol: str


@activity.defn
async def load_crew(inp: LoadCrewInput) -> LoadedCrew:
    """Read and validate the crew tree activity-side: the workflow sandbox
    cannot read files, the same split the agent registry already uses.

    Fails closed when lead_model is None (ADR-6, spec §5 finding 5): the
    crew role file's model never enters check_adr6_families, so the lead's
    model must be named in a layer ADR-6 already validates — registry role,
    benchmark arm, or run override."""
    from .loader import (
        check_crew_families, load_layout, read_skill, resolve_crew_roles,
    )
    if inp.lead_model is None:
        raise ApplicationError(
            "a crew run must name the lead's model in the layer ADR-6 "
            "already validates (registry role, benchmark arm, run "
            "override); the crew role file's model never enters "
            "check_adr6_families (spec §5, finding 5)",
            type=CREW_MODEL_UNRESOLVED, non_retryable=True)
    layout, roles = load_layout(inp.layout)
    resolved = resolve_crew_roles(layout, roles, inp.lead_harness,
                                  inp.lead_model)
    # After resolution, never before: the RUN's lead model is what the crew
    # must decorrelate from, and the role file's default may not be it.
    check_crew_families(layout.lead, resolved)
    return LoadedCrew(layout=layout, roles=resolved,
                      protocol=read_skill(roles[layout.lead].skill))
