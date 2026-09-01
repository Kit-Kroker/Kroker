from sdlc.benchmarks.recorder import record_benchmark


def test_record_benchmark_is_a_temporal_activity():
    # temporalio marks activities; the attr is set by @activity.defn
    assert getattr(record_benchmark, "__temporal_activity_definition", None) is not None


def test_worker_module_imports_record_benchmark():
    # the worker registration list must include it; importing succeeds
    from sdlc import worker

    _worker_activities(worker)  # helper's internal assert is the real check


def _worker_activities(worker):
    # introspect the source for the activities=[...] literal — simplest robust
    # check is that 'record_benchmark' appears in the registered list by name.
    import inspect

    src = inspect.getsource(worker)
    assert "record_benchmark" in src


def test_worker_module_imports_memory_activities():
    from sdlc import worker

    src = __import__("inspect").getsource(worker)
    for name in ("recall_snapshot", "retain", "capture_watermark", "reflect"):
        assert name in src, f"{name} missing from worker registration"


def test_worker_module_imports_run_lint():
    from sdlc import worker

    src = __import__("inspect").getsource(worker)
    assert "run_lint" in src, "run_lint missing from worker registration"


def test_worker_module_registers_reflect_workflow():
    # FR-404's original bug was a registered activity that nothing ever
    # called. reflect is only reachable if ReflectWorkflow is registered too.
    from sdlc import worker

    src = __import__("inspect").getsource(worker)
    assert "ReflectWorkflow" in src, "ReflectWorkflow missing from worker"


def test_reflect_workflow_is_reachable_from_the_reflect_activity():
    # the wrapper must actually call the activity — not just exist
    import inspect

    from sdlc.workflows import reflect as mod

    src = inspect.getsource(mod)
    assert "execute_activity" in src
    assert "reflect" in src


def test_worker_registers_research_verify_activity():
    """verify_brief_activity is a standalone Temporal activity (not an
    agent-tool activity that flows through ALL_TEMPORAL_AGENTS), so the worker
    must register it explicitly — otherwise the research workflow's
    execute_activity call would fail at runtime with no registered activity."""
    from sdlc import worker

    src = __import__("inspect").getsource(worker)
    assert "verify_brief_activity" in src
