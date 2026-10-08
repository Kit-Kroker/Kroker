"""012 T020 (RED): every failing analyze record names its cause (contract §6.1).

Drives the REAL ``analyze.step`` with a fake ctx whose run_role returns a
configured AnalysisReport and whose record() captures the REAL
BenchmarkRecord built by ``record_builder.stage_record``. With ``diff=``
supplied the step never dispatches an activity, so no workflow namespace is
needed (``_now``/``_workflow_id`` fall back outside a workflow).

RED today (contract §6.1 violated at base): the analyze record is built
without ``error=`` (src/sdlc/stages/analyze/step.py:148-167), so a failing
record (untraced criteria) carries error None.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from types import SimpleNamespace

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.core.models import PipelineConfig
from sdlc.stages.analyze.models import AnalysisReport, CriterionTrace
from sdlc.stages.plan.models import DevTask

# `sdlc.stages.analyze.__init__` re-exports the step FUNCTION, shadowing the
# module attribute — import the module explicitly to reach `step`.
analyze_mod = importlib.import_module("sdlc.stages.analyze.step")

_TRACED = "tests/test_x.py::test_ok"


def _tasks():
    """Four authoritative criteria across two tasks, in plan order."""
    return [
        DevTask(id="t1", title="T1", description="D", acceptance_criteria=["c1", "c2"]),
        DevTask(id="t2", title="T2", description="D", acceptance_criteria=["c3", "c4"]),
    ]


class _FakeCtx:
    def __init__(self, report: AnalysisReport) -> None:
        self.report = report
        self.records = []

    def stage(self, *a, **k):
        pass

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        assert role == "analyst"
        return SimpleNamespace(output=self.report)

    async def record(self, cfg, rec):
        self.records.append(rec)

    async def retain(self, *a, **k):
        pass


def _run(report: AnalysisReport, tasks):
    ctx = _FakeCtx(report)
    result = asyncio.run(
        analyze_mod.step(
            ctx,
            cfg=PipelineConfig(),
            integration_wt="/tmp/wt",
            tasks=tasks,
            diff={"stat": "s", "patch": "p"},
            analyst_agent=SimpleNamespace(),
        )
    )
    recs = [r for r in ctx.records if r.stage == "analyze"]
    assert len(recs) == 1
    return recs[0], result


def test_failing_record_error_counts_and_names_the_first_three_untraced():
    """Contract §6.1: a failing analyze record's error carries the COUNT of
    untraced criteria as a number and up to three 'task_id: criterion'
    labels — the fourth must be truncated away."""
    report = AnalysisReport(traceability=[], summary="nothing traced")
    rec, _ = _run(report, _tasks())
    assert rec.outcome is BenchmarkOutcome.FAIL
    assert rec.error is not None, "a failing analyze record must name its cause"
    # the count, as a standalone number (not a digit inside a label)
    assert re.search(r"\b4\b", rec.error), rec.error
    # the FIRST THREE labels in authoritative order
    assert "t1: c1" in rec.error
    assert "t1: c2" in rec.error
    assert "t2: c3" in rec.error
    # and NOT the fourth
    assert "t2: c4" not in rec.error


def test_failing_record_error_carries_all_labels_when_three_or_fewer():
    """§6.1 'up to three': exactly three untraced criteria are ALL named —
    truncation only kicks in above three."""
    report = AnalysisReport(
        traceability=[CriterionTrace(task_id="t1", criterion="c1", tests=[_TRACED])],
        summary="one traced",
    )
    rec, _ = _run(report, _tasks())
    assert rec.outcome is BenchmarkOutcome.FAIL
    assert rec.error is not None
    assert re.search(r"\b3\b", rec.error), rec.error
    assert "t1: c2" in rec.error
    assert "t2: c3" in rec.error
    assert "t2: c4" in rec.error


def test_passing_record_has_error_none():
    """Every criterion traced to at least one test: the record passes and
    carries no error."""
    report = AnalysisReport(
        traceability=[
            CriterionTrace(task_id="t1", criterion="c1", tests=[_TRACED]),
            CriterionTrace(task_id="t1", criterion="c2", tests=[_TRACED]),
            CriterionTrace(task_id="t2", criterion="c3", tests=[_TRACED]),
            CriterionTrace(task_id="t2", criterion="c4", tests=[_TRACED]),
        ],
        summary="all traced",
    )
    rec, _ = _run(report, _tasks())
    assert rec.outcome is BenchmarkOutcome.PASS
    assert rec.error is None
