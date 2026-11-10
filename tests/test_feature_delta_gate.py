"""E-84 D10/D11: the delta check in the architecture stage."""

from __future__ import annotations


def _arch_src() -> str:
    """020 T026: the FeatureWorkflow half is gone with the workflow. The
    stage source carries the delta wiring; the graph side is scoped to
    precode's architect_node (qa-chaos F2: a whole-file concat would let
    the pins match anywhere in precode.py)."""
    import inspect as _inspect
    import pathlib

    import sdlc.workflows.graph_nodes.precode as _precode

    step = pathlib.Path("src/sdlc/stages/architecture/step.py").read_text(encoding="utf-8")
    arch_node = _inspect.getsource(_precode.architect_node)
    return step + "\n" + arch_node


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
