"""026 T016 (FR-010/011, research R4 part 4, data-model): per-task lint in the
fix loop, driven through the REAL code.step.

Contract (T016 implements):
- run_test_suite gets QAInput(lint_base=<branch_point>,
  lint_key=f"{workflow_id}/base-{task.id}", lint_report_only=<fence globs on a
  containment repair attempt, else []>).
- task_passed also requires attempt_failure._lint_ok(qa_raw, report_only):
  the lint delta, minus report-only paths, must be empty. NOT_COLLECTED and
  lint None never fail a task.
- A failed lint delta feeds the next attempt's prompt: the header
  "lint findings introduced by this task (the merge gate's own check):"
  then one "RULE path: line" per finding, capped at 25 with "(+N more)".
- The QA record's outcome ignores lint; the CODE record carries the verdict.
- Clean-context prompts (qa, review) never see the lint payload.

Harness: copied from tests/code/test_attempt_records.py (the fake workflow
namespace with a +100 s clock, and the fake ctx that captures real records).
Extended with a queue of QA reports, captured activity inputs, and captured
role prompts.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from temporalio import workflow as real_workflow

code_step = importlib.import_module("sdlc.stages.code.step")
from sdlc.benchmarks.models import BenchmarkOutcome, QualityScore
from sdlc.core.models import GateOutcome, HarnessKind, PipelineConfig, RoleConfig
from sdlc.harness.models import HarnessRunResult
from sdlc.measurement import CollectionState
from sdlc.stages.code.activities import DriftGlobs
from sdlc.stages.plan.models import DevTask
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import ReviewReport
from sdlc.stages.review.step import _get_qa_raw_json
from sdlc.toolchain.lint_scope import LintFinding, ScopedLintReport
from sdlc.vcs import CodeArtifact, DriftReport

_BASE = datetime(2026, 7, 4, 10, tzinfo=UTC)
HEADER = "lint findings introduced by this task (the merge gate's own check):"
LINT_KEY = "wf-t016/base-t1"


# --- harness (copied from test_attempt_records.py, extended) ------------------


class _FakeWorkflow:
    """The slice of temporalio.workflow the code step touches. Activity answers
    are scripted: run_test_suite pops `qa_reports` in order and repeats the
    last one; every activity input is captured for assertions."""

    def __init__(self, qa_reports, fence=("tests/**",)) -> None:
        self._t = 0
        self._qa = list(qa_reports)
        self._fence = list(fence)
        self.qa_inputs: list = []
        self.coding_inputs: list = []

    # delegate the sandbox marker and config class to the real module
    unsafe = real_workflow.unsafe
    ActivityConfig = staticmethod(real_workflow.ActivityConfig)
    logger = logging.getLogger("t016-fake-workflow")

    def now(self):
        self._t += 100
        return _BASE + timedelta(seconds=self._t)

    def info(self):
        return SimpleNamespace(workflow_id="wf-t016")

    async def execute_activity(self, fn, arg=None, **kw):
        name = fn.__name__
        if name == "run_coding_task":
            self.coding_inputs.append(arg)
            return HarnessRunResult(
                harness=HarnessKind.CLAUDE_CODE,
                exit_code=0,
                summary="ok",
                commit_sha="c" * 40,
                cost_usd=0.01,
            )
        if name == "run_test_suite":
            self.qa_inputs.append(arg)
            report = self._qa.pop(0) if len(self._qa) > 1 else self._qa[0]
            return report.model_copy(deep=True)
        if name == "get_task_diff":
            return CodeArtifact(files=["app.py"], stat="app.py | 1 +", patch_ref=None)
        if name == "load_drift_globs":
            return DriftGlobs(fence=list(self._fence), report=[])
        if name == "check_test_drift":
            return DriftReport()
        raise AssertionError(f"unexpected activity {name}")


class _FakeCtx:
    """Captures real BenchmarkRecords via ctx.record and every role prompt via
    run_role. The gate rejects, so an exhausted loop returns instead of
    waiting on a human."""

    def __init__(self) -> None:
        self.records = []
        self.role_prompts: list[tuple[str, str]] = []

    def emit(self, kind, **kw):
        # step.py calls ctx.emit WITHOUT await (code/step.py:563, usage.py:42)
        pass

    async def record(self, cfg, rec):
        self.records.append(rec)

    async def judge(self, cfg, artifact, stage, **kw):
        return QualityScore(score=None, judge="llm_judge")

    async def run_role(self, cfg, role, model, agent, prompt, into=None):
        self.role_prompts.append((role, prompt))
        if role == "qa":
            return SimpleNamespace(output=QAReport(tests_passed=True, failing_tests=[], issues=[]))
        if role == "reviewer":
            return SimpleNamespace(output=ReviewReport(approve=True))
        raise AssertionError(f"unexpected role {role}")

    async def gate(self, name, settings, **kw):
        return SimpleNamespace(
            approved=False,
            outcome=GateOutcome.REJECT,
            comments="gate says no",
            guidance="",
            decided_by="human",
            thaw_tests=False,
        )

    async def retain(self, *a, **k):
        pass


def _cfg(*, max_fix_attempts=1, containment=False) -> PipelineConfig:
    return PipelineConfig(
        roles={"dev": RoleConfig(harness=HarnessKind.CLAUDE_CODE, model="test-model")},
        max_fix_attempts=max_fix_attempts,
        containment_enabled=containment,
    )


def _task() -> DevTask:
    return DevTask(id="t1", title="T", description="D", acceptance_criteria=["ac1"])


def _run(monkeypatch, qa_reports, *, cfg=None, branch_point="bp-123"):
    fake_wf = _FakeWorkflow(qa_reports)
    monkeypatch.setattr(code_step, "workflow", fake_wf)
    ctx = _FakeCtx()
    result = asyncio.run(
        code_step.step(
            ctx,
            cfg=cfg or _cfg(),
            task=_task(),
            worktree="/tmp/wt",
            branch="b",
            branch_point=branch_point,
            qa_agent=SimpleNamespace(),
            reviewer_agent=SimpleNamespace(),
            adversary_agent=None,
            deep_review_agent=None,
            handoff_agent=None,
        )
    )
    return result, ctx, fake_wf


def _by_stage(ctx):
    out: dict[str, list] = {}
    for r in ctx.records:
        out.setdefault(r.stage, []).append(r)
    return out


# --- fixtures for reports ------------------------------------------------------


def _finding(path="app.py", rule="I001", line="import os") -> LintFinding:
    return LintFinding(rule=rule, path=path, line=line)


def _lint(introduced=(), state=CollectionState.MEASURED, reason="") -> ScopedLintReport:
    return ScopedLintReport(state=state, reason=reason, introduced=list(introduced))


def _qa(*, lint=None, tests_passed=True, issues=()) -> QAReport:
    return QAReport(
        tests_passed=tests_passed,
        failing_tests=[],
        issues=list(issues),
        lint=lint,
    )


CLEAN = _qa()
TESTS_FAIL = _qa(tests_passed=False, issues=["boom"])


# --- (A1) what run_test_suite is asked to lint --------------------------------


def test_run_test_suite_receives_the_lint_base_and_key(monkeypatch):
    _, _, wf = _run(monkeypatch, [CLEAN], branch_point="bp-123")
    assert len(wf.qa_inputs) == 1
    qa_in = wf.qa_inputs[0]
    assert qa_in.lint_base == "bp-123"
    assert qa_in.lint_key == LINT_KEY
    assert qa_in.lint_report_only == []  # attempt 1 is never a repair attempt


def test_repair_attempt_passes_the_fence_as_report_only(monkeypatch):
    cfg = _cfg(max_fix_attempts=1, containment=True)
    _, _, wf = _run(monkeypatch, [TESTS_FAIL, CLEAN], cfg=cfg)
    assert [q.lint_report_only for q in wf.qa_inputs] == [[], ["tests/**"]]


# --- (A2) a dirty lint delta fails the attempt and feeds the retry ----------


def test_introduced_finding_fails_the_attempt_and_the_retry_carries_it(monkeypatch):
    dirty = _qa(lint=_lint([_finding()]))
    _, ctx, wf = _run(monkeypatch, [dirty])
    recs = _by_stage(ctx)
    assert recs["code"][0].outcome is BenchmarkOutcome.FAIL
    assert len(wf.coding_inputs) == 2, "a lint-only failure must trigger a second attempt"
    prompt = wf.coding_inputs[1].prompt
    assert HEADER in prompt
    assert prompt.index(HEADER) < prompt.index("I001 app.py: import os")


def test_lint_block_lists_25_findings_then_the_remainder(monkeypatch):
    findings = [_finding(path=f"m{i}.py", line=f"import m{i}") for i in range(30)]
    dirty = _qa(lint=_lint(findings))
    _, _, wf = _run(monkeypatch, [dirty])
    prompt = wf.coding_inputs[1].prompt
    assert HEADER in prompt
    listed = re.findall(r"^I001 m\d+\.py: import m\d+$", prompt, flags=re.MULTILINE)
    assert len(listed) == 25
    assert "I001 m0.py: import m0" in listed
    assert "I001 m24.py: import m24" in listed
    assert "I001 m25.py: import m25" not in prompt
    assert "(+5 more)" in prompt


# --- (b) no lint, not collected, or report-only: the task still passes ------


@pytest.mark.parametrize(
    "lint",
    [
        pytest.param(None, id="lint_none"),
        pytest.param(
            _lint(state=CollectionState.NOT_COLLECTED, reason="base not materialized"),
            id="not_collected_with_reason",
        ),
    ],
)
def test_lint_none_or_not_collected_never_fails_the_task(monkeypatch, lint):
    result, ctx, wf = _run(monkeypatch, [_qa(lint=lint)])
    assert len(wf.coding_inputs) == 1
    assert _by_stage(ctx)["code"][0].outcome is BenchmarkOutcome.PASS
    assert result.status == "done"


def test_report_only_introduced_findings_do_not_fail_a_repair_attempt(monkeypatch):
    cfg = _cfg(max_fix_attempts=1, containment=True)
    fenced_only = _qa(lint=_lint([_finding(path="tests/test_x.py", rule="F401", line="import re")]))
    result, ctx, wf = _run(monkeypatch, [TESTS_FAIL, fenced_only], cfg=cfg)
    assert len(wf.coding_inputs) == 2, "report-only findings must not force a third attempt"
    code = _by_stage(ctx)["code"]
    assert code[-1].outcome is BenchmarkOutcome.PASS
    assert result.status == "done"


# --- (c) the QA record ignores lint; the code record carries it -------------


def test_qa_record_ignores_lint_while_the_code_record_fails(monkeypatch):
    dirty = _qa(lint=_lint([_finding()]))
    _, ctx, _ = _run(monkeypatch, [dirty], cfg=_cfg(max_fix_attempts=0))
    recs = _by_stage(ctx)
    assert recs["qa"][0].outcome is BenchmarkOutcome.PASS
    assert recs["code"][0].outcome is BenchmarkOutcome.FAIL


# --- (d) clean-context prompts never see lint --------------------------------

SECRET = ("ZZ999", "lintonly.py", "marker-line-xyz")


def test_qa_and_review_prompts_never_carry_the_lint_payload(monkeypatch):
    rule, path, line = SECRET
    dirty = _qa(lint=_lint([_finding(path=path, rule=rule, line=line)]))
    _, ctx, _ = _run(monkeypatch, [dirty], cfg=_cfg(max_fix_attempts=0))
    prompts = dict(ctx.role_prompts)
    assert "qa" in prompts and "reviewer" in prompts
    for role in ("qa", "reviewer"):
        for needle in SECRET:
            assert needle not in prompts[role], (role, needle)
        assert '"lint"' not in prompts[role], role


def test_review_qa_json_excludes_the_lint_payload():
    rule, path, line = SECRET
    text = _get_qa_raw_json(_qa(lint=_lint([_finding(path=path, rule=rule, line=line)])))
    assert '"lint"' not in text
    for needle in SECRET:
        assert needle not in text


# --- (A3) the attempt-failure predicate ---------------------------------------


def test_lint_ok_when_lint_is_absent():
    from sdlc.stages.code.attempt_failure import _lint_ok

    assert _lint_ok(_qa(lint=None), []) is True


def test_lint_ok_when_not_collected_with_a_reason():
    from sdlc.stages.code.attempt_failure import _lint_ok

    lint = _lint(state=CollectionState.NOT_COLLECTED, reason="lint tool failed")
    assert _lint_ok(_qa(lint=lint), []) is True


def test_lint_ok_when_measured_with_nothing_introduced():
    from sdlc.stages.code.attempt_failure import _lint_ok

    assert _lint_ok(_qa(lint=_lint([])), []) is True


def test_lint_fails_when_an_introduced_finding_is_not_report_only():
    from sdlc.stages.code.attempt_failure import _lint_ok

    assert _lint_ok(_qa(lint=_lint([_finding()])), []) is False


def test_lint_ok_when_every_introduced_path_is_report_only():
    from sdlc.stages.code.attempt_failure import _lint_ok

    lint = _lint([_finding(path="tests/test_x.py"), _finding(path="tests/sub/test_y.py")])
    assert _lint_ok(_qa(lint=lint), ["tests/**"]) is True


def test_lint_fails_when_only_some_introduced_paths_are_report_only():
    from sdlc.stages.code.attempt_failure import _lint_ok

    lint = _lint([_finding(path="tests/test_x.py"), _finding(path="app.py")])
    assert _lint_ok(_qa(lint=lint), ["tests/**"]) is False


# --- chaos / edge cases (026 T016, chaos QA) --------------------------------


def _run_with(monkeypatch, qa_reports, *, task=None, cfg=None, branch_point="bp-123", wf_id=None):
    """_run with the task, workflow id and branch point left open."""
    fake_wf = _FakeWorkflow(qa_reports)
    if wf_id is not None:
        fake_wf.info = lambda: SimpleNamespace(workflow_id=wf_id)
    monkeypatch.setattr(code_step, "workflow", fake_wf)
    ctx = _FakeCtx()
    result = asyncio.run(
        code_step.step(
            ctx,
            cfg=cfg or _cfg(),
            task=task or _task(),
            worktree="/tmp/wt",
            branch="b",
            branch_point=branch_point,
            qa_agent=SimpleNamespace(),
            reviewer_agent=SimpleNamespace(),
            adversary_agent=None,
            deep_review_agent=None,
            handoff_agent=None,
        )
    )
    return result, ctx, fake_wf


# (1) _lint_ok boundary table: fnmatch semantics, empty entries, duplicates


def test_edge_glob_is_fnmatch_not_a_string_prefix():
    """'tests-x/test_a.py' starts with the text 'tests' but is not under
    'tests/**'. A startswith() implementation would wrongly fence it."""
    from sdlc.stages.code.attempt_failure import _lint_ok

    assert _lint_ok(_qa(lint=_lint([_finding(path="tests-x/test_a.py")])), ["tests/**"]) is False
    assert _lint_ok(_qa(lint=_lint([_finding(path="tests/test_a.py")])), ["tests/**"]) is True


def test_edge_empty_report_only_entry_matches_nothing():
    """An empty glob must not fence anything, including an empty path
    (fnmatch('', '') is True, so the entry needs an explicit guard)."""
    from sdlc.stages.code.attempt_failure import _lint_ok

    assert _lint_ok(_qa(lint=_lint([_finding(path="app.py")])), [""]) is False
    assert _lint_ok(_qa(lint=_lint([_finding(path="")])), [""]) is False


def test_edge_duplicate_fenced_findings_all_pass():
    from sdlc.stages.code.attempt_failure import _lint_ok

    same = _finding(path="tests/test_x.py", rule="F401", line="import re")
    assert _lint_ok(_qa(lint=_lint([same, same, same])), ["tests/**"]) is True


# (2) the failing-test evidence and the lint block coexist, in that order


def test_edge_failing_tests_and_lint_block_both_reach_the_prompt(monkeypatch):
    failing = _qa(
        tests_passed=False,
        issues=["boom"],
        lint=_lint([_finding(path="app.py", rule="I001", line="import os")]),
    )
    _, _, wf = _run_with(monkeypatch, [failing], cfg=_cfg(max_fix_attempts=1))
    prompt = wf.coding_inputs[1].prompt
    assert "boom" in prompt  # the test evidence is not displaced
    assert HEADER in prompt
    assert prompt.index("boom") < prompt.index(HEADER)  # tests first, then lint


# (3) cap arithmetic and the no-findings case


def _findings(n):
    return [_finding(path=f"m{i}.py", line=f"import m{i}") for i in range(n)]


def test_edge_exactly_26_findings_show_25_and_one_more(monkeypatch):
    _, _, wf = _run_with(monkeypatch, [_qa(lint=_lint(_findings(26)))])
    prompt = wf.coding_inputs[1].prompt
    assert len(re.findall(r"^I001 m\d+\.py: import m\d+$", prompt, flags=re.MULTILINE)) == 25
    assert "(+1 more)" in prompt


def test_edge_exactly_25_findings_show_no_more_line(monkeypatch):
    _, _, wf = _run_with(monkeypatch, [_qa(lint=_lint(_findings(25)))])
    prompt = wf.coding_inputs[1].prompt
    assert len(re.findall(r"^I001 m\d+\.py: import m\d+$", prompt, flags=re.MULTILINE)) == 25
    assert not re.search(r"\(\+\d+ more\)", prompt)


def test_edge_zero_findings_means_no_lint_block_even_with_other_issues(monkeypatch):
    _, _, wf = _run_with(monkeypatch, [_qa(tests_passed=False, issues=["boom"], lint=_lint([]))])
    prompt = wf.coding_inputs[1].prompt
    assert "boom" in prompt
    assert HEADER not in prompt


# (4) the wiring: lint_base, lint_key, and the fence on repair only


def test_edge_lint_base_follows_the_branch_point_it_is_given(monkeypatch):
    _, _, wf = _run_with(monkeypatch, [CLEAN], branch_point="bp-XYZ-999")
    assert wf.qa_inputs[0].lint_base == "bp-XYZ-999"


def test_edge_lint_key_is_built_from_the_workflow_and_task_ids(monkeypatch):
    task = DevTask(id="t9", title="T", description="D", acceptance_criteria=["ac1"])
    _, _, wf = _run_with(monkeypatch, [CLEAN], task=task, wf_id="wf-other")
    assert wf.qa_inputs[0].lint_key == "wf-other/base-t9"


def test_edge_first_attempt_gets_no_fence_even_with_containment_on(monkeypatch):
    cfg = _cfg(max_fix_attempts=1, containment=True)
    _, _, wf = _run_with(monkeypatch, [CLEAN], cfg=cfg)
    assert wf.qa_inputs[0].lint_report_only == []


def test_edge_repair_attempt_gets_no_fence_when_containment_is_off(monkeypatch):
    cfg = _cfg(max_fix_attempts=1, containment=False)
    _, _, wf = _run_with(monkeypatch, [TESTS_FAIL, CLEAN], cfg=cfg)
    assert [q.lint_report_only for q in wf.qa_inputs] == [[], []]


# (5) a lint-failed attempt still runs the review lens


def test_edge_lint_failed_attempt_still_runs_the_reviewer(monkeypatch):
    dirty = _qa(lint=_lint([_finding()]))
    _, ctx, _ = _run_with(monkeypatch, [dirty], cfg=_cfg(max_fix_attempts=0))
    assert _by_stage(ctx)["code"][0].outcome is BenchmarkOutcome.FAIL
    reviewer_prompts = [p for role, p in ctx.role_prompts if role == "reviewer"]
    assert reviewer_prompts, "lint failure skipped the review lens"
    assert all(p.strip() for p in reviewer_prompts)
