def test_benchmark_and_calibration_modules_import():
    import sdlc.benchmarks.heatmap          # noqa: F401
    import sdlc.benchmarks.calibration      # noqa: F401
    from sdlc.benchmarks.report import (    # noqa: F401
        finalize_benchmark_report, write_heatmap, resolve_language_map)
    from sdlc.benchmarks.cli import dispatch_calibrate  # noqa: F401
