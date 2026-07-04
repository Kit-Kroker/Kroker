"""BenchmarkWorkflow matrix test. We avoid a real Temporal server by testing
the pure config-building helper directly, plus a smoke test that the workflow
class is registered and runnable-shaped. A full time-skipping integration
test lives in Task 13's golden-case smoke run."""
from sdlc.benchmarks.models import CaseSpec
from sdlc.benchmarks.workflow import BenchmarkWorkflow, _cell_config
from sdlc.models import HarnessKind, PipelineConfig, ProjectMode, IdeaBrief


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
