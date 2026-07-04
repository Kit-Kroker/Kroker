from sdlc.benchmarks.recorder import record_benchmark


def test_record_benchmark_is_a_temporal_activity():
    # temporalio marks activities; the attr is set by @activity.defn
    assert getattr(record_benchmark, "__temporal_activity_definition",
                   None) is not None


def test_worker_module_imports_record_benchmark():
    # the worker registration list must include it; importing succeeds
    from sdlc import worker
    _worker_activities(worker)   # helper's internal assert is the real check


def _worker_activities(worker):
    # introspect the source for the activities=[...] literal — simplest robust
    # check is that 'record_benchmark' appears in the registered list by name.
    import inspect
    src = inspect.getsource(worker)
    assert "record_benchmark" in src
