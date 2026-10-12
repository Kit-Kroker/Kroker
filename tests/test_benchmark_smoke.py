"""Tests for smoke conditions and stamp (T007)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.smoke import (
    SMOKE_CONDITIONS,
    SmokeStamp,
    check_smoke,
    ops_root,
    passing_stamp,
    write_stamp,
)
from sdlc.core.models import HarnessKind

_T0 = datetime(2026, 7, 20, 10, tzinfo=UTC)


def _mk_record(
    stage: str,
    *,
    scope: BenchmarkScope = BenchmarkScope.STAGE,
    judge: str = "staged_rubric",
    score: float | None = 1.0,
    commit: str | None = "c1234567",
    outcome: BenchmarkOutcome = BenchmarkOutcome.PASS,
) -> BenchmarkRecord:
    return BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id="todo-api",
        scope=scope,
        stage=stage,
        role=stage,
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=score, judge=judge),  # type: ignore[arg-type]
        cost=CostBag(),
        speed=SpeedBag(wall_clock_s=1.0, started_at=_T0, ended_at=_T0 + timedelta(seconds=1)),
        outcome=outcome,
        kroker_commit=commit,
    )


def _passing_suite() -> tuple[list[BenchmarkRecord], list[str], int]:
    records = [
        _mk_record("clarify", judge="staged_rubric", score=0.9),
        _mk_record("architecture", judge="llm_judge", score=0.85),
        _mk_record("code", judge="llm_judge", score=1.0),
        _mk_record(
            "oracle",
            scope=BenchmarkScope.ORACLE,
            judge="oracle",
            score=1.0,
            outcome=BenchmarkOutcome.PASS,
        ),
    ]
    files = ["runs/benchmarks/b1/cell1.jsonl"]
    n_cells = 1
    return records, files, n_cells


def test_smoke_conditions_tuple():
    assert SMOKE_CONDITIONS == (
        "rubric_scores",
        "commit_on_records",
        "one_file_per_cell",
        "oracle_all_pass",
    )


def test_check_smoke_passing_run():
    records, files, n_cells = _passing_suite()
    failed = check_smoke(records, files, n_cells)
    assert failed == []


def test_check_smoke_fails_rubric_scores_when_clarify_judge_not_rubric():
    records, files, n_cells = _passing_suite()
    # clarify with non-rubric judge
    records[0] = _mk_record("clarify", judge="error", score=None)
    failed = check_smoke(records, files, n_cells)
    assert failed == ["rubric_scores"]


def test_check_smoke_fails_rubric_scores_when_arch_missing_or_judge_not_rubric():
    records, files, n_cells = _passing_suite()
    # architecture with human_override (not in RUBRIC_JUDGES)
    records[1] = _mk_record("architecture", judge="human_override", score=1.0)
    failed = check_smoke(records, files, n_cells)
    assert failed == ["rubric_scores"]


def test_check_smoke_fails_commit_on_records_when_none():
    records, files, n_cells = _passing_suite()
    records[2] = _mk_record("code", commit=None)
    failed = check_smoke(records, files, n_cells)
    assert failed == ["commit_on_records"]


def test_check_smoke_fails_commit_on_records_when_unknown():
    records, files, n_cells = _passing_suite()
    records[0] = _mk_record("clarify", commit="unknown")
    failed = check_smoke(records, files, n_cells)
    assert failed == ["commit_on_records"]


def test_check_smoke_fails_one_file_per_cell_when_mismatched():
    records, files, n_cells = _passing_suite()
    failed = check_smoke(records, files, n_cells=2)
    assert failed == ["one_file_per_cell"]


def test_check_smoke_fails_oracle_all_pass_when_oracle_failed():
    records, files, n_cells = _passing_suite()
    records[3] = _mk_record(
        "oracle",
        scope=BenchmarkScope.ORACLE,
        judge="oracle",
        score=0.5,
        outcome=BenchmarkOutcome.FAIL,
    )
    failed = check_smoke(records, files, n_cells)
    assert failed == ["oracle_all_pass"]


def test_check_smoke_fails_oracle_all_pass_when_no_oracle_record():
    records, files, n_cells = _passing_suite()
    records = [r for r in records if r.scope != BenchmarkScope.ORACLE and r.stage != "oracle"]
    failed = check_smoke(records, files, n_cells)
    assert failed == ["oracle_all_pass"]


def test_write_stamp_and_passing_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))

    stamp = SmokeStamp(
        kroker_commit="abcdef12",
        bench_run_id="b-smoke-1",
        passed=True,
        failed_conditions=[],
        written=datetime.now(UTC).isoformat(),
    )
    p = write_stamp(stamp)
    assert p == tmp_path / "ops" / "smoke" / "abcdef12.json"
    assert p.is_file()

    # passing_stamp returns the stamp
    loaded = passing_stamp("abcdef12")
    assert loaded is not None
    assert loaded.kroker_commit == "abcdef12"
    assert loaded.bench_run_id == "b-smoke-1"
    assert loaded.passed is True


def test_passing_stamp_returns_none_when_stamp_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))

    stamp = SmokeStamp(
        kroker_commit="abcdef12",
        bench_run_id="b-smoke-1",
        passed=False,
        failed_conditions=["oracle_all_pass"],
        written=datetime.now(UTC).isoformat(),
    )
    write_stamp(stamp)

    assert passing_stamp("abcdef12") is None


def test_passing_stamp_returns_none_when_file_missing_or_corrupt(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    assert passing_stamp("missing123") is None

    # Corrupted file
    smoke_dir = tmp_path / "ops" / "smoke"
    smoke_dir.mkdir(parents=True)
    (smoke_dir / "corrupt123.json").write_text("{bad-json", encoding="utf-8")
    assert passing_stamp("corrupt123") is None


def test_passing_stamp_returns_none_for_different_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))

    stamp = SmokeStamp(
        kroker_commit="commit-A",
        bench_run_id="b-smoke-1",
        passed=True,
        failed_conditions=[],
        written=datetime.now(UTC).isoformat(),
    )
    # Write into file commit-B.json
    base = ops_root()
    smoke_dir = base / "smoke"
    smoke_dir.mkdir(parents=True)
    (smoke_dir / "commit-B.json").write_text(stamp.model_dump_json(), encoding="utf-8")

    assert passing_stamp("commit-B") is None


def test_write_stamp_replaces_earlier_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))

    stamp1 = SmokeStamp(
        kroker_commit="abcdef12",
        bench_run_id="b-smoke-1",
        passed=False,
        failed_conditions=["rubric_scores"],
        written="2026-07-20T10:00:00Z",
    )
    write_stamp(stamp1)
    assert passing_stamp("abcdef12") is None

    stamp2 = SmokeStamp(
        kroker_commit="abcdef12",
        bench_run_id="b-smoke-2",
        passed=True,
        failed_conditions=[],
        written="2026-07-20T11:00:00Z",
    )
    write_stamp(stamp2)
    loaded = passing_stamp("abcdef12")
    assert loaded is not None
    assert loaded.bench_run_id == "b-smoke-2"
    assert loaded.passed is True


def test_extract_bench_run_id_variants():
    from sdlc.benchmarks.smoke import extract_bench_run_id

    # report.md path (relative or absolute, unix or windows)
    assert (
        extract_bench_run_id("runs/benchmarks/bench-todo-api-greenfield-1791804132/report.md")
        == "bench-todo-api-greenfield-1791804132"
    )
    assert (
        extract_bench_run_id(
            "/abs/path/runs/benchmarks/bench-todo-api-greenfield-1791804132/report.md"
        )
        == "bench-todo-api-greenfield-1791804132"
    )
    assert (
        extract_bench_run_id(r"C:\runs\benchmarks\bench-todo-api-greenfield-1791804132\report.md")
        == "bench-todo-api-greenfield-1791804132"
    )
    # direct bench_run_id
    assert (
        extract_bench_run_id("bench-todo-api-greenfield-1791804132")
        == "bench-todo-api-greenfield-1791804132"
    )
    assert extract_bench_run_id("b-smoke-pass") == "b-smoke-pass"
    # bench dir path
    assert (
        extract_bench_run_id("runs/benchmarks/bench-todo-api-greenfield-1791804132")
        == "bench-todo-api-greenfield-1791804132"
    )
    # trailing whitespace/newline
    assert (
        extract_bench_run_id("runs/benchmarks/bench-todo-api-greenfield-1791804132/report.md\n")
        == "bench-todo-api-greenfield-1791804132"
    )


def test_dispatch_smoke_with_real_run_matrix_report_path(tmp_path, capsys, monkeypatch):
    """Real contract test: _run_matrix returns the report path, not the bench run id.
    dispatch_smoke without run_fn stub must extract the bench run id, read records,
    and write the stamp with the real bench_run_id (not the report path).
    """
    import yaml

    from sdlc.benchmarks.cli import dispatch_smoke
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.benchmarks.smoke import passing_stamp

    cases_root = tmp_path / "cases"
    c_dir = cases_root / "todo-api"
    c_dir.mkdir(parents=True)
    (c_dir / "case.yaml").write_text(
        yaml.safe_dump(
            {
                "case_id": "todo-api",
                "idea_summary": "todo",
                "harnesses": ["opencode"],
                "models": ["m"],
                "judge_model": "j",
                "role": "smoke",
                "visibility": "public",
            }
        ),
        encoding="utf-8",
    )

    ops_dir = tmp_path / "ops"
    bench_dir = tmp_path / "runs"
    monkeypatch.setenv("SDLC_OPS_ROOT", str(ops_dir))
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(bench_dir))

    bench_run_id = "bench-todo-api-greenfield-1791804132"
    store = RecordStore(
        bench_run_id=bench_run_id, cell_id="todo-api#opencode#arm", root=str(bench_dir)
    )
    for r in [
        _mk_record("clarify", judge="staged_rubric", score=1.0, commit="commit-smoke-real"),
        _mk_record("architecture", judge="staged_rubric", score=1.0, commit="commit-smoke-real"),
        _mk_record(
            "oracle",
            scope=BenchmarkScope.ORACLE,
            judge="oracle",
            score=1.0,
            outcome=BenchmarkOutcome.PASS,
            commit="commit-smoke-real",
        ),
    ]:
        store.append(r)

    # The real report.md that finalize_benchmark_report writes
    report_file = bench_dir / bench_run_id / "report.md"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text("# Report", encoding="utf-8")

    # Mock Client.connect to simulate BenchmarkWorkflow.run finishing with report.md path
    class _DummyHandle:
        async def result(self):
            return str(report_file)

    class _DummyClient:
        async def start_workflow(self, *args, **kwargs):
            return _DummyHandle()

    async def _fake_connect(*args, **kwargs):
        return _DummyClient()

    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)

    # Call dispatch_smoke WITHOUT run_fn stub (run_fn=None)
    out = dispatch_smoke(cases_root=str(cases_root), ops_dir=str(ops_dir))
    assert "smoke: PASS commit-smoke-real" in out

    stamp = passing_stamp("commit-smoke-real", root=ops_dir)
    assert stamp is not None
    assert stamp.passed is True
    assert stamp.bench_run_id == bench_run_id
    assert stamp.failed_conditions == []
