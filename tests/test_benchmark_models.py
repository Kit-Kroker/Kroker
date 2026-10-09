from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkCell,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    BenchmarkSummary,
    CaseSpec,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.core.models import (
    BenchmarkConfig,
    HarnessKind,
)


def _record(**kw):
    base = dict(
        run_id="r1",
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


def test_record_serializes_round_trip():
    r = _record()
    js = r.model_dump_json()
    r2 = BenchmarkRecord.model_validate_json(js)
    assert r2.quality.score == 0.8
    assert r2.scope is BenchmarkScope.STAGE


def test_harness_optional_for_proposer():
    r = _record()
    assert r.harness is None  # architect is a proposer, no harness


def test_task_attempt_record_carries_task_id_and_attempt():
    r = _record(
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage="code",
        task_id="T1",
        attempt=0,
        role="dev",
        harness=HarnessKind.CLAUDE_CODE,
    )
    assert r.task_id == "T1" and r.attempt == 0


def test_benchmark_config_defaults_case_id_none():
    cfg = BenchmarkConfig()
    assert cfg.case_id is None
    assert cfg.bench_run_id is None


def test_composite_weights_default_quality_dominant():
    w = CompositeWeights()
    assert (w.quality, w.cost, w.speed) == (0.6, 0.2, 0.2)


def test_case_spec_matrix_axes():
    spec = CaseSpec(
        case_id="add-login",
        idea_summary="add login",
        mode="greenfield",
        harnesses=[HarnessKind.CLAUDE_CODE, HarnessKind.OPENCODE],
        models=["anthropic:claude-sonnet-4-6"],
        judge_model="openai/gpt-5.2",
        rubrics={"architect": "rubric-architect.md"},
    )
    assert len(spec.harnesses) == 2
    assert spec.judge_model.startswith("openai/")


def test_benchmark_cell_identity():
    c = BenchmarkCell(
        case_id="add-login", harness=HarnessKind.OPENCODE, arm_name="anthropic-claude-sonnet-4-6"
    )
    assert c.cell_id == "add-login#opencode#anthropic-claude-sonnet-4-6"


def test_benchmark_cell_identity_includes_lead_harness():
    """spec §5: `crew:<lead_harness>` rides the cell id so crew vs
    crew:claude_code cells over the same arm cannot collide."""
    c = BenchmarkCell(
        case_id="add-login",
        harness=HarnessKind.CREW,
        lead_harness=HarnessKind.CLAUDE_CODE,
        arm_name="zai-glm",
    )
    assert c.cell_id == "add-login#crew:claude_code#zai-glm"


def test_case_spec_harnesses_stay_raw_strings():
    """`crew:claude_code` must survive validation unparsed — parsing is
    expand_matrix's job, so the error names the entry at expansion time."""
    spec = CaseSpec(
        case_id="c",
        idea_summary="s",
        harnesses=["crew:claude_code"],
        models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2",
    )
    assert spec.harnesses == ["crew:claude_code"]


def test_benchmark_summary_aggregates_fields():
    s = BenchmarkSummary(
        case_id="add-login",
        stage="code",
        harness=HarnessKind.CLAUDE_CODE,
        model="anthropic:claude-sonnet-4-6",
        n=3,
        mean_quality=0.9,
        mean_cost_usd=0.5,
        mean_wall_clock_s=120.0,
        composite=0.88,
    )
    assert s.n == 3 and s.composite == 0.88


def test_oracle_scope_exists():
    assert BenchmarkScope.ORACLE.value == "oracle"


def test_quality_score_accepts_oracle_judge():
    q = QualityScore(score=0.5, judge="oracle")
    assert q.judge == "oracle"


def test_case_spec_language_defaults_none_and_accepts_value():
    base = dict(
        case_id="c",
        idea_summary="s",
        harnesses=[HarnessKind.OPENCODE],
        models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2",
    )
    assert CaseSpec(**base).language is None
    assert CaseSpec(**base, language="python").language == "python"


def test_oracle_task_scope_exists():
    assert BenchmarkScope.ORACLE_TASK.value == "oracle_task"


# --- E-77 T004 (RED): GraphAttribution + BenchmarkRecord.graph -------------
# Field names and invariants: .specify/specs/001-canonical-stage-graph-sha/
# data-model.md. Imports stay function-local so the not-yet-landed symbols
# fail these tests individually instead of breaking collection of the file.


def _graph_attribution(**kw):
    from sdlc.benchmarks.models import GraphAttribution

    base = dict(
        graph_sha="f" * 64,
        activation_id="act-1",
        node_id="plan-claims",
        round=2,
        node_stage="code",
        fail_reentry=1,
    )
    base.update(kw)
    return GraphAttribution(**base)


def test_graph_attribution_is_frozen():
    """data-model.md: the new benchmark models are frozen pydantic models."""
    import pytest
    from pydantic import ValidationError

    attrib = _graph_attribution()
    with pytest.raises(ValidationError):
        attrib.graph_sha = "0" * 64


def test_graph_attribution_without_activation_forbids_activation_fields():
    """Invariant: activation_id is None => node_id, round, node_stage and
    fail_reentry are all None; each violation raises ValidationError."""
    import pytest
    from pydantic import ValidationError

    violations = [
        ("node_id", "plan-claims"),
        ("round", 2),
        ("node_stage", "code"),
        ("fail_reentry", 1),
    ]
    for field, value in violations:
        with pytest.raises(ValidationError):
            _graph_attribution(activation_id=None, **{field: value})


def test_graph_attribution_fail_reentry_domain_is_none_zero_one():
    """Invariant: fail_reentry accepts exactly None, 0 and 1."""
    import pytest
    from pydantic import ValidationError

    assert _graph_attribution(fail_reentry=None).fail_reentry is None
    assert _graph_attribution(fail_reentry=0).fail_reentry == 0
    assert _graph_attribution(fail_reentry=1).fail_reentry == 1
    for bad in (2, -1, 7):
        with pytest.raises(ValidationError):
            _graph_attribution(fail_reentry=bad)


def test_benchmark_record_graph_defaults_to_none():
    """FR-024: `graph` is optional — FeatureWorkflow-shaped records keep None."""
    assert _record().graph is None


def test_current_record_json_without_graph_key_parses_unchanged():
    """records-and-store.md: JSON captured from a current record (no 'graph'
    key) still parses into BenchmarkRecord; absent reads as not recorded."""
    import json

    r = _record()
    captured = json.loads(r.model_dump_json())
    captured.pop("graph", None)  # a pre-E-77 capture carries no such key
    r2 = BenchmarkRecord.model_validate_json(json.dumps(captured))
    assert r2 == r
    assert r2.graph is None


# --- 012 T002 (RED): provenance fields, CellStatus, cell-key helpers --------
# Names: .specify/specs/012-benchmark-record-trust/data-model.md §1.1-1.4
# and §2.3. New symbols are imported function-local (the file's E-77
# convention) so each missing name fails its own test instead of breaking
# collection of the file.


def test_record_without_new_fields_reads_as_not_recorded():
    """data-model §1.1: every addition is optional with default None;
    absent reads as pre-012 / not recorded."""
    r = _record()
    assert r.kroker_commit is None
    assert r.tree_dirty is None
    assert r.arm is None
    assert r.cell_id is None
    assert r.cell is None


def test_cell_scope_and_not_evaluated_outcome_exist():
    """data-model §1.3: the two new enum values, exact strings."""
    assert BenchmarkScope.CELL.value == "cell"
    assert BenchmarkOutcome.NOT_EVALUATED.value == "not_evaluated"


def _cell_status(**kw):
    from sdlc.benchmarks.models import CellStatus

    base = dict(
        pipeline_finished=True,
        code_finished=True,
        completed=True,
        last_stage="merge",
        grading="graded",
        child_result="ok",
    )
    base.update(kw)
    return CellStatus(**base)


def test_cell_status_minimal_build_round_trips():
    """data-model §1.2: CellStatus built from its six fields keeps them."""
    s = _cell_status()
    assert (s.pipeline_finished, s.code_finished, s.completed) == (True, True, True)
    assert s.last_stage == "merge"
    assert s.grading == "graded"
    assert s.child_result == "ok"


def test_cell_status_child_result_may_be_none():
    assert _cell_status(child_result=None).child_result is None


def test_cell_status_is_frozen():
    import pytest
    from pydantic import ValidationError

    s = _cell_status()
    with pytest.raises(ValidationError):
        s.grading = "not_graded"


def test_cell_status_rejects_unknown_field():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _cell_status(bogus=1)


def test_cell_status_grading_is_limited_to_the_contract_states():
    import pytest
    from pydantic import ValidationError

    for grading in ("graded", "not_graded", "grading_failed", "no_oracle"):
        assert _cell_status(grading=grading).grading == grading
    with pytest.raises(ValidationError):
        _cell_status(grading="failed")


def test_cell_key_prefers_the_record_cell_id():
    from sdlc.benchmarks.models import cell_key

    r = _record(kroker_commit="deadbeef", arm="a1", cell_id="add-login#opencode#a1")
    assert cell_key(r) == "add-login#opencode#a1"


def test_cell_key_pre012_derivation_matches_recorder():
    """data-model §2.3: `case#harness[:lead]#model`, `proposer` when no
    harness — exactly recorder.py `_cell_id_for`'s pre-012 derivation."""
    from sdlc.benchmarks.models import cell_key

    proposer = _record(harness=None)
    assert cell_key(proposer) == f"add-login#proposer#{proposer.model}"
    harness = _record(harness=HarnessKind.OPENCODE)
    assert cell_key(harness) == (f"add-login#{HarnessKind.OPENCODE.value}#{harness.model}")
    crew = _record(harness=HarnessKind.CREW, lead_harness=HarnessKind.CLAUDE_CODE)
    assert cell_key(crew) == (
        f"add-login#{HarnessKind.CREW.value}:{HarnessKind.CLAUDE_CODE.value}#{crew.model}"
    )


def test_arm_label_prefers_arm_else_model():
    from sdlc.benchmarks.models import arm_label

    assert arm_label(_record(arm="zai-glm")) == "zai-glm"
    assert arm_label(_record(model="anthropic:claude-sonnet-4-6")) == (
        "anthropic:claude-sonnet-4-6"
    )


def test_is_pre012_cases():
    """data-model §2.3: `kroker_commit is None and case_id != '_production'`.
    Drift records are never pre-012; an explicit `unknown` commit is a 012
    record, not a pre-012 one."""
    from sdlc.benchmarks.models import is_pre012

    assert is_pre012(_record(kroker_commit="deadbeef")) is False
    assert is_pre012(_record(kroker_commit="unknown")) is False
    assert is_pre012(_record()) is True
    assert is_pre012(_record(case_id="_production")) is False
    assert is_pre012(_record(case_id="_production", kroker_commit="deadbeef")) is False


def test_post_code_stages_constant():
    from sdlc.benchmarks.models import POST_CODE_STAGES

    assert POST_CODE_STAGES == frozenset({"analyze", "merge", "deploy"})


# The 14 record-writing stage names in pipeline order (data-model §2.3;
# tasks T001(d) writer inventory).
_WRITER_STAGES = (
    "research",
    "clarify",
    "architecture",
    "plan",
    "code",
    "tool_approval",
    "qa",
    "review",
    "adversary",
    "deep_review",
    "handoff",
    "analyze",
    "merge",
    "deploy",
)


def test_cell_stage_order_covers_exactly_the_writer_inventory():
    """data-model §2.3: CELL_STAGE_ORDER holds exactly the record writers,
    in pipeline order — no renamed stage can silently fall out."""
    from sdlc.benchmarks.models import CELL_STAGE_ORDER

    assert set(CELL_STAGE_ORDER) == set(_WRITER_STAGES)
    order = {stage: i for i, stage in enumerate(CELL_STAGE_ORDER)}
    assert order["research"] < order["plan"] < order["code"] < order["qa"]
    assert order["code"] < order["review"] < order["analyze"]
    assert order["analyze"] < order["merge"] < order["deploy"]


def test_benchmark_summary_cell_row_fields_default():
    """data-model §1.4: BenchmarkSummary gains cell_id, arm (None) and
    pre012 (False); a row never starts out marked 012."""
    s = BenchmarkSummary(
        case_id="add-login",
        stage="code",
        harness=HarnessKind.CLAUDE_CODE,
        model="anthropic:claude-sonnet-4-6",
        n=3,
        mean_quality=0.9,
        mean_cost_usd=0.5,
        mean_wall_clock_s=120.0,
        composite=0.88,
    )
    assert s.cell_id is None
    assert s.arm is None
    assert s.pre012 is False


# --- 013 T002 (RED): shared status functions --------------------------------
# Names: .specify/specs/013-benchmark-scoring-output/data-model.md §2. The
# two functions move out of cell.py (summarize_cell / grading_status) into
# models.py; imports stay function-local (the file's E-77 convention) so
# each missing name fails its own test instead of breaking collection.


def test_cell_progress_no_records_gives_none_and_false():
    from sdlc.benchmarks.models import cell_progress

    assert cell_progress([]) == (None, False)


def test_cell_progress_research_clarify_last_stage_clarify_not_code_finished():
    from sdlc.benchmarks.models import cell_progress

    records = [_record(stage="research"), _record(stage="clarify")]
    assert cell_progress(records) == ("clarify", False)


def test_cell_progress_task_loop_without_post_code_gives_handoff():
    """code..handoff with no post-code record: last stage is `handoff`,
    code_finished stays False."""
    from sdlc.benchmarks.models import cell_progress

    records = [
        _record(stage="code"),
        _record(stage="qa"),
        _record(stage="review"),
        _record(stage="handoff"),
    ]
    assert cell_progress(records) == ("handoff", False)


def test_cell_progress_ignores_cell_and_oracle_stage_records():
    """The cell record (stage "cell") and oracle records are not in
    CELL_STAGE_ORDER and never become the last stage (contract §3.2)."""
    from sdlc.benchmarks.models import cell_progress

    records = [
        _record(stage="qa"),
        _record(stage="cell"),
        _record(stage="oracle"),
    ]
    assert cell_progress(records) == ("qa", False)


def test_cell_progress_post_code_stage_record_finishes_code():
    from sdlc.benchmarks.models import cell_progress

    for stage in ("analyze", "merge", "deploy"):
        assert cell_progress([_record(stage=stage)]) == (stage, True)


def test_grading_from_score_no_oracle_regardless_of_code_finished():
    from sdlc.benchmarks.models import grading_from_score

    assert grading_from_score(False, True, 1.0) == "no_oracle"
    assert grading_from_score(False, False, None) == "no_oracle"


def test_grading_from_score_oracle_without_code_finished_is_not_graded():
    from sdlc.benchmarks.models import grading_from_score

    assert grading_from_score(True, False, 0.5) == "not_graded"


def test_grading_from_score_graded_for_zero_and_one():
    from sdlc.benchmarks.models import grading_from_score

    assert grading_from_score(True, True, 0.0) == "graded"
    assert grading_from_score(True, True, 1.0) == "graded"


def test_grading_from_score_none_score_is_grading_failed():
    from sdlc.benchmarks.models import grading_from_score

    assert grading_from_score(True, True, None) == "grading_failed"


# --- 013 T002 chaos (RED): stage-loop and judge constants -------------------
# Names: .specify/specs/013-benchmark-scoring-output/data-model.md §2.
# Edge-angle pins on the two new constants: exact membership (no silent
# extra stage/judge slips in), subset relation, and exclusion of the
# neighbouring stages and judge kinds they must NOT contain. Imports stay
# function-local (the file's E-77 convention) so each missing name fails
# its own tests with ImportError instead of breaking collection.


def test_task_loop_stages_is_exactly_the_seven_loop_names():
    """data-model §2: TASK_LOOP_STAGES holds exactly the seven task-loop
    stage names — no more, no fewer."""
    from sdlc.benchmarks.models import TASK_LOOP_STAGES

    assert TASK_LOOP_STAGES == frozenset(
        {"code", "tool_approval", "qa", "review", "adversary", "deep_review", "handoff"}
    )


def test_task_loop_stages_is_subset_of_cell_stage_order():
    """data-model §2: every task-loop stage is a record-writing stage in
    CELL_STAGE_ORDER, so cell_progress can always position a run by it."""
    from sdlc.benchmarks.models import CELL_STAGE_ORDER, TASK_LOOP_STAGES

    assert TASK_LOOP_STAGES <= set(CELL_STAGE_ORDER)


def test_task_loop_stages_excludes_post_code_and_proposer_stages():
    """Edge angle: the loop ends at handoff — the post-code stages
    (analyze/merge/deploy) and the proposer stages (research/clarify/
    architecture/plan) stay outside it, or "lost in the task loop" would
    swallow runs the pipeline actually finished."""
    from sdlc.benchmarks.models import TASK_LOOP_STAGES

    assert not TASK_LOOP_STAGES & {"analyze", "merge", "deploy"}
    assert not TASK_LOOP_STAGES & {"research", "clarify", "architecture", "plan"}


def test_rubric_judges_is_exactly_the_two_rubric_kinds():
    """data-model §2: RUBRIC_JUDGES is exactly {llm_judge, staged_rubric}."""
    from sdlc.benchmarks.models import RUBRIC_JUDGES

    assert RUBRIC_JUDGES == frozenset({"llm_judge", "staged_rubric"})


def test_rubric_judges_excludes_the_non_rubric_judge_kinds():
    """Edge angle: every judge kind that is not a rubric judge — oracle,
    contract, the crew stages riding as judge labels, the human and error
    escapes — stays out, or mean_quality would silently absorb
    non-rubric scores."""
    from sdlc.benchmarks.models import RUBRIC_JUDGES

    assert not RUBRIC_JUDGES & {
        "contract",
        "oracle",
        "adversary",
        "deep_review",
        "handoff",
        "human_override",
        "error",
    }
