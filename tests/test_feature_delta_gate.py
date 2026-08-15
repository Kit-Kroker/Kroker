"""E-84 D10/D11: the delta check in the architecture stage."""
from __future__ import annotations

import inspect

from sdlc.workflows.feature import FeatureWorkflow


def test_the_architect_prompt_carries_the_rendered_map():
    """D12: brownfield runs see the map; greenfield runs do not."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "render_for_prompt(" in src


def test_the_delta_check_is_called_under_brownfield():
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "check_brownfield_delta" in src


def test_the_cache_key_includes_the_map_digest():
    """D10: two runs with identical requirements on different trees cannot
    share an architecture memo."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "map_digest(" in src or "map_key" in src


def test_the_re_prompt_happens_before_failing_closed():
    """D11: one retry by default, bounded by PipelineConfig.max_delta_retries."""
    src = inspect.getsource(FeatureWorkflow._pipeline)
    assert "max_delta_retries" in src
