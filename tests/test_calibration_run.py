from datetime import UTC, datetime

from sdlc.benchmarks.calibration import (
    CalibrationFixture,
    CalibrationReport,
    rubric_sha_of,
    run_calibration,
)
from sdlc.benchmarks.models import QualityScore


def _fx(human, author="zai-coding-plan/glm-5.2"):
    return CalibrationFixture(
        artifact_json="{}",
        rubric_ref="c/architect",
        rubric_text="r",
        rubric_sha=rubric_sha_of("r"),
        author_model=author,
        human_score=human,
    )


def test_run_calibration_scores_and_reports():
    fixtures = [_fx(0.8), _fx(0.6), _fx(0.4)]

    # judge always returns human+0.05 -> all within epsilon
    def judge(inp):
        # the fixture order is preserved; map by identity of rubric not needed
        return QualityScore(score=0.85, judge="llm_judge")

    rep = run_calibration(
        "architect", fixtures, "openai/gpt-5.2", now=datetime(2026, 7, 24, tzinfo=UTC), judge=judge
    )
    assert isinstance(rep, CalibrationReport)
    assert rep.rubric == "architect"
    assert rep.n_fixtures == 3
    assert rep.judge_model == "openai/gpt-5.2"


def test_run_calibration_skips_same_family_fixture():
    # judge shares family with this fixture's author -> skipped (ADR-6)
    fixtures = [_fx(0.8, author="openai/gpt-4.9"), _fx(0.5, author="zai/glm-5.2")]

    def judge(inp):
        return QualityScore(score=0.5, judge="llm_judge")

    rep = run_calibration("architect", fixtures, "openai/gpt-5.2", judge=judge)
    assert rep.n_fixtures == 1  # the openai-authored fixture was skipped


def test_run_calibration_excludes_judge_errors_from_pairs():
    fixtures = [_fx(0.8), _fx(0.5)]
    calls = {"n": 0}

    def judge(inp):
        calls["n"] += 1
        if calls["n"] == 1:
            return QualityScore(score=None, judge="error")  # judge failed
        return QualityScore(score=0.5, judge="llm_judge")

    rep = run_calibration("architect", fixtures, "openai/gpt-5.2", judge=judge)
    assert rep.n_fixtures == 1  # only the successfully-judged pair counts


def test_importing_calibration_does_not_import_temporalio():
    import subprocess
    import sys

    code = (
        "import sys; import sdlc.benchmarks.calibration; "
        "sys.exit(1 if 'temporalio' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    assert result.returncode == 0, (
        "importing sdlc.benchmarks.calibration pulled in temporalio:\n" + result.stderr
    )
