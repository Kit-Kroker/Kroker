"""C8: the task layer records what each lens did, and stops reading None as
approval. Ruling OQ1: none of this blocks the done path."""

from unittest.mock import AsyncMock, patch

import pytest
from test_code_slice_contract import _StubCtx  # same stub the slice tests use

from sdlc.core.models import GateDecision, GateOutcome, HarnessKind, PipelineConfig
from sdlc.harness.models import HarnessRunResult
from sdlc.stages import code
from sdlc.stages.plan.models import DevTask, ValidationContract
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.lenses import LensPresence
from sdlc.stages.review.models import DeepReviewReport, ReviewFinding, ReviewReport

# Absolute, not relative: there is no tests/__init__.py and pytest runs in
# prepend import mode, so test modules are top-level. This is the repo's own
# sibling-import idiom (tests/test_memory_wiring.py:14 and four others).


def _presence(tr, lens):
    return {o.lens: o.presence for o in tr.lens_outcomes}[lens]


def _task(task_id):
    return DevTask(
        id=task_id,
        title="Implement feature",
        description="Write code",
        role="dev",
        acceptance_criteria=["Tests pass"],
        files_hint=["app.py"],
    )


def _run():
    return HarnessRunResult(
        harness=HarnessKind.CLAUDE_CODE,
        exit_code=0,
        commit_sha="c1",
        cost_usd=0.5,
        summary="success",
    )


@pytest.mark.asyncio
async def test_adversary_failure_is_tombstoned_and_does_not_block_done():
    """REVIEW-1.3 stands: the lens stays fail-open. What changes is that its
    absence is no longer spelled the same as its approval."""
    ctx = _StubCtx()
    cfg = PipelineConfig(adversarial_review_enabled=True)
    task = _task("task-adv-raise")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = ReviewReport(approve=True)
        mock_adv.return_value = None  # the runner's fail-open leg
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=object(),
            adversary_agent=object(),
        )

    assert tr.status == "done"
    assert _presence(tr, "adversary") is LensPresence.UNDECLARED_ABSENT
    assert _presence(tr, "reviewer") is LensPresence.PRESENT


@pytest.mark.asyncio
async def test_disabled_adversary_is_declared_absent():
    ctx = _StubCtx()
    cfg = PipelineConfig(adversarial_review_enabled=False)
    task = _task("task-adv-off")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = ReviewReport(approve=True)
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=object(),
            adversary_agent=None,
        )

    assert tr.status == "done"
    assert _presence(tr, "adversary") is LensPresence.DECLARED_ABSENT


@pytest.mark.asyncio
async def test_adversary_runs_when_the_primary_is_disabled():
    """Regression for the compound guard at code/step.py:802. 'No primary,
    adversary only' used to run NO lens at all -- the operator enabled a lens
    that silently never executed."""
    ctx = _StubCtx()
    cfg = PipelineConfig(review_enabled=False, adversarial_review_enabled=True)
    task = _task("task-no-primary")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = None  # review_enabled=False
        mock_adv.return_value = ReviewReport(approve=True)
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=None,
            adversary_agent=object(),
        )

    assert mock_adv.await_count == 1, "the adversary must run without a primary"
    assert tr.status == "done"
    assert _presence(tr, "reviewer") is LensPresence.DECLARED_ABSENT
    assert _presence(tr, "adversary") is LensPresence.PRESENT


@pytest.mark.asyncio
async def test_blocking_adversary_rejection_still_bites_without_a_primary():
    """Test above pins that the adversary RUNS on the new path; this pins that
    its rejection still routes to the fix loop there."""
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(
                gate="task:task-adv-blocks", outcome=GateOutcome.REJECT, decided_by="human"
            )
        ]
    )
    cfg = PipelineConfig(review_enabled=False, adversarial_review_enabled=True, max_fix_attempts=1)
    task = _task("task-adv-blocks")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("sdlc.stages.code.step._run_handoff", new_callable=AsyncMock) as mock_ho,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        mock_qa.return_value = QAReport(tests_passed=True, issues=[])
        mock_rev.return_value = None
        mock_adv.return_value = ReviewReport(
            approve=False,
            findings=[ReviewFinding(assertion="a1", severity="critical", detail="unsafe")],
        )
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        mock_ho.return_value = None
        # budget = cfg.max_fix_attempts + 1 = 2 (code/step.py:535), and the
        # blocking adversary rejection puts non-empty issues in the fix loop
        # (_fix_loop_issues unions the adversary's blocking findings), so a
        # SECOND attempt runs before the gate. Each attempt consumes two
        # execute_activity side effects -- run_test_suite then get_task_diff --
        # so four entries are required. Same shape as the repo's own
        # quarantine-path tests (test_code_slice_contract.py:277-282, :394-399).
        mock_act.side_effect = [
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
            QAReport(tests_passed=True, issues=[]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=None,
            adversary_agent=object(),
        )

    assert tr.status == "quarantined"
    assert _presence(tr, "adversary") is LensPresence.PRESENT


@pytest.mark.asyncio
async def test_unreached_adversary_is_not_reached_not_undeclared_absent():
    """Reviewer A1: the adversary's run site sits inside the approving block,
    so a task that never gets there never reached its lens. That is routine
    pipeline geometry, not broken wiring -- typing it NOT_REACHED is what keeps
    UNDECLARED_ABSENT meaning 'enabled, reached, and the wiring broke'."""
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(gate="task:task-unreached", outcome=GateOutcome.REJECT, decided_by="human")
        ]
    )
    cfg = PipelineConfig(adversarial_review_enabled=True, max_fix_attempts=1)
    task = _task("task-unreached")

    with (
        patch("sdlc.stages.code.step._execute_coding_task", new_callable=AsyncMock) as mock_exec,
        patch("sdlc.stages.code.step.qa_step", new_callable=AsyncMock) as mock_qa,
        patch("sdlc.stages.review.step.step", new_callable=AsyncMock) as mock_rev,
        patch("sdlc.stages.code.step._run_adversary", new_callable=AsyncMock) as mock_adv,
        patch("sdlc.stages.code.step._run_deep_review", new_callable=AsyncMock) as mock_deep,
        patch("temporalio.workflow.execute_activity", new_callable=AsyncMock) as mock_act,
    ):
        mock_exec.return_value = _run()
        # tests fail -> task_passed is False -> the approving block is skipped
        mock_qa.return_value = QAReport(tests_passed=False, issues=["boom"])
        mock_rev.return_value = ReviewReport(approve=True)
        mock_deep.return_value = DeepReviewReport(approve=True, summary="LGTM")
        # Failing QA gives the fix loop non-empty issues, so a second attempt
        # runs before the budget-exhausted gate: four side effects, two per
        # attempt (test_code_slice_contract.py:277-282 is the same shape).
        mock_act.side_effect = [
            QAReport(tests_passed=False, issues=["boom"]),
            {"files": ["app.py"]},
            QAReport(tests_passed=False, issues=["boom"]),
            {"files": ["app.py"]},
        ]

        tr = await code.step(
            ctx,
            cfg=cfg,
            task=task,
            contract=ValidationContract(task_id=task.id, assertions=["Tests pass"]),
            worktree="/worktree",
            notes=["Note 1"],
            dev_agent=None,
            crew_layout=None,
            branch="feature-1",
            reviewer_agent=object(),
            adversary_agent=object(),
        )

    assert tr.status == "quarantined"
    assert mock_adv.await_count == 0
    assert _presence(tr, "adversary") is LensPresence.NOT_REACHED
    assert _presence(tr, "reviewer") is LensPresence.PRESENT


def test_classifier_is_invoked_with_the_runners_own_predicate_facts():
    """C8 spec 3.2: if a call site classifies from facts other than the ones
    the runner's pre-check reads, the tombstone can drift away from what
    actually gated the run -- the quintuplicated-predicate failure, one layer
    down."""
    import pathlib

    src = pathlib.Path("src/sdlc/stages/code/step.py").read_text(encoding="utf-8")
    assert src.count("enabled=cfg.adversarial_review_enabled") == 2, (
        "both adversary classify_lens sites read the runner's own flag"
    )
    assert src.count("agent_present=adversary_agent is not None") == 2
    assert "enabled=cfg.review_enabled" in src
    assert "agent_present=reviewer_agent is not None" in src
