"""012 T013b (RED): the benchmark parent's per-cell sequence (US2, R-4).

Exercises the REAL BenchmarkWorkflow end to end against an ephemeral
time-skipping Temporal environment with STUBS: the child pipeline is a
workflow class shadowing the real GraphWorkflow by NAME (the parent
dispatches children by name via execute_child_workflow —
src/sdlc/workflows/pipeline_child.py), and every activity the parent
calls is a stub registered under the real activity's name.

The five sequence cases of tasks.md T013's sequence-test paragraph:
(i)   child raises + code not finished  -> not graded, no oracle at all
(ii)  child returns + code finished + score -> oracle + oracle-task
      records, then the cell record `graded`
(iii) grade without a score -> ONE oracle record `not_evaluated`
      carrying the grade's detail, no oracle-task records, cell record
      `grading_failed`
(iv)  case without a language -> no oracle call, cell record `no_oracle`
(v)   provenance resolved EXACTLY ONCE for two cells; both cell records
      carry the resolved commit

RED at base: the parent never calls summarize_cell/resolve_provenance
and grades unconditionally whenever spec.language is set — so no cell
record exists at all and the grade stub fires where (i)/(iv) expect
silence.

Stubs run in-process (the time-skipping environment), so module-level
STATE is shared; the worker uses UnsandboxedWorkflowRunner (the
tests/durability pattern) so the test module is never re-imported into a
sandbox copy.
"""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

with workflow.unsafe.imports_passed_through():
    from sdlc.benchmarks.cell import CellProgress
    from sdlc.benchmarks.models import (
        BenchmarkOutcome,
        BenchmarkRecord,
        BenchmarkScope,
        CaseSpec,
    )
    from sdlc.benchmarks.oracle import OracleGrade
    from sdlc.benchmarks.provenance import Provenance
    from sdlc.benchmarks.tasks import TaskGrade
    from sdlc.benchmarks.workflow import BenchmarkWorkflow

pytestmark = pytest.mark.temporal

TASK_QUEUE = "bench-seq"

# In-process stub configuration, reset by every test.
STATE: dict = {
    "child": "return",  # "return" | "raise"
    "progress": None,  # CellProgress the summarize_cell stub returns
    "grade": None,  # OracleGrade the grade_oracle stub returns
    "records": [],  # every record the record_benchmark stub captured
    "grade_calls": 0,
    "summarize_calls": 0,
    "provenance_calls": 0,
}


def _reset() -> None:
    STATE.update(
        child="return",
        progress=None,
        grade=None,
        records=[],
        grade_calls=0,
        summarize_calls=0,
        provenance_calls=0,
    )


@workflow.defn(name="GraphWorkflow")
class StubGraphChild:
    """Shadows the real GraphWorkflow by NAME: the parent starts the child
    by class reference, Temporal dispatches by name."""

    @workflow.run
    async def run(self, run_input) -> str:
        if STATE["child"] == "raise":
            raise ApplicationError("stub child failed", non_retryable=True)
        return "stub child ok"


@activity.defn(name="load_case_assets")
async def stub_load_case_assets(case_id, files) -> dict:
    return {}


@activity.defn(name="record_benchmark")
async def stub_record_benchmark(record: BenchmarkRecord) -> None:
    STATE["records"].append(record)


@activity.defn(name="grade_oracle")
async def stub_grade_oracle(inp) -> OracleGrade:
    STATE["grade_calls"] += 1
    if STATE["grade"] is None:
        # the BASE parent grades unconditionally whenever spec.language is
        # set; returning None here would crash it into an endless
        # workflow-task retry loop (AttributeError is retryable) — RED must
        # come from the assertions, never from a wedged run
        return _grade()
    return STATE["grade"]


@activity.defn(name="summarize_cell")
async def stub_summarize_cell(bench_run_id: str, cell_id: str) -> CellProgress:
    STATE["summarize_calls"] += 1
    return STATE["progress"]


@activity.defn(name="resolve_provenance")
async def stub_resolve_provenance() -> Provenance:
    STATE["provenance_calls"] += 1
    return Provenance(kroker_commit="abc123", tree_dirty=False)


@activity.defn(name="finalize_benchmark_report")
async def stub_finalize_benchmark_report(bench_run_id: str) -> str:
    return "report.md"


def _spec_json(**kw) -> str:
    """A minimal one-cell case (opencode, one model, no crew entries)."""
    base = dict(
        case_id="seq-case",
        idea_summary="sequence probe",
        mode="greenfield",
        harnesses=["opencode"],
        models=["openai/gpt-5.2"],
        judge_model="google:gemini-3.5-flash",
        language="python",
    )
    base.update(kw)
    return CaseSpec(**base).model_dump_json()


def _grade(score=1.0, **kw) -> OracleGrade:
    base = dict(
        score=score,
        passed=2,
        total=2,
        language_manifest="python",
        language_detected="python",
        language_match=True,
        held_out_ok=True,
        detail="2/2",
        task_grades=[
            TaskGrade(
                task_id="t01", error_class="functional", score=1.0, judge="oracle", detail="ok"
            ),
            TaskGrade(
                task_id="t02", error_class="security", score=0.0, judge="oracle", detail="missed"
            ),
        ],
    )
    base.update(kw)
    return OracleGrade(**base)


async def _run_parent(spec_json: str) -> str:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        # the budget-gate pattern: wall-clock worker pacing, or the parent's
        # wait on the child workflow can deadlock the time-skipping clock
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[BenchmarkWorkflow, StubGraphChild],
                activities=[
                    stub_load_case_assets,
                    stub_record_benchmark,
                    stub_grade_oracle,
                    stub_summarize_cell,
                    stub_resolve_provenance,
                    stub_finalize_benchmark_report,
                ],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                handle = await env.client.start_workflow(
                    BenchmarkWorkflow.run,
                    spec_json,
                    id=f"bench-seq-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )
                return await handle.result()


def _scopes(scope):
    return [r for r in STATE["records"] if r.scope is scope]


def _cell_records():
    return _scopes(BenchmarkScope.CELL)


@pytest.mark.asyncio
async def test_aborted_cell_is_not_graded_and_writes_one_cell_record():
    """(i) the child raises and the cell never reached post-code: no
    grading, no oracle anything, exactly one cell record not_graded."""
    _reset()
    STATE["child"] = "raise"
    STATE["progress"] = CellProgress(last_stage="clarify", code_finished=False)
    result = await _run_parent(_spec_json())
    assert result == "report.md"
    assert STATE["grade_calls"] == 0, "the oracle must not run for a cell without code"
    assert _scopes(BenchmarkScope.ORACLE) == []
    assert _scopes(BenchmarkScope.ORACLE_TASK) == []
    cells = _cell_records()
    assert len(cells) == 1
    status = cells[0].cell
    assert status is not None
    assert status.grading == "not_graded"
    assert status.last_stage == "clarify"
    assert status.pipeline_finished is False
    assert status.completed is False


@pytest.mark.asyncio
async def test_graded_cell_writes_oracle_records_then_the_cell_record():
    """(ii) child returned, code finished, grade has a score: one oracle
    record + one oracle-task record per task grade, then cell record
    `graded`."""
    _reset()
    STATE["progress"] = CellProgress(last_stage="merge", code_finished=True)
    STATE["grade"] = _grade(score=1.0)
    await _run_parent(_spec_json())
    oracle = _scopes(BenchmarkScope.ORACLE)
    assert len(oracle) == 1
    assert oracle[0].outcome is BenchmarkOutcome.PASS
    tasks = _scopes(BenchmarkScope.ORACLE_TASK)
    assert [t.task_id for t in tasks] == ["t01", "t02"]
    cells = _cell_records()
    assert len(cells) == 1
    status = cells[0].cell
    assert status is not None
    assert status.grading == "graded"
    assert status.completed is True
    assert status.pipeline_finished is True


@pytest.mark.asyncio
async def test_grade_without_score_is_not_evaluated_and_grading_failed():
    """(iii) the grade carries no score: ONE oracle record with outcome
    not_evaluated and error = the grade's detail, NO oracle-task records,
    cell record grading_failed."""
    _reset()
    STATE["progress"] = CellProgress(last_stage="code", code_finished=True)
    STATE["grade"] = _grade(score=None, detail="oracle environment failed: pip exploded")
    await _run_parent(_spec_json())
    oracle = _scopes(BenchmarkScope.ORACLE)
    assert len(oracle) == 1
    assert oracle[0].outcome is BenchmarkOutcome.NOT_EVALUATED
    assert oracle[0].error == "oracle environment failed: pip exploded"
    assert _scopes(BenchmarkScope.ORACLE_TASK) == []
    cells = _cell_records()
    assert len(cells) == 1
    assert cells[0].cell is not None
    assert cells[0].cell.grading == "grading_failed"


@pytest.mark.asyncio
async def test_case_without_language_gets_no_oracle_and_a_no_oracle_cell():
    """(iv) spec.language None: grade_oracle never called, no oracle
    records, one cell record `no_oracle`."""
    _reset()
    STATE["progress"] = CellProgress(last_stage="code", code_finished=True)
    STATE["grade"] = _grade()
    await _run_parent(_spec_json(language=None))
    assert STATE["grade_calls"] == 0
    assert _scopes(BenchmarkScope.ORACLE) == []
    assert _scopes(BenchmarkScope.ORACLE_TASK) == []
    cells = _cell_records()
    assert len(cells) == 1
    assert cells[0].cell is not None
    assert cells[0].cell.grading == "no_oracle"


@pytest.mark.asyncio
async def test_provenance_resolved_once_for_two_cells():
    """(v) a two-model matrix expands to two cells; resolve_provenance runs
    EXACTLY ONCE for the whole run and both cell records carry its commit."""
    _reset()
    STATE["progress"] = CellProgress(last_stage="merge", code_finished=True)
    STATE["grade"] = _grade(score=1.0)
    await _run_parent(_spec_json(models=["openai/gpt-5.2", "openai/gpt-5.3"]))
    assert STATE["provenance_calls"] == 1
    cells = _cell_records()
    assert len(cells) == 2
    assert all(c.kroker_commit == "abc123" for c in cells)
