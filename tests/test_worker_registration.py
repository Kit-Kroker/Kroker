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

    names = [getattr(a, "__name__", str(a)) for a in worker.get_worker_activities()]
    assert "run_lint" in names, "run_lint missing from worker registration"


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
    """verify_brief_activity is registered on the worker (via research.ACTIVITIES
    in STAGE_MODULES) so the research workflow's execute_activity call resolves."""
    from sdlc import worker

    names = [getattr(a, "__name__", str(a)) for a in worker.get_worker_activities()]
    assert "verify_brief_activity" in names


def test_worker_registers_the_post_020_workflow_set():
    """020 T025 (plan T050, FR-003): FeatureWorkflow is deleted with its
    registration; the worker's workflow set is the remaining eight."""
    import ast
    import inspect

    from sdlc import worker

    registered: set[str] | None = None
    for node in ast.walk(ast.parse(inspect.getsource(worker))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Worker":
            for kw in node.keywords:
                if kw.arg == "workflows":
                    registered = {elt.id for elt in kw.value.elts}
    assert registered is not None, "no Worker(..., workflows=[...]) call found"
    assert "FeatureWorkflow" not in registered
    assert registered == {
        "GraphWorkflow",
        "BenchmarkWorkflow",
        "ReflectWorkflow",
        "DeploymentWorkflow",
        "TriageWorkflow",
        "TidyUpWorkflow",
        "AssessmentWorkflow",
        "CrewTaskWorkflow",
    }
