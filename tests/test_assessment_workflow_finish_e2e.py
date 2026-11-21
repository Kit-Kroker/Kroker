"""E-51 (FR-918) end to end on the temporal tier: FINISH measured on the
clean admitted run, and FD13's all-degraded short-circuit.

The unit suite (tests/test_assessment_finish.py) composes the same artifacts
by hand; these two run Task 5's wiring end to end. test_finish_measured_e2e
drives the existing admitted-run e2e path -- real scan/discover/assess over
a real git tree, no proposers -- and pins the four static owed rows.
test_all_degraded_run_keeps_no_phases fails the tree resolver so scan,
discover and risk all report not_collected on an ADMITTED run, and pins
finish's guard: nothing to grade, no report, and a terminal status that
stays "admitted:no-phases-implemented". A measuring finish there would flip
NO_PHASES to PARTIAL -- a run that assessed nothing must not read as one
that assessed something (FD13).

FD16: evaluate_finish is an inline pure call, so neither test schedules a
workflow command the pre-E-51 corpus lacks -- tests/replay/ stays green
unchanged.

This module is deliberately a sibling of tests/test_assessment_workflow_e2e
rather than an extension of it: that file is over the 1000-line ceiling and
recorded in .file-size-baseline.json, and baselined files may shrink, never
grow (the ratchet, AGENTS.md). The harness -- the fake triage activities,
the real scan stubs, the assessed_repo fixture -- is imported from it
unchanged, pytestmark included.
"""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.assessment.activities import (
    AssessmentTree,
    AssessmentTreeInput,
    assess_risk,
    assessment_resolve_tree,
    discover_context,
    discover_finalize,
    discover_lock,
    discover_memo_load,
    discover_memo_store,
    load_blueprint,
    risk_memo_load,
    risk_memo_store,
    verify_discover_refs,
    verify_risk_refs,
)
from sdlc.assessment.finish.models import CRITERIA_MANIFEST
from sdlc.assessment.models import PARTIAL, PhaseId
from sdlc.measurement import CollectionState
from sdlc.triage.activities import TriagePin, TriagePinInput
from sdlc.workflows.assessment import AssessmentInput, AssessmentWorkflow
from tests.test_assessment_workflow_e2e import (
    ACTIVITIES,
    SCAN_ACTS,
    TASK_QUEUE,
    WORKFLOWS,
    fake_baseline,
    fake_deps,
    fake_misconfig,
    fake_outliers,
    fake_probe,
    fake_resolve_tree,
    fake_scaffold,
    fake_secrets,
)
from tests.test_assessment_workflow_e2e import assessed_repo as assessed_repo

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

# The four static owed rows on a clean admitted run (FD12/FD14): c07 defers
# to E-56 while the unified composites cannot exist, and c13 plus the
# report/generate exits are owed to E-52. Pinned verbatim -- wire strings,
# sorted, which is the order FinishReport's NFR-10 validator enforces.
KNOWN_OWED = (
    "c07_unified_drivers: deferred (E-56)",
    "c13_five_reports: not collected (E-52)",
    "exit:generate:seeds_emitted: not collected (E-52)",
    "exit:report:reports_emitted: not collected (E-52)",
)


async def test_finish_measured_e2e(assessed_repo, tmp_path, monkeypatch):
    """The clean admitted run's finish: all three producers measured, so
    evaluate_finish grades -- the finish row and Assessment.finish.collected
    are MEASURED, the twelve evaluable criteria evaluated, and owed is
    exactly the four static rows. Everything else is an evaluated row; a
    criterion that cannot be graded names its owner in `owed`, never a
    silent absence (FD3/FD11)."""
    repo_dir, sha = assessed_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    acts = [
        real_pin,
        fake_baseline,
        fake_scaffold,
        fake_probe,
        fake_secrets,
        fake_misconfig,
        fake_outliers,
        fake_deps,
        assessment_resolve_tree,
        *SCAN_ACTS,
        discover_context,
        discover_lock,
        discover_finalize,
        discover_memo_load,
        discover_memo_store,
        load_blueprint,
        verify_discover_refs,
        assess_risk,
        risk_memo_load,
        risk_memo_store,
        verify_risk_refs,
    ]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()

    assert result.admitted is True
    # scan, discover, assess and finish measured; report and generate are
    # still owed to E-52, so the status is partial, not assessed.
    assert result.terminal_status == PARTIAL
    finish_row = next(p for p in result.phases if p.phase is PhaseId.FINISH)
    assert finish_row.collected.state is CollectionState.MEASURED
    assert result.finish is not None
    assert result.finish.collected.state is CollectionState.MEASURED
    assert {c.name for c in result.finish.criteria} == set(CRITERIA_MANIFEST) - {
        "c07_unified_drivers",
        "c13_five_reports",
    }
    assert result.finish.owed == KNOWN_OWED


async def test_all_degraded_run_keeps_no_phases():
    """FD13 pinned end to end. The triage child admitted the repository (the
    fake probe reports buildable and runnable), then the tree resolver
    fails -- scan cannot resolve its tree, and discover and assess both
    degrade off it. Finish's short-circuit fires BEFORE evaluate_finish:
    with no producer measured there is nothing to grade, the finish row is
    not_collected, and no FinishReport exists. The terminal status stays
    "admitted:no-phases-implemented" -- pinned as the literal, not the
    constant, so a rename cannot drift the wire value."""

    @activity.defn(name="assessment_resolve_tree")
    async def failing_tree(inp: AssessmentTreeInput) -> AssessmentTree:
        raise ApplicationError("git unavailable", non_retryable=True)

    acts = [failing_tree if a is fake_resolve_tree else a for a in ACTIVITIES]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r"),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()

    assert result.admitted is True
    assert result.terminal_status == "admitted:no-phases-implemented"
    finish_row = next(p for p in result.phases if p.phase is PhaseId.FINISH)
    assert finish_row.collected.state is CollectionState.NOT_COLLECTED
    # FD13's short-circuit, not some other failure: the row names what is
    # missing -- nothing to grade.
    assert "nothing to grade" in finish_row.collected.reason
    for phase in (PhaseId.SCAN, PhaseId.DISCOVER, PhaseId.ASSESS):
        row = next(p for p in result.phases if p.phase is phase)
        assert row.collected.state is CollectionState.NOT_COLLECTED, phase
    # FD13's shape: a short-circuited finish ships no report, and a run that
    # assessed nothing ships no producer payload either.
    assert result.finish is None
    assert result.scan is None
    assert result.discover is None
    assert result.risk is None
