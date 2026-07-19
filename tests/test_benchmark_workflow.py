"""BenchmarkWorkflow matrix test. We avoid a real Temporal server by testing
the pure config-building helper directly, plus a smoke test that the workflow
class is registered and runnable-shaped. A full time-skipping integration
test lives in Task 13's golden-case smoke run."""
from sdlc.benchmarks.models import CaseSpec
from sdlc.benchmarks.workflow import BenchmarkWorkflow, _cell_config
from sdlc.models import (GatePolicy, HarnessKind, PipelineConfig, ProjectMode,
                         IdeaBrief)


def _spec():
    return CaseSpec(
        case_id="add-login", idea_summary="add login",
        mode="greenfield",
        harnesses=[HarnessKind.CLAUDE_CODE],
        models=["anthropic:claude-sonnet-4-6"],
        judge_model="openai/gpt-5.2", rubrics={})


def test_cell_config_overrides_role_and_sets_benchmark():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d",
                     mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(),
                       HarnessKind.OPENCODE, "openai/gpt-5.2",
                       bench_run_id="b1")
    # every role is overridden to the cell's harness+model
    for role, rc in cfg.roles.items():
        assert rc.harness is HarnessKind.OPENCODE
        assert rc.model == "openai/gpt-5.2"
    assert cfg.benchmark.case_id == "add-login"
    assert cfg.benchmark.bench_run_id == "b1"


def test_cell_config_is_pure_when_base_unbenchmark():
    base = PipelineConfig()
    assert base.benchmark.case_id is None
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), HarnessKind.OPENCODE,
                       "openai/gpt-5.2", bench_run_id="b1")
    assert cfg.benchmark.case_id == "add-login"


def test_benchmark_workflow_class_has_run():
    # the @workflow.run method exists
    assert hasattr(BenchmarkWorkflow, "run")


def test_cell_config_forwards_per_model_extra_args():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    spec = CaseSpec(
        case_id="todo-api", idea_summary="todo api", mode="greenfield",
        harnesses=[HarnessKind.OPENCODE], models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2", rubrics={},
        extra_args_by_model={"zai-coding-plan/glm-5.2": ["--variant", "max"]})
    cfg = _cell_config(base, idea, spec, HarnessKind.OPENCODE,
                       "zai-coding-plan/glm-5.2", bench_run_id="b1")
    for rc in cfg.roles.values():
        assert rc.extra_args == ["--variant", "max"]

    # a model with no entry gets no extra args
    cfg2 = _cell_config(base, idea, _spec(), HarnessKind.OPENCODE,
                        "openai/gpt-5.2", bench_run_id="b1")
    for rc in cfg2.roles.values():
        assert rc.extra_args == []


def test_cell_config_auto_approves_every_gate():
    # a benchmark run is unattended — no human to click approve, so every
    # gate must be forced to OFF regardless of the base config's policy
    base = PipelineConfig()
    assert any(g.policy != GatePolicy.OFF for g in base.gates.values())
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), HarnessKind.OPENCODE,
                       "openai/gpt-5.2", bench_run_id="b1")
    assert all(g.policy == GatePolicy.OFF for g in cfg.gates.values())
    assert set(cfg.gates) == set(base.gates)
    # dynamic gates not named in cfg.gates (e.g. task:<id> escalation)
    # must also auto-approve — otherwise an unattended cell still blocks
    assert cfg.default_gate_policy == GatePolicy.OFF


def _research_spec():
    return CaseSpec(
        case_id="cat-cafe", idea_summary="cats",
        mode="greenfield",
        harnesses=[HarnessKind.OPENCODE],
        models=["zai-coding-plan/glm-5.2"],
        judge_model="openai/gpt-5.2", rubrics={},
        research_enabled=True)


def test_case_spec_research_disabled_by_default():
    assert _spec().research_enabled is False


def test_cell_config_leaves_research_off_by_default():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _spec(), HarnessKind.OPENCODE,
                       "openai/gpt-5.2", bench_run_id="b1")
    assert cfg.research_enabled is False
    assert "research" not in cfg.roles


def test_cell_config_enables_research_and_injects_provider():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(base, idea, _research_spec(), HarnessKind.OPENCODE,
                       "zai-coding-plan/glm-5.2", bench_run_id="b1")
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
    cfg = _cell_config(base, idea, _research_spec(), HarnessKind.OPENCODE,
                       "zai-coding-plan/glm-5.2", bench_run_id="b1")
    assert cfg.roles["research"].harness is None
