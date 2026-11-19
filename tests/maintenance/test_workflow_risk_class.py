"""FR-502 e2e: an ops-bearing plan's repair gate is HARD from birth (RED).

The one temporal cell of the ops risk-class round (2026-11-19): a mixed
plan (one ``code_fix`` + one ``ops`` action) whose effective confidence
sits ABOVE the configured threshold at round 1 must never be resolved by
policy — the gate owes a human from the moment it is built, and the human
approval then executes exactly the code_fix subset (GATE 1 Q6 semantics,
unchanged).

Scenario arithmetic — two forced deviations from the scaffolding list,
each provable, each required for the cell to go RED at HEAD and GREEN
under the conjunct:

* The fault is the committed ``.env`` pair (``commit_env_file``), not
  ``commit_build_break``: the build-break finding is JUDGEMENT
  (confidence ceiling 0.6; floor 0.40 for an unreproduced 2-action plan),
  which can never clear ANY legal threshold (``threshold`` is bounded
  ``ge=0.5``), and its reproduced repricing (floor 0.55) lands through
  ``_reprice`` — whose policy submit resolves a gate regardless of its
  policy, a different hole this round does not touch. The gate-construction
  auto path the conjunct guards is only reachable above threshold via
  ``env_file_tracked``, the fixture's sole MECHANICAL finding.
* The threshold is 0.7, not the default 0.8: a 2-action unreproduced
  MECHANICAL plan floors at 0.95 - 0.15 - 0.05 = 0.75, and the auto branch
  is strict (``effective > threshold``); at 0.8 nothing clears and the cell
  could not go RED. 0.7 keeps the plan above threshold so the ONLY thing
  hardening this gate is the FR-502 risk class (Review Focus 1), and keeps
  the sibling JUDGEMENT incident's reproduced reprice (0.55) below
  threshold so it never draws a policy decision either.

Harness: the 023b US suites verbatim — conftest's ``maint_worker`` (stub
repair child under the real ``GraphWorkflow`` wire name, triage fakes,
vcs activities), the ``submit_gate_decision`` human-approve pattern, and
``_until`` polling (gates never block the cycle, so states are observed,
not assumed). No SC-002 fingerprint assert: the approved start cuts
branches and worktrees through the stub child, exactly like the exec US1
mixed-plan cell this extends.
"""

from __future__ import annotations

import asyncio
import re
import time

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from sdlc.core.models import GateDecision, GateOutcome
from sdlc.maintenance.execution import OPS_REFUSAL_OUTCOME
from sdlc.maintenance.models import (
    MaintenanceConfig,
    MaintenanceState,
    RepairAction,
    RepairProposal,
)
from sdlc.workflows.maintenance import MaintenanceWorkflow
from tests.maintenance.conftest import commit_env_file, maint_worker
from tests.maintenance.stub_child import StubRepairChild

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "maint-risk"

CHILD_RE = re.compile(r"^maint-demo-[0-9a-f]{8}-inc\d+-a1$")

# One code_fix (the .gitignore half of the env pair) + one ops action:
# self_confidence 0.95, so effective = min(0.95, floor 0.75) = 0.75 sits
# ABOVE the 0.7 threshold — confidence alone would clear this gate.
PROPOSAL = RepairProposal(
    analysis="The .env is tracked; untrack it and rotate the token it leaked.",
    actions=[
        RepairAction(
            kind="code_fix",
            summary="untrack .env and add it to .gitignore",
            target_paths=[".gitignore"],
        ),
        RepairAction(kind="ops", summary="rotate the disclosed token", ops_action="rollback"),
    ],
    self_confidence=0.95,
)


@pytest.fixture(autouse=True)
def _worktrees(tmp_path, monkeypatch):
    """The stub child's integration worktrees land under a tmp root."""
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


def _cfg(repo, **kw) -> MaintenanceConfig:
    base = dict(
        project="demo",
        repo_dir=str(repo),
        ack_unattended_build_probe=True,
        execute=True,
        threshold=0.7,
    )
    base.update(kw)
    return MaintenanceConfig(**base)


def _state(repo) -> MaintenanceState:
    return MaintenanceState(config=_cfg(repo))


async def _until(pred, timeout: float = 90.0, what: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await pred():
                return
        except Exception:  # noqa: BLE001 -- query before the first task lands
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


async def _incidents(handle):
    return await handle.query(MaintenanceWorkflow.incidents)


async def _by_rule(handle, rule: str):
    for inc in await _incidents(handle):
        if inc.finding is not None and inc.finding.rule == rule:
            return inc
    raise AssertionError(f"no incident for rule {rule!r}")


async def test_ops_bearing_plan_is_human_only_even_above_threshold(repo_dir):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with maint_worker(env, task_queue=TASK_QUEUE, proposal=PROPOSAL):
            handle = await env.client.start_workflow(
                MaintenanceWorkflow.run,
                _state(repo_dir),
                id="maint-demo",
                task_queue=TASK_QUEUE,
            )
            await handle.signal("nudge")  # cycle 1: baseline

            async def _baseline_recorded() -> bool:
                return (await handle.query(MaintenanceWorkflow.maintenance_state)).baseline_recorded

            await _until(_baseline_recorded, what="cycle 1 baseline")

            commit_env_file(repo_dir)
            await handle.signal("nudge")  # cycle 2: detect, plan, gate

            # Wait until the gate has SETTLED one way or the other: under the
            # conjunct it pends for a human (round 1); at HEAD it is resolved
            # by policy at construction. Either way the plan has landed.
            async def _gate_settled() -> bool:
                inc = await _by_rule(handle, "env_file_tracked")
                pending = await handle.query(MaintenanceWorkflow.pending_decisions)
                return inc.decision is not None or any(
                    p.gate == f"repair:{inc.no}" and p.round == 1 for p in pending
                )

            await _until(_gate_settled, what="the repair gate to settle")

            # (1) HARD from birth: above threshold at round 1, the incident
            # still owes a HUMAN — awaiting, undecided, and no policy
            # decision anywhere in the loop's state (the sibling JUDGEMENT
            # incident included).
            inc = await _by_rule(handle, "env_file_tracked")
            assert inc.state.value == "awaiting_decision", (
                f"an ops-bearing plan must stay human-gated, got {inc.state.value}"
            )
            assert inc.decision is None, (
                f"the gate was decided by {inc.decision.decided_by!r} — policy must "
                "never resolve an ops-bearing plan"
            )
            pending = await handle.query(MaintenanceWorkflow.pending_decisions)
            assert any(p.gate == f"repair:{inc.no}" and p.round == 1 for p in pending)
            for other in await _incidents(handle):
                if other.decision is not None:
                    assert other.decision.decided_by != "policy", other.key

            # (2) A human approve (the US-suite submit_gate_decision pattern)
            # resolves it, and Execute then starts exactly ONE child — seeded
            # from the env_file_tracked finding's code_fix path — with the ops
            # action recorded verbatim as not executed.
            await handle.signal(
                "submit_gate_decision",
                GateDecision(
                    gate=f"repair:{inc.no}",
                    round=1,
                    outcome=GateOutcome.APPROVE,
                    decided_by="human",
                ),
            )

            async def _executing() -> bool:
                inc = await _by_rule(handle, "env_file_tracked")
                return inc.execution is not None

            await handle.signal("nudge")  # cycle 3: Execute starts the child
            await _until(_executing, what="exactly one repair child to start")

            inc = await _by_rule(handle, "env_file_tracked")
            assert inc.execution is not None
            assert CHILD_RE.match(inc.execution.child_id), inc.execution.child_id
            assert inc.attempt == 1, "a second start would be a second attempt"
            assert [r.child_id for r in inc.executions] == [inc.execution.child_id]
            # B-FR-017 / GATE 1 Q6: the human approval executes the code_fix
            # subset only; the ops proposal is recorded, never executed.
            assert inc.execution.detail == OPS_REFUSAL_OUTCOME
            assert OPS_REFUSAL_OUTCOME in inc.model_dump_json()

            child = await env.client.get_workflow_handle(inc.execution.child_id).query(
                StubRepairChild.run_state
            )
            assert child.run_id == inc.execution.child_id
            assert child.title == "env_file_tracked in .gitignore"

            # The never-approved JUDGEMENT sibling started nothing.
            sibling = await _by_rule(handle, "secret_committed")
            assert sibling.state.value == "awaiting_decision"
            assert sibling.execution is None
            assert sibling.executions == []
