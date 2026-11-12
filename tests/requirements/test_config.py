"""FR-113: the requirements config flag and the graph-presence overlay.

Off by default everywhere: `RequirementsConfig()` ships inert bounds,
`PipelineConfig()` ships `requirements_enabled=False`, and the flag is set
only by graph presence -- a `requirements`-typed node in the run's graph
turns it on, exactly the way `research_enabled` follows a research node.
A cfg that says enabled is overridden by the graph, never the reverse.
"""

from __future__ import annotations

import pytest

from sdlc.core.models import PipelineConfig, RequirementsConfig
from sdlc.graph import NODE_TYPES, from_yaml
from sdlc.workflows.graph_catalog import GRAPHS_DIR
from sdlc.workflows.graph_nodes.base import graph_has_requirements, project_cfg

# default-requirements ships on the graph path; this module loads both graphs
# by path to pin the overlay directly, independent of catalog wiring.


def _graph(name: str):
    return from_yaml((GRAPHS_DIR / f"{name}.graph.yaml").read_text(encoding="utf-8"))


def test_requirements_config_defaults():
    cfg = RequirementsConfig()
    assert (cfg.enabled, cfg.max_stories, cfg.max_requests) == (False, 8, 6)


def test_pipeline_config_requirements_defaults_off():
    cfg = PipelineConfig()
    assert cfg.requirements_enabled is False
    assert isinstance(cfg.requirements, RequirementsConfig)


@pytest.mark.parametrize(
    ("graph_name", "in_graph"),
    [("default", False), ("default-requirements", True)],
)
def test_requirements_presence_detection(graph_name, in_graph):
    assert graph_has_requirements(_graph(graph_name)) is in_graph


@pytest.mark.parametrize(
    ("graph_name", "expected"),
    [("default", False), ("default-requirements", True)],
)
def test_project_cfg_requirements_enabled_follows_the_graph(graph_name, expected):
    """Graph presence wins over the cfg's own flag (mirrors research)."""
    graph = _graph(graph_name)
    node = next(n for n in graph.nodes if n.id == "intake")
    out = project_cfg(
        PipelineConfig(requirements={"enabled": True}),
        node,
        NODE_TYPES["requirements"],
        research_in_graph=False,
        constitution_in_graph=False,
        requirements_in_graph=graph_has_requirements(graph),
    )
    assert out.requirements_enabled is expected


def test_project_cfg_requirements_in_graph_is_required():
    """FR-113: the kwarg has no default -- a caller missing it fails loudly
    (TypeError), never silently off. FR-112's defaulted bridge was the
    parked footgun this deliberately does not repeat."""
    graph = _graph("default")
    node = next(n for n in graph.nodes if n.id == "intake")
    with pytest.raises(TypeError):
        project_cfg(
            PipelineConfig(),
            node,
            NODE_TYPES["requirements"],
            research_in_graph=False,
            constitution_in_graph=False,
        )
