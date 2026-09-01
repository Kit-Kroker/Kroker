from datetime import UTC, datetime

from sdlc.benchmarks.calibration import (
    CalibrationReport,
    load_calibration_reports,
    render_calibration_html,
    render_calibration_markdown,
    trust_for_stage,
    write_calibration_report,
)


def _rep(rubric, rate=0.83, verdict="calibrated"):
    return CalibrationReport(
        rubric=rubric,
        judge_model="openai/gpt-5.2",
        n_fixtures=24,
        epsilon=0.15,
        threshold=0.75,
        agreement_rate=rate,
        mae=0.09,
        spearman=0.71,
        verdict=verdict,
        computed_at=datetime(2026, 7, 24, tzinfo=UTC),
    )


def test_write_then_load_round_trips(tmp_path):
    write_calibration_report(_rep("architect"), tmp_path / "architect")
    reports = load_calibration_reports(tmp_path)
    assert "architect" in reports
    assert reports["architect"].agreement_rate == 0.83


def test_markdown_lists_rubric_stats_and_verdict():
    md = render_calibration_markdown({"architect": _rep("architect")})
    assert "Rubric calibration" in md
    assert "architect" in md and "0.83" in md and "calibrated" in md


def test_html_lists_rubric_stats():
    html = render_calibration_html({"architect": _rep("architect")})
    assert "architect" in html and "0.83" in html


def test_trust_for_stage_maps_record_stage_to_rubric():
    reports = {"architect": _rep("architect", rate=0.83)}
    assert "0.83" in trust_for_stage("architecture", reports)
    assert trust_for_stage("planning", reports) == "uncalibrated"
    assert trust_for_stage("code", reports) == "-"  # no rubric for code
