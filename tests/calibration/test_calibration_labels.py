"""C7: realized-outcome labels (ruling OQ9).

The label is the quantity the whole verdict is a function of, so each formula
is pinned exactly rather than described. Both labels are "1 - badness", so a
clean run labels near 1.0 and a bad one near 0.0, on the same [0, 1] scale the
self-reported confidence uses.
"""

from sdlc.calibration.labels import fix_attempt_label, plan_drift_label, unhinted_ratio
from sdlc.stages.plan.models import PlanDrift


def _drift(hinted: int, touched: int, unhinted: list[str]) -> PlanDrift:
    return PlanDrift(
        files_hinted=hinted,
        files_touched=touched,
        hinted_untouched=[],
        touched_unhinted=unhinted,
    )


def test_unhinted_ratio_is_touched_unhinted_over_files_touched():
    """Ruling OQ9(1): the CONTINUOUS ratio, not merge's binary threshold flag."""
    assert unhinted_ratio(_drift(4, 4, ["a.py", "b.py"])) == 0.5


def test_unhinted_ratio_of_a_perfectly_hinted_task_is_zero():
    assert unhinted_ratio(_drift(3, 3, [])) == 0.0


def test_unhinted_ratio_guards_zero_files_touched():
    """compute_plan_drift never emits files_touched=0 (plan/models.py:52-54
    returns None first), but the ratio must not be the one place a future
    caller discovers that by ZeroDivisionError."""
    assert unhinted_ratio(_drift(2, 0, [])) == 0.0


def test_plan_drift_label_inverts_the_mean_ratio():
    assert plan_drift_label([0.0, 0.5]) == 0.75


def test_plan_drift_label_clamps_to_zero():
    """touched_unhinted can exceed files_touched only if a caller builds an
    inconsistent PlanDrift, but the label's contract is [0, 1] regardless."""
    assert plan_drift_label([1.5]) == 0.0


def test_plan_drift_label_of_no_measured_tasks_is_none():
    """None means UNLABELLABLE, which means no sample -- not a 1.0 that would
    silently vote 'the plan was perfect' for a run that measured nothing."""
    assert plan_drift_label([]) is None


def test_fix_attempt_label_is_one_minus_the_capped_mean():
    """max_fix_attempts=2: one stage took 0 attempts, one took 2 (capped).
    mean(0/2, 2/2) = 0.5 -> label 0.5."""
    assert fix_attempt_label([0, 2], max_fix_attempts=2) == 0.5


def test_fix_attempt_label_caps_runaway_attempts():
    assert fix_attempt_label([99], max_fix_attempts=2) == 0.0


def test_fix_attempt_label_of_a_clean_run_is_one():
    assert fix_attempt_label([0, 0, 0], max_fix_attempts=2) == 1.0


def test_fix_attempt_label_of_no_stages_is_none():
    assert fix_attempt_label([], max_fix_attempts=2) is None


def test_fix_attempt_label_guards_a_zero_cap():
    """cfg.max_fix_attempts is 2 by default (core/models.py:362) but is
    operator-settable; 0 must not divide."""
    assert fix_attempt_label([0], max_fix_attempts=0) is None


# --- calibration_samples_for (Task 4) -------------------------------------

from sdlc.calibration.labels import calibration_samples_for
from sdlc.calibration.models import LabelSource
from sdlc.calibration.verdict import bucket_key
from sdlc.core.models import GateOutcomeSummary, RunSummary, StageOutcome

_T = "2026-09-10T12:00:00+00:00"


def _summary(gates, stages=()) -> RunSummary:
    return RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        terminal_stage="merge",
        started_at=_T,
        ended_at=_T,
        duration_s=1.0,
        stages=list(stages),
        gates=list(gates),
    )


def _auto(gate: str, conf: float, model: str = "m/x") -> GateOutcomeSummary:
    return GateOutcomeSummary(
        gate=gate,
        round=1,
        policy="soft",
        decided_by="policy",
        approved=True,
        confidence=conf,
        author_model=model,
    )


def _stage(stage: str, role: str, **kw) -> StageOutcome:
    return StageOutcome(stage=stage, role=role, outcome="pass", duration_s=1.0, **kw)


def test_a_soft_auto_approved_plan_gate_yields_a_drift_labelled_sample():
    """Drift is recorded on the task rows (code/step.py:769), not on the plan
    stage's own row."""
    s = _summary([_auto("plan", 0.9)], [_stage("code", "dev", plan_drift=0.25)])
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=False)
    assert len(samples) == 1
    assert samples[0].gate == "plan"
    assert samples[0].confidence == 0.9
    assert samples[0].outcome_label == 0.75
    assert samples[0].bucket_key == bucket_key("m/x", LabelSource.PRODUCTION_PROXY)


def test_an_architecture_gate_is_labelled_from_fix_attempts():
    s = _summary([_auto("architecture", 0.8)], [_stage("code", "dev", fix_attempts=1)])
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=False)
    assert len(samples) == 1
    assert samples[0].outcome_label == 0.5


def test_zero_attempt_non_task_rows_cannot_dilute_the_label():
    """The population is the run's TASKS. Every other stage emits a row with
    fix_attempts=0, so aggregating over all rows would drag a run in which
    every task exhausted its budget up toward 'mostly fine' -- rebuilding
    audit row 8's hole by dilution rather than by omission."""
    s = _summary(
        [_auto("architecture", 0.9)],
        [
            _stage("code", "dev", fix_attempts=2),
            _stage("intake", "intake"),
            _stage("clarify", "clarify"),
            _stage("architecture", "architect"),
            _stage("plan", "planner"),
            _stage("qa", "qa"),
        ],
    )
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=False)
    assert samples[0].outcome_label == 0.0


def test_benchmarking_prefers_the_judge_score_and_tags_the_source():
    """Ruling OQ1 + OQ6: the stronger label wins, and lands in its own bucket."""
    s = _summary(
        [_auto("plan", 0.9)],
        [
            _stage("plan", "planner", quality_score=0.85, quality_judge="llm_judge"),
            _stage("code", "dev", plan_drift=0.9),
        ],
    )
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=True)
    assert samples[0].outcome_label == 0.85
    assert samples[0].bucket_key == bucket_key("m/x", LabelSource.BENCHMARK)


def test_the_judge_label_is_attributed_to_its_own_stage():
    """Spec 4.2.1: the judge score FOR THIS STAGE. A run-wide blend would let
    the planner's rubric score help authorize the architecture gate, and the
    architect's help authorize the plan gate -- each gate would be graded
    partly on work it did not produce."""
    s = _summary(
        [_auto("architecture", 0.9)],
        [
            _stage("plan", "planner", quality_score=0.95, quality_judge="llm_judge"),
            _stage("code", "dev", fix_attempts=2),
        ],
    )
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=True)
    assert samples[0].outcome_label == 0.0, (
        "the architecture gate has no judge score of its own, so it must fall "
        "back to the proxy -- not borrow the plan stage's score"
    )


def test_a_contract_score_never_displaces_the_proxy_label():
    """QualityScore also carries CONTRACT pass/fail bookkeeping -- the code
    stage records 1.0/0.0 (code/step.py:760-761). That is not the rubric
    judgment spec 3 calls the strongest signal, and it must not stand in for
    one: a green run would otherwise label 1.0 on every benchmark run
    regardless of what the rubric thought."""
    s = _summary(
        [_auto("plan", 0.9)],
        [
            _stage("plan", "planner", quality_score=1.0, quality_judge="contract"),
            _stage("code", "dev", plan_drift=0.25),
        ],
    )
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=True)
    assert samples[0].outcome_label == 0.75


def test_a_human_decided_gate_is_not_a_sample():
    """Only auto-approves are calibration evidence: a human-decided gate has
    no 'would the human have caught it' counterfactual to score against."""
    g = GateOutcomeSummary(
        gate="plan",
        round=1,
        policy="soft",
        decided_by="human",
        approved=True,
        confidence=0.9,
        author_model="m/x",
    )
    s = _summary([g], [_stage("code", "dev", plan_drift=0.0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_an_off_policy_approval_is_not_a_sample():
    """gates.py:195-198 synthesizes decided_by='policy' for OFF gates too. The
    filter must exclude them on purpose, not by accident of having no
    confidence to score."""
    g = GateOutcomeSummary(
        gate="plan",
        round=1,
        policy="off",
        decided_by="policy",
        approved=True,
        confidence=0.9,
        author_model="m/x",
    )
    s = _summary([g], [_stage("code", "dev", plan_drift=0.0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_a_policy_approval_without_confidence_is_not_a_sample():
    g = GateOutcomeSummary(
        gate="plan",
        round=1,
        policy="soft",
        decided_by="policy",
        approved=True,
        confidence=None,
        author_model="m/x",
    )
    s = _summary([g], [_stage("code", "dev", plan_drift=0.0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_the_merge_gate_is_never_labelled():
    """Ruling OQ2. Note the absence of any gate-name branch in the source: a
    merge auto-approve produces no sample because merge has no realized-outcome
    label defined, not because it is named 'merge'."""
    s = _summary([_auto("merge", 0.99)], [_stage("code", "dev", fix_attempts=0)])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_an_unlabellable_run_yields_nothing():
    """A plan gate with no measured drift anywhere: no sample, rather than a
    1.0 that would vote 'the plan was perfect' on no evidence."""
    s = _summary([_auto("plan", 0.9)], [_stage("plan", "planner")])
    assert calibration_samples_for(s, max_fix_attempts=2, benchmarking=False) == []


def test_a_pre_c7_gate_row_buckets_as_unknown_and_still_samples():
    g = GateOutcomeSummary(
        gate="plan",
        round=1,
        policy="soft",
        decided_by="policy",
        approved=True,
        confidence=0.9,
        author_model=None,
    )
    s = _summary([g], [_stage("code", "dev", plan_drift=0.0)])
    samples = calibration_samples_for(s, max_fix_attempts=2, benchmarking=False)
    assert samples[0].bucket_key == bucket_key(None, LabelSource.PRODUCTION_PROXY)
