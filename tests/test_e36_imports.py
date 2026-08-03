def test_benchmark_and_calibration_modules_import():
    import sdlc.benchmarks.heatmap          # noqa: F401
    import sdlc.benchmarks.calibration      # noqa: F401
    from sdlc.benchmarks.report import (    # noqa: F401
        finalize_benchmark_report, write_heatmap, resolve_language_map)
    from sdlc.benchmarks.cli import dispatch_calibrate  # noqa: F401


def test_scoring_path_modules_import():
    import sdlc.benchmarks.evidence         # noqa: F401
    import sdlc.benchmarks.score            # noqa: F401
    from sdlc.benchmarks.cli import dispatch_score      # noqa: F401


def test_benchmark_cli_has_no_module_level_temporal_client():
    """`sdlc benchmark score` must run with no worker and no server, so the
    Temporal client import belongs inside _run_matrix, not at module scope."""
    import pathlib
    src = pathlib.Path("src/sdlc/benchmarks/cli.py").read_text(encoding="utf-8")
    head = src.split("def _run_matrix")[0]
    assert "from temporalio.client import Client" not in head
