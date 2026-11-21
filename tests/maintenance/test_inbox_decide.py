"""The maintenance inbox and decision path (023a T022, R11/FR-015).

Contract: ``contracts/cli.md`` — ``sdlc inbox`` additionally lists pending
``MaintenanceWorkflow`` gates — and research.md R11: the existing decision
verbs resolve a pending item by run id and send ``submit_gate_decision``,
unchanged, against a GateHost-only workflow.

Two halves:

* **(a) Fast tier** — ``fetch_inbox`` over a mocked Temporal client whose
  ``list_workflows`` honours the WorkflowType query the way the real
  visibility store does. A pending ``repair:1`` item on run ``maint-demo``
  (workflow type ``MaintenanceWorkflow``) must appear in the inbox. Today
  ``fetch_inbox`` asks only for GraphWorkflow + CrewTaskWorkflow
  (``channels/inbox.py``), so the run is never listed: RED until T023 adds
  the type.
* **(b) Temporal tier** — ``sdlc reject maint-demo --gate repair:1`` as the
  CLI drives it (``cli.py`` ``selector_for`` -> ``transport.resolve`` ->
  ``transport.submit``) lands on the maintenance workflow and the incident
  becomes ``rejected`` (decided_by "human", the comment in ``note``).

Recorded T022 result for (b), 2026-11-14: **PASSED today** (uv run
--extra dev pytest -q -m temporal tests/maintenance/test_inbox_decide.py,
1 passed). The existing decision path already resolves repair gates on a
MaintenanceWorkflow run — T023 does NOT need the ``sdlc maintain decide``
fallback verb; only the inbox type list changes. Note: the repo's
pytest ``addopts`` deselect ``-m temporal``, so (b) needs
``-m "temporal"`` (or ``-m ""``) to run.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.channels.contract import Reply
from sdlc.channels.inbox import fetch_inbox
from sdlc.channels.transport import Selector, resolve, submit
from sdlc.converter import sdlc_data_converter
from sdlc.core.models import GateOutcome
from sdlc.maintenance.models import MaintenanceConfig, MaintenanceState, RepairProposal
from sdlc.pending import GateContext, gate_pending
from sdlc.workflows.maintenance import MaintenanceWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.fakes.fake_agents import fake_agent_activities
from tests.maintenance.fake_triage import TRIAGE_ACTIVITIES

with workflow.unsafe.imports_passed_through():
    from sdlc.notify.contract import NotifyInput, Results

# =========================================================================== #
# (a) Fast tier: the inbox lists pending MaintenanceWorkflow gates
# =========================================================================== #


class _TypedStubHandle:
    """One scripted pending_decisions() response (raw json, like Temporal)."""

    def __init__(self, response):
        self._response = response

    async def query(self, name):
        assert name == "pending_decisions"
        return self._response


class _TypedStubClient:
    """A client whose visibility honours the WorkflowType query.

    Unlike ``tests/test_channel_inbox.py``'s stub (which yields every run it
    was handed), this one filters: a run is listed only when its workflow
    type appears in the query. That is what the real visibility store does,
    and it is what makes the test RED for the right reason — ``fetch_inbox``
    must ASK for MaintenanceWorkflow before the run can ever come back.
    """

    def __init__(self, runs: dict[str, tuple[str, list]]):
        # run_id -> (workflow_type, pending items)
        self._runs = runs
        self.queries: list[str] = []

    async def list_workflows(self, query):
        self.queries.append(query)
        for run_id, (wf_type, _pending) in self._runs.items():
            if f"WorkflowType='{wf_type}'" in query:
                yield SimpleNamespace(id=run_id)

    def get_workflow_handle(self, run_id):
        return _TypedStubHandle([i.model_dump(mode="json") for i in self._runs[run_id][1]])


@pytest.mark.asyncio
async def test_inbox_query_names_maintenance_workflow():
    """contracts/cli.md: the inbox additionally lists MaintenanceWorkflow
    gates — the visibility query has to ask for the type."""
    client = _TypedStubClient({})
    await fetch_inbox(client)
    assert "MaintenanceWorkflow" in client.queries[0]


@pytest.mark.asyncio
async def test_inbox_lists_a_pending_maintenance_repair_gate():
    item = gate_pending("repair:1", 1, GateContext(spec_summary="INC-1: the build breaks"))
    client = _TypedStubClient({"maint-demo": ("MaintenanceWorkflow", [item])})

    inbox = await fetch_inbox(client)

    run = next((r for r in inbox.runs if r.run_id == "maint-demo"), None)
    assert run is not None, (
        "the pending MaintenanceWorkflow repair gate is missing from the "
        f"inbox; the query was: {client.queries[0]}"
    )
    assert [d.gate for d in run.pending] == ["repair:1"]


# =========================================================================== #
# (b) Temporal tier: `sdlc reject maint-demo` over the existing decision path
# =========================================================================== #

TASK_QUEUE = "maint-inbox-decide"

PROPOSAL = RepairProposal(
    analysis="The build breaks on a syntax error committed to the package; "
    "restore the return expression.",
    actions=[],
    self_confidence=0.9,
)


def _state(repo) -> MaintenanceState:
    return MaintenanceState(
        config=MaintenanceConfig(
            project="demo", repo_dir=str(repo), ack_unattended_build_probe=True
        )
    )


def _maintainer_activities():
    return fake_agent_activities([("maintainer_agent", RepairProposal, PROPOSAL)])


async def _until(pred, timeout: float = 90.0, what: str = "condition"):
    import asyncio
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await pred():
                return
        except Exception:  # noqa: BLE001 -- query before the first task lands
            pass
        await asyncio.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


@activity.defn(name="notify")
async def fake_notify(inp: NotifyInput) -> Results:  # noqa: ANN001, ARG001
    return Results(results=[])


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_reject_over_the_existing_decision_path_rejects_the_incident(repo_dir):
    """R11: `sdlc reject maint-demo --gate repair:1 --comment ...` drives
    cli.selector_for -> transport.resolve -> transport.submit; against a
    GateHost-only MaintenanceWorkflow run it must resolve repair:1 and the
    incident must become `rejected`."""
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=sdlc_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceWorkflow, TriageWorkflow],
            plugins=[SdlcPydanticAIPlugin()],
            activities=[*TRIAGE_ACTIVITIES, *_maintainer_activities(), fake_notify],
        ):
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

            from tests.maintenance.conftest import commit_build_break

            commit_build_break(repo_dir)
            await handle.signal("nudge")  # cycle 2: detect, plan, gate

            async def _gate_pending() -> bool:
                pending = await handle.query(MaintenanceWorkflow.pending_decisions)
                return any(p.gate == "repair:1" for p in pending)

            await _until(_gate_pending, what="the repair:1 gate")

            # The exact (Selector, Reply) pair `selector_for` builds for
            # `sdlc reject --id maint-demo --gate repair:1 --comment ...`,
            # over the same resolve/submit calls cli.py makes.
            selector = Selector(reply_kind="gate", name="repair:1")
            reply = Reply(outcome=GateOutcome.REJECT, text="not this plan")

            pending = await resolve(handle, selector)
            assert pending.gate == "repair:1"
            await submit(handle, pending, reply)

            async def _rejected() -> bool:
                incs = await handle.query(MaintenanceWorkflow.incidents)
                return bool(incs) and incs[0].state.value == "rejected"

            await _until(_rejected, what="the incident to become rejected")
            inc = (await handle.query(MaintenanceWorkflow.incidents))[0]
            assert inc.decision is not None
            assert inc.decision.decided_by == "human"
            assert inc.decision.outcome is GateOutcome.REJECT
            assert inc.note == "not this plan"
