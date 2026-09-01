import json
from datetime import datetime

from sdlc.benchmarks.task_matrix import (
    TaskMatrix,
    TaskMatrixColumn,
    render_task_matrix_html,
    render_task_matrix_json,
)


def _tm():
    col = TaskMatrixColumn(
        bench_run_id="b1",
        cell_id="c1#opencode#m1",
        harness="opencode",
        model="m1",
        started_at=datetime(2026, 7, 20, 10),
        mean_score=0.5,
    )
    return TaskMatrix(
        case_id="c1",
        task_ids=["t01", "t02"],
        columns=[col],
        scores={"t01": {"b1#c1#opencode#m1": 1.0}, "t02": {"b1#c1#opencode#m1": None}},
    )


def test_json_round_trips():
    data = json.loads(render_task_matrix_json(_tm()))
    assert data["case_id"] == "c1"
    assert data["task_ids"] == ["t01", "t02"]


def test_html_is_wellformed_and_shows_task_rows():
    html = render_task_matrix_html(_tm())
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "t01" in html and "t02" in html
    assert "m1" in html


def test_html_colors_pass_fail_and_missing_distinctly():
    html = render_task_matrix_html(_tm())
    # t01 scored 1.0 -> green; t02 is None -> grey/empty marker
    assert "#3aa757" in html
    assert "#e5e5e5" in html


def test_html_handles_no_columns():
    tm = TaskMatrix(case_id="c1", task_ids=["t01"], columns=[], scores={"t01": {}})
    html = render_task_matrix_html(tm)
    assert "No task records" in html


def test_html_escapes_case_id():
    tm = TaskMatrix(case_id="<x>", task_ids=[], columns=[], scores={})
    html = render_task_matrix_html(tm)
    assert "<x>" not in html.split("<body>")[1] or "&lt;x&gt;" in html
