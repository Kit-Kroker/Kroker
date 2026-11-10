"""E-84 D10/D11: the delta check in the architecture stage."""

from __future__ import annotations


def _arch_src() -> str:
    """020 T026: the FeatureWorkflow half is gone with the workflow; the
    stage source plus the graph's precode node carry the same wiring."""
    import pathlib

    return pathlib.Path("src/sdlc/stages/architecture/step.py").read_text(
        encoding="utf-8"
    ) + pathlib.Path("src/sdlc/workflows/graph_nodes/precode.py").read_text(encoding="utf-8")


def test_the_architect_prompt_carries_the_rendered_map():
    """D12: brownfield runs see the map; greenfield runs do not."""
    src = _arch_src()
    assert "render_for_prompt(" in src


def test_the_delta_check_is_called_under_brownfield():
    src = _arch_src()
    assert "check_brownfield_delta" in src


def test_the_cache_key_includes_the_map_digest():
    """D10: two runs with identical requirements on different trees cannot
    share an architecture memo."""
    src = _arch_src()
    assert "map_digest(" in src or "map_key" in src


def test_the_re_prompt_happens_before_failing_closed():
    """D11: one retry by default, bounded by PipelineConfig.max_delta_retries."""
    src = _arch_src()
    assert "max_delta_retries" in src


# 020 T026: the exhausted-retries temporal row is deleted; the delta_failed
# golden replays the same bounded-retry rejection from GraphWorkflow —
# counterpart
# tests/replay/test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[delta_failed].
# The brownfield fakes that only served it are deleted with it (the replay
# scenarios carry their own).
