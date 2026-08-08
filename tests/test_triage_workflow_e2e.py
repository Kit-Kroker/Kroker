"""Sequencing through the workflow, following tests/test_deployment_workflow.py
and the WorkflowEnvironment pattern in tests/test_board_workflow.py."""
from __future__ import annotations

import uuid

import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio import activity

from sdlc.measurement import CollectionState, Measurement
from sdlc.models import (
    GateConfig, GateDecision, GateOutcome, GatePolicy, GateSettings,
)
from sdlc.triage.activities import (
    TriageDependencyInput, TriagePin, TriagePinInput, TriageProbeInput,
    TriageSignalInput,
)
from sdlc.triage.models import SignalResult, Verdict
from sdlc.workflows.triage import TriageInput, TriageWorkflow

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "triage-test"


def _ok(signal: str, version: int, metrics=None) -> SignalResult:
    return SignalResult(signal=signal, version=version,
                        collected=Measurement.measured(0.0),
                        metrics=metrics or {})


@activity.defn(name="triage_resolve_commit")
async def fake_pin(inp: TriagePinInput) -> TriagePin:
    return TriagePin(commit_sha="a" * 40, toolchain="python")


@activity.defn(name="triage_baseline")
async def fake_baseline(inp: TriageSignalInput) -> SignalResult:
    return _ok("baseline", 2,
               {"tests_present": Measurement.measured(3.0)})


@activity.defn(name="triage_scaffold")
async def fake_scaffold(inp: TriageSignalInput) -> SignalResult:
    return _ok("scaffold", 1,
               {"structure_discernible": Measurement.measured(1.0)})


@activity.defn(name="triage_build_probe")
async def fake_probe(inp: TriageProbeInput) -> SignalResult:
    return _ok("build_probe", 1,
               {"buildable": Measurement.measured(1.0),
                "runnable": Measurement.measured(1.0)})


@activity.defn(name="triage_secrets")
async def fake_secrets(inp: TriageSignalInput) -> SignalResult:
    return _ok("secrets", 2)


@activity.defn(name="triage_misconfig")
async def fake_misconfig(inp: TriageSignalInput) -> SignalResult:
    return _ok("misconfig", 1)


@activity.defn(name="triage_outliers")
async def fake_outliers(inp: TriageSignalInput) -> SignalResult:
    return _ok("outliers", 1)


@activity.defn(name="triage_dependencies")
async def fake_deps(inp: TriageDependencyInput) -> SignalResult:
    return _ok("dependencies", 1)


ACTIVITIES = [fake_pin, fake_baseline, fake_scaffold, fake_probe,
              fake_secrets, fake_misconfig, fake_outliers, fake_deps]


async def test_ready_repo_opens_no_gate():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await handle.result()
    assert result.readiness.verdict is Verdict.READY
    assert result.override is None
    assert result.commit_sha == "a" * 40
    assert result.toolchain == "python"


async def test_not_ready_opens_a_gate_that_approve_overrides():
    """Swap the build probe for one reporting an unbuildable repo."""
    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok("build_probe", 1,
                   {"buildable": Measurement.measured(0.0),
                    "runnable": Measurement.measured(0.0)})

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=acts):
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)

            async def pending():
                return await handle.query(TriageWorkflow.pending_decisions)

            while not await pending():
                await env.sleep(1)
            items = await pending()
            assert items[0].gate == "readiness"
            assert items[0].round == 1
            assert "not_ready" in items[0].spec_summary

            await handle.signal(TriageWorkflow.submit_gate_decision,
                                GateDecision(gate="readiness", round=1,
                                             outcome=GateOutcome.APPROVE,
                                             decided_by="human",
                                             reviewer="alice",
                                             comments="known, accepted"))
            result = await handle.result()

    assert result.readiness.verdict is Verdict.NOT_READY
    assert result.override is not None
    assert result.override.approved_by == "human"
    assert result.override.reviewer == "alice"
    assert result.override.reason == "known, accepted"


async def test_revise_re_runs_the_fan_out_at_round_two():
    """D9: 'I just deleted the committed .env -- look again.' The second round
    re-resolves the commit, so it legitimately describes a different tree."""
    shas = iter(["a" * 40, "b" * 40])

    @activity.defn(name="triage_resolve_commit")
    async def moving_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=next(shas), toolchain="python")

    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok("build_probe", 1,
                   {"buildable": Measurement.measured(0.0),
                    "runnable": Measurement.measured(0.0)})

    acts = [a for a in ACTIVITIES
            if a not in (fake_probe, fake_pin)] + [broken, moving_pin]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=acts):
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)

            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            await handle.signal(TriageWorkflow.submit_gate_decision,
                                GateDecision(gate="readiness", round=1,
                                             outcome=GateOutcome.REVISE,
                                             decided_by="human",
                                             comments="removed the .env"))

            items = []
            while not items or items[0].round != 2:
                await env.sleep(1)
                items = await handle.query(TriageWorkflow.pending_decisions)
            assert items[0].gate == "readiness"

            await handle.signal(TriageWorkflow.submit_gate_decision,
                                GateDecision(gate="readiness", round=2,
                                             outcome=GateOutcome.APPROVE,
                                             decided_by="human"))
            result = await handle.result()

    assert result.commit_sha == "b" * 40      # re-resolved, not the round-1 sha
    assert result.override.gate_round == 2


async def test_the_triage_query_serves_the_artifact():
    """D11: the workflow result plus this query ARE the record -- there is no
    durable store until a consumer needs one."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            await handle.result()
            served = await handle.query(TriageWorkflow.triage)
    assert served is not None
    assert served.commit_sha == "a" * 40
    assert served.readiness.verdict is Verdict.READY


async def test_the_cli_show_path_renders_json():
    """Review fix (critical). `sdlc triage show` crashed on every invocation:
    it queried by NAME, which carries no result type, so the converter returned
    a plain dict and `.model_dump_json()` was an AttributeError.

    This walks the CLI's exact path -- untyped handle, then the typed query --
    and renders, which is the step that used to blow up. The old test suite
    missed it because every other test queries via the METHOD, and the wiring
    test only grepped cli.py for strings.
    """
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=ACTIVITIES):
            wf_id = f"triage-{uuid.uuid4()}"
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=wf_id, task_queue=TASK_QUEUE)
            await handle.result()

            # get_workflow_handle, exactly as cli.py does -- an UNTYPED handle.
            cli_handle = env.client.get_workflow_handle(wf_id)
            by_name = await cli_handle.query("triage")
            report = await cli_handle.query(TriageWorkflow.triage)

    # The bug, pinned: querying by name really does yield an un-rendered dict.
    assert isinstance(by_name, dict)
    assert not hasattr(by_name, "model_dump_json")
    # The fix: the typed query renders.
    rendered = report.model_dump_json(indent=2)
    assert '"commit_sha"' in rendered
    assert "a" * 40 in rendered


async def test_a_human_approves_through_the_channel_transport():
    """Spec section 5: channels/transport.py resolves signals and queries BY
    NAME and imports nothing workflow-specific, so `sdlc approve --gate
    readiness` reaches a TriageWorkflow with no change to the channel layer.
    Checked here through the transport itself, not by grepping for a string."""
    from sdlc.channels.contract import Reply
    from sdlc.channels.transport import Selector, resolve, submit

    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok("build_probe", 1,
                   {"buildable": Measurement.measured(0.0),
                    "runnable": Measurement.measured(0.0)})

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=acts):
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            # transport.py:143,149 -- resolve narrows the selector to one
            # pending item, submit translates the reply to its signal.
            pending = await resolve(
                handle, Selector(reply_kind="gate", name="readiness"))
            out = await submit(handle, pending,
                               Reply(outcome=GateOutcome.APPROVE,
                                     text="accepted"))
            assert out.confirmed
            result = await handle.result()
    assert result.override is not None
    assert result.override.reason == "accepted"


async def test_reject_leaves_no_override():
    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok("build_probe", 1,
                   {"buildable": Measurement.measured(0.0),
                    "runnable": Measurement.measured(0.0)})

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=acts):
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            await handle.signal(TriageWorkflow.submit_gate_decision,
                                GateDecision(gate="readiness", round=1,
                                             outcome=GateOutcome.REJECT,
                                             decided_by="human",
                                             reviewer="alice"))
            result = await handle.result()
            status = await handle.query(TriageWorkflow.status)
    assert result.override is None
    assert status == "blocked:readiness"


async def test_a_failed_signal_does_not_fail_the_run():
    """D8: the other six still report."""
    @activity.defn(name="triage_secrets")
    async def boom(inp: TriageSignalInput) -> SignalResult:
        raise RuntimeError("worker died")

    acts = [a for a in ACTIVITIES if a is not fake_secrets] + [boom]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=acts):
            handle = await env.client.start_workflow(
                TriageWorkflow.run, TriageInput(repo_dir="/r"),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await handle.result()
    by_id = {s.signal: s for s in result.signals}
    assert by_id["secrets"].collected.state is CollectionState.NOT_COLLECTED
    assert "secrets activity failed" in by_id["secrets"].collected.reason
    assert len(by_id) == 7                            # the other six reported
    assert result.readiness.verdict is Verdict.READY   # unaffected dimensions


async def test_skipping_the_build_probe_yields_indeterminate():
    """D6: no gate is opened by the OFF policy, but the artifact still says
    the readiness dimensions were never measured, and why."""
    acts = [a for a in ACTIVITIES if a is not fake_probe]
    gates = GateSettings(gates={"readiness": GateConfig(policy=GatePolicy.OFF)})
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=acts):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r", build_probe=False, gates=gates),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            result = await handle.result()
    assert result.readiness.verdict is Verdict.INDETERMINATE
    probe = {s.signal: s for s in result.signals}["build_probe"]
    assert "--no-build-probe" in probe.collected.reason
    assert result.readiness.buildable.state is CollectionState.NOT_COLLECTED
    # OFF still records an override -- and says it was the policy, not a human.
    assert result.override is not None
    assert result.override.approved_by == "policy"
    assert result.override.reviewer is None


async def test_a_soft_policy_still_waits_for_a_human():
    """D10: triage produces no confidence, so a SOFT gate has nothing to
    auto-approve WITH. It degrades to HARD by _gate's existing logic -- no
    special case, but asserted so a future reader does not 'fix' it."""
    @activity.defn(name="triage_build_probe")
    async def broken(inp: TriageProbeInput) -> SignalResult:
        return _ok("build_probe", 1,
                   {"buildable": Measurement.measured(0.0),
                    "runnable": Measurement.measured(0.0)})

    acts = [a for a in ACTIVITIES if a is not fake_probe] + [broken]
    gates = GateSettings(
        gates={"readiness": GateConfig(policy=GatePolicy.SOFT)})
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[TriageWorkflow], activities=acts):
            handle = await env.client.start_workflow(
                TriageWorkflow.run,
                TriageInput(repo_dir="/r", gates=gates),
                id=f"triage-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            while not await handle.query(TriageWorkflow.pending_decisions):
                await env.sleep(1)
            # It waited rather than auto-approving: that is the assertion.
            assert await handle.query(TriageWorkflow.status) == \
                "awaiting:readiness"
            await handle.signal(TriageWorkflow.submit_gate_decision,
                                GateDecision(gate="readiness", round=1,
                                             outcome=GateOutcome.REJECT,
                                             decided_by="human"))
            await handle.result()
