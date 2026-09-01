"""BenchmarkWorkflow matrix test. We avoid a real Temporal server by testing
the pure config-building helper directly, plus a smoke test that the workflow
class is registered and runnable-shaped. A full time-skipping integration
test lives in Task 13's golden-case smoke run."""

from datetime import UTC, datetime

from sdlc.benchmarks.models import BenchmarkCell, BenchmarkOutcome, BenchmarkScope, CaseSpec
from sdlc.benchmarks.oracle import OracleGrade
from sdlc.benchmarks.tasks import TaskGrade
from sdlc.benchmarks.workflow import (
    BenchmarkWorkflow,
    _cell_config,
    _oracle_record,
    _oracle_task_records,
)
from sdlc.models import GatePolicy, HarnessKind, IdeaBrief, PipelineConfig, ProjectMode


def _grade(**kw):
    base = dict(
        score=0.5,
        passed=1,
        total=2,
        language_manifest="python",
        language_detected="python",
        language_match=True,
        held_out_ok=True,
        detail="1/2",
    )
    base.update(kw)
    return OracleGrade(**base)


def _cell():
    return BenchmarkCell(case_id="todo-api", harness=HarnessKind.OPENCODE, arm_name="m")


def _harness_cell(model, harness=HarnessKind.OPENCODE, arm_name="a"):
    """A backward-compat-shaped cell: the three harness roles all set to the
    same model (what the pre-E-37 `models=[...]` desugar produces)."""
    return BenchmarkCell(
        case_id="todo-api",
        harness=harness,
        arm_name=arm_name,
        role_models={"dev": model, "test": model, "devops": model},
    )


def _rec(grade):
    t0 = datetime(2026, 7, 23, tzinfo=UTC)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=UTC)
    return _oracle_record(_cell(), grade, "b1", "b1/todo-api#opencode#m", t0, t1)


def test_oracle_record_shape():
    r = _rec(_grade())
    assert r.scope is BenchmarkScope.ORACLE
    assert r.stage == "oracle" and r.role == "oracle"
    assert r.quality.judge == "oracle" and r.quality.score == 0.5
    assert r.quality.components["passed"] == 1.0
    assert r.quality.components["total"] == 2.0
    assert r.harness is HarnessKind.OPENCODE
    assert r.error is None


def test_oracle_record_flags_held_out_breach():
    r = _rec(_grade(held_out_ok=False))
    assert r.error is not None and "held-out" in r.error


def test_oracle_record_flags_language_mismatch():
    r = _rec(_grade(language_match=False, language_detected="typescript"))
    assert r.error is not None and "mismatch" in r.error


def test_oracle_record_none_score_is_fail():
    from sdlc.benchmarks.models import BenchmarkOutcome

    r = _rec(_grade(score=None, passed=0))
    assert r.outcome is BenchmarkOutcome.FAIL
    assert r.quality.score is None


def _spec():
    return CaseSpec(
        case_id="add-login",
        idea_summary="add login",
        mode="greenfield",
        harnesses=[HarnessKind.CLAUDE_CODE],
        models=["anthropic:claude-sonnet-4-6"],
        judge_model="openai/gpt-5.2",
        rubrics={},
    )


def test_cell_config_overrides_role_and_sets_benchmark():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), _harness_cell("openai/gpt-5.2"), bench_run_id="b1")
    # every harness role is overridden to the cell's harness+model
    for _role, rc in cfg.roles.items():
        assert rc.harness is HarnessKind.OPENCODE
        assert rc.model == "openai/gpt-5.2"
    assert cfg.benchmark.case_id == "add-login"
    assert cfg.benchmark.bench_run_id == "b1"


def test_cell_config_is_pure_when_base_unbenchmark():
    base = PipelineConfig()
    assert base.benchmark.case_id is None
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), _harness_cell("openai/gpt-5.2"), bench_run_id="b1")
    assert cfg.benchmark.case_id == "add-login"


def test_cell_config_carries_lead_harness_for_crew_cells():
    """spec §5: a crew:<lead_harness> cell reaches the dev RoleConfig as
    lead_harness (the harness dimension survives the composition); every
    other harness leaves lead_harness unset."""
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cell = BenchmarkCell(
        case_id="add-login",
        harness=HarnessKind.CREW,
        lead_harness=HarnessKind.CLAUDE_CODE,
        arm_name="a",
        role_models={"dev": "zai-coding-plan/glm-5.2"},
    )
    cfg = _cell_config(base, idea, _spec(), cell, bench_run_id="b1")
    assert cfg.roles["dev"].harness is HarnessKind.CREW
    assert cfg.roles["dev"].lead_harness is HarnessKind.CLAUDE_CODE
    plain = _cell_config(
        base, idea, _spec(), _harness_cell("zai-coding-plan/glm-5.2"), bench_run_id="b1"
    )
    assert all(rc.lead_harness is None for rc in plain.roles.values())


def test_benchmark_workflow_class_has_run():
    # the @workflow.run method exists
    assert hasattr(BenchmarkWorkflow, "run")


def test_cell_config_forwards_per_model_extra_args():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    spec = CaseSpec(
        case_id="todo-api",
        idea_summary="todo api",
        mode="greenfield",
        harnesses=[HarnessKind.OPENCODE],
        models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2",
        rubrics={},
        extra_args_by_model={"zai-coding-plan/glm-5.2": ["--variant", "max"]},
    )
    cfg = _cell_config(
        base, idea, spec, _harness_cell("zai-coding-plan/glm-5.2"), bench_run_id="b1"
    )
    for rc in cfg.roles.values():
        assert rc.extra_args == ["--variant", "max"]

    # a model with no entry gets no extra args
    cfg2 = _cell_config(base, idea, _spec(), _harness_cell("openai/gpt-5.2"), bench_run_id="b1")
    for rc in cfg2.roles.values():
        assert rc.extra_args == []


def test_cell_config_defaults_every_gate_to_soft():
    # SOFT is CaseSpec.gate_policy's default: a task that exhausts its fix
    # budget still gets judged instead of rubber-stamped into a merge-time
    # rejection, regardless of the base config's per-gate policy.
    base = PipelineConfig()
    assert any(g.policy != GatePolicy.SOFT for g in base.gates.values())
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), _harness_cell("openai/gpt-5.2"), bench_run_id="b1")
    assert all(g.policy == GatePolicy.SOFT for g in cfg.gates.values())
    assert set(cfg.gates) == set(base.gates)
    # dynamic gates not named in cfg.gates (e.g. task:<id> escalation) must
    # honor the same policy
    assert cfg.default_gate_policy == GatePolicy.SOFT


def test_cell_config_honors_spec_gate_policy_override():
    # --gate-policy off (a fire-and-forget batch run) must still force every
    # gate, including dynamic ones, to auto-approve
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    spec = _spec().model_copy(update={"gate_policy": GatePolicy.OFF})
    cfg = _cell_config(base, idea, spec, _harness_cell("openai/gpt-5.2"), bench_run_id="b1")
    assert all(g.policy == GatePolicy.OFF for g in cfg.gates.values())
    assert cfg.default_gate_policy == GatePolicy.OFF


def _research_spec():
    return CaseSpec(
        case_id="cat-cafe",
        idea_summary="cats",
        mode="greenfield",
        harnesses=[HarnessKind.OPENCODE],
        models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2",
        rubrics={},
        research_enabled=True,
    )


def test_case_spec_research_disabled_by_default():
    assert _spec().research_enabled is False


def test_cell_config_leaves_research_off_by_default():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), _harness_cell("openai/gpt-5.2"), bench_run_id="b1")
    assert cfg.research_enabled is False
    assert "research" not in cfg.roles


def test_cell_config_enables_research_and_injects_provider():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(
        base, idea, _research_spec(), _harness_cell("zai-coding-plan/glm-5.2"), bench_run_id="b1"
    )
    assert cfg.research_enabled is True
    rc = cfg.roles["research"]
    assert rc.kind == "research"
    assert rc.provider == "tavily"


def test_cell_config_research_role_is_not_harness_overridden():
    """The research role is a proposer-side role: the cell's harness/model
    override applies to harness roles, but the injected research role must
    keep kind='research' and carry no harness."""
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(
        base, idea, _research_spec(), _harness_cell("zai-coding-plan/glm-5.2"), bench_run_id="b1"
    )
    assert cfg.roles["research"].harness is None


def _grade_with_tasks(*task_grades):
    return OracleGrade(
        score=0.5,
        passed=1,
        total=2,
        language_manifest="python",
        language_detected="python",
        language_match=True,
        held_out_ok=True,
        detail="1/2",
        task_grades=list(task_grades),
    )


def test_oracle_task_records_one_per_task_grade():
    t0 = datetime(2026, 7, 23, tzinfo=UTC)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=UTC)
    grade = _grade_with_tasks(
        TaskGrade(task_id="t01", error_class="functional", score=1.0, judge="oracle", detail="1/1"),
        TaskGrade(
            task_id="t02",
            error_class="security",
            score=0.0,
            judge="llm_judge",
            detail="rubric-graded",
        ),
    )
    recs = _oracle_task_records(_cell(), grade, "b1", "b1/todo-api#opencode#m", t0, t1)
    assert len(recs) == 2
    assert {r.task_id for r in recs} == {"t01", "t02"}
    r01 = next(r for r in recs if r.task_id == "t01")
    assert r01.scope is BenchmarkScope.ORACLE_TASK
    assert r01.stage == "oracle" and r01.role == "oracle"
    assert r01.quality.score == 1.0 and r01.quality.judge == "oracle"
    assert r01.outcome is BenchmarkOutcome.PASS
    r02 = next(r for r in recs if r.task_id == "t02")
    assert r02.outcome is BenchmarkOutcome.FAIL


def test_oracle_task_records_none_score_is_fail():
    from sdlc.benchmarks.models import BenchmarkOutcome as BO

    t0 = datetime(2026, 7, 23, tzinfo=UTC)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=UTC)
    grade = _grade_with_tasks(
        TaskGrade(task_id="t01", error_class="functional", score=None, judge="error", detail="oops")
    )
    recs = _oracle_task_records(_cell(), grade, "b1", "run1", t0, t1)
    assert recs[0].outcome is BO.FAIL
    assert recs[0].quality.score is None


def test_oracle_task_records_empty_when_no_task_grades():
    t0 = datetime(2026, 7, 23, tzinfo=UTC)
    t1 = datetime(2026, 7, 23, 0, 0, 5, tzinfo=UTC)
    recs = _oracle_task_records(_cell(), _grade(), "b1", "run1", t0, t1)
    assert recs == []
