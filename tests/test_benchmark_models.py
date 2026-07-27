from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkCell, BenchmarkOutcome, BenchmarkRecord,
    BenchmarkScope, BenchmarkSummary, CaseSpec, CompositeWeights, CostBag,
    QualityScore, SpeedBag,
)
from sdlc.models import BenchmarkConfig, HarnessKind


def _record(**kw):
    base = dict(
        run_id="r1", bench_run_id="b1", case_id="add-login",
        scope=BenchmarkScope.STAGE, stage="architecture", role="architect",
        model="anthropic:claude-sonnet-4-6", prompt_sha="abc",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(wall_clock_s=12.0,
                       started_at=datetime(2026, 7, 4, 10),
                       ended_at=datetime(2026, 7, 4, 10, 0, 12)),
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
    r = _record(scope=BenchmarkScope.TASK_ATTEMPT, stage="code",
                task_id="T1", attempt=0, role="dev",
                harness=HarnessKind.CLAUDE_CODE)
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
    c = BenchmarkCell(case_id="add-login", harness=HarnessKind.OPENCODE,
                     arm_name="anthropic-claude-sonnet-4-6")
    assert c.cell_id == "add-login#opencode#anthropic-claude-sonnet-4-6"


def test_benchmark_summary_aggregates_fields():
    s = BenchmarkSummary(case_id="add-login", stage="code",
                         harness=HarnessKind.CLAUDE_CODE,
                         model="anthropic:claude-sonnet-4-6",
                         n=3, mean_quality=0.9, mean_cost_usd=0.5,
                         mean_wall_clock_s=120.0, composite=0.88)
    assert s.n == 3 and s.composite == 0.88


def test_oracle_scope_exists():
    assert BenchmarkScope.ORACLE.value == "oracle"


def test_quality_score_accepts_oracle_judge():
    q = QualityScore(score=0.5, judge="oracle")
    assert q.judge == "oracle"


def test_case_spec_language_defaults_none_and_accepts_value():
    base = dict(case_id="c", idea_summary="s",
                harnesses=[HarnessKind.OPENCODE],
                models=["zai-coding-plan/glm-5.2"],
                judge_model="openai/gpt-5.2")
    assert CaseSpec(**base).language is None
    assert CaseSpec(**base, language="python").language == "python"


def test_oracle_task_scope_exists():
    assert BenchmarkScope.ORACLE_TASK.value == "oracle_task"
