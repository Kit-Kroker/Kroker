"""US4 e2e: a verified fix closes only when it is seen on the default branch (023b T034).

Contracts: tasks.md T034, US4 AC1-AC4, SC-B04, research.md R8 (lines 89-108),
data-model transitions (verified rows).

Helper shape and scripting channel copied from ``test_workflow_exec_us2.py``. The
inline worker's ``triage_secrets`` emits one JUDGEMENT ``.env`` finding whose rule
carries the stub script prefix. It reads the commit it is asked about, so a
default-branch Detect sees the real default branch.

Shared flow: a ``fix:`` child parks, Report verifies it, and the merge gate stays
open. Each cell then diverges:
1. merge -> closed (RED on HEAD until closure_step lands, T035).
2. squash -> resolved_externally, with no lesson claimed (RED).
3. never merged -> stays verified. PRE-GREEN regression pin: HEAD already keeps
   verified incidents where they are, and this cell guards that.
4. regression -> the same .env is back on the default branch: dirty -> reopened
   (RED). The dirty closure never sends a REJECT, since the child already completed.
5. lost cycle -> a not-collected Detect changes nothing, then the next collected
   Detect closes (RED).

Ambiguity resolved in cell 4: the data-model names no ExecutionRecord outcome for
a regression after merge. This file pins ``completed`` (the child did complete).
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from temporalio import activity
from temporalio.client import WorkflowExecutionStatus
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

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-us4-closure"
CHILD_RE = re.compile(r"^maint-demo-[0-9a-f]{8}-inc1-a1$")
SECRET_SCRIPT = "secret_committed"
PROPOSAL = RepairProposal(
    analysis="The tracked .env leaks a live token; untrack it and rotate the token.",
    actions=[RepairAction(kind="code_fix", summary="untrack .env", target_paths=[".env"])],
    self_confidence=0.9,
)


@pytest.fixture(autouse=True)
def _worktrees(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


def _wts_root() -> str:
    return os.environ["SDLC_WORKTREES_ROOT"]


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(
        project="demo",
        repo_dir=str(repo),
        ack_unattended_build_probe=True,
        execute=True,
    )
    base.update(kw)
    return MaintenanceConfig(**base)


def _reintroduce_env(repo: Path) -> str:
    """The same .env content commit_env_file writes. The merged fix added .env to
    .gitignore, so this forces the add, the way a real re-commit would."""
    (repo / ".env").write_text("API_TOKEN=0123456789abcdef0123\n", encoding="utf-8")
    git(repo, "add", "-f", ".env")
    git(repo, "commit", "-m", "re-commit the .env")
    return head_sha(repo)


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


async def _nudge(handle) -> None:
    """One nudge, waiting until the cycle it starts has completed."""
    before = (await handle.query(MaintenanceWorkflow.maintenance_state)).cycle
    await handle.signal("nudge")

    async def _done() -> bool:
        s = await handle.query(MaintenanceWorkflow.maintenance_state)
        return s.cycle == before + 1 and not s.running_cycle

    await _until(_done, what=f"cycle {before + 1} to complete")


async def _only(handle):
    incs = await handle.query(MaintenanceWorkflow.incidents)
    assert len(incs) == 1, f"expected one incident, got {len(incs)}"
    return incs[0]


async def _pending(handle):
    return await handle.query(MaintenanceWorkflow.pending_decisions)


def _secrets_activity(rule: str, arm: dict):
    """The scripted triage_secrets. While ``arm['on']`` it reports a not-collected
    signal regardless of commit (the lost-cycle cell); otherwise it emits one
    .env finding, read at the commit it is asked about."""

    @activity.defn(name="triage_secrets")
    async def scripted_secrets(inp: TriageSignalInput) -> SignalResult:
        if arm.get("on"):
            return SignalResult(
                signal="secrets",
                version=3,
                collected=Measurement.not_collected("scripted: lost cycle"),
            )
        repo = Path(inp.repo_dir)
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
async def _worker(env, script: str, arm: dict):
    """The inline worker: the maint_worker activity list, with the scripted
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
            _secrets_activity(rule, arm),
            *fake_agent_activities([("maintainer_agent", RepairProposal, PROPOSAL)]),
            fake_notify,
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
        ],
    ):
        yield


async def _drive_to_verified(env, repo, script: str, arm: dict):
    """Baseline, incident, human approval of the repair gate, child start, the
    child parks, one verify cycle. Returns (handle, child_id); the child's merge
    gate is still open."""
    handle = await _start(env, _cfg(repo))
    await _nudge(handle)  # cycle 1: baseline
    commit_env_file(repo)
    await _nudge(handle)  # cycle 2: incident, plan, repair:1 (human)

    async def _gate_open() -> bool:
        return any(p.gate == "repair:1" for p in await _pending(handle))

    await _until(_gate_open, what="repair:1 to open")
    await handle.signal(
        "submit_gate_decision",
        GateDecision(gate="repair:1", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )
    await _nudge(handle)  # Execute starts exactly one child
    inc = await _only(handle)
    assert inc.execution is not None, "the approved incident must start a child"
    child_id = inc.execution.child_id
    assert CHILD_RE.match(child_id), child_id

    child = env.client.get_workflow_handle(child_id)

    async def _parked() -> bool:
        return bool(await child.query(StubRepairChild.pending_decisions))

    await _until(_parked, what="the child to park at its merge gate")
    await _nudge(handle)  # Report: probe -> verification -> verdict resolved
    inc = await _only(handle)
    assert inc.state.value == "verified", f"the fix must verify first, got {inc.state.value}"
    return handle, child_id


async def _approve_child_merge(env, child_id: str) -> str:
    """A human approves the child's merge gate; the child publishes and completes."""
    child = env.client.get_workflow_handle(child_id)
    (pending,) = await child.query(StubRepairChild.pending_decisions)
    assert pending.gate == "merge"
    await child.signal(
        "submit_gate_decision",
        GateDecision(
            gate=pending.gate,
            round=pending.round,
            outcome=GateOutcome.APPROVE,
            decided_by="human",
        ),
    )
    return await asyncio.wait_for(child.result(), timeout=60)


def _ref_exists(repo: Path, ref: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


# ---------------------------------------------------------- 1. merge -> closed (RED)


async def test_a_merged_fix_seen_on_the_default_branch_is_closed(repo_dir):
    """RED on HEAD until closure_step lands (T035): the verified incident stays
    verified, although the default branch now carries the fix.

    Expected: the human merge lands the child's head; the next collected Detect
    reads the default branch, the identity is absent, and the child head is an
    ancestor, so the incident closes. Retention is US6's job, so ``retained``
    stays False here."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "fix", arm)

            result = await _approve_child_merge(env, child_id)
            assert result == "merged-not-deployed:stub"
            child = env.client.get_workflow_handle(child_id)
            assert (await child.describe()).status == WorkflowExecutionStatus.COMPLETED

            await _nudge(handle)  # the collected default-branch Detect

            inc = await _only(handle)
            assert inc.state.value == "closed"
            assert inc.retained is False, "retention is US6's job, not closure's"
            head = git(repo_dir, "rev-parse", f"sdlc/{child_id}/integration").strip()
            assert inc.execution.integration_head == head, "R8: the recorded child head"


# ------------------------------------------------ 2. squash -> resolved_externally (RED)


async def test_a_squash_merged_fix_is_resolved_externally_with_no_lesson(repo_dir):
    """RED on HEAD until closure_step lands (T035).

    The stub lands a squash commit with no child ancestry, so the identity is
    absent but the child head is not an ancestor. The incident is terminal as
    resolved_externally, and retained stays False: no lesson is claimed without
    provable provenance (R8)."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "squash:fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "squash:fix", arm)

            result = await _approve_child_merge(env, child_id)
            assert result == "merged-not-deployed:stub"

            await _nudge(handle)

            inc = await _only(handle)
            assert inc.state.value == "resolved_externally"
            assert inc.retained is False, "a squash outcome is never a lesson (R8)"


# ----------------------------------------------- 3. never merged -> stays verified (PRE-GREEN)


async def test_a_fix_that_is_never_merged_stays_verified(repo_dir):
    """PRE-GREEN regression pin (no closure_step needed). Expected to PASS on HEAD.

    Verified is a live state. Without a merge, no collected Detect can close or
    resolve it, and the execution record is unchanged. This guards the T035 wiring
    from closing an incident whose fix never reached the default branch.

    No render check here: the incidents table has no note column until T047."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, _ = await _drive_to_verified(env, repo_dir, "fix", arm)
            before = (await _only(handle)).execution.model_dump(mode="json")

            await _nudge(handle)
            await _nudge(handle)

            inc = await _only(handle)
            assert inc.state.value == "verified"
            assert inc.execution.model_dump(mode="json") == before
            assert inc.retained is False


# --------------------------------------------- 4. regression after merge -> reopened (RED)


async def test_a_regression_after_merge_is_dirty_and_reopens_without_a_reject(repo_dir):
    """RED on HEAD until closure_step lands (T035).

    The fix merges, then the same .env is committed back to the default branch.
    The identity is present and the child head is an ancestor, so the fix did not
    hold: dirty, and the incident reopens. The child already completed, so no
    REJECT is sent. Its completed result stands.

    The ExecutionRecord outcome is pinned to ``completed``. The data-model names
    no outcome for a regression after merge."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "fix", arm)
            assert await _approve_child_merge(env, child_id) == "merged-not-deployed:stub"

            _reintroduce_env(repo_dir)  # the same .env is back on the default branch
            await _nudge(handle)

            inc = await _only(handle)
            assert inc.state.value == "reopened"
            assert inc.reopens == 1
            assert inc.execution is not None
            assert inc.execution.outcome == "completed"

            child = env.client.get_workflow_handle(child_id)
            assert (await child.describe()).status == WorkflowExecutionStatus.COMPLETED
            assert await asyncio.wait_for(child.result(), timeout=60) == (
                "merged-not-deployed:stub"
            ), "no REJECT may reach a completed child"


# ------------------------------------------------------ 5. lost cycle (RED)


async def test_a_not_collected_cycle_neither_strands_nor_degrades_the_closure(repo_dir):
    """RED on HEAD until closure_step lands (T035).

    After the merge, one Detect is not collected. Closure is a state check that
    re-runs on the next collected cycle, so the incident stays verified: not
    resolved_externally, and not reopened. The next collected cycle closes it."""
    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "fix", arm)
            assert await _approve_child_merge(env, child_id) == "merged-not-deployed:stub"

            arm["on"] = True
            await _nudge(handle)  # the lost cycle
            inc = await _only(handle)
            assert inc.state.value == "verified", "a lost cycle must not degrade the incident"
            assert inc.reopens == 0

            arm["on"] = False
            await _nudge(handle)  # the next collected cycle closes it
            inc = await _only(handle)
            assert inc.state.value == "closed"
            assert inc.reopens == 0


# ------------------------------------------------------ edge: closed is terminal (RED)


async def test_a_closed_incident_is_terminal_and_inert(repo_dir):
    """Edge, RED on HEAD. Reaching 'closed' needs closure_step (T035), so this fails
    at the closed assertion until T035 lands. Once closed, the terminal checks are
    the point. Two or three further cycles must leave the incident byte-equal
    (attempt 1, executions unchanged, retained False), start nothing (the
    starts_in_window count is unchanged, and no a2 child exists), and still
    complete every cycle. A closed incident is outside the live set, so nothing
    probes, verifies or retries it."""
    from temporalio.service import RPCError

    arm: dict = {"on": False}
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with _worker(env, "fix", arm):
            handle, child_id = await _drive_to_verified(env, repo_dir, "fix", arm)
            assert await _approve_child_merge(env, child_id) == "merged-not-deployed:stub"
            await _nudge(handle)  # the collected default-branch Detect closes it

            inc = await _only(handle)
            assert inc.state.value == "closed"
            frozen = inc.model_dump(mode="json")
            before = await handle.query(MaintenanceWorkflow.maintenance_state)

            for _ in range(3):
                await _nudge(handle)

            after = await handle.query(MaintenanceWorkflow.maintenance_state)
            assert after.cycle == before.cycle + 3, "cycles must keep completing"
            assert after.starts_in_window == before.starts_in_window

            inc = await _only(handle)
            assert inc.model_dump(mode="json") == frozen, "a closed incident is inert"
            assert inc.retained is False
            assert inc.attempt == 1

            prefix = child_id.rsplit("-a1", 1)[0]
            with pytest.raises(RPCError):
                await env.client.get_workflow_handle(f"{prefix}-a2").describe()
