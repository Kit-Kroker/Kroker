from __future__ import annotations

import inspect

from sdlc.benchmarks import workflow as benchmark_workflow
from sdlc.workflows import tidyup


def test_parents_start_pipeline_children_through_the_patched_helper():
    for module in (tidyup, benchmark_workflow):
        src = inspect.getsource(module)
        assert "execute_pipeline_child(" in src, module.__name__
        assert "FeatureWorkflow.run" not in src, module.__name__
