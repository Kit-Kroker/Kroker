"""CrewTaskWorkflow (E-88) -- a coding stage as a round loop.

The round machine, the brakes, and the durable state live here; every side
effect is an activity. That is the whole point of the design: E-87 hand-wrote
this inside an activity, complete with a journal file and a recovery path,
because an activity has no history of its own.

Deliberately NOT here yet (E-88 step 2): the critic role, GateHost, and the
`deferred` gate. A suspended tool call is returned upward, where
feature.py's existing E-17 loop already handles it.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from ..crew.activities import (
        AGENT_FAILURE, CheckpointInput, CrewTurnInput, PrepareCrewInput,
        ReadRoundInput, checkpoint_round, prepare_crew, read_round,
        run_crew_turn,
    )
    from ..crew.config import CrewRole
    from ..crew.models import CrewRunResult, RoundRecord, TurnRecord
    from ..models import HarnessKind, HarnessRunResult, ToolGrant

EXIT_OK = 0
EXIT_PROTOCOL_VIOLATION = 65
EXIT_ROUNDS_EXHAUSTED = 66
EXIT_DEADLINE = 67
EXIT_BUDGET = 68

# Read-only and cheap; retrying is free.
FS_ACT = dict(start_to_close_timeout=timedelta(minutes=2),
              retry_policy=RetryPolicy(maximum_attempts=3))
# Commits. Retrying a failed `git add` is safe; retrying it forever is not.
GIT_ACT = dict(start_to_close_timeout=timedelta(minutes=5),
               retry_policy=RetryPolicy(maximum_attempts=2))


class CrewTaskInput(BaseModel):
    """Resolved layout VALUES, not a layout name: the workflow sandbox cannot
    read files, the same split CodingTaskInput already uses for the agent
    registry."""
    layout: str
    lead: str
    roles: list[CrewRole]
    prompt: str
    worktree: str
    task_id: str = "task"
    attempt: int = 1
    deliverable_path: str = "notes.md"
    rounds_max: int = 1
    wall_clock_s: int = 3000
    turn_timeout_s: int = 1800
    cost_usd: float = 25.0
    # role -> session_id, so a re-invocation continues rather than restarts.
    sessions: dict[str, str] = Field(default_factory=dict)
    containment_enabled: bool = False
    containment_policy_path: str | None = None
    containment_strict: bool = False
    grants: list[ToolGrant] = Field(default_factory=list)


def _turn_act(turn_timeout_s: int) -> dict:
    """spec §3: infrastructure failures retry (and resume from heartbeat
    details); agent-level failures are raised non-retryable by the activity
    itself, so this policy never applies to them."""
    return dict(
        start_to_close_timeout=timedelta(seconds=turn_timeout_s + 60),
        heartbeat_timeout=timedelta(seconds=min(300, turn_timeout_s)),
        retry_policy=RetryPolicy(maximum_attempts=2,
                                 non_retryable_error_types=[AGENT_FAILURE]))


@workflow.defn
class CrewTaskWorkflow:
    def __init__(self) -> None:
        self._status = "starting"
        self._rounds: list[RoundRecord] = []

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def rounds(self) -> list[RoundRecord]:
        return self._rounds

    @workflow.run
    async def run(self, inp: CrewTaskInput) -> CrewRunResult:
        deadline = workflow.now() + timedelta(seconds=inp.wall_clock_s)
        lead = next(r for r in inp.roles if r.name == inp.lead)
        sessions = dict(inp.sessions)
        refs: list = []
        spent = 0.0
        last: TurnRecord | None = None
        summary = ""
        exit_code = EXIT_ROUNDS_EXHAUSTED
        commit_sha: str | None = None
        cost_incomplete = False

        await workflow.execute_activity(
            prepare_crew,
            PrepareCrewInput(worktree=inp.worktree, layout=inp.layout,
                             brief=inp.prompt),
            **FS_ACT)

        for rnd in range(1, inp.rounds_max + 1):
            self._status = f"round:{rnd}:lead"
            record = RoundRecord(round=rnd)
            self._rounds.append(record)

            remaining = (deadline - workflow.now()).total_seconds()
            if remaining <= 0:
                exit_code = EXIT_DEADLINE
                break

            turn = workflow.start_activity(
                run_crew_turn,
                CrewTurnInput(
                    worktree=inp.worktree, layout=inp.layout, role=lead.name,
                    harness=lead.harness, model=lead.model,
                    prompt=self._round_brief(inp, rnd),
                    session_id=sessions.get(lead.name), round=rnd, attempt=1,
                    turn_timeout_s=min(inp.turn_timeout_s, int(remaining)),
                    task_id=inp.task_id,
                    containment_enabled=inp.containment_enabled,
                    containment_policy_path=inp.containment_policy_path,
                    containment_strict=inp.containment_strict,
                    grants=inp.grants),
                **_turn_act(min(inp.turn_timeout_s, int(remaining))))

            # Pick First: the crew's own deadline must win over the turn, so
            # the workflow ends itself with a classified reason rather than
            # being killed by an outer timeout that loses the diagnosis.
            timer = asyncio.ensure_future(
                workflow.sleep(timedelta(seconds=remaining)))
            done, _ = await asyncio.wait(
                [turn, timer], return_when=asyncio.FIRST_COMPLETED)
            if timer in done:
                turn.cancel()
                exit_code = EXIT_DEADLINE
                break
            timer.cancel()

            try:
                out = await turn
            except ActivityError as e:
                rec = self._record_from_failure(e, lead, rnd)
                record.turns.append(rec)
                cost_incomplete = cost_incomplete or rec.cost_incomplete
                exit_code = EXIT_PROTOCOL_VIOLATION
                break

            record.turns.append(out.record)
            last = out.record
            if out.run.session_ref is not None:
                refs.append(out.run.session_ref)
            if out.record.session_id:
                sessions[lead.name] = out.record.session_id

            self._status = f"round:{rnd}:reading"
            reading = await workflow.execute_activity(
                read_round,
                ReadRoundInput(worktree=inp.worktree, layout=inp.layout,
                               round=rnd,
                               deliverable_path=inp.deliverable_path),
                **FS_ACT)
            record.deliverable_path = reading.deliverable_path
            record.note_summary = reading.note_summary

            commit_sha = await workflow.execute_activity(
                checkpoint_round,
                CheckpointInput(worktree=inp.worktree, round=rnd,
                                exit_code=out.run.exit_code),
                **GIT_ACT)

            if reading.missing:
                # The one surviving row of E-87's disagreement table: the
                # agent exited without running the protocol.
                exit_code = EXIT_PROTOCOL_VIOLATION
                break

            summary = reading.note_summary
            rc = record.cost_usd()
            if rc is None:
                cost_incomplete = True
            else:
                spent += rc

            if out.run.deferred is not None:
                # Step 2 gates this here. Until then it travels upward, where
                # feature.py's E-17 loop already knows what to do with it.
                exit_code = out.run.exit_code
                break

            if rnd >= inp.rounds_max:
                exit_code = EXIT_OK
                break
            if spent >= inp.cost_usd:
                exit_code = EXIT_BUDGET
                break

        self._status = "done"
        run = HarnessRunResult(
            harness=HarnessKind.CREW,
            session_id=sessions.get(lead.name),
            exit_code=exit_code,
            summary=summary,
            cost_usd=None if cost_incomplete else spent,
            commit_sha=commit_sha,
            input_tokens=last.input_tokens if last else None,
            output_tokens=last.output_tokens if last else None,
            context_window=last.context_window if last else None,
        )
        return CrewRunResult(run=run, sessions=sessions, session_refs=refs,
                             rounds=self._rounds)

    def _round_brief(self, inp: CrewTaskInput, rnd: int) -> str:
        if rnd == 1:
            return inp.prompt
        return (f"{inp.prompt}\n\nThis is round {rnd}. Your previous round's "
                f"note is at round-{rnd - 1}/{inp.deliverable_path}. Continue "
                f"from it; do not restate it.")

    def _record_from_failure(self, e: ActivityError, role: CrewRole,
                             rnd: int) -> TurnRecord:
        """spec §3: recover the abandoned attempt's cost from the error's
        details, or mark it incomplete. Never silently zero."""
        cause = e.cause
        if isinstance(cause, ApplicationError) and cause.details:
            payload = cause.details[0]
            if isinstance(payload, dict):
                return TurnRecord(**payload)
        return TurnRecord(role=role.name, round=rnd, attempt=1,
                          harness=role.harness, model=role.model,
                          cost_incomplete=True)
