from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    BenchmarkSummary,
    CellStatus,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.recorder import RecordStore
from sdlc.benchmarks.report import aggregate, render_markdown
from sdlc.core.models import (
    HarnessKind,
)


def _rec(model, q, usd, secs, *, arm="a1", stage="code", judge="contract"):
    # 013 (R-11): stored-shape run id per arm, so records of two arms are
    # two runs and form two rows.
    return BenchmarkRecord(
        run_id=f"b1/c1#claude_code#{arm}",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage=stage,
        role="dev",
        harness=HarnessKind.CLAUDE_CODE,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=q, judge=judge),
        cost=CostBag(usd=usd),
        speed=SpeedBag(
            wall_clock_s=secs,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=secs),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def _graded(model, q, usd, secs, *, arm):
    """A graded pre-012 run (013 FR-034): a rubric-judged stage record, a
    post-code (merge) record and an oracle record -- the shape a case
    needs on two arms for composites to be shown and rankable."""
    oracle = _rec(model, 1.0, None, 1.0, arm=arm).model_copy(
        update={
            "scope": BenchmarkScope.ORACLE,
            "stage": "oracle",
            "role": "oracle",
            "quality": QualityScore(
                score=1.0, judge="oracle", components={"passed": 5.0, "total": 5.0}
            ),
        }
    )
    return [
        _rec(model, q, usd, secs, arm=arm, stage="architecture", judge="llm_judge"),
        _rec(model, None, None, 1.0, arm=arm, stage="merge"),
        oracle,
    ]


def test_aggregate_reads_store_and_returns_summaries(tmp_path):
    store = RecordStore(root=str(tmp_path), bench_run_id="b1")
    for rec in _graded("sonnet", 0.9, 1.0, 100, arm="a1") + _graded("opus", 0.5, 0.5, 50, arm="a2"):
        store.append(rec)
    sums = aggregate("b1", CompositeWeights(), root=str(tmp_path))
    by_model = {s.model: s for s in sums if s.stage == "architecture"}
    assert by_model["sonnet"].composite > by_model["opus"].composite


def test_render_markdown_has_headers_and_rows(tmp_path):
    recs = _graded("sonnet", 0.9, 1.0, 100, arm="a1")
    sums = aggregate("b1", CompositeWeights(), root=str(tmp_path), _records=recs)
    md = render_markdown(sums, records=recs)
    assert "| case" in md
    assert "sonnet" in md
    # 013 (contract 7.2): one graded arm -> no composite column; the
    # decision prints as a line in ## Notes instead.
    header = next(line for line in md.splitlines() if line.startswith("| case"))
    assert "composite" not in header
    assert "composite not shown for c1: 1 arm(s) with a graded run; it needs two" in md


def test_render_markdown_handles_empty():
    md = render_markdown([])
    assert "no records" in md.lower()


def test_aggregate_sort_is_deterministic_on_model_tie():
    recs = [
        _rec("beta", None, 1.0, 100, arm="a2"),
        _rec("alpha", None, 1.0, 100, arm="a1"),
    ]
    sums = aggregate("b1", CompositeWeights(), _records=recs)
    assert [s.model for s in sums] == ["alpha", "beta"]


def test_render_markdown_surfaces_stage_failures():
    """A degraded stage (research grounding rejected, pipeline continues
    per the 2026-07-20 decision) still leaves a trace in the human-facing
    report instead of vanishing silently."""
    failed = BenchmarkRecord(
        run_id="r",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="research",
        role="research",
        model="google:gemini-3.5-flash",
        prompt_sha="",
        quality=QualityScore(score=None, judge="error"),
        speed=SpeedBag(
            wall_clock_s=1.0,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=1),
        ),
        outcome=BenchmarkOutcome.FAIL,
        error="rejected:research.grounding: quote_not_found: https://x/1: 'q'",
    )
    sums = aggregate("b1", CompositeWeights(), _records=[failed])
    md = render_markdown(sums)
    assert "Stage failures" in md
    assert "c1 / research" in md
    assert "rejected:research.grounding" in md


def test_resolve_language_map_reads_case_manifests(tmp_path):
    from sdlc.benchmarks.report import resolve_language_map

    (tmp_path / "c1").mkdir()
    (tmp_path / "c1" / "case.yaml").write_text("case_id: c1\nlanguage: python\n", encoding="utf-8")
    (tmp_path / "c2").mkdir()  # no case.yaml
    m = resolve_language_map(["c1", "c2"], cases_dir=tmp_path)
    assert m == {"c1": "python", "c2": ""}


def test_write_heatmap_emits_both_files(tmp_path):
    from sdlc.benchmarks.report import write_heatmap
    from sdlc.benchmarks.runs import build_runs

    recs = [_rec("sonnet", 0.9, 1.0, 100)]
    html_p, json_p = write_heatmap(build_runs(recs), tmp_path, {"c1": "python"})
    assert html_p.exists() and json_p.exists()
    assert html_p.name == "heatmap.html" and json_p.name == "heatmap.json"
    assert "<!doctype html>" in html_p.read_text(encoding="utf-8")


def test_render_markdown_appends_calibration_when_provided():
    from datetime import datetime

    from sdlc.benchmarks.calibration import CalibrationReport
    from sdlc.benchmarks.models import CompositeWeights
    from sdlc.benchmarks.report import aggregate, render_markdown

    sums = aggregate("b1", CompositeWeights(), _records=[_rec("sonnet", 0.9, 1.0, 100)])
    rep = CalibrationReport(
        rubric="architect",
        judge_model="j",
        n_fixtures=10,
        epsilon=0.15,
        threshold=0.75,
        agreement_rate=0.8,
        mae=0.1,
        spearman=0.7,
        verdict="calibrated",
        computed_at=datetime(2026, 7, 24, tzinfo=UTC),
    )
    md = render_markdown(sums, calibration={"architect": rep})
    assert "Rubric calibration" in md


def test_scan_case_records_reads_across_multiple_bench_run_ids(tmp_path):
    from datetime import datetime, timedelta

    from sdlc.benchmarks.models import (
        BenchmarkOutcome,
        BenchmarkRecord,
        BenchmarkScope,
        QualityScore,
        SpeedBag,
    )
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.benchmarks.report import scan_case_records
    from sdlc.core.models import (
        HarnessKind,
    )

    t = datetime(2026, 7, 20, 10)

    def rec(run, task_id):
        return BenchmarkRecord(
            run_id=f"{run}/c1#opencode#m1",
            bench_run_id=run,
            case_id="c1",
            scope=BenchmarkScope.ORACLE_TASK,
            stage="oracle",
            task_id=task_id,
            role="oracle",
            harness=HarnessKind.OPENCODE,
            model="m1",
            quality=QualityScore(score=1.0, judge="oracle"),
            speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
            outcome=BenchmarkOutcome.PASS,
        )

    RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec("b1", "t01"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(rec("b2", "t01"))

    records = scan_case_records("c1", root=str(tmp_path))
    assert {r.bench_run_id for r in records} == {"b1", "b2"}


def test_scan_case_records_filters_other_cases(tmp_path):
    from datetime import datetime, timedelta

    from sdlc.benchmarks.models import (
        BenchmarkOutcome,
        BenchmarkRecord,
        BenchmarkScope,
        QualityScore,
        SpeedBag,
    )
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.benchmarks.report import scan_case_records
    from sdlc.core.models import (
        HarnessKind,
    )

    t = datetime(2026, 7, 20, 10)
    rec = BenchmarkRecord(
        run_id="b1/other#opencode#m1",
        bench_run_id="b1",
        case_id="other-case",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id="t01",
        role="oracle",
        harness=HarnessKind.OPENCODE,
        model="m1",
        quality=QualityScore(score=1.0, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec)
    assert scan_case_records("c1", root=str(tmp_path)) == []


def test_scan_case_records_empty_root_returns_empty(tmp_path):
    from sdlc.benchmarks.report import scan_case_records

    assert scan_case_records("c1", root=str(tmp_path / "does-not-exist")) == []


# --- 012 T009b (chaos seat): pre-012 section, Cells section, cell column ------


def _summary(case, stage, model, *, pre012=False, cell_id=None, arm=None):
    return BenchmarkSummary(
        case_id=case,
        stage=stage,
        harness=HarnessKind.OPENCODE,
        model=model,
        n=3,
        mean_quality=0.8,
        mean_cost_usd=0.01,
        mean_wall_clock_s=10.0,
        composite=0.9,
        cell_id=cell_id,
        arm=arm,
        pre012=pre012,
    )


def _cell_record(
    *,
    grading,
    completed,
    pipeline_finished=True,
    code_finished=True,
    last_stage="clarify",
    bench="b1",
    case="c1",
    cell_id="c1#opencode#a1",
    arm="a1",
):
    t = datetime(2026, 7, 4, 10)
    return BenchmarkRecord(
        run_id=f"{bench}/{cell_id}",
        bench_run_id=bench,
        case_id=case,
        scope=BenchmarkScope.CELL,
        stage="cell",
        role="cell",
        harness=HarnessKind.OPENCODE,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS if completed else BenchmarkOutcome.FAIL,
        kroker_commit="abc",
        tree_dirty=False,
        arm=arm,
        cell_id=cell_id,
        cell=CellStatus(
            pipeline_finished=pipeline_finished,
            code_finished=code_finished,
            completed=completed,
            last_stage=last_stage,
            grading=grading,
            child_result=None if completed else "child failed",
        ),
    )


# contract 7.4: 012 rows in the main table, pre-012 rows in their own section


def test_render_markdown_lists_012_rows_then_pre012_section():
    sums = [
        _summary("c012", "code", "sonnet", pre012=False, cell_id="c012#opencode#a1", arm="a1"),
        _summary("cold1", "code", "sonnet", pre012=True),
        _summary("cold2", "qa", "sonnet", pre012=True),
    ]
    md = render_markdown(sums)
    assert "## Pre-012 records (untrusted)" in md
    title_at = md.index("## Pre-012 records (untrusted)")
    # 012 rows live in the MAIN table, above the section
    assert md.index("c012") < title_at
    # the pre-012 rows render under the section, after it
    assert md.index("cold1") > title_at and md.index("cold2") > title_at
    # one sentence saying why: the reason is the missing commit provenance
    section = md[title_at : md.index("cold1")]
    assert "commit" in section.lower()


def test_render_markdown_without_pre012_rows_omits_the_section():
    sums = [_summary("c012", "code", "sonnet", pre012=False, cell_id="x", arm="a1")]
    md = render_markdown(sums)
    assert "## Pre-012 records (untrusted)" not in md


def test_render_markdown_pre012_only_still_renders_rows_under_the_section():
    sums = [_summary("cold1", "code", "sonnet", pre012=True)]
    md = render_markdown(sums)
    assert "## Pre-012 records (untrusted)" in md
    assert md.index("## Pre-012 records (untrusted)") < md.index("cold1")


# contract 8: ## Cells is replaced by the totals line of ## Runs


def test_runs_totals_line_counts_every_grading_state():
    sums = [_summary("c1", "code", "sonnet")]
    records = [
        _cell_record(
            grading="graded", completed=True, last_stage="merge", cell_id="c1#opencode#a0", arm="a0"
        ),
        _cell_record(
            grading="not_graded", completed=False, last_stage="clarify", cell_id="c1#opencode#a1"
        ),
        _cell_record(
            grading="not_graded",
            completed=False,
            last_stage="clarify",
            cell_id="c1#opencode#a2",
            arm="a2",
        ),
        _cell_record(
            grading="not_graded",
            completed=False,
            last_stage="research",
            cell_id="c1#opencode#a3",
            arm="a3",
        ),
        _cell_record(
            grading="grading_failed",
            completed=False,
            last_stage="code",
            cell_id="c1#opencode#a4",
            arm="a4",
        ),
    ]
    md = render_markdown(sums, calibration=None, records=records)
    assert "## Cells" not in md
    section = md[md.index("## Runs") :]
    assert "runs started: 5" in section
    assert "graded: 1" in section
    # the three not_graded cells are lost (R-2: whatever the label), with
    # the count per last stage
    assert "lost: 3" in section
    assert "clarify: 2" in section and "research: 1" in section
    assert "grading failed: 1" in section
    assert "discarded oracle records: 0" in section
    # every status came from a cell record, so none was derived
    assert "statuses derived: 0" in section


def test_render_markdown_has_no_cells_heading():
    sums = [_summary("c1", "code", "sonnet")]
    assert "## Cells" not in render_markdown(sums, calibration=None, records=None)
    assert "## Cells" not in render_markdown(
        sums, calibration=None, records=[_rec("sonnet", 0.9, 1.0, 100)]
    )
    assert "## Cells" not in render_markdown(
        sums,
        calibration=None,
        records=[_cell_record(grading="graded", completed=True, last_stage="merge")],
    )


# contract 8 item 3: the main table's fourth column is headed `arm`


def test_render_markdown_012_rows_show_arm_column():
    sums = [
        _summary("c012", "code", "sonnet", pre012=False, cell_id="c012#opencode#a1", arm="a1"),
        _summary("cold1", "code", "sonnet", pre012=True),
    ]
    md = render_markdown(sums)
    header = md[md.index("| case") : md.index("\n", md.index("| case"))]
    cells = [c.strip() for c in header.strip("|").split("|")]
    assert cells[3] == "arm"
    row_012 = next(line for line in md.splitlines() if "| c012" in line)
    assert "a1" in row_012
    # the pre-012 row keeps its model label and is not mislabelled with the arm
    row_pre = next(line for line in md.splitlines() if "cold1" in line and line.startswith("|"))
    assert "sonnet" in row_pre
    assert "a1" not in row_pre


# --- 013 T011: the report's nine sections (contract 8) -----------------------


def _012(recs, commit="abc123"):
    """kroker_commit on every record: the run becomes generation 012."""
    return [r.model_copy(update={"kroker_commit": commit}) for r in recs]


def _failed_research():
    return BenchmarkRecord(
        run_id="b1/c1#claude_code#a1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="research",
        role="research",
        harness=HarnessKind.CLAUDE_CODE,
        model="google:gemini-3.5-flash",
        prompt_sha="",
        quality=QualityScore(score=None, judge="error"),
        speed=SpeedBag(
            wall_clock_s=1.0,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=1),
        ),
        outcome=BenchmarkOutcome.FAIL,
        error="rejected:research.grounding: quote_not_found: https://x/1: 'q'",
    )


def _calib():
    from sdlc.benchmarks.calibration import CalibrationReport

    return {
        "architect": CalibrationReport(
            rubric="architect",
            judge_model="j",
            n_fixtures=10,
            epsilon=0.15,
            threshold=0.75,
            agreement_rate=0.8,
            mae=0.1,
            spearman=0.7,
            verdict="calibrated",
            computed_at=datetime(2026, 7, 24, tzinfo=UTC),
        )
    }


def _full_fixture():
    """Records that light up every section of contract 8: two graded 012
    arms (composite shown), a pre-012 arm, and a failed research stage."""
    recs = (
        _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1"))
        + _012(_graded("opus", 0.5, 0.5, 50, arm="a2"), commit="def456")
        + _graded("old", 0.4, 0.2, 20, arm="a3")
        + _012([_failed_research()])
    )
    return recs, aggregate("b1", CompositeWeights(), _records=recs)


_SECTIONS = [
    "# Benchmark report",
    "## Runs",
    "## Stages",
    "## Pre-012 records (untrusted)",
    "## Gate versus oracle",
    "## Stage failures",
    "## Success criteria",
    "## Notes",
    "## Rubric calibration",
]


def test_render_markdown_orders_every_section_per_contract():
    recs, sums = _full_fixture()
    md = render_markdown(
        sums,
        calibration=_calib(),
        records=recs,
        sc_rollup="## Success criteria\n\n2 of 2 runs left a run summary",
        notes=["evidence note"],
    )
    positions = [md.index(h) for h in _SECTIONS]
    assert positions == sorted(positions)
    for heading in _SECTIONS:
        assert md.count(heading) == 1


def test_runs_section_opens_with_totals_line_then_grid():
    recs = _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1"))
    sums = aggregate("b1", CompositeWeights(), _records=recs)
    md = render_markdown(sums, records=recs)
    section = md[md.index("## Runs") : md.index("## Stages")]
    # the totals line carries all seven figures (contract 8 item 2)
    assert "runs started: 1" in section
    assert "graded: 1" in section
    assert "lost: 0" in section
    assert "grading failed: 0" in section
    assert "no oracle: 0" in section
    assert "discarded oracle records: 0" in section
    assert "statuses derived: 1" in section
    # then the grid markdown (contract 2.5 header cells)
    assert section.index("runs started:") < section.index("| run | status | last |")


def test_stage_table_columns_in_contract_order():
    recs = _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1"))
    sums = aggregate("b1", CompositeWeights(), _records=recs)
    md = render_markdown(sums, records=recs)
    header = next(line for line in md.splitlines() if line.startswith("| case"))
    cells = [c.strip() for c in header.strip("|").split("|")]
    assert cells == [
        "case",
        "stage",
        "harness",
        "arm",
        "model",
        "n",
        "quality",
        "pass rate",
        "first attempt",
        "after repair",
        "tokens",
        "cost ($)",
        "wall (s)",
        "trust",
    ]
    # one graded arm: no composite column, the line sits in ## Notes
    assert "composite not shown for c1: 1 arm(s) with a graded run; it needs two" in md
    assert md.index("composite not shown for c1") > md.index("## Notes")


def test_stage_table_composite_column_when_a_case_shows_one():
    recs = _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1")) + _012(
        _graded("opus", 0.5, 0.5, 50, arm="a2"), commit="def456"
    )
    sums = aggregate("b1", CompositeWeights(), _records=recs)
    md = render_markdown(sums, records=recs)
    header = next(line for line in md.splitlines() if line.startswith("| case"))
    cells = [c.strip() for c in header.strip("|").split("|")]
    assert cells.index("composite") == 13
    assert cells[12] == "wall (s)" and cells[14] == "trust"
    assert "composite not shown" not in md


def test_pre012_section_uses_the_same_header():
    recs = _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1")) + _graded("old", 0.4, 0.2, 20, arm="a3")
    sums = aggregate("b1", CompositeWeights(), _records=recs)
    md = render_markdown(sums, records=recs)
    headers = [line for line in md.splitlines() if line.startswith("| case")]
    assert len(headers) == 2
    assert headers[0] == headers[1]


def test_qa_copy_row_prints_copy_of_code():
    s = _summary("c1", "qa", "sonnet").model_copy(update={"qa_is_copy": True})
    md = render_markdown([s])
    row = next(line for line in md.splitlines() if line.startswith("| c1") and "| qa |" in line)
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[7] == "copy of code"


def test_gate_versus_oracle_section_requires_graded_runs():
    graded = _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1"))
    md = render_markdown(aggregate("b1", CompositeWeights(), _records=graded), records=graded)
    assert "## Gate versus oracle" in md
    lost = [_rec("sonnet", 0.9, 1.0, 100, stage="research")]
    md2 = render_markdown(aggregate("b1", CompositeWeights(), _records=lost), records=lost)
    assert "## Gate versus oracle" not in md2


def test_render_markdown_is_ascii_with_every_section():
    recs, sums = _full_fixture()
    md = render_markdown(
        sums,
        calibration=_calib(),
        records=recs,
        sc_rollup="## Success criteria\n\n2 of 2 runs left a run summary",
        notes=["evidence note"],
    )
    md.encode("ascii")


def test_render_markdown_with_no_records_returns_no_records_report():
    assert render_markdown([]) == "# Benchmark report\n\nNo records found.\n"
    assert "No records found." in render_markdown([], records=[])


def test_success_criteria_and_notes_once_before_calibration():
    recs = _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1"))
    sums = aggregate("b1", CompositeWeights(), _records=recs)
    md = render_markdown(
        sums,
        calibration=_calib(),
        records=recs,
        sc_rollup="## Success criteria\n\n1 of 1 runs left a run summary",
        notes=["evidence note"],
    )
    assert md.count("## Success criteria") == 1
    assert md.count("## Notes") == 1
    assert md.index("## Notes") > md.index("## Success criteria")
    assert md.index("## Rubric calibration") > md.index("## Notes")
    assert "evidence note" in md
    assert "1 of 1 runs left a run summary" in md


# --- 013 T012: one writer for both paths (contract 11.1 to 11.3) ---------------

_SCORE_FILE_NAMES = {
    "report.md",
    "grid.html",
    "grid.json",
    "heatmap.html",
    "heatmap.json",
    "gate-oracle.html",
    "gate-oracle.json",
    "sc-rollup.html",
    "sc-rollup.json",
    "waste-matrix.html",
    "waste-matrix.json",
    "agreement-matrix.html",
    "agreement-matrix.json",
    "task-matrix.html",
    "task-matrix.json",
    "error-matrix.html",
    "error-matrix.json",
}


def test_finalize_benchmark_report_uses_the_shared_writer(tmp_path, monkeypatch):
    """finalize_benchmark_report is the score command's writer aimed at the
    bench directory (contract 11.2): same files, byte-identical report, and
    no record file touched (11.3)."""
    import asyncio

    from sdlc.benchmarks.evidence import load_evidence
    from sdlc.benchmarks.report import finalize_benchmark_report
    from sdlc.benchmarks.score import load_config_weights, write_score

    runs_root = tmp_path / "runs"
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(runs_root))
    export = tmp_path / "export"
    export.mkdir()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(export))
    cases = tmp_path / "cases"
    (cases / "c1").mkdir(parents=True)
    (cases / "c1" / "tasks.yaml").write_text(
        'tasks:\n  - id: t01\n    error_class: functional\n    oracle_tests: ["x::y"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases))

    store = RecordStore(root=str(runs_root), bench_run_id="b1")
    for rec in _012(_graded("sonnet", 0.9, 1.0, 100, arm="a1")):
        store.append(rec)

    bench_dir = runs_root / "b1"
    jsonls = sorted(bench_dir.rglob("*.jsonl"))
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in jsonls}

    result = asyncio.run(finalize_benchmark_report("b1"))

    assert result == str(bench_dir / "report.md")
    # the contract 11.1 file set, beside report.md
    assert _SCORE_FILE_NAMES <= {p.name for p in bench_dir.iterdir()}
    # contract 11.3: no .jsonl file's bytes or mtime change
    for p in jsonls:
        assert (p.stat().st_mtime_ns, p.read_bytes()) == before[p]

    # contract 11.2: the same writer gives the same report
    ev = load_evidence(bench="b1", root=str(runs_root), export_root_=str(export))
    out2 = tmp_path / "score-out"
    write_score(ev, out2, load_config_weights())
    assert (bench_dir / "report.md").read_bytes() == (out2 / "report.md").read_bytes()
