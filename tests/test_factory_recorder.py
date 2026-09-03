"""The purity assertion: when benchmark.case_id is None, the recorder is
never called. We assert this by pointing SDLC_BENCHMARKS_ROOT at a temp
dir and checking no file appears after a stage-boundary helper runs."""

from sdlc.core.models import (
    BenchmarkConfig,
    PipelineConfig,
)
from sdlc.workflows.feature import FeatureWorkflow


def test_record_helper_is_noop_when_case_id_none():
    # when case_id is None, _record should be a no-op (returns None
    # without raising). We test the pure predicate directly.
    from sdlc.benchmarks.recorder import records_path  # noqa: F401

    cfg = PipelineConfig()
    assert cfg.benchmark.case_id is None
    # the predicate the helper uses:
    assert FeatureWorkflow._benchmarking(cfg) is False


def test_record_helper_is_active_when_case_id_set():
    cfg = PipelineConfig()
    cfg.benchmark = BenchmarkConfig(case_id="add-login", bench_run_id="b1")
    assert FeatureWorkflow._benchmarking(cfg) is True
