from sdlc.models import BenchmarkConfig, PipelineConfig


def test_default_pipeline_config_has_no_benchmark():
    cfg = PipelineConfig()
    assert cfg.benchmark.case_id is None
    assert cfg.benchmark.bench_run_id is None


def test_pipeline_config_accepts_benchmark_fields():
    cfg = PipelineConfig()
    cfg.benchmark = BenchmarkConfig(case_id="add-login",
                                    bench_run_id="b1")
    assert cfg.benchmark.case_id == "add-login"


def test_pipeline_config_serializes_with_benchmark():
    cfg = PipelineConfig()
    js = cfg.model_dump_json()
    assert "benchmark" in js
    # round-trip preserves defaults
    cfg2 = PipelineConfig.model_validate_json(js)
    assert cfg2.benchmark.case_id is None
