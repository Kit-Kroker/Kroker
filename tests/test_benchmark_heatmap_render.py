"""013 T008 (RED): heatmap scales and rendering, contract section 4.

Scales (4.1, `step_for` in `sdlc.benchmarks.heatmap_render`), cell states
(4.2, via T007's `build_layers`), HTML rendering (4.3, fixed format), the
single-hue stylesheet and no red/green (4.4), the stage note (3.7), the
calibration block, the pre-012 records line, the layered JSON, and the
removal of the old heatmap names. Record factories are copied verbatim
from `tests/test_benchmark_heatmap_layers.py`. Every test imports its
`sdlc.benchmarks` symbol function-local (the repo's RED convention).
"""

import json
import re
from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CostBag,
    QualityScore,
    SpeedBag,
)

_T0 = datetime(2026, 7, 4, 10, 0)
_T1 = datetime(2026, 7, 4, 10, 30)
_T2 = datetime(2026, 7, 4, 11, 0)


def _record(**kw):
    base = dict(
        run_id="b1/c1#opencode#a1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="architecture",
        role="architect",
        model="anthropic:claude-sonnet-4-6",
        prompt_sha="abc",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(
            wall_clock_s=12.0,
            started_at=_T0,
            ended_at=_T0.replace(minute=12),
        ),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return BenchmarkRecord(**base)


def _stage(run_id, stage, start, outcome=BenchmarkOutcome.PASS, wall=12.0, **kw):
    """A run-level (no task) stage record."""
    return _record(
        run_id=run_id,
        stage=stage,
        role=stage,
        scope=BenchmarkScope.STAGE,
        outcome=outcome,
        speed=SpeedBag(wall_clock_s=wall, started_at=start, ended_at=start),
        **kw,
    )


def _task(run_id, stage, task_id, attempt, start, outcome, wall=10.0, **kw):
    """A task-attempt record (code attempts, per-task qa)."""
    return _record(
        run_id=run_id,
        stage=stage,
        role=stage,
        scope=BenchmarkScope.TASK_ATTEMPT,
        task_id=task_id,
        attempt=attempt,
        outcome=outcome,
        speed=SpeedBag(wall_clock_s=wall, started_at=start, ended_at=start),
        **kw,
    )


def _oracle(run_id, passed, total, start=_T2, **kw):
    """An oracle-scope record; `passed`/`total` ride quality.components."""
    kw.setdefault("scope", BenchmarkScope.ORACLE)
    return _record(
        run_id=run_id,
        stage="oracle",
        role="oracle",
        model="openai/gpt-5.2",
        quality=QualityScore(
            score=passed / total, judge="oracle", components={"passed": passed, "total": total}
        ),
        speed=SpeedBag(wall_clock_s=1.0, started_at=start, ended_at=start),
        **kw,
    )


def _cell(
    run_id, start, last_stage, *, code_finished=True, pipeline_finished=True, grading="graded"
):
    """A 012 cell record carrying the recorded status."""
    return _record(
        run_id=run_id,
        stage="cell",
        role="cell",
        scope=BenchmarkScope.CELL,
        model="deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=start, ended_at=start),
        cell=CellStatus(
            pipeline_finished=pipeline_finished,
            code_finished=code_finished,
            completed=pipeline_finished and code_finished,
            last_stage=last_stage,
            grading=grading,
        ),
    )


def _graded(run_id, start, passed=3, total=4, commit=None, arm="a1"):
    """A minimal derived graded run: analyze (code finished) + oracle."""
    extra = {}
    if commit is not None:
        extra["kroker_commit"] = commit
    if arm is not None:
        extra["arm"] = arm
    return [
        _stage(run_id, "analyze", start, wall=12.0, **extra),
        _oracle(run_id, passed, total, start, **extra),
    ]


def _ids(commit="x", arm="a1"):
    """Extra record fields pinning the run to one generation and arm."""
    extra = {}
    if commit is not None:
        extra["kroker_commit"] = commit
    if arm is not None:
        extra["arm"] = arm
    return extra


def _lost(run_id, start, last_stage, stage_records):
    """A lost run: a cell record says code did not finish (contract 1.2)."""
    return stage_records + [
        _cell(
            run_id,
            start,
            last_stage,
            code_finished=False,
            pipeline_finished=False,
            grading="not_graded",
        )
    ]


def _one(hm, layer, stage):
    """The single cell of one layer and stage on a one-row heatmap."""
    got = [c for c in hm.cells if c.layer == layer and c.stage == stage]
    assert len(got) == 1, f"expected one {layer}/{stage} cell, got {len(got)}"
    return got[0]


def _n_graded(n, case="c1", commit="x"):
    """n graded runs of one case/arm/generation (contract 4.2 fixtures)."""
    records = []
    for i in range(n):
        records.extend(_graded(f"b{i + 1}/{case}#opencode#a1", _T0, commit=commit))
    return records


# --- 4.1 step_for on every scale edge -------------------------------------------


def test_step_for_edges_attrition():
    from sdlc.benchmarks.heatmap_render import step_for

    assert step_for("attrition", 0.0) == 0
    assert step_for("attrition", 0.05) == 1
    assert step_for("attrition", 0.0501) == 2
    assert step_for("attrition", 0.10) == 2
    assert step_for("attrition", 0.25) == 3
    assert step_for("attrition", 0.2501) == 4
    assert step_for("attrition", 1.0) == 4


def test_step_for_edges_first_attempt_and_wasted_tokens():
    from sdlc.benchmarks.heatmap_render import step_for

    for layer in ("first_attempt", "wasted_tokens"):
        assert step_for(layer, 0.0) == 0, layer
        assert step_for(layer, 0.10) == 1, layer
        assert step_for(layer, 0.1001) == 2, layer
        assert step_for(layer, 0.25) == 2, layer
        assert step_for(layer, 0.2501) == 3, layer
        assert step_for(layer, 0.50) == 3, layer
        assert step_for(layer, 0.5001) == 4, layer
        assert step_for(layer, 1.0) == 4, layer


def test_step_for_edges_oracle():
    from sdlc.benchmarks.heatmap_render import step_for

    assert step_for("oracle", 1.0) == 0
    assert step_for("oracle", 0.9) == 1
    assert step_for("oracle", 0.8999) == 2
    assert step_for("oracle", 0.75) == 2
    assert step_for("oracle", 0.7499) == 3
    assert step_for("oracle", 0.5) == 3
    assert step_for("oracle", 0.49) == 4
    assert step_for("oracle", 0.0) == 4


# --- 4.2 cell states (PIN: T007's build_layers rule; red is a stop-guard) -------


def test_cell_state_blank_when_den_is_zero():  # PIN:
    """Contract 4.2: blank when den == 0 -- the research-disabled row of
    the two-row fixture has no research units at all."""
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    records = [
        _stage("b1/c1#opencode#a1", "research", _T0, wall=1.0, **_ids()),
        *_graded("b1/c1#opencode#a1", _T1, commit="x"),
        *_graded("b1/c2#opencode#a1", _T1, commit="x"),  # research disabled
    ]
    hm = build_layers(build_runs(records))

    keys = {r.case_id: r.key for r in hm.rows}
    cell = next(
        c
        for c in hm.cells
        if c.layer == "first_attempt" and c.stage == "research" and c.row == keys["c2"]
    )
    assert cell.den == 0.0
    assert cell.state == "blank"


def test_cell_state_low_n_at_four_observations():  # PIN:
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_n_graded(4)))
    assert _one(hm, "attrition", "analyze").state == "low_n"


def test_cell_state_value_at_five_observations():  # PIN:
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_n_graded(5)))
    assert _one(hm, "attrition", "analyze").state == "value"


def test_cell_state_copy_for_qa_of_an_all_copy_pre012_row():  # PIN:
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b0/c1#opencode#m"  # pre-012: no record carries kroker_commit
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, wall=1.0),
        _task(run_id, "qa", "t1", 1, _T1, BenchmarkOutcome.PASS, wall=1.0),
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 4, 4),
    ]
    hm = build_layers(build_runs(records))
    assert _one(hm, "first_attempt", "qa").state == "copy"


# --- 4.3 HTML rendering -----------------------------------------------------------


def test_html_value_cell_takes_its_step_class_and_text():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_n_graded(5)))
    html = render_heatmap_html(hm)

    # attrition/analyze on five graded runs: 0.0, step 0, five observations
    assert '<td class="hm-s0">0.00 (0/5)</td>' in html


def test_html_low_n_cell_takes_the_grey_class_and_keeps_text():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_n_graded(4)))
    html = render_heatmap_html(hm)

    # four observations: grey class, but the figure and its denominator stay
    assert '<td class="hm-low">0.00 (0/4)</td>' in html


def test_html_blank_cell_has_no_text_and_no_fill():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    records = [
        _stage("b1/c1#opencode#a1", "research", _T0, wall=1.0, **_ids()),
        *_graded("b1/c1#opencode#a1", _T1, commit="x"),
        *_graded("b1/c2#opencode#a1", _T1, commit="x"),  # research disabled
    ]
    html = render_heatmap_html(build_layers(build_runs(records)))

    assert '<td class="hm-empty"></td>' in html


def test_html_copy_cell_reads_copy_of_code():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    run_id = "b0/c1#opencode#m"
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, wall=1.0),
        _task(run_id, "qa", "t1", 1, _T1, BenchmarkOutcome.PASS, wall=1.0),
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 4, 4),
    ]
    html = render_heatmap_html(build_layers(build_runs(records)))

    assert "<td>copy of code</td>" in html


def test_html_oracle_mark_prints_passed_total():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_n_graded(1)))  # oracle 3/4 = 0.75 -> step 2
    html = render_heatmap_html(hm)

    assert '<span class="hm-s2">3/4</span>' in html


def test_same_value_gives_the_same_class_in_any_report():
    """SC-007 / contract 4.4: two heatmaps from different data whose cells
    hold the same ratio 0.25 render the same step class."""
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    # first_attempt code: 2 failed first attempts of 8 task units
    attempt_runs = []
    for i in range(8):
        run_id = f"b{i + 1}/c1#opencode#a1"
        outcome = BenchmarkOutcome.FAIL if i < 2 else BenchmarkOutcome.PASS
        attempt_runs.append(_task(run_id, "code", "t1", 1, _T0, outcome, 1.0, **_ids()))
        attempt_runs.extend(_graded(run_id, _T2, commit="x"))
    html_first = render_heatmap_html(build_layers(build_runs(attempt_runs)))

    # wasted research tokens: two lost runs' 300 of 1200 tokens at research
    x = _ids()
    waste_runs = []
    for i in range(2):
        run_id = f"b{i + 1}/c1#opencode#a1"
        waste_runs.extend(
            _lost(
                run_id,
                _T0,
                "research",
                [_stage(run_id, "research", _T0, BenchmarkOutcome.FAIL, 1.0, **x)],
            )
        )
    for i in range(3, 9):
        run_id = f"b{i}/c1#opencode#a1"
        waste_runs.append(_stage(run_id, "research", _T0, BenchmarkOutcome.PASS, 1.0, **x))
        waste_runs.extend(_graded(run_id, _T1, commit="x"))
    html_waste = render_heatmap_html(build_layers(build_runs(waste_runs)))

    assert '<td class="hm-s2">0.25 ' in html_first
    assert '<td class="hm-s2">0.25 ' in html_waste


# --- 4.4 stylesheet ---------------------------------------------------------------


def test_stylesheet_five_steps_one_hue_grey_and_no_red_green():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    html = render_heatmap_html(build_layers(build_runs(_n_graded(5))))

    steps = re.findall(r"\.hm-s(\d)\{background:hsl\((\d+),", html)
    assert sorted(step for step, _ in steps) == ["0", "1", "2", "3", "4"]
    assert len({hue for _, hue in steps}) == 1  # one hue, five lightness steps
    assert ".hm-low" in html
    assert "green" not in html.lower()
    assert "hsl(120" not in html


# --- 3.7 note, calibration block, pre-012 line ------------------------------------


def _render_graded(**kw):
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    return render_heatmap_html(build_layers(build_runs(_n_graded(5))), **kw)


def test_the_stage_note_is_present_verbatim():
    html = _render_graded()
    assert (
        "A stage record is written when the stage ends. A run that stopped "
        "inside a stage shows the stage before it as its last."
    ) in html


def test_calibration_block_is_appended():
    html = _render_graded(calibration_html="<p>CALIB-MARKER</p>")
    assert "CALIB-MARKER" in html


def test_pre012_records_line_kept_and_absent_for_all_012():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.heatmap_render import render_heatmap_html
    from sdlc.benchmarks.runs import build_runs

    # 2 pre-012 runs (analyze + oracle each) beside one 012 run
    mixed = _n_graded(2, case="c1", commit=None) + _n_graded(1, case="c1", commit="x")
    html = render_heatmap_html(build_layers(build_runs(mixed)))
    assert "includes 4 pre-012 records (untrusted)" in html

    html_012 = render_heatmap_html(build_layers(build_runs(_n_graded(1, commit="x"))))
    assert "pre-012" not in html_012


# --- layered JSON -----------------------------------------------------------------


def test_render_heatmap_json_carries_layers_and_no_raw_records():  # PIN:
    from sdlc.benchmarks.heatmap import build_layers, render_heatmap_json
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_n_graded(5)))
    data = json.loads(render_heatmap_json(hm))

    assert {"rows", "stages", "cells", "oracle_marks"} <= set(data)
    assert "records" not in data
    assert all("records" not in cell for cell in data["cells"])


# --- removal of the old heatmap (data-model section 3, "Removed") -----------------


def test_removed_heatmap_names_are_gone():
    import sdlc.benchmarks.heatmap as hm_mod

    for name in (
        "Heatmap",
        "HeatmapCell",
        "build_heatmap",
        "ORACLE_STAGE",
        "REWORK_OUTCOMES",
        "render_heatmap_html",  # moved to heatmap_render (data-model section 3)
    ):
        assert not hasattr(hm_mod, name), name
