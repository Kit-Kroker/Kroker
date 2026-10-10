"""013 T009 (RED): the gate-versus-oracle view, `sdlc.benchmarks.gate_oracle`.

Names: .specify/specs/013-benchmark-scoring-output/data-model.md section 4;
behaviour: contracts/scoring-output.md section 6 (run verdict research R-9,
oracle verdict, rates, low_n, credits, qa copy rows). `build_gate_oracle`
takes the output of `sdlc.benchmarks.runs.build_runs`. Every test imports
its `sdlc.benchmarks.gate_oracle` symbol function-local (the repo's RED
convention) so each missing name fails its own test instead of breaking
collection. The record factories below are copied verbatim from
tests/test_benchmark_runs.py; do not modify that file.
"""

from datetime import datetime

import pytest

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.core.models import HarnessKind


def _record(**kw):
    base = dict(
        run_id="b1/add-login#opencode#a1",
        bench_run_id="b1",
        case_id="add-login",
        scope=BenchmarkScope.STAGE,
        stage="architecture",
        role="architect",
        model="anthropic:claude-sonnet-4-6",
        prompt_sha="abc",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(
            wall_clock_s=12.0,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10, 0, 12),
        ),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return BenchmarkRecord(**base)


def _oracle_record(**kw):
    """An oracle-scope record; `passed`/`total` ride quality.components."""
    base = dict(
        stage="oracle",
        role="oracle",
        scope=BenchmarkScope.ORACLE,
        model="openai/gpt-5.2",
        quality=QualityScore(score=1.0, judge="oracle"),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return _record(**base)


def _speed(dt):
    return SpeedBag(wall_clock_s=1.0, started_at=dt, ended_at=dt)


def _code_attempt(task_id, attempt, outcome, **kw):
    return _record(
        stage="code",
        role="dev",
        task_id=task_id,
        attempt=attempt,
        outcome=outcome,
        **kw,
    )


def _graded_run(run_id, passed, total, **kw):
    """A minimal graded run: code + merge (code finished) + a scored oracle."""
    return [
        _record(run_id=run_id, stage="code", harness=HarnessKind.OPENCODE, **kw),
        _record(run_id=run_id, stage="merge", harness=HarnessKind.OPENCODE, **kw),
        _oracle_record(
            run_id=run_id,
            quality=QualityScore(
                score=passed / total,
                judge="oracle",
                components={"passed": float(passed), "total": float(total)},
            ),
            **kw,
        ),
    ]


# --- local helpers on top of the copied factories -------------------------


def _at(hour, minute=0):
    return datetime(2026, 7, 4, hour, minute)


_TEN = datetime(2026, 7, 4, 10)


def _gate(run_id, stage, outcome, when=None, **kw):
    """A run-level gate record (analyze, merge) at `when`."""
    kw.setdefault("harness", HarnessKind.OPENCODE)
    kw.setdefault("speed", _speed(when or _TEN))
    return _record(run_id=run_id, stage=stage, outcome=outcome, **kw)


def _task_gate(run_id, stage, task_id, outcome, when=None, **kw):
    """A task-level gate record (qa, review, ...) at `when`, attempt 0
    unless the caller passes one."""
    kw.setdefault("attempt", 0)
    return _gate(run_id, stage, outcome, when=when, task_id=task_id, **kw)


def _four_cell_corpus():
    """Contract 6 opening: four graded runs over one analyze gate covering
    pass/pass, pass/fail, reject/pass, reject/fail."""
    out = []
    for bench, gate_outcome, passed in (
        ("b1", BenchmarkOutcome.PASS, 5),
        ("b2", BenchmarkOutcome.PASS, 3),
        ("b3", BenchmarkOutcome.FAIL, 5),
        ("b4", BenchmarkOutcome.FAIL, 3),
    ):
        run_id = f"{bench}/c#opencode#a1"
        out += _graded_run(run_id, passed, 5)
        out.append(_gate(run_id, "analyze", gate_outcome))
    return out


def _copy_graded(run_id, passed, total):
    """A graded pre-012 run whose qa verdicts copy its code verdicts."""
    return _graded_run(run_id, passed, total) + [
        _code_attempt(
            "T1",
            0,
            BenchmarkOutcome.PASS,
            run_id=run_id,
            harness=HarnessKind.OPENCODE,
        ),
        _task_gate(run_id, "qa", "T1", BenchmarkOutcome.PASS),
    ]


_MD_HEADER = (
    "| row | gate | n | pass/pass | pass/fail | reject/pass | reject/fail"
    " | agree | escape | false reject | credit passed | credit rejected |"
)


# --- 1. the four-run opening case -----------------------------------------


def test_four_runs_cover_the_four_cells_and_half_rates():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    go = build_gate_oracle(build_runs(_four_cell_corpus()))
    (row,) = [r for r in go.rows if r.gate == "analyze"]
    assert row.row == "c / opencode / a1 / pre012"
    assert (row.pass_pass, row.pass_fail, row.reject_pass, row.reject_fail) == (
        1,
        1,
        1,
        1,
    )
    assert row.n == 4
    assert row.agree_rate == 0.5
    assert row.escape_rate == 0.5
    assert row.false_reject_rate == 0.5


# --- 2. only graded runs enter (6.1) ---------------------------------------


def test_only_graded_runs_enter_a_gate_row():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    lost_run_id = "b1/c#opencode#a1"
    lost = [
        _code_attempt(
            "T1",
            0,
            BenchmarkOutcome.FAIL,
            run_id=lost_run_id,
            harness=HarnessKind.OPENCODE,
        ),
        _task_gate(lost_run_id, "qa", "T1", BenchmarkOutcome.PASS),
        _task_gate(lost_run_id, "review", "T1", BenchmarkOutcome.PASS),
        _oracle_record(
            run_id=lost_run_id,
            quality=QualityScore(
                score=1.0, judge="oracle", components={"passed": 5.0, "total": 5.0}
            ),
        ),
    ]
    graded_run_id = "b2/c#opencode#a1"
    graded = _graded_run(graded_run_id, 3, 5) + [
        _task_gate(graded_run_id, "review", "T1", BenchmarkOutcome.FAIL),
    ]
    runs = {r.run_id: r for r in build_runs(lost + graded)}
    assert runs[lost_run_id].status == "lost"
    assert runs[graded_run_id].status == "graded"

    go = build_gate_oracle(list(runs.values()))
    (row,) = [r for r in go.rows if r.gate == "review"]
    assert row.n == 1  # the lost run's passing review changed no count
    assert (row.pass_pass, row.pass_fail, row.reject_pass, row.reject_fail) == (
        0,
        0,
        0,
        1,
    )
    assert row.mean_credit_passed is None  # the lost run's 5/5 oracle is discarded
    assert row.mean_credit_rejected == pytest.approx(0.6)


# --- 3. run-level gate takes its last record (6.2, R-9) --------------------


def test_run_level_gate_takes_its_last_record():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    fail_then_pass = _graded_run("b1/c#opencode#a1", 5, 5) + [
        _gate("b1/c#opencode#a1", "analyze", BenchmarkOutcome.FAIL, _at(10)),
        _gate("b1/c#opencode#a1", "analyze", BenchmarkOutcome.PASS, _at(11)),
    ]
    pass_then_fail = _graded_run("b2/c#opencode#a1", 5, 5) + [
        _gate("b2/c#opencode#a1", "analyze", BenchmarkOutcome.PASS, _at(10)),
        _gate("b2/c#opencode#a1", "analyze", BenchmarkOutcome.FAIL, _at(11)),
    ]
    go = build_gate_oracle(build_runs(fail_then_pass + pass_then_fail))
    (row,) = [r for r in go.rows if r.gate == "analyze"]
    assert row.n == 2
    assert (row.pass_pass, row.reject_pass) == (1, 1)


# --- 4. task gate needs every task's last record passed (6.2, R-9) ---------


def test_task_gate_needs_every_task_last_passed():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    repaired = _graded_run("b1/c#opencode#a1", 5, 5) + [
        _task_gate("b1/c#opencode#a1", "review", "t1", BenchmarkOutcome.FAIL, _at(10)),
        _task_gate(
            "b1/c#opencode#a1",
            "review",
            "t1",
            BenchmarkOutcome.PASS,
            _at(11),
            attempt=1,
        ),
        _task_gate("b1/c#opencode#a1", "review", "t2", BenchmarkOutcome.PASS, _at(10)),
    ]
    one_task_failed = _graded_run("b2/c#opencode#a1", 5, 5) + [
        _task_gate("b2/c#opencode#a1", "review", "t1", BenchmarkOutcome.PASS, _at(10)),
        _task_gate("b2/c#opencode#a1", "review", "t2", BenchmarkOutcome.FAIL, _at(10)),
    ]
    go = build_gate_oracle(build_runs(repaired + one_task_failed))
    (row,) = [r for r in go.rows if r.gate == "review"]
    # t1's earlier failure does not reject the repaired run; t2's does
    assert row.n == 2
    assert (row.pass_pass, row.reject_pass) == (1, 1)


# --- 5. merge revise is a pass (6.2) ----------------------------------------


def test_merge_revised_counts_on_the_passed_side():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c#opencode#a1"
    records = _graded_run(run_id, 5, 5) + [
        _gate(run_id, "merge", BenchmarkOutcome.REVISED, _at(11)),
    ]
    go = build_gate_oracle(build_runs(records))
    (row,) = [r for r in go.rows if r.gate == "merge"]
    assert row.n == 1
    assert row.pass_pass == 1
    assert row.mean_credit_passed == 1.0


# --- 6. only not_evaluated in a run: not in n; no row without a verdict -----


def test_not_evaluated_only_run_is_out_and_no_gate_row_without_a_verdict():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    ne_run_id = "b1/c#opencode#a1"
    not_evaluated = _graded_run(ne_run_id, 5, 5) + [
        _gate(ne_run_id, "analyze", BenchmarkOutcome.NOT_EVALUATED),
    ]
    rejected = _graded_run("b2/c#opencode#a1", 5, 5) + [
        _gate("b2/c#opencode#a1", "analyze", BenchmarkOutcome.FAIL),
    ]
    go = build_gate_oracle(build_runs(not_evaluated + rejected))
    (row,) = [r for r in go.rows if r.gate == "analyze"]
    assert row.n == 1
    assert row.reject_pass == 1

    only_ne = build_gate_oracle(build_runs(not_evaluated))
    assert [r for r in only_ne.rows if r.gate == "analyze"] == []


# --- 7. oracle verdict needs passed == total > 0 (6.3) ----------------------


def test_oracle_pass_needs_passed_equal_to_total_positive():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    records = []
    for bench, passed in (("b1", 5), ("b2", 3), ("b3", 0)):
        run_id = f"{bench}/c#opencode#a1"
        records += _graded_run(run_id, passed, 5)
        records.append(_task_gate(run_id, "adversary", "T1", BenchmarkOutcome.PASS))
    go = build_gate_oracle(build_runs(records))
    (row,) = [r for r in go.rows if r.gate == "adversary"]
    assert row.n == 3
    assert row.pass_pass == 1  # 5/5
    assert row.pass_fail == 2  # 3/5 and 0/5


# --- 8. zero-denominator rates are None and read n/a (0) (6.4) --------------


def test_zero_denominator_rate_is_none_and_renders_na_zero():
    from sdlc.benchmarks.gate_oracle import (
        build_gate_oracle,
        render_gate_oracle_markdown,
    )
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c#opencode#a1"
    records = _graded_run(run_id, 5, 5) + [
        _gate(run_id, "analyze", BenchmarkOutcome.FAIL),
    ]
    go = build_gate_oracle(build_runs(records))
    (row,) = [r for r in go.rows if r.gate == "analyze"]
    assert row.reject_pass == 1
    assert row.escape_rate is None  # pass_pass + pass_fail == 0
    assert row.low_n["escape_rate"] is True
    assert "n/a (0)" in render_gate_oracle_markdown(go)


# --- 9. low_n is per rate (6.4) ----------------------------------------------


def test_low_n_is_per_rate():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    records = []
    for i in range(1, 7):
        run_id = f"b{i}/c#opencode#a1"
        outcome = BenchmarkOutcome.PASS if i <= 4 else BenchmarkOutcome.FAIL
        records += _graded_run(run_id, 5, 5)
        records.append(_gate(run_id, "analyze", outcome))
    go = build_gate_oracle(build_runs(records))
    (row,) = [r for r in go.rows if r.gate == "analyze"]
    assert row.n == 6
    assert row.low_n == {
        "agree_rate": False,  # denominator n == 6
        "escape_rate": True,  # pass_pass + pass_fail == 4
        "false_reject_rate": True,  # reject_pass + reject_fail == 2
    }


# --- 10. mean_credit_passed / mean_credit_rejected (6.5) ---------------------


def test_mean_credit_per_side_and_none_for_an_empty_side():
    from sdlc.benchmarks.gate_oracle import (
        build_gate_oracle,
        render_gate_oracle_markdown,
    )
    from sdlc.benchmarks.runs import build_runs

    records = []
    for bench, passed, outcome in (
        ("b1", 5, BenchmarkOutcome.PASS),
        ("b2", 3, BenchmarkOutcome.PASS),
        ("b3", 0, BenchmarkOutcome.FAIL),
    ):
        run_id = f"{bench}/c#opencode#a1"
        records += _graded_run(run_id, passed, 5)
        records.append(_task_gate(run_id, "handoff", "T1", outcome))
    go = build_gate_oracle(build_runs(records))
    (row,) = [r for r in go.rows if r.gate == "handoff"]
    assert row.mean_credit_passed == pytest.approx(0.8)  # mean(1.0, 0.6)
    assert row.mean_credit_rejected == 0.0  # 0/5 alone

    single = _graded_run("b9/c#opencode#a1", 5, 5) + [
        _task_gate("b9/c#opencode#a1", "deep_review", "T1", BenchmarkOutcome.PASS),
    ]
    go_single = build_gate_oracle(build_runs(single))
    (row2,) = [r for r in go_single.rows if r.gate == "deep_review"]
    assert row2.mean_credit_passed == 1.0
    assert row2.mean_credit_rejected is None  # empty side
    assert "n/a" in render_gate_oracle_markdown(go_single)


# --- 11. qa over copy runs (6.6) ---------------------------------------------


def test_qa_row_of_only_copy_runs():
    from sdlc.benchmarks.gate_oracle import (
        build_gate_oracle,
        render_gate_oracle_markdown,
    )
    from sdlc.benchmarks.runs import build_runs

    records = _copy_graded("b1/c#opencode#a1", 4, 5)
    (run,) = build_runs(records)
    assert run.qa_is_copy is True

    go = build_gate_oracle(build_runs(records))
    (row,) = [r for r in go.rows if r.gate == "qa"]
    assert row.is_copy is True
    assert (row.pass_pass, row.pass_fail, row.reject_pass, row.reject_fail, row.n) == (
        0,
        0,
        0,
        0,
        0,
    )
    assert "copy of code (pre-012)" in render_gate_oracle_markdown(go)


# --- 12. qa over a mixed row --------------------------------------------------


def test_qa_mixed_row_counts_only_the_non_copy_run():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    copy = _copy_graded("b1/c#opencode#a1", 5, 5)
    not_copy = _graded_run("b2/c#opencode#a1", 3, 5) + [
        _code_attempt(
            "T1",
            0,
            BenchmarkOutcome.PASS,
            run_id="b2/c#opencode#a1",
            harness=HarnessKind.OPENCODE,
        ),
        _task_gate("b2/c#opencode#a1", "qa", "T1", BenchmarkOutcome.FAIL),
    ]
    runs = {r.run_id: r for r in build_runs(copy + not_copy)}
    assert runs["b1/c#opencode#a1"].qa_is_copy is True
    assert runs["b2/c#opencode#a1"].qa_is_copy is False

    go = build_gate_oracle(list(runs.values()))
    (row,) = [r for r in go.rows if r.gate == "qa"]
    assert row.is_copy is False
    assert row.n == 1
    assert row.reject_fail == 1  # the non-copy run: qa reject, oracle fail


# --- 13. one row set per heatmap row (6.1) ------------------------------------


def test_generations_never_share_a_gate_row():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    pre012 = _graded_run("b1/c#opencode#a1", 5, 5) + [
        _gate("b1/c#opencode#a1", "analyze", BenchmarkOutcome.PASS),
    ]
    gen012 = _graded_run("b2/c#opencode#a1", 3, 5, kroker_commit="deadbeef") + [
        _gate(
            "b2/c#opencode#a1",
            "analyze",
            BenchmarkOutcome.PASS,
            kroker_commit="deadbeef",
        ),
    ]
    rows = [r for r in build_gate_oracle(build_runs(pre012 + gen012)).rows if r.gate == "analyze"]
    assert len(rows) == 2
    by_row = {r.row: r for r in rows}
    assert set(by_row) == {"c / opencode / a1 / pre012", "c / opencode / a1 / 012"}
    assert by_row["c / opencode / a1 / pre012"].pass_pass == 1
    assert by_row["c / opencode / a1 / 012"].pass_fail == 1


# --- 14. GATE_STAGES, row key, row and gate ordering --------------------------


def test_gate_stages_row_key_and_orderings():
    from sdlc.benchmarks.gate_oracle import GATE_STAGES, build_gate_oracle
    from sdlc.benchmarks.runs import build_runs

    assert GATE_STAGES == (
        "qa",
        "review",
        "adversary",
        "deep_review",
        "handoff",
        "analyze",
        "merge",
    )

    # row key from the run id alone: no record carries a harness
    plain = [
        _record(run_id="b1/c#opencode#a1", stage="code"),
        _record(run_id="b1/c#opencode#a1", stage="analyze"),
        _oracle_record(
            run_id="b1/c#opencode#a1",
            quality=QualityScore(
                score=1.0, judge="oracle", components={"passed": 5.0, "total": 5.0}
            ),
        ),
    ]
    (only,) = build_gate_oracle(build_runs(plain)).rows
    assert only.row == "c / opencode / a1 / pre012"
    assert only.gate == "analyze"

    # ordering: case, arm, generation (012 first), first start; gates
    # within a row in GATE_STAGES order. The opencode row starts at 10:00,
    # the claude_code row at 9:00; the merge record is emitted by
    # _graded_run before the other gate records, so gate order is sorted,
    # not input order.
    r_opencode = _graded_run("b1/c#opencode#a1", 5, 5, speed=_speed(_at(10))) + [
        _code_attempt(
            "T1",
            0,
            BenchmarkOutcome.PASS,
            run_id="b1/c#opencode#a1",
            harness=HarnessKind.OPENCODE,
        ),
        _task_gate("b1/c#opencode#a1", "qa", "T1", BenchmarkOutcome.FAIL, _at(10)),
        _task_gate("b1/c#opencode#a1", "review", "T1", BenchmarkOutcome.PASS, _at(10)),
        _task_gate("b1/c#opencode#a1", "handoff", "T1", BenchmarkOutcome.PASS, _at(10)),
        _gate("b1/c#opencode#a1", "analyze", BenchmarkOutcome.PASS, _at(10)),
    ]
    r_012 = _graded_run(
        "b2/c#opencode#a1", 5, 5, kroker_commit="deadbeef", speed=_speed(_at(9))
    ) + [
        _gate(
            "b2/c#opencode#a1",
            "analyze",
            BenchmarkOutcome.PASS,
            _at(9),
            kroker_commit="deadbeef",
        ),
    ]
    r_claude = [
        _record(
            run_id="b3/c#claude_code#a1",
            stage="code",
            harness=HarnessKind.CLAUDE_CODE,
            speed=_speed(_at(9)),
        ),
        _record(
            run_id="b3/c#claude_code#a1",
            stage="merge",
            harness=HarnessKind.CLAUDE_CODE,
            speed=_speed(_at(9)),
        ),
        _oracle_record(
            run_id="b3/c#claude_code#a1",
            harness=HarnessKind.CLAUDE_CODE,
            speed=_speed(_at(9)),
            quality=QualityScore(
                score=1.0, judge="oracle", components={"passed": 5.0, "total": 5.0}
            ),
        ),
        _gate(
            "b3/c#claude_code#a1",
            "analyze",
            BenchmarkOutcome.PASS,
            _at(9),
            harness=HarnessKind.CLAUDE_CODE,
        ),
    ]
    r_case_a = _graded_run("b4/a#opencode#a1", 5, 5, speed=_speed(_at(8))) + [
        _gate("b4/a#opencode#a1", "analyze", BenchmarkOutcome.PASS, _at(8)),
    ]
    r_arm_z = _graded_run("b5/c#opencode#z9", 5, 5, speed=_speed(_at(8))) + [
        _gate("b5/c#opencode#z9", "analyze", BenchmarkOutcome.PASS, _at(8)),
    ]
    go = build_gate_oracle(build_runs(r_case_a + r_012 + r_claude + r_opencode + r_arm_z))
    # every _graded_run fixture carries a merge record, so each row built
    # on one has a merge GateRow too (GATE_STAGES order: analyze, merge)
    assert [(r.row, r.gate) for r in go.rows] == [
        ("a / opencode / a1 / pre012", "analyze"),
        ("a / opencode / a1 / pre012", "merge"),
        ("c / opencode / a1 / 012", "analyze"),
        ("c / opencode / a1 / 012", "merge"),
        ("c / claude_code / a1 / pre012", "analyze"),
        ("c / claude_code / a1 / pre012", "merge"),
        ("c / opencode / a1 / pre012", "qa"),
        ("c / opencode / a1 / pre012", "review"),
        ("c / opencode / a1 / pre012", "handoff"),
        ("c / opencode / a1 / pre012", "analyze"),
        ("c / opencode / a1 / pre012", "merge"),
        ("c / opencode / z9 / pre012", "analyze"),
        ("c / opencode / z9 / pre012", "merge"),
    ]


# --- 15. markdown ------------------------------------------------------------


def test_markdown_header_ascii_and_no_separator():
    from sdlc.benchmarks.gate_oracle import (
        build_gate_oracle,
        render_gate_oracle_markdown,
    )
    from sdlc.benchmarks.runs import build_runs

    md = render_gate_oracle_markdown(
        build_gate_oracle(build_runs(_four_cell_corpus() + _copy_graded("b9/c#opencode#a9", 4, 5)))
    )
    assert _MD_HEADER in [line.strip() for line in md.splitlines()]
    assert "---" not in md  # no separator row, nowhere
    assert md.isascii()


def test_markdown_rates_credits_and_copy_row_lines():
    from sdlc.benchmarks.gate_oracle import (
        build_gate_oracle,
        render_gate_oracle_markdown,
    )
    from sdlc.benchmarks.runs import build_runs

    md = render_gate_oracle_markdown(
        build_gate_oracle(build_runs(_four_cell_corpus() + _copy_graded("b9/c#opencode#a9", 4, 5)))
    )
    lines = [line.strip() for line in md.splitlines()]
    # rates render k/d over their own denominators, each low here; credits
    # render with three decimals: passed side mean(1.0, 0.6), rejected same
    assert (
        "| c / opencode / a1 / pre012 | analyze | 4 | 1 | 1 | 1 | 1"
        " | 2/4 (low n) | 1/2 (low n) | 1/2 (low n) | 0.800 | 0.800 |"
    ) in lines
    copy_line = "| c / opencode / a9 / pre012 | qa | copy of code (pre-012) |" + " |" * 9
    assert copy_line in lines


def test_markdown_pre012_trailer_line():
    from sdlc.benchmarks.gate_oracle import (
        build_gate_oracle,
        render_gate_oracle_markdown,
    )
    from sdlc.benchmarks.runs import build_runs

    pre012 = _graded_run("b1/c#opencode#a1", 5, 5) + [
        _gate("b1/c#opencode#a1", "analyze", BenchmarkOutcome.PASS),
    ]
    gen012 = _graded_run("b2/c#opencode#a1", 3, 5, kroker_commit="deadbeef") + [
        _gate(
            "b2/c#opencode#a1",
            "analyze",
            BenchmarkOutcome.PASS,
            kroker_commit="deadbeef",
        ),
    ]
    mixed = render_gate_oracle_markdown(build_gate_oracle(build_runs(pre012 + gen012)))
    # 4 pre-012 non-cell records: code, merge, oracle, analyze
    non_empty = [ln for ln in mixed.splitlines() if ln.strip()]
    assert non_empty[-1] == "includes 4 pre-012 records (untrusted)"

    all012 = render_gate_oracle_markdown(build_gate_oracle(build_runs(gen012)))
    assert "pre-012" not in all012


# --- 16. html ------------------------------------------------------------------


def test_html_title_low_n_span_and_none_rate():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle, render_gate_oracle_html
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c#opencode#a1"
    records = _graded_run(run_id, 5, 5) + [
        _gate(run_id, "analyze", BenchmarkOutcome.FAIL),
    ]
    html = render_gate_oracle_html(build_gate_oracle(build_runs(records)))
    assert "<title>Gate versus oracle</title>" in html
    assert "<h1>Gate versus oracle</h1>" in html
    assert '<span class="low_n">1/1 (low n)</span>' in html
    assert "n/a (0)" in html  # escape_rate: no gate-passed run


def test_html_copy_row_and_pre012_untrusted_line():
    from sdlc.benchmarks.gate_oracle import build_gate_oracle, render_gate_oracle_html
    from sdlc.benchmarks.runs import build_runs

    pre012 = _graded_run("b1/c#opencode#a1", 5, 5) + [
        _gate("b1/c#opencode#a1", "analyze", BenchmarkOutcome.PASS),
    ]
    copy = _copy_graded("b9/c#opencode#a9", 4, 5)
    html = render_gate_oracle_html(build_gate_oracle(build_runs(pre012 + copy)))
    assert "copy of code (pre-012)" in html
    assert "pre-012 records (untrusted)" in html  # pre012_records > 0

    gen012 = _graded_run("b2/c#opencode#a1", 3, 5, kroker_commit="deadbeef") + [
        _gate(
            "b2/c#opencode#a1",
            "analyze",
            BenchmarkOutcome.PASS,
            kroker_commit="deadbeef",
        ),
    ]
    html012 = render_gate_oracle_html(build_gate_oracle(build_runs(gen012)))
    assert "pre-012 records (untrusted)" not in html012


# --- 17. json --------------------------------------------------------------------


def test_json_shape_and_row_keys():
    import json

    from sdlc.benchmarks.gate_oracle import build_gate_oracle, render_gate_oracle_json
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c#opencode#a1"
    records = _graded_run(run_id, 4, 5) + [
        _gate(run_id, "analyze", BenchmarkOutcome.FAIL),
    ]
    data = json.loads(render_gate_oracle_json(build_gate_oracle(build_runs(records))))
    assert set(data) == {"rows", "pre012_records"}
    assert data["pre012_records"] == 4
    assert data["rows"]
    expected = {
        "row",
        "gate",
        "pass_pass",
        "pass_fail",
        "reject_pass",
        "reject_fail",
        "n",
        "agree_rate",
        "escape_rate",
        "false_reject_rate",
        "mean_credit_passed",
        "mean_credit_rejected",
        "low_n",
        "is_copy",
    }
    for row in data["rows"]:
        assert set(row) == expected
    (analyze,) = [row for row in data["rows"] if row["gate"] == "analyze"]
    assert analyze["row"] == "c / opencode / a1 / pre012"
    # oracle 4/5 is a fail (6.3), so the rejected run lands in reject_fail
    assert analyze["reject_fail"] == 1
