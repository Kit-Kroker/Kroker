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
    sums = aggregate(
        "b1",
        CompositeWeights(),
        root=str(tmp_path),
        _records=[_rec("sonnet", 0.9, 1.0, 100), _rec("opus", 0.5, 0.5, 50)],
    )
    md = render_markdown(sums)
    assert "| case" in md or "case" in md
    assert "sonnet" in md and "opus" in md
    assert "composite" in md.lower()


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

    recs = [_rec("sonnet", 0.9, 1.0, 100)]
    html_p, json_p = write_heatmap(recs, tmp_path, {"c1": "python"})
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


# contract 7.5: the Cells section, built from cell-scope records


def test_render_markdown_cells_section_counts_every_grading_state():
    sums = [_summary("c1", "code", "sonnet")]
    records = [
        _cell_record(grading="graded", completed=True, last_stage="merge"),
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
    assert "## Cells" in md
    section = md[md.index("## Cells") :]
    assert "5" in section  # cells started: one per cell record
    assert "not graded" in section
    assert "grading failed" in section or "grading_failed" in section
    # the count per last_stage, rendered readably
    assert ("clarify: 2" in section) or ("clarify=2" in section)
    assert ("research: 1" in section) or ("research=1" in section)
    assert "1" in section  # completed / graded / grading failed counts


def test_render_markdown_without_cell_records_has_no_cells_section():
    sums = [_summary("c1", "code", "sonnet")]
    assert "## Cells" not in render_markdown(sums, calibration=None, records=None)
    assert "## Cells" not in render_markdown(
        sums, calibration=None, records=[_rec("sonnet", 0.9, 1.0, 100)]
    )


# contract 7.4: the main table's cell column carries the arm for 012 rows


def test_render_markdown_012_rows_show_arm_in_cell_column():
    sums = [
        _summary("c012", "code", "sonnet", pre012=False, cell_id="c012#opencode#a1", arm="a1"),
        _summary("cold1", "code", "sonnet", pre012=True),
    ]
    md = render_markdown(sums)
    header = md[md.index("| case") : md.index("\n", md.index("| case"))]
    assert "cell" in header
    row_012 = next(line for line in md.splitlines() if "| c012" in line)
    assert "a1" in row_012
    # the pre-012 row keeps its model label and is not mislabelled with the arm
    row_pre = next(line for line in md.splitlines() if "cold1" in line and line.startswith("|"))
    assert "sonnet" in row_pre
    assert "a1" not in row_pre
