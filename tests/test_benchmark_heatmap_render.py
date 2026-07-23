import json

from sdlc.benchmarks.heatmap import (
    Heatmap, HeatmapCell, render_heatmap_html, render_heatmap_json,
)


def _hm():
    return Heatmap(
        cells=[HeatmapCell(case="c1", stage="code", gate_rejects=2,
                           fix_attempts=5, oracle_fails=0, n_runs=2,
                           density=3.5),
               HeatmapCell(case="c2", stage="code", gate_rejects=0,
                           fix_attempts=0, oracle_fails=0, n_runs=1,
                           density=0.0)],
        cases=["c1", "c2"], stages=["code"], max_density=3.5,
        language_by_case={"c1": "python", "c2": "go"})


def test_json_round_trips_and_keeps_breakdown():
    data = json.loads(render_heatmap_json(_hm()))
    assert data["max_density"] == 3.5
    cell = next(c for c in data["cells"] if c["case"] == "c1")
    assert cell["gate_rejects"] == 2 and cell["fix_attempts"] == 5


def test_html_is_wellformed_and_escapes_and_has_language_grids():
    html = render_heatmap_html(_hm())
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "python" in html and "go" in html      # per-language grids
    assert "3.5" in html                            # density shown/tooltip


def test_html_escapes_case_names():
    hm = Heatmap(cells=[HeatmapCell(case="<x>", stage="code", gate_rejects=1,
                                    fix_attempts=0, oracle_fails=0, n_runs=1,
                                    density=1.0)],
                 cases=["<x>"], stages=["code"], max_density=1.0,
                 language_by_case={"<x>": ""})
    assert "<x>" not in render_heatmap_html(hm)
    assert "&lt;x&gt;" in render_heatmap_html(hm)


def test_html_handles_empty():
    html = render_heatmap_html(Heatmap())
    assert "No records" in html


def test_calibration_html_is_embedded():
    html = render_heatmap_html(_hm(), calibration_html="<p>CALIB-MARKER</p>")
    assert "CALIB-MARKER" in html
