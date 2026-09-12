"""DS7/DS10: the four absolute checks, built from scoped reports, fail closed."""

import ast
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.core.models import IdeaBrief, PipelineConfig, ProjectMode
from sdlc.measurement import CollectionState, Measurement
from sdlc.stages import merge
from sdlc.stages.merge.activities import IntegrationChecks
from sdlc.stages.merge.models import (
    CoverageReport,
    LintFinding,
    ScopedLintReport,
    ScopedTestReport,
)
from sdlc.stages.merge.step import lint_check, security_checks, tests_check
from sdlc.stages.qa.models import QAReport, ScopedSecurityReport, SecurityFinding
from sdlc.vcs import BaseWorktree
from sdlc.workflows.models import TaskResult
from tests.merge.test_merge_slice_contract import _lenses_ran, _StubCtx

M, NC = CollectionState.MEASURED, CollectionState.NOT_COLLECTED
CRIT = SecurityFinding(
    severity="critical", rule="dangerous-eval", detail="d", path="a.py", line="x"
)


def test_clean_deltas_pass_and_report_pre_existing_counts():
    t = tests_check(ScopedTestReport(state=M, preexisting=["t::a"]))
    lint = lint_check(ScopedLintReport(state=M, preexisting=7))
    col, crit = security_checks(ScopedSecurityReport(state=M, preexisting=4))
    assert t.passed and lint.passed and col.passed and crit.passed
    assert "1 pre-existing" in t.detail and "7 pre-existing" in lint.detail
    assert "4 pre-existing" in crit.detail


def test_introduced_findings_fail_and_are_named():
    t = tests_check(ScopedTestReport(state=M, introduced=["tests/t.py::t"], head_failed=1))
    lint = lint_check(
        ScopedLintReport(
            state=M, introduced=[LintFinding(rule="F401", path="a.py", line="import os")]
        )
    )
    _, crit = security_checks(ScopedSecurityReport(state=M, introduced=[CRIT]))
    assert not t.passed and "tests/t.py::t" in t.detail
    assert not lint.passed and "F401" in lint.detail
    assert not crit.passed and "a.py" in crit.detail


def test_lint_detail_reports_policy_relaxation():
    lint = lint_check(
        ScopedLintReport(state=M, policy_paths_changed=["ruff.toml"], suppressions_added=2)
    )
    assert lint.passed
    assert "1 policy path(s) changed" in lint.detail and "2 suppression(s) added" in lint.detail


def test_not_collected_fails_closed_and_no_critical_passes_vacuously():
    assert not tests_check(ScopedTestReport(state=NC, reason="r")).passed
    assert not lint_check(ScopedLintReport(state=NC, reason="r")).passed
    col, crit = security_checks(ScopedSecurityReport(state=NC, reason="base lock"))
    assert not col.passed and "base lock" in col.detail
    assert crit.passed  # vacuous by design: security_scan_collected carries the failure


def _results():
    return [
        TaskResult(
            task_id="t1",
            status="done",
            attempts=1,
            branch="b",
            qa=QAReport(tests_passed=True),
            lens_outcomes=_lenses_ran(),
        )
    ]


@pytest.mark.clause("MERGE-1.2")
@pytest.mark.clause("MERGE-1.10")
@pytest.mark.asyncio
async def test_an_unmaterialized_base_is_terminal_through_the_real_gate():
    """Failure-modes row 1, end to end through step and the REAL evaluate_gate."""
    ctx = _StubCtx()
    idea = IdeaBrief(title="F", description="d", repo_url="/r", mode=ProjectMode.BROWNFIELD)
    base = BaseWorktree(path=None, reason="WinError 32 lock")
    ichecks = IntegrationChecks(
        toolchain="python",
        lint=ScopedLintReport(state=NC, reason="base not materialized: WinError 32 lock"),
        tests=ScopedTestReport(state=NC, reason="base not materialized: WinError 32 lock"),
    )
    sec = ScopedSecurityReport(state=NC, reason="base not materialized: WinError 32 lock")
    with (
        patch(
            "sdlc.stages.merge.step.prepare_base_worktree", new=AsyncMock(return_value=base)
        ) as prep,
        patch("sdlc.stages.merge.step.run_integration_checks", new=AsyncMock(return_value=ichecks)),
        patch("sdlc.stages.merge.step.scoped_security_scan", new=AsyncMock(return_value=sec)),
        patch(
            "sdlc.stages.merge.step.measure_coverage",
            new=AsyncMock(return_value=CoverageReport(coverage=Measurement.not_collected("x"))),
        ),
    ):
        res = await merge.step(
            ctx,
            cfg=PipelineConfig(),
            task_results=_results(),
            integration_wt="/wt",
            idea=idea,
            base_sha="abc123",
        )
    assert res.startswith("rejected:merge:absolute-gate-failed:")
    for name in ("build_integration_green", "lint_clean", "security_scan_collected"):
        assert name in res
    assert ctx.gates_called == []
    assert prep.call_args.args[0].base_sha == "abc123"


def test_step_measures_base_first_and_uses_only_the_scoped_scan():
    tree = ast.parse(pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "step")
    calls = sorted(
        (
            c
            for c in ast.walk(fn)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == "_exec_activity"
        ),
        key=lambda c: (c.lineno, c.col_offset),
    )
    order = [c.args[0].id for c in calls if isinstance(c.args[0], ast.Name)]
    assert order.index("prepare_base_worktree") < order.index("run_integration_checks")
    assert order.index("scoped_security_scan") < order.index("evaluate_gate")
    assert "security_scan" not in order
