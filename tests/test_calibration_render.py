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


# --- 012 T005 (RED): the plan stage shows its trust value -------------------


def test_trust_for_stage_plan_uses_the_planner_rubric():
    """contract §1.6 / FR-004: records use the stage name 'plan'; the trust
    lookup must return the planner bucket's value for 'plan' (and keep
    serving the legacy 'planning' spelling). The planner bucket's rate is
    distinct from every other bucket used in this file."""
    from sdlc.benchmarks.calibration import STAGE_TO_RUBRIC

    assert STAGE_TO_RUBRIC.get("plan") == "planner"
    reports = {"planner": _rep("planner", rate=0.91, verdict="planner-calibrated")}
    assert "0.91" in trust_for_stage("plan", reports)
    assert "0.91" in trust_for_stage("planning", reports)


def test_stage_to_rubric_keys_are_record_or_heatmap_stages():
    """FR-005 pin: every STAGE_TO_RUBRIC key must be a stage name records
    actually use (CELL_STAGE_ORDER) or a heatmap column (CANONICAL_STAGES)
    -- a renamed stage must break this pin instead of silently losing its
    trust mapping."""
    from sdlc.benchmarks.calibration import STAGE_TO_RUBRIC
    from sdlc.benchmarks.heatmap import CANONICAL_STAGES
    from sdlc.benchmarks.models import CELL_STAGE_ORDER

    allowed = set(CELL_STAGE_ORDER) | set(CANONICAL_STAGES)
    assert set(STAGE_TO_RUBRIC) <= allowed


def test_corpus_registers_every_judged_stage_rubric_key():
    """Pin against the shipped corpus: each rubric-map key a judged stage's
    step passes to ctx.judge -- clarifier (clarify), architect
    (architecture), planner (plan), qa (code), research (research) -- must
    be registered by at least one benchmarks/cases/*/case.yaml, so a
    vocabulary change on either side breaks loudly here."""
    from pathlib import Path

    import yaml

    corpus = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"
    registered: set[str] = set()
    for manifest in sorted(corpus.glob("*/case.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        registered |= set((data.get("rubrics") or {}).keys())
    for key in ("clarifier", "architect", "planner", "qa", "research"):
        assert key in registered, (
            f"no shipped case registers the {key!r} rubric key a judged "
            "stage's step passes to ctx.judge"
        )
