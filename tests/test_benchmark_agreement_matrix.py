"""task x arm split-rate grid (spec 4.4)."""

from datetime import UTC, datetime

from sdlc.benchmarks.agreement_matrix import build_agreement_matrix
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.core.models import (
    HarnessKind,
)

_T = datetime(2026, 8, 5, tzinfo=UTC)


def _rec(stage, outcome, task_id="t1", usd=0.02, run_id="r1", case_id="c1"):
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id="b1",
        case_id=case_id,
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage=stage,
        task_id=task_id,
        role=stage,
        harness=HarnessKind.CLAUDE_CODE,
        model="anthropic:x",
        quality=QualityScore(score=1.0, judge="adversary"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(wall_clock_s=1.0, started_at=_T, ended_at=_T),
        outcome=outcome,
        fix_attempts=0,
    )


def test_split_rate_counts_only_adversary_records():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.FAIL),
            _rec("adversary", BenchmarkOutcome.PASS),
            _rec("code", BenchmarkOutcome.FAIL),  # must not count
        ],
    )
    cell = next(c for c in am.cells if c.metric == "split_rate")
    assert cell.value == 0.5


def test_cost_per_split_sums_adversary_spend():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.FAIL, usd=0.02),
            _rec("adversary", BenchmarkOutcome.PASS, usd=0.02),
        ],
    )
    cell = next(c for c in am.cells if c.metric == "cost_per_split")
    assert cell.value == 0.04  # total adversary spend / 1 split


def test_no_adversary_records_yields_no_cells():
    """Not measured is not zero -- a blank cell, never a 0.0 (waste_matrix)."""
    am = build_agreement_matrix("c1", [_rec("code", BenchmarkOutcome.PASS)])
    assert am.cells == []


def test_zero_splits_yields_a_rate_but_no_cost_per_split():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.PASS),
        ],
    )
    metrics = {c.metric for c in am.cells}
    assert "split_rate" in metrics
    assert "cost_per_split" not in metrics


def test_other_cases_are_excluded():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.FAIL, case_id="c2"),
            _rec("adversary", BenchmarkOutcome.PASS, case_id="c1"),
        ],
    )
    cell = next(c for c in am.cells if c.metric == "split_rate")
    assert cell.value == 0.0


# --- 012 T010b (chaos seat): immunity, keying, pre-012 line -------------------


def _cell_rec(*, arm="a1"):
    from datetime import timedelta

    from sdlc.benchmarks.models import CellStatus

    return BenchmarkRecord(
        run_id=f"b1/c1#opencode#{arm}",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.CELL,
        stage="cell",
        role="cell",
        harness=HarnessKind.OPENCODE,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=_T, ended_at=_T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL,
        kroker_commit="abc",
        tree_dirty=False,
        arm=arm,
        cell_id=f"c1#opencode#{arm}",
        cell=CellStatus(
            pipeline_finished=True,
            code_finished=False,
            completed=False,
            last_stage="clarify",
            grading="not_graded",
            child_result=None,
        ),
    )


def _rec012(stage, outcome, *, arm="a1", task_id="t1", usd=0.02):
    r = _rec(stage, outcome, task_id=task_id, usd=usd)
    return r.model_copy(
        update={
            "kroker_commit": "abc",
            "tree_dirty": False,
            "arm": arm,
            "cell_id": f"c1#claude_code#{arm}",
        }
    )


def test_not_evaluated_record_enters_no_cell():
    """Contract 7.8: a not_evaluated adversary record with the SAME task_id
    and arm as existing records enters neither n_records, nor the split
    denominator, nor the spend."""
    base = [
        _rec("adversary", BenchmarkOutcome.FAIL),
        _rec("adversary", BenchmarkOutcome.PASS),
    ]
    am = build_agreement_matrix("c1", base)
    polluter = _rec("adversary", BenchmarkOutcome.NOT_EVALUATED, usd=0.99)
    am2 = build_agreement_matrix("c1", base + [polluter, _cell_rec()])
    assert [c.model_dump() for c in am2.cells] == [c.model_dump() for c in am.cells]
    assert am2.arms == am.arms


def test_012_arm_key_uses_the_arm_label():
    recs = [_rec012("adversary", BenchmarkOutcome.FAIL, arm="a1")]
    am = build_agreement_matrix("c1", recs)
    assert am.arms == ["claude_code#a1"]
    cell = next(c for c in am.cells if c.metric == "split_rate")
    assert cell.arm_key == "claude_code#a1"


def test_pre012_arm_key_stays_harness_model_byte_identical():
    am = build_agreement_matrix("c1", [_rec("adversary", BenchmarkOutcome.FAIL)])
    assert am.arms == ["claude_code#anthropic:x"]


def test_agreement_matrix_carries_the_pre012_count_when_present():
    import json

    from sdlc.benchmarks.agreement_matrix import (
        render_agreement_matrix_html,
        render_agreement_matrix_json,
    )

    recs = [
        _rec("adversary", BenchmarkOutcome.FAIL),
        _rec012("adversary", BenchmarkOutcome.FAIL, arm="a1"),
        _cell_rec(),  # cell-scope records are not counted
    ]
    am = build_agreement_matrix("c1", recs)
    assert "includes 1 pre-012 records (untrusted)" in render_agreement_matrix_html(am)
    assert json.loads(render_agreement_matrix_json(am))["pre012_records"] == 1


def test_agreement_matrix_has_no_pre012_line_when_count_is_zero():
    import json

    from sdlc.benchmarks.agreement_matrix import (
        render_agreement_matrix_html,
        render_agreement_matrix_json,
    )

    am = build_agreement_matrix("c1", [_rec012("adversary", BenchmarkOutcome.FAIL)])
    assert "pre-012" not in render_agreement_matrix_html(am)
    assert json.loads(render_agreement_matrix_json(am))["pre012_records"] == 0


# --- 013 T009 (FR-033): the split view is named so it cannot be mistaken for
# --- the gate-versus-oracle view ------------------------------------------------


def test_title_and_heading_read_reviewer_vs_adversary_split():
    """013 FR-033: the reviewer-agreement view keeps its figures but is
    titled "Reviewer vs adversary split - <case>", never "agreement"
    alone, so it cannot be mistaken for the gate-versus-oracle view."""
    from sdlc.benchmarks.agreement_matrix import (
        build_agreement_matrix,
        render_agreement_matrix_html,
    )

    am = build_agreement_matrix(
        "c1",
        [_rec("adversary", BenchmarkOutcome.FAIL)],
    )
    html = render_agreement_matrix_html(am)
    assert "<title>Reviewer vs adversary split - c1</title>" in html
    assert "<h1>Reviewer vs adversary split - c1</h1>" in html
