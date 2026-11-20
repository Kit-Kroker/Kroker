"""FR-702 Task 5: the per-task diff path is claim-checked end to end.

Drives the REAL code.step with a fake workflow namespace (the
test_task_lint_loop.py harness shape) and asserts the three consumer
contracts:

- Happy path: get_task_diff's CodeArtifact carries a real stored ref; ONE
  load_diff read-back materializes the prompt text for BOTH clean-context
  lenses (qa, reviewer); run.diff_ref rides TaskResult (spec D6); the fetch
  is labelled per task+attempt so each attempt's patch lands at its own
  artifact path.
- Review Focus 3: patch_ref=None (propose-mode/legacy) — prompts receive
  EMPTY patch text, run.diff_ref is None, and NO load_diff command is
  scheduled (calling load_diff(None) would crash the attempt).
- Legacy replay shape: a pre-claim-check history replays its recorded dict
  result (json/plain payload); the step must normalize it without crashing
  and without scheduling a read-back (tests/review's shadowing-chaos replay
  depends on exactly this).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from temporalio import workflow as real_workflow

code_step = importlib.import_module("sdlc.stages.code.step")
from sdlc.artifacts.read import load_diff
from sdlc.artifacts.store import LocalFileStore
from sdlc.core.models import HarnessKind, PipelineConfig, RoleConfig
from sdlc.harness.models import HarnessRunResult
from sdlc.stages.plan.models import DevTask
from sdlc.stages.qa.models import QAReport
from sdlc.stages.review.models import ReviewReport
from sdlc.vcs import CodeArtifact
from sdlc.vcs.models import as_code_artifact

_BASE = datetime(2026, 11, 19, 10, tzinfo=UTC)
PATCH = "diff --git a/app.py b/app.py\n+MARKER-LINE-702\n"
STAT = " app.py | 3 +++"


class _FakeWorkflow:
    """Activity dispatch by name. `artifact` is what get_task_diff answers;
    load_diff is the REAL read-back (the store holds real bytes), and every
    diff-shaped call is recorded for the assertions."""

    def __init__(self, artifact) -> None:
        self._t = 0
        self.artifact = artifact
        self.diff_inputs: list = []
        self.load_diff_inputs: list = []

    unsafe = real_workflow.unsafe
    ActivityConfig = staticmethod(real_workflow.ActivityConfig)
    logger = logging.getLogger("fr702-fake-workflow")

    def now(self):
        self._t += 100
        return _BASE + timedelta(seconds=self._t)

    def info(self):
        return SimpleNamespace(workflow_id="wf-fr702")

    async def execute_activity(self, fn, arg=None, **kw):
        name = fn.__name__
        if name == "run_coding_task":
            return HarnessRunResult(
                harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="ok", commit_sha="c" * 40
            )
        if name == "run_test_suite":
            return QAReport(tests_passed=True, failing_tests=[], issues=[])
        if name == "get_task_diff":
            self.diff_inputs.append(arg)
            return self.artifact
        if name == "load_diff":
            self.load_diff_inputs.append(arg)
            return await load_diff(arg)
        raise AssertionError(f"unexpected activity {name}")


class _FakeCtx:
    def __init__(self) -> None:
        self.role_prompts: list[tuple[str, str]] = []

    def emit(self, kind, **kw):
        pass

    async def record(self, cfg, rec):
        pass

    async def judge(self, cfg, artifact, stage, **kw):
        return SimpleNamespace(score=None, judge="llm_judge")

    async def run_role(self, cfg, role, model, agent, prompt, into=None):
        self.role_prompts.append((role, prompt))
        if role == "qa":
            return SimpleNamespace(output=QAReport(tests_passed=True, failing_tests=[], issues=[]))
        if role == "reviewer":
            return SimpleNamespace(output=ReviewReport(approve=True))
        raise AssertionError(f"unexpected role {role}")

    async def gate(self, name, settings, **kw):
        raise AssertionError("the happy path never gates")

    async def retain(self, *a, **k):
        pass


def _run(monkeypatch, tmp_path, artifact):
    """One happy-path attempt (tests pass, qa clean, reviewer approves)."""
    fake_wf = _FakeWorkflow(artifact)
    monkeypatch.setattr(code_step, "workflow", fake_wf)
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    cfg = PipelineConfig(
        roles={"dev": RoleConfig(harness=HarnessKind.CLAUDE_CODE, model="test-model")},
        max_fix_attempts=0,
    )
    ctx = _FakeCtx()
    result = asyncio.run(
        code_step.step(
            ctx,
            cfg=cfg,
            task=DevTask(id="t1", title="T", description="D", acceptance_criteria=["ac1"]),
            worktree="/tmp/wt",
            branch="b",
            branch_point="bp-123",
            qa_agent=SimpleNamespace(),
            reviewer_agent=SimpleNamespace(),
            adversary_agent=None,
            deep_review_agent=None,
            handoff_agent=None,
        )
    )
    return result, ctx, fake_wf


def _prompts(ctx, role):
    return [p for r, p in ctx.role_prompts if r == role]


# --- happy path: one read-back feeds both lenses, ref rides TaskResult -----


def test_stored_patch_reaches_both_lens_prompts_via_one_load_diff(monkeypatch, tmp_path):
    ref = LocalFileStore().put("diff", "wf-fr702", "t1-a1.patch", PATCH.encode("utf-8"))
    result, ctx, fake_wf = _run(
        monkeypatch, tmp_path, CodeArtifact(files=["app.py"], stat=STAT, patch_ref=ref)
    )
    qa_p = _prompts(ctx, "qa")
    rev_p = _prompts(ctx, "reviewer")
    assert qa_p and rev_p
    assert "MARKER-LINE-702" in qa_p[0], "qa prompt must carry the stored patch text"
    assert "MARKER-LINE-702" in rev_p[0], "reviewer prompt must carry the stored patch text"
    assert STAT in qa_p[0], "qa prompt carries the artifact's stat block"
    # exactly one read-back, of the artifact's own ref
    assert len(fake_wf.load_diff_inputs) == 1
    assert fake_wf.load_diff_inputs[0].ref == ref
    # D6: the claim-check rides TaskResult
    assert result.run.diff_ref == ref
    # the fetch is labelled per task+attempt (audit path <label>.patch)
    assert [d.label for d in fake_wf.diff_inputs] == ["t1-a1"]


# --- Review Focus 3: patch_ref=None -> empty patch, no read-back ----------


def test_patch_ref_none_means_empty_patch_text_and_no_load_diff(monkeypatch, tmp_path):
    result, ctx, fake_wf = _run(
        monkeypatch, tmp_path, CodeArtifact(files=["app.py"], stat=STAT, patch_ref=None)
    )
    qa_p = _prompts(ctx, "qa")
    rev_p = _prompts(ctx, "reviewer")
    assert qa_p and rev_p
    assert qa_p[0].endswith("Diff:\n"), "patch_ref=None leaves the Diff section empty"
    assert rev_p[0].endswith("Diff:\n")
    assert fake_wf.load_diff_inputs == [], "no load_diff command may be scheduled"
    assert result.run.diff_ref is None


# --- legacy replay payload: the recorded dict normalizes, never crashes ----


def test_legacy_replayed_dict_result_normalizes_without_a_read_back(monkeypatch, tmp_path):
    legacy = {"files": ["app.py"], "stat": STAT, "patch": PATCH, "renames": []}
    result, _, fake_wf = _run(monkeypatch, tmp_path, legacy)
    assert result.run.diff_ref is None, "a legacy dict has no ref to claim-check"
    assert fake_wf.load_diff_inputs == []


# --- the shared decode shim: three legs (final review, Minor 2) -------------


def test_as_code_artifact_helper_three_legs():
    """The ONE shim both call sites (code stage, postplan's analyze node)
    decode through — pinned at the helper itself, beside the call-site
    replay test above."""
    art = CodeArtifact(files=["app.py"], stat=STAT)
    assert as_code_artifact(art) is art, "a CodeArtifact passes through unchanged"

    legacy = {"files": ["app.py"], "stat": STAT, "renames": [], "patch": PATCH}
    norm = as_code_artifact(legacy)
    assert isinstance(norm, CodeArtifact)
    assert norm.files == ["app.py"] and norm.stat == STAT, "metadata kept"
    assert norm.patch_ref is None, "a legacy dict has no ref to claim-check"
    assert "patch" not in norm.model_dump(), "extra-ignore drops the legacy inline patch"

    with pytest.raises(TypeError):
        as_code_artifact("not an artifact")
