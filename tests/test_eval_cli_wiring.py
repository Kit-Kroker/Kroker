from __future__ import annotations

from sdlc.cli import build_parser


def test_eval_parser_has_gate_and_no_capture_target():
    args = build_parser().parse_args(["eval", "clarify", "--gate"])
    assert args.cmd == "eval"
    assert args.target == "clarify"
    assert args.gate is True


def test_eval_defaults_to_advisory_report():
    assert build_parser().parse_args(["eval", "clarify"]).gate is False


def test_eval_accepts_case_and_repeat():
    args = build_parser().parse_args(
        ["eval", "planner", "--case", "cat-cafe-monitoring", "--n", "5"])
    assert args.case == "cat-cafe-monitoring"
    assert args.k == 5


def test_against_is_threaded_to_the_baseline_ref(monkeypatch):
    """--against must reach run_gate as baseline_ref, not be a dead flag."""
    seen = {}

    def _fake(role, case, **kw):
        seen.update(kw)
        from sdlc.eval.verdict import (GateVerdict, JudgeStatus,
                                       PromptGateResult)
        return PromptGateResult(verdict=GateVerdict.PASS,
                                judge_status=JudgeStatus.NO_BASELINE,
                                reason="ok")

    monkeypatch.setattr("sdlc.eval.cli.run_gate", _fake)
    from sdlc.eval.cli import run_eval
    run_eval("clarify", case="add-login-greenfield", against="main", k=1,
             judge_model="openai/gpt-5.2", gate=False)
    assert seen["baseline_ref"] == "main"


def test_eval_stays_client_free():
    """`eval` must not require a Temporal client — capture was the only
    target that did, and it is retired."""
    from sdlc.cli import _needs_temporal_client
    args = build_parser().parse_args(["eval", "clarify"])
    assert _needs_temporal_client(args) is False


def test_render_report_shows_verdict_and_delta():
    from sdlc.eval.cli import render_report
    from sdlc.eval.verdict import GateVerdict, JudgeStatus, PromptGateResult
    text = render_report(PromptGateResult(
        verdict=GateVerdict.FAIL_REGRESSION,
        judge_status=JudgeStatus.MEASURED, role="clarify", case="c",
        mean_baseline=0.85, mean_working=0.50, delta=-0.35, floor=0.05,
        reason="regression: baseline 0.85 -> working 0.50"))
    assert "fail_regression" in text
    assert "-0.35" in text


def test_default_judge_model_reads_config(tmp_path):
    from sdlc.eval.cli import default_judge_model
    cfg = tmp_path / "config.yaml"
    cfg.write_text("default_judge_model: openai/gpt-5.2\n", encoding="utf-8")
    assert default_judge_model(cfg) == "openai/gpt-5.2"


def test_default_judge_model_raises_when_missing(tmp_path):
    import pytest

    from sdlc.eval.cli import EvalError, default_judge_model
    cfg = tmp_path / "config.yaml"
    cfg.write_text("weights: {}\n", encoding="utf-8")
    with pytest.raises(EvalError):
        default_judge_model(cfg)


def test_run_eval_refuses_a_deps_role():
    """architect/research carry deps; a prompt-string fixture cannot
    reconstruct them. Ported from the retired test_eval_cli.py."""
    import pytest

    from sdlc.eval.cli import EvalError, run_eval
    with pytest.raises(EvalError, match="deps"):
        run_eval("architect", case="add-login-greenfield", against="HEAD",
                 k=1, judge_model="openai/gpt-5.2", gate=False)


def test_run_eval_refuses_an_unknown_role():
    import pytest

    from sdlc.eval.cli import EvalError, run_eval
    with pytest.raises(EvalError, match="unknown role"):
        run_eval("nonsense", case="add-login-greenfield", against="HEAD",
                 k=1, judge_model="openai/gpt-5.2", gate=False)
