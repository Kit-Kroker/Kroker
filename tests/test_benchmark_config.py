from sdlc.core.models import (
    BenchmarkConfig,
    PipelineConfig,
)


def test_default_pipeline_config_has_no_benchmark():
    cfg = PipelineConfig()
    assert cfg.benchmark.case_id is None
    assert cfg.benchmark.bench_run_id is None


def test_benchmark_config_rubric_and_judge_model_default():
    bc = BenchmarkConfig()
    assert bc.rubrics == {}
    assert bc.judge_model is None


def test_pipeline_config_accepts_benchmark_fields():
    cfg = PipelineConfig()
    cfg.benchmark = BenchmarkConfig(case_id="add-login", bench_run_id="b1")
    assert cfg.benchmark.case_id == "add-login"


def test_pipeline_config_serializes_with_benchmark():
    cfg = PipelineConfig()
    js = cfg.model_dump_json()
    assert "benchmark" in js
    # round-trip preserves defaults
    cfg2 = PipelineConfig.model_validate_json(js)
    assert cfg2.benchmark.case_id is None


def test_benchmark_config_payload_without_new_fields_defaults_them_none():
    """012 data-model §1.5: a payload without the four new fields validates
    unchanged, and arm / cell_id / kroker_commit / tree_dirty default None."""
    payload = {"case_id": "add-login", "bench_run_id": "b1"}
    bc = BenchmarkConfig.model_validate(payload)
    assert bc.case_id == "add-login" and bc.bench_run_id == "b1"
    assert bc.arm is None
    assert bc.cell_id is None
    assert bc.kroker_commit is None
    assert bc.tree_dirty is None
    bare = BenchmarkConfig()
    assert (bare.arm, bare.cell_id, bare.kroker_commit, bare.tree_dirty) == (
        None,
        None,
        None,
        None,
    )
