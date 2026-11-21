"""E-44. Pure helpers directly; sequencing through the workflow, following
tests/test_triage_workflow.py."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.converter import sdlc_data_converter
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    GatePolicy,
)
from sdlc.measurement import Measurement
from sdlc.triage.activities import (
    TriageDependencyInput,
    TriagePin,
    TriagePinInput,
    TriageProbeInput,
    TriageSignalInput,
)
from sdlc.triage.models import FixClass, SignalResult, TriageFinding, Verdict, finding_identity
from sdlc.vcs import VerifyBranchInput, VerifyResult
from sdlc.workflows.tidyup import (
    FixRunResult,
    TidyUpInput,
    TidyUpReport,
    TidyUpWorkflow,
    branches_to_verify,
    fix_workflow_id,
    reached_a_pr,
    triage_gates,
    unrecognized_selection,
)
from sdlc.workflows.triage import TriageWorkflow


def test_input_defaults():
    inp = TidyUpInput(repo_dir="/r")
    assert inp.commit == "HEAD"
    assert inp.build_probe is True
    assert inp.max_fix_runs == 10


def test_fix_cfg_disables_the_deploy_gate():
    """D9: feature.py opens the deploy gate BEFORE checking deploy.enabled,
    and the default policy is HARD -- so an unconfigured tidy-up PR would
    park for 48h on a deploy that was never going to run."""
    inp = TidyUpInput(repo_dir="/r")
    assert inp.fix_cfg.gates["deploy"].policy is GatePolicy.OFF
    assert inp.fix_cfg.deploy.enabled is False


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("deployed:https://example/pr/1", True),
        ("merged-not-deployed:https://example/pr/1", True),
        ("merged-not-deployed:skipped:benchmark-run-has-no-remote", True),
        ("rejected:merge:soft-verdict", False),
        ("rejected:plan", False),
        ("rejected:budget", False),
        ("failed:plan-validation:cycle", False),
        ("", False),
    ],
)
def test_reached_a_pr(outcome, expected):
    """D6 step 6: 'produced a branch worth merging' is read off the return
    string, which is the only thing the workflow gives a caller."""
    assert reached_a_pr(outcome) is expected


def test_branches_to_verify_keeps_accepted_order_and_drops_failures():
    runs = [
        FixRunResult(
            identity="a", workflow_id="w-fix-00", outcome="merged-not-deployed:u", branch="b0"
        ),
        FixRunResult(
            identity="b", workflow_id="w-fix-01", outcome="rejected:merge:soft-verdict", branch="b1"
        ),
        FixRunResult(identity="c", workflow_id="w-fix-02", outcome="deployed:u", branch="b2"),
    ]
    assert branches_to_verify(runs) == ["b0", "b2"]


def test_branches_to_verify_drops_a_run_with_no_branch():
    runs = [FixRunResult(identity="a", workflow_id="w", outcome="deployed:u", branch=None)]
    assert branches_to_verify(runs) == []


def test_fix_workflow_id_is_derived_and_stable():
    """D10: no uuid, no clock. Replay must produce the same id."""
    assert fix_workflow_id("tidyup-repo-x", 0) == "tidyup-repo-x-fix-00"
    assert fix_workflow_id("tidyup-repo-x", 7) == "tidyup-repo-x-fix-07"
    assert fix_workflow_id("tidyup-repo-x", 11) == "tidyup-repo-x-fix-11"


def test_report_defaults_are_honest_about_an_unmeasured_after():
    """TidyUpReport.before is required (a report always has a baseline); the
    after side is optional and None until the verification triage runs."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TidyUpReport(before=None, readiness_before=None)  # type: ignore[arg-type]


def test_before_triage_inherits_the_operators_gates():
    """The before-triage gates admission, so the operator's HARD readiness
    setting applies unchanged."""
    from sdlc.core.models import (
        GateConfig,
        GatePolicy,
        GateSettings,
    )

    hard = GateSettings(
        default_gate_policy=GatePolicy.HARD, gates={"readiness": GateConfig(policy=GatePolicy.HARD)}
    )
    assert triage_gates(hard, gating=True) is hard


def test_after_triage_never_parks_on_a_readiness_gate():
    """The after-triage only MEASURES the verification tree for the delta; it
    must not open a readiness gate and park 48h. With --no-build-probe the
    after-verdict is INDETERMINATE, which a HARD readiness gate would block
    on. OFF resolves automatically; the verdict is still recorded."""
    from sdlc.core.models import (
        GateConfig,
        GatePolicy,
        GateSettings,
    )

    hard = GateSettings(
        default_gate_policy=GatePolicy.HARD, gates={"readiness": GateConfig(policy=GatePolicy.HARD)}
    )
    after = triage_gates(hard, gating=False)
    assert after.default_gate_policy is GatePolicy.OFF


def test_unrecognized_selection_is_surfaced_not_dropped():
    """The CLI confirms the count it SENT; the workflow keeps only the subset
    in the backlog. The difference is surfaced in the report rather than
    dropped silently, so the two counts can be reconciled."""
    backlog = ["a", "b", "c"]
    assert unrecognized_selection(["a", "x", "y"], backlog) == ["x", "y"]


def test_unrecognized_selection_is_empty_when_no_signal_or_all_known():
    assert unrecognized_selection(None, ["a"]) == []
    assert unrecognized_selection(["a", "b"], ["a", "b"]) == []


# --- temporal half -----------------------------------------------------------

TASK_QUEUE = "tidyup-test"


def _mech_findings(n: int) -> list[TriageFinding]:
    return [
        TriageFinding(
            signal="secrets",
            rule=f"mech_rule_{i}",
            severity="high",
            detail=f"mechanical finding {i}",
            path=f"p{i}.py",
            fix_class=FixClass.MECHANICAL,
        )
        for i in range(n)
    ]


def _ok(signal: str, version: int, findings: list[TriageFinding] | None = None) -> SignalResult:
    return SignalResult(
        signal=signal,
        version=version,
        collected=Measurement.measured(0.0),
        findings=findings or [],
    )


def _triage_fakes(*, verdict: str, mechanical: int) -> list[Any]:
    probe = 1.0 if verdict == "ready" else 0.0

    @activity.defn(name="triage_resolve_commit")
    async def pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha="a" * 40, toolchain="python")

    @activity.defn(name="triage_baseline")
    async def baseline(inp: TriageSignalInput) -> SignalResult:
        return SignalResult(
            signal="baseline",
            version=2,
            collected=Measurement.measured(0.0),
            metrics={"tests_present": Measurement.measured(3.0)},
        )

    @activity.defn(name="triage_scaffold")
    async def scaffold(inp: TriageSignalInput) -> SignalResult:
        return SignalResult(
            signal="scaffold",
            version=1,
            collected=Measurement.measured(0.0),
            metrics={"structure_discernible": Measurement.measured(1.0)},
        )

    @activity.defn(name="triage_build_probe")
    async def build_probe(inp: TriageProbeInput) -> SignalResult:
        return SignalResult(
            signal="build_probe",
            version=1,
            collected=Measurement.measured(0.0),
            metrics={
                "buildable": Measurement.measured(probe),
                "runnable": Measurement.measured(probe),
            },
        )

    @activity.defn(name="triage_secrets")
    async def secrets(inp: TriageSignalInput) -> SignalResult:
        return _ok("secrets", 3, _mech_findings(mechanical))

    @activity.defn(name="triage_misconfig")
    async def misconfig(inp: TriageSignalInput) -> SignalResult:
        return _ok("misconfig", 1)

    @activity.defn(name="triage_outliers")
    async def outliers(inp: TriageSignalInput) -> SignalResult:
        return _ok("outliers", 1)

    @activity.defn(name="triage_dependencies")
    async def dependencies(inp: TriageDependencyInput) -> SignalResult:
        return SignalResult(
            signal="dependencies",
            version=2,
            collected=Measurement.not_collected("advisory source is none (not configured)"),
        )

    return [pin, baseline, scaffold, build_probe, secrets, misconfig, outliers, dependencies]


# D8 read-once, deterministically: the first fix run parks on the barrier,
# which it can only reach AFTER the parent computed `accepted` at the gate
# decision -- so a selection the test sends while it is parked provably lands
# after the decision, mid-fix-loop, and must not change what ran.
_HOLD_FIX_RUN = False
_BARRIER_ENTERED = asyncio.Event()
_BARRIER_RELEASE = asyncio.Event()


@activity.defn
async def _stub_fix_run_barrier() -> str:
    """The park the first fix run waits on when the scenario holds it."""
    _BARRIER_ENTERED.set()
    await _BARRIER_RELEASE.wait()
    return "released"


@workflow.defn(name="GraphWorkflow", sandboxed=False)
class _StubFixRun:
    """Shadows the pipeline child by wire name (cf. tests/test_pools_routing.py
    _StubGraphChild; unsandboxed like tests/graph_workflow
    test_pipeline_child_upgrade.py's stub, so the barrier events below are the
    test's own). Since E-74 fix runs are GraphWorkflow children."""

    @workflow.run
    async def run(self, run_input: Any) -> str:
        if _HOLD_FIX_RUN:
            await workflow.execute_activity(
                _stub_fix_run_barrier, start_to_close_timeout=timedelta(minutes=5)
            )
        return "merged-not-deployed:stub"


@activity.defn(name="build_verification_branch")
async def _fake_verify(inp: VerifyBranchInput) -> VerifyResult:
    return VerifyResult(
        ref=f"{inp.tidyup_id}-verify",
        head_sha="b" * 40,
        merged=list(inp.branches),
        conflicted=[],
    )


async def _run_tidyup(
    *,
    verdict: str = "ready",
    mechanical: int,
    select: list[str] | None = None,
    select_after_decision: list[str] | None = None,
    max_fix_runs: int = 10,
    hold_fix_run: bool = False,
) -> TidyUpReport:
    global _HOLD_FIX_RUN
    _HOLD_FIX_RUN = hold_fix_run
    _BARRIER_ENTERED.clear()
    _BARRIER_RELEASE.clear()
    try:
        async with await WorkflowEnvironment.start_time_skipping(
            data_converter=sdlc_data_converter
        ) as env:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[TidyUpWorkflow, TriageWorkflow, _StubFixRun],
                activities=[
                    *_triage_fakes(verdict=verdict, mechanical=mechanical),
                    _fake_verify,
                    _stub_fix_run_barrier,
                ],
            ):
                handle = await env.client.start_workflow(
                    TidyUpWorkflow.run,
                    TidyUpInput(repo_dir="/r", max_fix_runs=max_fix_runs),
                    id=f"tidyup-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )
                if verdict == "ready":
                    while not await handle.query(TidyUpWorkflow.pending_decisions):
                        await env.sleep(1)
                    if select is not None:
                        await handle.signal(TidyUpWorkflow.select_items, select)
                    await handle.signal(
                        TidyUpWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="tidy_up",
                            round=1,
                            outcome=GateOutcome.APPROVE,
                            decided_by="human",
                        ),
                    )
                    if select_after_decision is not None:
                        # Parked child == parent committed to its accepted set.
                        # Wait bounded so a workflow that died before the
                        # barrier fails the test instead of hanging it.
                        await asyncio.wait_for(_BARRIER_ENTERED.wait(), timeout=60)
                        await handle.signal(TidyUpWorkflow.select_items, select_after_decision)
                        _BARRIER_RELEASE.set()
                return await handle.result()
    finally:
        _HOLD_FIX_RUN = False


_IDS = [finding_identity(f) for f in _mech_findings(3)]
FIRST, SECOND, THIRD = _IDS


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_not_admitted_returns_the_backlog_and_starts_no_fix_runs():
    """D7: not admitted is not empty-handed. The backlog IS US-8's checkable
    hygiene list, and it lands even when nothing is fixed."""
    report = await _run_tidyup(verdict="not_ready", mechanical=2)
    assert len(report.backlog) == 2
    assert report.accepted == [] and report.runs == []
    # Non-vacuous: one unverifiable delta PER backlog finding, and the report
    # is honest that nothing was measured after.
    assert len(report.deltas) == 2
    assert all(d.state.value == "unverifiable" for d in report.deltas)
    assert report.after is None and report.verify_ref is None


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_select_items_narrows_the_accepted_set():
    """D8: a signal for content, a gate for the decision."""
    report = await _run_tidyup(verdict="ready", mechanical=3, select=[SECOND])
    assert len(report.accepted) == 1 and report.accepted == [SECOND]
    # The fix half really ran, reached its PR, and was verified.
    assert [r.identity for r in report.runs] == report.accepted
    assert all(reached_a_pr(r.outcome) and r.merged_into_verify for r in report.runs)
    assert report.verify_ref is not None and report.after is not None
    assert report.readiness_after is Verdict.READY
    assert len(report.deltas) == len(report.backlog)


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_a_signal_after_the_gate_resolves_does_not_change_what_ran():
    """D8: selection is read once, at decision time. The first fix run parks
    on a barrier it can only reach AFTER `accepted` was computed, so the late
    selection provably lands mid-fix-loop -- and must change nothing."""
    report = await _run_tidyup(
        verdict="ready",
        mechanical=2,
        select_after_decision=[FIRST],
        hold_fix_run=True,
    )
    assert len(report.accepted) == 2
    assert [r.identity for r in report.runs] == report.accepted
    assert all(reached_a_pr(r.outcome) and r.merged_into_verify for r in report.runs)
    assert report.verify_ref is not None and report.after is not None
    assert report.readiness_after is Verdict.READY
    assert len(report.deltas) == len(report.backlog)
    # The late signal was consumed by the handler (a backlog identity, so
    # nothing unrecognized) and still changed nothing.
    assert report.unrecognized == []


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_max_fix_runs_defers_the_excess_with_the_reason_recorded():
    report = await _run_tidyup(verdict="ready", mechanical=3, max_fix_runs=2)
    assert len(report.runs) == 2 and len(report.deferred) == 1 and report.deferred == [THIRD]
    # The two runs that were admitted really ran, reached their PRs, and the
    # composite verification re-triage happened over their branches.
    assert [r.identity for r in report.runs] == report.accepted
    assert all(reached_a_pr(r.outcome) and r.merged_into_verify for r in report.runs)
    assert report.verify_ref is not None and report.after is not None
    assert report.readiness_after is Verdict.READY
    assert len(report.deltas) == len(report.backlog)


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_an_unrecognized_selection_is_surfaced_end_to_end_not_dropped():
    """D8: identities sent via select_items that are not in the backlog land in
    report.unrecognized; the recognized ones still narrow the accepted set."""
    report = await _run_tidyup(verdict="ready", mechanical=2, select=[FIRST, "not-in-backlog"])
    assert report.unrecognized == ["not-in-backlog"]
    assert report.accepted == [FIRST]
    assert [r.identity for r in report.runs] == report.accepted
    assert all(reached_a_pr(r.outcome) and r.merged_into_verify for r in report.runs)
    assert report.verify_ref is not None and report.after is not None
    assert report.readiness_after is Verdict.READY
    assert len(report.deltas) == len(report.backlog)
