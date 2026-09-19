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
