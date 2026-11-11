"""FR-112: the constitution config flag and the graph-presence overlay.

Off by default everywhere: `ConstitutionConfig()` ships inert bounds,
`PipelineConfig()` ships `constitution_enabled=False`, and the flag is set
only by graph presence -- a `constitution`-typed node in the run's graph
turns it on, exactly the way `research_enabled` follows a research node.
A cfg that says enabled is overridden by the graph, never the reverse.
"""

from __future__ import annotations

import pytest

from sdlc.core.models import ConstitutionConfig, PipelineConfig
from sdlc.graph import NODE_TYPES, from_yaml
from sdlc.workflows.graph_catalog import GRAPHS_DIR
from sdlc.workflows.graph_nodes.base import graph_has_constitution, project_cfg

# default-constitution is opt-in: NOT in graph_catalog.SHIPPED_NAMES until a
# later task wires selection, so this module loads both graphs by path.


def _graph(name: str):
    return from_yaml((GRAPHS_DIR / f"{name}.graph.yaml").read_text(encoding="utf-8"))


def test_constitution_config_defaults():
    cfg = ConstitutionConfig()
    assert (cfg.enabled, cfg.max_principles, cfg.max_requests) == (False, 12, 6)


def test_pipeline_config_constitution_defaults_off():
    assert PipelineConfig().constitution_enabled is False


@pytest.mark.parametrize(
    ("graph_name", "in_graph"),
    [("default", False), ("default-constitution", True)],
)
def test_constitution_presence_detection(graph_name, in_graph):
    assert graph_has_constitution(_graph(graph_name)) is in_graph


@pytest.mark.parametrize(
    ("graph_name", "expected"),
    [("default", False), ("default-constitution", True)],
)
def test_project_cfg_constitution_enabled_follows_the_graph(graph_name, expected):
    """Graph presence wins over the cfg's own flag (mirrors research)."""
    graph = _graph(graph_name)
    node = next(n for n in graph.nodes if n.id == "intake")
    out = project_cfg(
        PipelineConfig(constitution_enabled=True),
        node,
        NODE_TYPES["constitution"],
        research_in_graph=False,
        constitution_in_graph=graph_has_constitution(graph),
    )
    assert out.constitution_enabled is expected
