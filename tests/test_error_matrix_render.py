import json

from sdlc.benchmarks.error_matrix import (
    ErrorMatrix, ErrorMatrixCell, render_error_matrix_html, render_error_matrix_json)


def _em():
    return ErrorMatrix(
        case_id="c1", error_classes=["functional", "security"],
        arms=["opencode#m1"],
        cells=[ErrorMatrixCell(error_class="functional", arm_key="opencode#m1",
                              avg_failure_mass=0.5, n_runs=2)],
        max_value=0.5)


def test_json_round_trips():
    data = json.loads(render_error_matrix_json(_em()))
    assert data["case_id"] == "c1"
    assert data["cells"][0]["avg_failure_mass"] == 0.5


def test_html_is_wellformed_and_shows_classes_and_arms():
    html = render_error_matrix_html(_em())
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "functional" in html and "security" in html
    assert "opencode#m1" in html
    assert "0.50" in html


def test_html_handles_empty():
    html = render_error_matrix_html(ErrorMatrix(case_id="c1"))
    assert "No task records" in html


def test_html_escapes_arm_key():
    em = ErrorMatrix(case_id="c1", error_classes=["functional"], arms=["<x>"],
                    cells=[ErrorMatrixCell(error_class="functional", arm_key="<x>",
                                          avg_failure_mass=1.0, n_runs=1)],
                    max_value=1.0)
    html = render_error_matrix_html(em)
    assert "<x>" not in html.split("<body>")[1]
    assert "&lt;x&gt;" in html
