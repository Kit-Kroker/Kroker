"""render_report must not assume the optional numbers travel together.

After E-83 Task 1 a one-sided judge populates mean_baseline while leaving
delta and floor None, which the old single `if` formatted unconditionally."""
from sdlc.eval.cli import render_report
from sdlc.eval.verdict import GateVerdict, JudgeStatus, PromptGateResult


def test_render_handles_baseline_mean_without_delta():
    r = PromptGateResult(
        verdict=GateVerdict.PASS, judge_status=JudgeStatus.UNAVAILABLE,
        role="clarify", case="cat-cafe-monitoring", reason="one-sided",
        mean_baseline=0.5, n_baseline=2)
    text = render_report(r)
    assert "baseline  0.50" in text
    assert "delta" not in text


def test_render_shows_delta_when_the_comparison_ran():
    r = PromptGateResult(
        verdict=GateVerdict.PASS, judge_status=JudgeStatus.MEASURED,
        role="clarify", case="c", reason="ok",
        mean_baseline=0.80, mean_working=0.85, delta=0.05, floor=0.05,
        n_baseline=3, n_working=3)
    text = render_report(r)
    assert "delta     +0.05" in text
