"""US2 e2e: a child's fix is verified on its own branch before any PR (023b T026, RED).

Subject: ``MaintenanceWorkflow`` with ``cfg.execute=True`` driving the stub repair
child through Report: probe -> verification branch -> re-triage (gating off) ->
delta -> verdict -> (verified | REJECT the child's merge gate -> reopened) ->
cleanup. Contracts: tasks.md T026, research.md R4/R5, data-model.md transitions,
VerificationResult / ExecutionRecord literals, workflow-wire.md.

Scripting channel: the loop-built child title is ``<rule> in <path>``, and the
stub reads its script from the first colon segment of the title. So this suite
runs an INLINE worker whose ``triage_secrets`` is a scripted activity. It emits
one JUDGEMENT finding at ``.env`` whose rule carries the script prefix
(``fix: secret_committed``, ``nofix: ...``, ``empty: ...``, ``fail: ...``,
``hang: ...``), iff ``.env`` is tracked at the commit it is asked about.
The commit comes from ``TriageSignalInput.commit_sha``, so a verify triage sees
the verify tree, not HEAD.

Cells (one incident each; human-approved single code_fix plan, default threshold):
1. fix:          verified; verdict resolved; child keeps its merge gate; cleanup.
2. nofix:        child REJECTed once; reopened; verdict persisted.
3. empty:        parked with no commit; dirty; reopened.
4. fail:         child fails before parking; no merge decision; reopened.
5. not-collected verify tree not collected: stays verifying; verdict unverifiable.
6. conflict:     the integration branch is gone before verify; verdict conflicted
                 (R4: a non-conflict merge failure is recorded as conflicted).
7. hang:         child_timeout_hours=1; the attempt times out; reopened.
8. replay:       the fix: and nofix: parent histories replay clean.

Deviations for the reviewer:
- Outcome literals. ``ExecutionRecord.outcome`` has no ``verified`` value. A
  verified child is still parked for a human, so fix: pins ``awaiting_merge``.
  An empty diff that parks is a dirty verdict, so empty: pins
  ``rejected_by_loop``. ``empty_diff`` is kept for a probe-side finding.
- Current record. Once an attempt finishes, this file reads the record from
  ``incident.execution`` when set, else the last of ``incident.executions``. The
  data-model does not say which one holds a finished attempt.

RED honesty: on HEAD the verify nudge does nothing (no report_step), so every
cell fails on its own state or verification assertion, not on setup.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from temporalio import activity
from temporalio.client import WorkflowExecutionStatus, WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.core.models import GateDecision, GateOutcome
from sdlc.maintenance.models import (
    MaintenanceConfig,
    MaintenanceState,
    RepairAction,
    RepairProposal,
)
from sdlc.measurement import Measurement
from sdlc.triage.activities import TriageSignalInput
from sdlc.triage.models import FixClass, SignalResult, TriageFinding
from sdlc.vcs import build_verification_branch, setup_integration_branch
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import fake_agent_activities
from tests.maintenance.conftest import (
    MAINT_023B_ACTIVITIES,
    commit_env_file,
    fake_notify,
    git,
    head_sha,
)
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES, fake_secrets
from tests.maintenance.stub_child import STUB_ACTIVITIES, StubRepairChild
from tests.replay.harness import replayer

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us2-verify"
CHILD_RE = re.compile(r"^maint-demo-[0-9a-f]{8}-inc1-a1$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SECRET_SCRIPT = "secret_committed"
PROPOSAL = RepairProposal(
    analysis="The tracked .env leaks a live token; untrack it and rotate the token.",
    actions=[
        RepairAction(kind="code_fix", summary="untrack .env", target_paths=[".env"]),
    ],
    self_confidence=0.9,
)


@pytest.fixture(autouse=True)
def _worktrees(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


def _wts_root() -> str:
    return os.environ["SDLC_WORKTREES_ROOT"]


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(project="demo", repo_dir=str(repo), ack_unattended_build_probe=True)
    base.update(kw)
    return MaintenanceConfig(**base)


def _execute_cfg(repo, **kw) -> MaintenanceConfig:
    return _cfg(repo, execute=True, **kw)


def _ref_exists(repo: Path, ref: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


async def _until(pred, timeout: float = 90.0, what: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await pred():
                return
        except Exception:  # noqa: BLE001 -- queries before the first task
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


async def _start(env, cfg: MaintenanceConfig):
    return await env.client.start_workflow(
        MaintenanceWorkflow.run,
        MaintenanceState(config=cfg),
        id="maint-demo",
        task_queue=TASK_QUEUE,
    )


async def _cycle_done(handle, cycle: int) -> None:
    async def _done() -> bool:
        s = await handle.query(MaintenanceWorkflow.maintenance_state)
        return s.cycle == cycle and not s.running_cycle

    await _until(_done, what=f"cycle {cycle} to complete")


async def _nudge(handle, cycle_after: int) -> None:
    await handle.signal("nudge")
    await _cycle_done(handle, cycle_after)


async def _only(handle):
    incs = await handle.query(MaintenanceWorkflow.incidents)
    assert len(incs) == 1, f"expected one incident, got {len(incs)}"
    return incs[0]


def _record(inc):
    """The current attempt's ExecutionRecord (see the module's deviations)."""
    if inc.execution is not None:
        return inc.execution
    assert inc.executions, "no ExecutionRecord on the incident"
    return inc.executions[-1]


def _secrets_activity(rule: str, *, not_collect_verify: bool = False):
    """The scripted triage_secrets: one .env finding, read at the given commit."""

    @activity.defn(name="triage_secrets")
    async def scripted_secrets(inp: TriageSignalInput) -> SignalResult:
        repo = Path(inp.repo_dir)
        if not_collect_verify and inp.commit_sha != head_sha(repo):
            return SignalResult(
                signal="secrets",
                version=3,
                collected=Measurement.not_collected("scripted: verify tree not collected"),
            )
        tracked = set(git(repo, "ls-tree", "-r", "--name-only", inp.commit_sha).split())
        findings: list[TriageFinding] = []
        if ".env" in tracked:
            findings.append(
                TriageFinding(
                    signal="secrets",
                    rule=rule,
                    severity="critical",
                    detail="scripted: a committed .env holds a live token",
                    path=".env",
                    fix_class=FixClass.JUDGEMENT,
                )
            )
        return SignalResult(
            signal="secrets",
            version=3,
            collected=Measurement.measured(float(len(findings))),
            findings=findings,
        )

    return scripted_secrets


@asynccontextmanager
async def _worker(env, script: str, *, not_collect_verify: bool = False):
    """The inline worker: the maint_worker activity list with the scripted
    triage_secrets in place of fake_secrets."""
    rule = f"{script}: {SECRET_SCRIPT}"
    triage = [a for a in TRIAGE_ACTIVITIES if a is not fake_secrets]
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild],
        plugins=[SdlcPydanticAIPlugin()],
        activities=[
            *triage,
            _secrets_activity(rule, not_collect_verify=not_collect_verify),
            *fake_agent_activities([("maintainer_agent", RepairProposal, PROPOSAL)]),
            fake_notify,
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
    ):
        yield


async def _approve_and_start(handle) -> str:
    """Human-approve the repair gate, then start exactly one child; return its id."""

    async def _gate_open() -> bool:
        return any(
            p.gate == "repair:1" for p in await handle.query(MaintenanceWorkflow.pending_decisions)
        )

    await _until(_gate_open, what="repair:1 to open")
    await handle.signal(
        "submit_gate_decision",
        GateDecision(gate="repair:1", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )
    await _nudge(handle, 4)  # Execute starts exactly one child
    inc = await _only(handle)
    assert inc.execution is not None, "the approved incident must start a child"
    assert CHILD_RE.match(inc.execution.child_id), inc.execution.child_id
    return inc.execution.child_id


async def _drive_to_parked(env, repo, script: str, *, not_collect_verify: bool = False):
    """Baseline, incident, human approval, child start; wait until the child
    parks at its merge gate. Returns (handle, child_id)."""
    handle = await _start(env, _execute_cfg(repo))
    await _nudge(handle, 2)  # cycle 1: baseline
    commit_env_file(repo)
    await _nudge(handle, 3)  # cycle 2: incident, plan, repair:1 (human)
    child_id = await _approve_and_start(handle)

    child = env.client.get_workflow_handle(child_id)

    async def _parked() -> bool:
        return bool(await child.query(StubRepairChild.pending_decisions))

    await _until(_parked, what="the child to park at its merge gate")
    return handle, child_id


async def _drive_to_started(env, repo, *, cfg: MaintenanceConfig):
    handle = await _start(env, cfg)
    await _nudge(handle, 2)
    commit_env_file(repo)
    await _nudge(handle, 3)
    child_id = await _approve_and_start(handle)
    return handle, child_id


# ------------------------------------------------------------------ 1. fix:


async def test_fix_is_verified_and_the_child_keeps_its_merge_gate(repo_dir):
    base = head_sha(repo_dir)
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix"):
            handle, child_id = await _drive_to_parked(env, repo_dir, "fix")
            await _nudge(handle, 5)  # verify nudge: probe -> verification -> verdict

            inc = await _only(handle)
            assert inc.state.value == "verified"
            assert inc.verification is not None
            assert inc.verification.verdict == "resolved"
            assert inc.verification.collected is True

            rec = _record(inc)
            assert rec.integration_branch == f"sdlc/{child_id}/integration"
            assert rec.integration_head is not None
            assert SHA40.match(rec.integration_head)
            assert rec.integration_head != base

            # The loop never decides the child's merge: the gate is still open.
            child = env.client.get_workflow_handle(child_id)
            pending = await child.query(StubRepairChild.pending_decisions)
            assert [p.gate for p in pending] == ["merge"]
            assert (await child.describe()).status == WorkflowExecutionStatus.RUNNING

            # Cleanup: the verify worktree and its ref are gone.
            assert not os.path.exists(os.path.join(_wts_root(), child_id, "verify"))
            assert not _ref_exists(repo_dir, f"refs/heads/sdlc/tidyup-verify/{child_id}")


# ---------------------------------------------------------------- 2. nofix:


async def test_nofix_gets_exactly_one_reject_and_the_incident_reopens(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "nofix"):
            handle, child_id = await _drive_to_parked(env, repo_dir, "nofix")
            await _nudge(handle, 5)

            inc = await _only(handle)
            assert inc.state.value == "reopened"
            assert inc.attempt == 1
            assert inc.verification is not None
            assert inc.verification.verdict == "persisted"
            assert _record(inc).outcome == "rejected_by_loop"

            child = env.client.get_workflow_handle(child_id)
            result = await asyncio.wait_for(child.result(), timeout=60)
            assert result == "rejected:merge"


# ---------------------------------------------------------------- 3. empty:


async def test_empty_diff_parks_dirty_and_the_incident_reopens(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "empty"):
            handle, child_id = await _drive_to_parked(env, repo_dir, "empty")
            await _nudge(handle, 5)

            inc = await _only(handle)
            assert inc.state.value == "reopened"
            assert inc.verification is not None
            assert inc.verification.verdict == "persisted"
            assert _record(inc).outcome == "rejected_by_loop"

            child = env.client.get_workflow_handle(child_id)
            assert await asyncio.wait_for(child.result(), timeout=60) == "rejected:merge"


# ---------------------------------------------------------------- 4. fail:


async def test_a_child_that_fails_before_parking_reopens_with_no_merge_decision(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fail"):
            handle, child_id = await _drive_to_started(env, repo_dir, cfg=_execute_cfg(repo_dir))
            child = env.client.get_workflow_handle(child_id)
            with pytest.raises(WorkflowFailureError):
                await asyncio.wait_for(child.result(), timeout=60)

            await _nudge(handle, 5)  # the probe sees a failed child

            inc = await _only(handle)
            assert inc.state.value == "reopened"
            assert _record(inc).outcome == "failed"
            assert (await child.describe()).status == WorkflowExecutionStatus.FAILED


# -------------------------------------------------------------- 5. not collected


async def test_a_verify_triage_that_is_not_collected_stays_verifying(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "nofix", not_collect_verify=True):
            handle, _ = await _drive_to_parked(env, repo_dir, "nofix", not_collect_verify=True)
            await _nudge(handle, 5)

            inc = await _only(handle)
            assert inc.state.value == "verifying"
            assert inc.verification is not None
            assert inc.verification.verdict == "unverifiable"

            await _nudge(handle, 6)  # a further verify cycle: still verifying
            inc = await _only(handle)
            assert inc.state.value == "verifying"


# ------------------------------------------------------------------ 6. conflict


async def test_a_missing_integration_branch_is_recorded_conflicted_and_rejected(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "nofix"):
            handle, child_id = await _drive_to_parked(env, repo_dir, "nofix")

            # Remove the integration branch before the verify nudge: the merge of a
            # missing branch is a non-conflict failure, which R4 records as conflicted.
            integration_wt = os.path.join(_wts_root(), child_id, "integration")
            branch = f"sdlc/{child_id}/integration"
            git(repo_dir, "worktree", "remove", "--force", integration_wt)
            git(repo_dir, "branch", "-D", branch)

            await _nudge(handle, 5)

            inc = await _only(handle)
            assert inc.verification is not None
            assert inc.verification.verdict == "conflicted"
            assert inc.state.value == "reopened"

            child = env.client.get_workflow_handle(child_id)
            assert await asyncio.wait_for(child.result(), timeout=60) == "rejected:merge"


# ------------------------------------------------------------------- 7. hang:


async def test_a_child_that_never_parks_times_out_and_the_incident_reopens(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "hang"):
            handle, child_id = await _drive_to_started(
                env, repo_dir, cfg=_execute_cfg(repo_dir, child_timeout_hours=1)
            )

            # Advance past the 1h child timeout, then let the cycles observe it.
            await env.sleep(timedelta(hours=2))
            for cycle in range(5, 10):
                await _nudge(handle, cycle)
                if (await _only(handle)).state.value != "executing":
                    break

            inc = await _only(handle)
            assert inc.state.value == "reopened"
            assert _record(inc).outcome == "timed_out"

            child = env.client.get_workflow_handle(child_id)
            status = (await child.describe()).status
            assert status != WorkflowExecutionStatus.RUNNING, "the timed-out child must end"


# ----------------------------------------------------------------- 8. replay


async def test_fix_history_replays_clean(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix"):
            handle, _ = await _drive_to_parked(env, repo_dir, "fix")
            await _nudge(handle, 5)
            assert (await _only(handle)).state.value == "verified"
            history = await handle.fetch_history()

    result = await replayer(MaintenanceWorkflow, TriageWorkflow).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert result is not None


async def test_nofix_history_replays_clean(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "nofix"):
            handle, _ = await _drive_to_parked(env, repo_dir, "nofix")
            await _nudge(handle, 5)
            assert (await _only(handle)).state.value == "reopened"
            history = await handle.fetch_history()

    result = await replayer(MaintenanceWorkflow, TriageWorkflow).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert result is not None


# ------------------------------------------------------------ EDGE (023b T026) -- qa-chaos


def _repo_fingerprint(repo: Path) -> tuple[str, str, str]:
    """Refs, worktrees and HEAD: the state the loop must never leave behind."""
    return (
        git(repo, "for-each-ref"),
        git(repo, "worktree", "list", "--porcelain"),
        git(repo, "rev-parse", "HEAD"),
    )


async def test_the_verify_child_runs_under_its_wire_id_distinct_from_the_cycle_triage(repo_dir):
    """Edge, contracts/workflow-wire.md: the verification triage child id is
    maint-<project>-<run8>-inc<no>-a<attempt>-verify. It is awaited, completed,
    and is never shaped like the cycle triage id maint-<project>-c<cycle>-triage."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix"):
            handle, child_id = await _drive_to_parked(env, repo_dir, "fix")
            await _nudge(handle, 5)

            verify_id = f"{child_id}-verify"
            assert re.match(r"^maint-demo-[0-9a-f]{8}-inc1-a1-verify$", verify_id), verify_id
            assert not re.fullmatch(r"maint-demo-c\d+-triage", verify_id)
            desc = await env.client.get_workflow_handle(verify_id).describe()
            assert desc.status == WorkflowExecutionStatus.COMPLETED


async def test_the_verify_pass_leaves_refs_worktrees_and_head_exactly_as_it_found_them(repo_dir):
    """Edge, SC-002 shape: fingerprint after the child parks and before the verify
    nudge. After the verify cycle (REJECT, reopen, cleanup), it must be unchanged.
    The reopened assertion first proves the verify pass actually ran."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "nofix"):
            handle, _ = await _drive_to_parked(env, repo_dir, "nofix")
            before = _repo_fingerprint(repo_dir)

            await _nudge(handle, 5)
            assert (await _only(handle)).state.value == "reopened"
            assert _repo_fingerprint(repo_dir) == before
