"""Tests for analyze stage under 017-analyze-evidence (T010, US1)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sdlc.benchmarks.models import BenchmarkOutcome, TraceBag
from sdlc.core.models import PipelineConfig
from sdlc.stages import analyze
from sdlc.stages.analyze.models import (
    AnalysisReport,
    AnalyzeOutcome,
    CriterionTrace,
    Evidence,
    KeyedCriterion,
    TraceInventory,
)
from sdlc.stages.analyze.prompts import analyst_prompt, analyst_prompt_v2
from sdlc.stages.plan.models import DevTask
from sdlc.workflows.models import TaskResult


class _StubStageContext:
    def __init__(self, report: AnalysisReport) -> None:
        self.report = report
        self.records: list = []
        self.prompts: list[str] = []

    def stage(self, *a, **k):
        pass

    async def run_role(self, cfg, role, model, agent, prompt, into=None):
        self.prompts.append(prompt)
        return SimpleNamespace(output=self.report)

    async def record(self, cfg, rec):
        self.records.append(rec)

    async def retain(self, *a, **k):
        pass


def test_analyst_prompt_v2_section_order_and_byte_identical_tail():
    """Contract C-1: section order and v1 byte-identical tail from Aggregate test output."""
    crit = [KeyedCriterion(key="T1#1", task_id="T1", criterion="Do X")]
    inv = TraceInventory(
        changed_files=["src/foo.py"],
        tests=["tests/test_foo.py::test_x"],
        tree=["src/foo.py"],
        task_changed={"T1": 1},
        task_files={"T1": ["src/foo.py"]},
        truncated={"changed_files": False, "tests": False},
    )
    qa = "- T1: tests_passed=1 failing=[]"
    stat = "src/foo.py | 1 +"
    diff = "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -0,0 +1 @@\n+x = 1"

    v2 = analyst_prompt_v2(crit, inv, ["T1"], qa, stat, diff)

    # Section headers in C-1 order
    idx1 = v2.index("Acceptance criteria (key, task_id, text):")
    idx2 = v2.index("Changed files (1):")
    idx3 = v2.index("Tests in the tree (1):")
    idx4 = v2.index("Files changed per task:")
    idx5 = v2.index("Aggregate test output:")
    idx6 = v2.index("Integration diff stat:")
    idx7 = v2.index("Integration diff:")

    assert idx1 < idx2 < idx3 < idx4 < idx5 < idx6 < idx7

    # Section 1 format
    assert "- [T1#1] [T1] Do X" in v2
    # Section 4 format
    assert "T1: 1 files changed" in v2

    # Tail is byte-identical to v1 tail
    v1 = analyst_prompt("- [T1] Do X", qa, stat, diff)
    tail_start = "\nAggregate test output:\n"
    v1_tail = v1[v1.index(tail_start) :]
    assert v2.endswith(v1_tail)


def test_analyst_prompt_v2_150k_cap_halving_and_carryover():
    """Research D-3 / advisor-unlock-18:

    Budget halves (75k each) with carry-over; if (a) alone exceeds 150k,
    whole lines are cut, truncation note added, and section 3 still lists tests.
    """
    crit = [KeyedCriterion(key="T1#1", task_id="T1", criterion="Do X")]
    # Create changed_files totaling ~205k characters (> 150k budget)
    changed = [f"src/very_long_path_name_{i:04d}/file_{i:04d}.py" for i in range(5000)]
    tests = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]

    inv = TraceInventory(
        changed_files=changed,
        tests=tests,
        tree=changed,
        task_changed={"T1": 10},
        task_files={"T1": changed[:10]},
        truncated={"changed_files": True, "tests": False},
    )

    v2 = analyst_prompt_v2(crit, inv, ["T1"], "qa", "stat", "diff")

    # Section 2 has inventory capped note and prompt cap note
    assert "(inventory capped at 2,000 entries)" in v2
    assert "more not shown: prompt cap 150,000 characters)" in v2

    # Section 3 is NOT starved: header and all tests are present
    assert "Tests in the tree (2):" in v2
    assert "tests/test_a.py::test_one" in v2
    assert "tests/test_b.py::test_two" in v2


@pytest.mark.asyncio
async def test_analyze_step_patched_path(tmp_path):
    """Patched path: executes build_trace_inventory, enforces traces, record has trace."""
    # Create a small git repo in tmp_path with a test file
    import subprocess

    def _run(args):
        subprocess.run(
            args,
            cwd=str(tmp_path),
            capture_output=True,
            encoding="utf-8",
            check=True,
            stdin=subprocess.DEVNULL,
        )

    _run(["git", "init", "-q"])
    _run(["git", "config", "user.email", "t@example.com"])
    _run(["git", "config", "user.name", "T"])
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    _run(["git", "add", "README.md"])
    _run(["git", "commit", "-q", "-m", "init"])
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path),
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()

    # Add a test
    t_file = tmp_path / "test_example.py"
    t_file.write_text("def test_works(): pass\n", encoding="utf-8")
    _run(["git", "add", "test_example.py"])
    _run(["git", "commit", "-q", "-m", "add test"])

    tasks = [
        DevTask(id="T1", title="Task 1", description="desc", acceptance_criteria=["criterion 1"]),
        DevTask(id="T2", title="Task 2", description="desc", acceptance_criteria=["criterion 2"]),
    ]
    # Analyst report maps T1#1 to valid test, T2#1 has command only
    report = AnalysisReport(
        traceability=[
            CriterionTrace(
                key="T1#1",
                task_id="T1",
                criterion="criterion 1",
                tests=["test_example.py::test_works"],
            ),
            CriterionTrace(
                key="T2#1",
                task_id="T2",
                criterion="criterion 2",
                evidence=[Evidence(kind="command", ref="pytest tests/")],
            ),
        ],
        summary="partial trace",
    )

    ctx = _StubStageContext(report)
    cfg = PipelineConfig()

    with patch("sdlc.stages.analyze.step._EVIDENCE_V2", return_value=True):
        outcome = await analyze.step(
            ctx,
            cfg=cfg,
            integration_wt=str(tmp_path),
            base_sha=base_sha,
            tasks=tasks,
            task_results=[
                TaskResult(task_id="T1", status="done", attempts=1, branch="branch-1"),
                TaskResult(task_id="T2", status="done", attempts=1, branch="branch-2"),
            ],
            diff={"stat": "test_example.py | 1 +", "patch": "+def test_works(): pass"},
            analyst_agent=SimpleNamespace(),
        )

    assert isinstance(outcome, AnalyzeOutcome)
    assert outcome.report == report
    # T1 is traced, T2 is untraced (command only)
    assert outcome.untraced == ["T2: criterion 2"]

    # Verify prompt format
    prompt = ctx.prompts[0]
    assert "Acceptance criteria (key, task_id, text):" in prompt
    assert "- [T1#1] [T1] criterion 1" in prompt
    assert "Tests in the tree (1):" in prompt
    assert "test_example.py::test_works" in prompt

    # Verify record
    assert len(ctx.records) == 1
    rec = ctx.records[0]
    assert rec.outcome == BenchmarkOutcome.FAIL
    assert isinstance(rec.trace, TraceBag)
    assert rec.trace.traced_by_test == 1
    assert rec.trace.traced_by_command == 1
    assert rec.trace.untraced == 1
    # Error message marks (command only)
    assert "1 untraced criterion(s): T2: criterion 2 (command only)" in rec.error


@pytest.mark.asyncio
async def test_analyze_step_unpatched_path():
    """Unpatched path: no inventory activity, base prompt, untraced from untraced_criteria."""
    tasks = [
        DevTask(id="T1", title="Task 1", description="desc", acceptance_criteria=["criterion 1"]),
    ]
    report = AnalysisReport(
        traceability=[
            # In unpatched path, merely having tests=["test_one"] is considered traced
            CriterionTrace(task_id="T1", criterion="criterion 1", tests=["test_one"])
        ],
        summary="all traced",
    )

    ctx = _StubStageContext(report)
    cfg = PipelineConfig()

    with patch("sdlc.stages.analyze.step._EVIDENCE_V2", return_value=False):
        outcome = await analyze.step(
            ctx,
            cfg=cfg,
            integration_wt="/fake/wt",
            tasks=tasks,
            diff={"stat": "stat", "patch": "patch"},
            analyst_agent=SimpleNamespace(),
        )

    assert isinstance(outcome, AnalyzeOutcome)
    assert outcome.untraced == []

    # Prompt is byte-identical to analyst_prompt v1
    prompt = ctx.prompts[0]
    expected_prompt = analyst_prompt("- [T1] criterion 1", "", "stat", "patch")
    assert prompt == expected_prompt

    # Record trace is None
    rec = ctx.records[0]
    assert rec.outcome == BenchmarkOutcome.PASS
    assert rec.trace is None
    assert rec.error is None
