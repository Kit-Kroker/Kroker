from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.scoring import compute_summaries
from sdlc.core.models import (
    HarnessKind,
)


def _rec(
    case,
    harness,
    model,
    q,
    usd,
    secs,
    lead_harness=None,
    *,
    stage="code",
    judge="contract",
    arm="a1",
):
    # 013 (R-11): rows key on the run, so every fixture record carries a
    # stored-shape run id `<bench>/<case>#<harness[:lead]>#<arm>`.
    tag = (
        f"{harness.value}:{lead_harness.value}"
        if harness is not None and lead_harness is not None
        else harness.value
        if harness is not None
        else "proposer"
    )
    return BenchmarkRecord(
        run_id=f"b/{case}#{tag}#{arm}",
        bench_run_id="b",
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage=stage,
        role="dev",
        harness=harness,
        lead_harness=lead_harness,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=q, judge=judge),
        cost=CostBag(usd=usd, input_tokens=10, output_tokens=5),
        speed=SpeedBag(
            wall_clock_s=secs,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=secs),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def _summarize(records, weights=None):
    # 013 (R-11): keyed by (stage, model) -- the row key no longer holds
    # the model, so a run's stage rows and its oracle row can share one.
    return {(s.stage, s.model): s for s in compute_summaries(records, weights)}


def _oracle_rec(
    case,
    harness,
    model,
    q,
    *,
    scope=BenchmarkScope.ORACLE,
    task_id=None,
    arm="a1",
    components=None,
):
    t = datetime(2026, 7, 27, 10)
    return BenchmarkRecord(
        run_id=f"b/{case}#{harness.value}#{arm}",
        bench_run_id="b",
        case_id=case,
        scope=scope,
        stage="oracle",
        task_id=task_id,
        role="oracle",
        harness=harness,
        model=model,
        quality=QualityScore(score=q, judge="oracle", components=components or {}),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )


def test_oracle_task_records_excluded_from_oracle_summary():
    # ORACLE_TASK records (E-31 task matrix) share stage="oracle" and the
    # cell's harness/model with the case-level ORACLE record. They must NOT
    # merge into the same BenchmarkSummary row -- that would inflate n and
    # blend mean_quality/composite the moment a case has tasks.yaml tasks.
    # The merge record makes the run code-finished so its oracle row exists.
    merge = _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", None, None, 1.0, stage="merge")
    oracle_only = [
        _oracle_rec(
            "c1", HarnessKind.CLAUDE_CODE, "sonnet", 0.8, components={"passed": 4.0, "total": 5.0}
        ),
    ]
    with_tasks = oracle_only + [
        _oracle_rec(
            "c1",
            HarnessKind.CLAUDE_CODE,
            "sonnet",
            1.0,
            scope=BenchmarkScope.ORACLE_TASK,
            task_id="t01",
        ),
        _oracle_rec(
            "c1",
            HarnessKind.CLAUDE_CODE,
            "sonnet",
            0.0,
            scope=BenchmarkScope.ORACLE_TASK,
            task_id="t02",
        ),
    ]
    s_only = _summarize(oracle_only + [merge])
    s_with = _summarize(with_tasks + [merge])
    assert s_with[("oracle", "sonnet")].n == s_only[("oracle", "sonnet")].n == 1
    assert s_with[("oracle", "sonnet")].mean_quality == s_only[("oracle", "sonnet")].mean_quality
    assert s_with[("oracle", "sonnet")].mean_quality == 0.8
    assert s_with[("oracle", "sonnet")].composite == s_only[("oracle", "sonnet")].composite


def test_multiple_records_averaged_per_cell():
    kw = {"stage": "architecture", "judge": "llm_judge"}
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", 0.8, 1.0, 100, **kw),
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", 0.6, 2.0, 200, **kw),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", 0.5, 0.5, 50, arm="a2", **kw),
    ]
    s = _summarize(recs)
    assert s[("architecture", "sonnet")].n == 2
    assert abs(s[("architecture", "sonnet")].mean_quality - 0.7) < 1e-9


def test_crew_leads_summarize_into_separate_cells():
    """spec §5: harness=CREW records for two different leads share
    (case_id, stage, model) -- without the lead in the run's harness key
    they would blend into one row, hiding the very comparison the
    crew:<lead_harness> sweep exists to make."""
    kw = {"stage": "architecture", "judge": "llm_judge"}
    recs = [
        _rec(
            "c1",
            HarnessKind.CREW,
            "glm",
            q=0.9,
            usd=1.0,
            secs=100,
            lead_harness=HarnessKind.CLAUDE_CODE,
            **kw,
        ),
        _rec(
            "c1",
            HarnessKind.CREW,
            "glm",
            q=0.1,
            usd=1.0,
            secs=100,
            lead_harness=HarnessKind.OPENCODE,
            **kw,
        ),
    ]
    summaries = compute_summaries(recs)
    assert len(summaries) == 2
    by_lead = {s.lead_harness: s for s in summaries}
    assert by_lead[HarnessKind.CLAUDE_CODE].mean_quality == 0.9
    assert by_lead[HarnessKind.OPENCODE].mean_quality == 0.1


# --- 012 T009 (RED): rows never mix pre-012 and 012 records (contract §7.2) -

_CELL_STATUS = CellStatus(
    pipeline_finished=True,
    code_finished=True,
    completed=True,
    last_stage="merge",
    grading="graded",
    child_result="ok",
)


def _012_rec(case, stage, role, model, q, *, cell_id, arm, usd=0.1, secs=10.0):
    """A 012-shape record: provenance + cell identity set (harness None --
    a proposer record -- so the cell label is the only grouping that can
    hold the row together). The run id is the stored shape `B/workflow.py`
    forms: f"{bench_run_id}/{cell.cell_id}"."""
    r = _rec(case, None, model, q, usd, secs, judge="llm_judge")
    return r.model_copy(
        update={
            "stage": stage,
            "role": role,
            "kroker_commit": "abc123",
            "cell_id": cell_id,
            "arm": arm,
            "run_id": f"b/{cell_id}",
        }
    )


def _cell_scope_rec(case, cell_id, arm):
    r = _rec(case, None, "deterministic", None, None, 0.0)
    return r.model_copy(
        update={
            "scope": BenchmarkScope.CELL,
            "stage": "cell",
            "role": "cell",
            "quality": QualityScore(score=None, judge="contract"),
            "cell": _CELL_STATUS,
            "kroker_commit": "abc123",
            "cell_id": cell_id,
            "arm": arm,
        }
    )


def test_cell_scope_records_are_excluded_from_summaries():
    """contract §7.2: the one cell record per cell is status, not a
    measurement -- it enters no row and no count."""
    recs = [_rec("c1", None, "m1", q=0.8, usd=0.5, secs=10)]
    with_cell = recs + [_cell_scope_rec("c1", "c1#opencode#a1", "a1")]
    s_without = compute_summaries(recs)
    s_with = compute_summaries(with_cell)
    assert len(s_with) == len(s_without) == 1
    assert s_with[0].model == "m1"
    assert s_with[0].n == 1


def test_pre012_and_012_records_form_separate_rows():
    """contract §5.1: grouping is by (case, stage, harness, arm,
    generation) -- the same case and stage from a pre-012 and a 012 record
    are two runs of two generations, so two rows, one pre012 True and one
    False. A row never mixes generations."""
    pre = _rec("c1", None, "m1", q=0.8, usd=0.5, secs=10, stage="architecture", judge="llm_judge")
    new = _012_rec(
        "c1", "architecture", "architect", "m1", q=0.2, cell_id="c1#opencode#a1", arm="a1"
    )
    rows = compute_summaries([pre, new])
    assert len(rows) == 2
    by_kind = {s.pre012: s for s in rows}
    assert by_kind[True].mean_quality == 0.8
    assert by_kind[False].mean_quality == 0.2
    assert by_kind[True].n == 1 and by_kind[False].n == 1


def test_012_row_keys_by_cell_and_joins_distinct_models_sorted():
    """contract §7.3 / data-model §1.4: a 012 row is keyed by the cell, so
    two records of the same cell with different models land in ONE row
    whose model is the sorted comma-joined distinct models, with cell_id
    and arm carried from the records."""
    cell_id = "c1#opencode#a1"
    recs = [
        _012_rec("c1", "code", "architect", "anthropic:glm-5.2", q=0.8, cell_id=cell_id, arm="a1"),
        _012_rec(
            "c1",
            "code",
            "dev",
            "zai-coding-plan/glm-5.3",
            q=0.6,
            cell_id=cell_id,
            arm="a1",
        ),
    ]
    rows = compute_summaries(recs)
    assert len(rows) == 1
    row = rows[0]
    assert row.model == "anthropic:glm-5.2,zai-coding-plan/glm-5.3"
    assert row.cell_id == cell_id
    assert row.arm == "a1"


def test_not_evaluated_record_changes_no_count_and_no_mean():
    """A `not_evaluated` record (score None) enters no count and no mean:
    the row it lands in keeps the n and mean_quality it had without it."""
    scored = _012_rec("c1", "merge", "dev", "m1", q=0.8, cell_id="c1#opencode#a1", arm="a1")
    not_evaluated = scored.model_copy(
        update={
            "role": "merge_verdict",
            "outcome": BenchmarkOutcome.NOT_EVALUATED,
            "quality": QualityScore(score=None, judge="contract"),
        }
    )
    without = compute_summaries([scored])
    with_row = compute_summaries([scored, not_evaluated])
    assert len(with_row) == len(without) == 1
    assert with_row[0].n == without[0].n == 1
    assert with_row[0].mean_quality == without[0].mean_quality == 0.8


def test_pre012_only_records_pin_base_values_and_carry_no_cell_identity():
    """PIN over the fixture's shape, 013 values: with only pre-012 records,
    every row keeps its base means (n, quality, cost, wall) and carries
    pre012 True, cell_id None -- a row never starts out marked 012. The
    013 changes: the arm is recovered from the stored-shape run id (R-3)
    and the composite is None until the case has two graded arms (FR-034)."""
    recs = [
        _rec(
            "c1",
            HarnessKind.CLAUDE_CODE,
            "sonnet",
            q=0.8,
            usd=1.0,
            secs=100,
            stage="architecture",
            judge="llm_judge",
        ),
        _rec(
            "c1",
            HarnessKind.CLAUDE_CODE,
            "sonnet",
            q=0.6,
            usd=2.0,
            secs=200,
            stage="architecture",
            judge="llm_judge",
        ),
    ]
    rows = compute_summaries(recs)
    assert len(rows) == 1
    s = rows[0]
    assert s.n == 2
    assert abs(s.mean_quality - 0.7) < 1e-9
    assert abs(s.mean_cost_usd - 1.5) < 1e-9
    assert abs(s.mean_wall_clock_s - 150.0) < 1e-9
    # one arm, no graded run: the composite is not shown (FR-034)
    assert s.composite is None
    assert s.pre012 is True
    assert s.generation == "pre012"
    assert s.cell_id is None
    assert s.arm == "a1"


# --- 013 T004 (RED): summary rows from runs (contract 5.1-5.4) ---------------
# Names: data-model §2, contract §5, research R-11. compute_summaries is
# rewritten to build runs once (sdlc.benchmarks.runs.build_runs) and key
# rows (case, stage, harness, arm, generation); the records here carry run
# ids of the stored shape so the run builder can parse them.

_T0 = datetime(2026, 7, 4, 10)


def _t4_rec(
    run_id,
    stage,
    *,
    model="zai-coding-plan/glm-5.2",
    judge="llm_judge",
    score=0.8,
    outcome=BenchmarkOutcome.PASS,
    task_id=None,
    attempt=None,
    scope=BenchmarkScope.STAGE,
    kroker_commit=None,
    arm=None,
    components=None,
    minute=0,
):
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=run_id.split("/")[0],
        case_id="c1",
        scope=scope,
        stage=stage,
        task_id=task_id,
        attempt=attempt,
        role=stage,
        harness=HarnessKind.OPENCODE,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=score, judge=judge, components=components or {}),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(
            wall_clock_s=10.0,
            started_at=_T0 + timedelta(minutes=minute),
            ended_at=_T0 + timedelta(minutes=minute, seconds=10),
        ),
        outcome=outcome,
        kroker_commit=kroker_commit,
        arm=arm,
    )


def _rowkey(s):
    """The R-11 row key minus the harness (every record here is opencode):
    (case, stage, arm, generation)."""
    return (s.case_id, s.stage, s.arm, s.generation)


def test_pre012_one_row_per_stage_with_models_joined_sorted():
    """contract §5.1: rows are keyed (case, stage, harness, arm,
    generation) — a pre-012 run whose records carry different model
    strings gives ONE row per stage, and the row's model is the sorted
    comma-joined distinct models."""
    rid = "b1/c1#opencode#glm"
    recs = [
        _t4_rec(rid, "research", model="m-research", minute=0),
        _t4_rec(rid, "clarify", model="m-clarify", minute=1),
        _t4_rec(rid, "code", model="m-code-2", minute=2),
        _t4_rec(rid, "code", model="m-code-1", minute=3),
    ]
    rows = compute_summaries(recs)
    assert len(rows) == 3
    by_key = {_rowkey(s): s for s in rows}
    assert {key[1] for key in by_key} == {"research", "clarify", "code"}
    assert by_key[("c1", "research", "glm", "pre012")].model == "m-research"
    assert by_key[("c1", "clarify", "glm", "pre012")].model == "m-clarify"
    assert by_key[("c1", "code", "glm", "pre012")].model == "m-code-1,m-code-2"


def test_mean_quality_only_from_rubric_judges():
    """contract §5.2: the mean comes only from records whose judge is in
    RUBRIC_JUDGES; a contract-judged record is counted in n but its score
    is not in the mean."""
    rid = "b1/c1#opencode#glm"
    recs = [
        _t4_rec(rid, "architecture", judge="llm_judge", score=0.8, minute=0),
        _t4_rec(rid, "architecture", judge="llm_judge", score=0.6, minute=1),
        _t4_rec(rid, "architecture", judge="contract", score=0.9, minute=2),
    ]
    (row,) = compute_summaries(recs)
    assert row.n == 3
    assert abs(row.mean_quality - 0.7) < 1e-9


def test_oracle_row_mean_partial_credit_all_pass_and_no_pass_rate():
    """contract §5.2/§5.3: the oracle row's mean_quality is the mean
    partial credit of the row's graded runs (4/5 and 3/5 -> 0.7), its
    all_pass is (0, 2), and pass_n/pass_d stay None."""
    recs = []
    for i, (passed, total) in enumerate([(4, 5), (3, 5)]):
        rid = f"b{i + 1}/c1#opencode#glm"
        recs.append(_t4_rec(rid, "code", minute=2 * i))
        recs.append(_t4_rec(rid, "merge", judge="contract", score=1.0, minute=2 * i))
        recs.append(
            _t4_rec(
                rid,
                "oracle",
                scope=BenchmarkScope.ORACLE,
                judge="oracle",
                score=passed / total,
                components={"passed": float(passed), "total": float(total)},
                minute=2 * i + 1,
            )
        )
    rows = compute_summaries(recs)
    oracle = next(s for s in rows if s.stage == "oracle")
    assert abs(oracle.mean_quality - 0.7) < 1e-9
    assert oracle.all_pass == (0, 2)
    assert oracle.pass_n is None
    assert oracle.pass_d is None


def test_merge_row_pass_rate_counts_revise_as_pass():
    """contract §5.3 + R-9: pass_n/pass_d from gate_passed — pass and merge
    `revise` are passes, fail and escalated are not, not_evaluated is in
    neither."""
    rid = "b1/c1#opencode#glm"
    verdicts = [
        (BenchmarkOutcome.PASS, 1.0),
        (BenchmarkOutcome.REVISED, 1.0),
        (BenchmarkOutcome.FAIL, 0.0),
        (BenchmarkOutcome.ESCALATED, 0.0),
        (BenchmarkOutcome.NOT_EVALUATED, None),
    ]
    recs = [
        _t4_rec(
            rid,
            "merge",
            judge="contract",
            score=score,
            outcome=outcome,
            minute=i,
        )
        for i, (outcome, score) in enumerate(verdicts)
    ]
    rows = compute_summaries(recs)
    merge = next(s for s in rows if s.stage == "merge")
    assert merge.pass_n == 2
    assert merge.pass_d == 4


def test_code_row_first_attempt_and_after_repair_sums_and_no_quality():
    """contract §5.4: first_attempt and after_repair are the sums of the
    row's runs' (k, n); the code row's mean_quality is None even when its
    records carry rubric scores. Per R-5, k counts tasks whose first /
    last code attempt passed. Run A: T1 pass@0; T2 fail@0,pass@1;
    T3 fail@0 -> first (1,3), last (2,3). Run B: T1 pass@0; T2 fail@0,
    fail@1 -> first (1,2), last (1,2)."""
    a, b = "b1/c1#opencode#glm", "b2/c1#opencode#glm"
    attempts = [
        (a, "T1", 0, BenchmarkOutcome.PASS),
        (a, "T2", 0, BenchmarkOutcome.FAIL),
        (a, "T2", 1, BenchmarkOutcome.PASS),
        (a, "T3", 0, BenchmarkOutcome.FAIL),
        (b, "T1", 0, BenchmarkOutcome.PASS),
        (b, "T2", 0, BenchmarkOutcome.FAIL),
        (b, "T2", 1, BenchmarkOutcome.FAIL),
    ]
    recs = [
        _t4_rec(
            rid,
            "code",
            scope=BenchmarkScope.TASK_ATTEMPT,
            task_id=task_id,
            attempt=attempt,
            outcome=outcome,
            score=0.9,
            minute=i,
        )
        for i, (rid, task_id, attempt, outcome) in enumerate(attempts)
    ]
    rows = compute_summaries(recs)
    code = next(s for s in rows if s.stage == "code")
    assert code.first_attempt == (2, 5)
    assert code.after_repair == (3, 5)
    assert code.mean_quality is None


def test_rows_of_two_generations_never_merge():
    """contract §5.1 tail: no row holds records of two runs' generations —
    a pre-012 run and a 012 run of the same case and stage are two rows,
    and each row's pre012 flag agrees with its generation."""
    pre = _t4_rec("b1/c1#opencode#glm", "code", minute=0)
    new = _t4_rec("b1/c3#opencode#glm", "code", kroker_commit="abc123", minute=1)
    rows = compute_summaries([pre, new])
    assert len(rows) == 2
    by_gen = {s.generation: s for s in rows}
    assert set(by_gen) == {"pre012", "012"}
    assert by_gen["pre012"].pre012 is True
    assert by_gen["012"].pre012 is False


# --- 013 T004 chaos (RED): copy qa, lost-run records, tokens -----------------
# Names: data-model §2, contract §5.5/§5.6, research R-11. Edge angles the
# main T004 section does not pin: a qa row of copy-only runs, a mixed qa
# row, a lost run whose oracle record must vanish from every row, the
# per-run token mean and its None, and the not_evaluated/quality split on
# a verdict stage. Reuses qa-happy's _t4_rec/_rowkey; cost overrides ride
# model_copy so no helper is duplicated.


def _qa_copy_run(run_id, minute):
    """A pre-012 run whose qa outcome equals its code outcome per
    (task_id, attempt) — the R-5 copy shape."""
    return [
        _t4_rec(
            run_id,
            "code",
            scope=BenchmarkScope.TASK_ATTEMPT,
            task_id="T1",
            attempt=0,
            outcome=BenchmarkOutcome.FAIL,
            judge="contract",
            score=None,
            minute=minute,
        ),
        _t4_rec(
            run_id,
            "qa",
            scope=BenchmarkScope.TASK_ATTEMPT,
            task_id="T1",
            attempt=0,
            outcome=BenchmarkOutcome.FAIL,
            judge="contract",
            score=None,
            minute=minute + 1,
        ),
    ]


def test_qa_row_of_copy_only_runs_shows_copy_and_no_pass_rate():
    """contract §5.5: a qa row built only from qa_is_copy runs carries
    qa_is_copy True and no pass rate at all — `copy of code` replaces it,
    so pass_n/pass_d must be None, not 0/0."""
    rows = compute_summaries(_qa_copy_run("b1/c1#opencode#glm", 0))
    qa = next(s for s in rows if s.stage == "qa")
    assert qa.qa_is_copy is True
    assert qa.pass_n is None
    assert qa.pass_d is None


def test_qa_row_mixing_copy_and_non_copy_counts_only_non_copy():
    """contract §5.5: in a row that mixes, the copy run's qa records are
    left out of the pass rate and qa_is_copy is False — one differing
    attempt unmarks the whole row."""
    copy_run = _qa_copy_run("b1/c1#opencode#glm", 0)
    non_copy = [
        _t4_rec(
            "b2/c1#opencode#glm",
            "code",
            scope=BenchmarkScope.TASK_ATTEMPT,
            task_id="T1",
            attempt=0,
            outcome=BenchmarkOutcome.FAIL,
            judge="contract",
            score=None,
            minute=0,
        ),
        _t4_rec(
            "b2/c1#opencode#glm",
            "qa",
            scope=BenchmarkScope.TASK_ATTEMPT,
            task_id="T1",
            attempt=0,
            outcome=BenchmarkOutcome.PASS,
            judge="contract",
            score=1.0,
            minute=1,
        ),
    ]
    rows = compute_summaries(copy_run + non_copy)
    qa = next(s for s in rows if s.stage == "qa")
    assert qa.qa_is_copy is False
    # only the non-copy run's qa verdict is counted: one pass, one verdict
    assert qa.pass_n == 1
    assert qa.pass_d == 1


def test_lost_run_stage_records_stay_and_its_oracle_record_makes_no_row():
    """contract §5.6: a lost run's stage records stay in their stage rows
    (the stage ran), and its oracle record is in no row — oracle rows come
    from graded runs only, so no oracle row exists for this case at all."""
    rid = "b1/c9#opencode#glm"
    recs = [
        _t4_rec(rid, "research", judge="contract", score=None, minute=0),
        _t4_rec(
            rid,
            "oracle",
            scope=BenchmarkScope.ORACLE,
            judge="oracle",
            score=1.0,
            components={"passed": 5.0, "total": 5.0},
            minute=1,
        ),
    ]
    rows = compute_summaries(recs)
    research = next(s for s in rows if s.stage == "research")
    assert research.n == 1  # the lost run's research record is still counted
    assert [s for s in rows if s.stage == "oracle"] == []  # nothing of the lost run


def test_code_row_tokens_is_mean_per_run_and_none_without_token_data():
    """data-model §2 `tokens`: the mean per run at the stage, as an int —
    run A 150 tokens, run B 50 -> 100. A stage where no run carries token
    data reads None, not 0."""
    a, b = "b1/c1#opencode#glm", "b2/c1#opencode#glm"
    recs = [
        _t4_rec(a, "code", minute=0).model_copy(
            update={"cost": CostBag(usd=0.1, input_tokens=100, output_tokens=50)}
        ),
        _t4_rec(b, "code", minute=1).model_copy(
            update={"cost": CostBag(usd=0.1, input_tokens=30, output_tokens=20)}
        ),
    ]
    code = next(s for s in compute_summaries(recs) if s.stage == "code")
    assert code.tokens == 100

    bare = [
        _t4_rec("b1/c3#opencode#glm", "review", judge="contract", score=None, minute=0).model_copy(
            update={"cost": CostBag()}
        )
    ]
    review = next(s for s in compute_summaries(bare) if s.stage == "review")
    assert review.tokens is None


def test_review_row_not_evaluated_excluded_and_contract_judge_no_quality():
    """contract §5.3/§5.2 edge: `not_evaluated` is in neither pass_n nor
    pass_d, and a verdict stage judged only by `contract` has mean_quality
    None — a pass/fail verdict never lands in the quality column."""
    rid = "b1/c1#opencode#glm"
    verdicts = [
        (BenchmarkOutcome.PASS, 1.0),
        (BenchmarkOutcome.FAIL, 0.0),
        (BenchmarkOutcome.NOT_EVALUATED, None),
    ]
    recs = [
        _t4_rec(rid, "review", judge="contract", score=score, outcome=outcome, minute=i)
        for i, (outcome, score) in enumerate(verdicts)
    ]
    review = next(s for s in compute_summaries(recs) if s.stage == "review")
    assert review.mean_quality is None
    assert review.pass_n == 1
    assert review.pass_d == 2
