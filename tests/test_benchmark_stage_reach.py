"""017 T015: StageReach, final_stage_for, with_final_stage, and stage_reach_from."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sdlc.benchmarks.cell import CellProgress, summarize_cell
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CaseSpec,
    CostBag,
    QualityScore,
    SpeedBag,
    StageReach,
    final_stage_for,
    stage_reach_from,
    with_final_stage,
)
from sdlc.benchmarks.recorder import RecordStore


def _mk_record(
    stage: str,
    outcome: BenchmarkOutcome = BenchmarkOutcome.PASS,
    task_id: str | None = None,
    attempt: int | None = None,
    tasks_total: int | None = None,
    blocking_checks: list[str] | None = None,
) -> BenchmarkRecord:
    now = datetime.now(UTC)
    return BenchmarkRecord(
        run_id="run-1",
        bench_run_id="bench-1",
        case_id="case-1",
        scope=BenchmarkScope.TASK_ATTEMPT if task_id else BenchmarkScope.STAGE,
        stage=stage,
        task_id=task_id,
        attempt=attempt,
        role="test-role",
        model="test-model",
        quality=QualityScore(score=1.0, judge="contract"),
        cost=CostBag(),
        speed=SpeedBag(wall_clock_s=1.0, started_at=now, ended_at=now),
        outcome=outcome,
        tasks_total=tasks_total,
        blocking_checks=blocking_checks,
    )


# --- 1. final_stage_for & with_final_stage table tests -----------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, None),
        (object(), None),
        ({"deploy_enabled": True}, "deploy"),
        ({"deploy_enabled": False}, "merge"),
        (SimpleNamespace(deploy_enabled=True), "deploy"),
        (SimpleNamespace(deploy_enabled=False), "merge"),
        (
            CaseSpec(
                case_id="c1",
                idea_summary="s",
                harnesses=["h"],
                models=["m"],
                judge_model="jm",
                deploy_enabled=True,
            ),
            "deploy",
        ),
        (
            CaseSpec(
                case_id="c1",
                idea_summary="s",
                harnesses=["h"],
                models=["m"],
                judge_model="jm",
                deploy_enabled=False,
            ),
            "merge",
        ),
    ],
)
def test_final_stage_for_table(spec: Any, expected: str | None) -> None:
    assert final_stage_for(spec) == expected


def test_with_final_stage() -> None:
    assert with_final_stage(None, SimpleNamespace(deploy_enabled=True)) is None

    reach = StageReach(last_stage="merge", last_stage_outcome="pass")
    stamped_deploy = with_final_stage(reach, SimpleNamespace(deploy_enabled=True))
    assert stamped_deploy is not None
    assert stamped_deploy.final_stage == "deploy"

    stamped_merge = with_final_stage(reach, SimpleNamespace(deploy_enabled=False))
    assert stamped_merge is not None
    assert stamped_merge.final_stage == "merge"


# --- 2. stage_reach_from pure tests ------------------------------------------


def test_stage_reach_r1_shape_merge_fail_deploy_off() -> None:
    records = [
        _mk_record("plan", tasks_total=2),
        _mk_record("code", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("qa", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("code", task_id="t2", outcome=BenchmarkOutcome.PASS),
        _mk_record("qa", task_id="t2", outcome=BenchmarkOutcome.PASS),
        _mk_record("analyze", outcome=BenchmarkOutcome.PASS),
        _mk_record("merge", outcome=BenchmarkOutcome.FAIL, blocking_checks=["lint"]),
    ]

    reach = stage_reach_from(records, final_stage="merge")
    assert reach.last_stage == "merge"
    assert reach.last_stage_outcome == "fail"
    assert reach.final_stage == "merge"
    assert reach.tasks_total == 2
    assert reach.tasks_qa_passed == 2
    assert reach.tasks_not_finished == 0
    assert reach.merge_outcome == "fail"
    assert reach.merge_blocking_checks == ["lint"]


def test_stage_reach_mid_loop_code_stall() -> None:
    records = [
        _mk_record("plan", tasks_total=3),
        _mk_record("code", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("code", task_id="t2", outcome=BenchmarkOutcome.FAIL),
    ]

    reach = stage_reach_from(records, final_stage="merge")
    assert reach.last_stage == "code"
    assert reach.last_stage_outcome == "fail"
    assert reach.final_stage == "merge"
    assert reach.tasks_total == 3
    assert reach.tasks_qa_passed == 0
    assert reach.tasks_not_finished == 3
    assert reach.merge_outcome is None
    assert reach.merge_blocking_checks == []


def test_stage_reach_mid_loop_qa_stall() -> None:
    records = [
        _mk_record("plan", tasks_total=3),
        _mk_record("code", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("qa", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("code", task_id="t2", outcome=BenchmarkOutcome.PASS),
        _mk_record("qa", task_id="t2", outcome=BenchmarkOutcome.FAIL),
    ]

    reach = stage_reach_from(records, final_stage="merge")
    assert reach.last_stage == "qa"
    assert reach.last_stage_outcome == "fail"
    assert reach.final_stage == "merge"
    assert reach.tasks_total == 3
    assert reach.tasks_qa_passed == 1
    assert reach.tasks_not_finished == 2  # 3 total - 1 finished (t1)
    assert reach.merge_outcome is None
    assert reach.merge_blocking_checks == []


def test_stage_reach_finished_run() -> None:
    records = [
        _mk_record("plan", tasks_total=1),
        _mk_record("code", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("qa", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("analyze", outcome=BenchmarkOutcome.PASS),
        _mk_record("merge", outcome=BenchmarkOutcome.PASS, blocking_checks=[]),
        _mk_record("deploy", outcome=BenchmarkOutcome.PASS),
    ]

    reach = stage_reach_from(records, final_stage="deploy")
    assert reach.last_stage == "deploy"
    assert reach.last_stage_outcome == "pass"
    assert reach.final_stage == "deploy"
    assert reach.tasks_total == 1
    assert reach.tasks_qa_passed == 1
    assert reach.tasks_not_finished == 0
    assert reach.merge_outcome == "pass"
    assert reach.merge_blocking_checks == []


def test_stage_reach_no_plan_record() -> None:
    records = [
        _mk_record("code", task_id="t1", outcome=BenchmarkOutcome.PASS),
        _mk_record("qa", task_id="t1", outcome=BenchmarkOutcome.PASS),
    ]

    reach = stage_reach_from(records, final_stage="merge")
    assert reach.last_stage == "qa"
    assert reach.last_stage_outcome == "pass"
    assert reach.tasks_total is None
    assert reach.tasks_not_finished is None
    assert reach.tasks_qa_passed == 1


# --- 3. summarize_cell on record store ----------------------------------------


def test_summarize_cell_computes_stage_reach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    store = RecordStore(bench_run_id="bench-x", cell_id="add-login#opencode#a1")
    store.append(_mk_record("plan", tasks_total=1))
    store.append(_mk_record("code", task_id="t1", outcome=BenchmarkOutcome.PASS))
    store.append(_mk_record("qa", task_id="t1", outcome=BenchmarkOutcome.PASS))

    progress = asyncio.run(summarize_cell("bench-x", "add-login#opencode#a1", final_stage="merge"))
    assert isinstance(progress, CellProgress)
    assert progress.stage_reach is not None
    assert progress.stage_reach.last_stage == "qa"
    assert progress.stage_reach.final_stage == "merge"
    assert progress.stage_reach.tasks_total == 1
    assert progress.stage_reach.tasks_not_finished == 0
