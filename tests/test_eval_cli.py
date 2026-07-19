"""CLI-level behavior: rendering, role refusal, case resolution, defaults."""
import pytest

from sdlc.eval.cli import default_judge_model, render_report, run_eval
from sdlc.eval.compare import EvalError, EvalReport, RunScore


def test_render_shows_head_working_and_delta():
    rep = EvalReport(role="reviewer", case="c1", judge_model="openai/gpt-5.2",
                     against_ref="HEAD", mean_a=0.71, mean_b=0.83,
                     mean_delta=0.12, runs=[RunScore(score_a=0.71, score_b=0.83,
                                                     delta=0.12)])
    text = render_report(rep)
    assert "0.71" in text and "0.83" in text and "+0.12" in text


def test_render_unchanged():
    rep = EvalReport(role="reviewer", case="c1", judge_model="m",
                     against_ref="HEAD", unchanged=True)
    assert "no change" in render_report(rep).lower()


def test_render_no_baseline():
    rep = EvalReport(role="reviewer", case="c1", judge_model="m",
                     against_ref="HEAD", no_baseline=True, mean_b=0.8,
                     runs=[RunScore(score_a=None, score_b=0.8, delta=None)])
    assert "no committed baseline" in render_report(rep).lower()


def test_run_eval_refuses_deps_role(tmp_path):
    with pytest.raises(EvalError, match="deps"):
        run_eval("architect", against="HEAD", case="c1", k=1,
                 judge_model="openai/gpt-5.2", agents_dir=tmp_path,
                 cases_root=tmp_path, repo_root=tmp_path)


def test_run_eval_refuses_unknown_role(tmp_path):
    with pytest.raises(EvalError, match="unknown role"):
        run_eval("nonsense", against="HEAD", case="c1", k=1,
                 judge_model="openai/gpt-5.2", agents_dir=tmp_path,
                 cases_root=tmp_path, repo_root=tmp_path)


def test_default_judge_model_reads_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("default_judge_model: openai/gpt-5.2\n", encoding="utf-8")
    assert default_judge_model(cfg) == "openai/gpt-5.2"


def test_default_judge_model_raises_when_missing(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("weights: {}\n", encoding="utf-8")
    with pytest.raises(EvalError):
        default_judge_model(cfg)
