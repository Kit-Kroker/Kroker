"""E-74 §5.8, §7.1: shipped graphs, selection, templating, executable."""

from __future__ import annotations

import pytest

from sdlc.core.models import PipelineConfig, RoleConfig
from sdlc.graph import NODE_TYPES, PipelineGraph, validate
from sdlc.workflows.graph_catalog import (
    NOT_EXECUTABLE,
    SHIPPED,
    GraphStartError,
    build_run_input,
    executable,
    resolved_roles,
    select_graph,
    template_revise_bounds,
)
from sdlc.workflows.graph_nodes.base import graph_has_research, project_cfg
from sdlc.workflows.models import SeededWork
from tests.fakes.canned import ARCH, PLAN, e2e_config, greenfield_idea
from tests.graph.fixtures.registries import roles

ALL_TYPES = [t for t in NODE_TYPES if t not in NOT_EXECUTABLE]


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_shipped_graphs_are_legal_and_executable(name):
    graph = SHIPPED[name]
    assert validate(graph, roles=roles()).problems == ()
    assert executable(graph, ALL_TYPES) == ()


def test_research_graph_is_the_only_one_with_research():
    assert [n for n in sorted(SHIPPED) if graph_has_research(SHIPPED[n])] == ["default-research"]


def test_select_graph():
    reg = roles()
    assert select_graph(PipelineConfig(), None, reg) is SHIPPED["default"]
    assert (
        select_graph(PipelineConfig(research_enabled=True), None, reg)
        is SHIPPED["default-research"]
    )
    no_research = roles(research=None)
    assert (
        select_graph(PipelineConfig(research_enabled=True), None, no_research) is SHIPPED["default"]
    )
    seeded = SeededWork(arch=ARCH, plan=PLAN)
    assert select_graph(PipelineConfig(research_enabled=True), seeded, reg) is SHIPPED["seeded"]


def test_template_revise_bounds_sets_only_pre_code_revise_edges():
    graph = template_revise_bounds(SHIPPED["default"], 4)
    bounded = {(e.source, e.source_port): e.max_traversals for e in graph.edges if e.max_traversals}
    assert bounded == {("architecture", "revise"): 4, ("plan", "revise"): 4}
    assert template_revise_bounds(SHIPPED["seeded"], 4) == SHIPPED["seeded"]


def test_resolved_roles_run_override_wins_and_loader_fields_are_stripped():
    reg = {"architect": RoleConfig(kind="proposer", model="reg", instructions="prompt text")}
    cfg = PipelineConfig()
    cfg.roles["architect"] = RoleConfig(kind="proposer", model="run")
    out = resolved_roles(cfg, reg)
    assert out["architect"].model == "run"
    assert all(rc.instructions is None and rc.tool_files == [] for rc in out.values())
    assert list(out) == sorted(out)


def test_executable_rows():
    from tests.graph.fixtures.registries import node

    base = SHIPPED["default"]
    no_handler = executable(base, [t for t in ALL_TYPES if t != "deploy"])
    assert [(p.code, p.node) for p in no_handler] == [("no_handler", "deploy")]
    with_research_gate = PipelineGraph(
        schema_version=1,
        nodes=[*base.nodes, node("research", "gate.research")],
        edges=list(base.edges),
    )
    codes = {(p.code, p.node) for p in executable(with_research_gate, ALL_TYPES)}
    assert ("not_executable", "research") in codes


def test_executable_flags_a_gate_named_like_a_handler_internal_gate():
    from tests.graph.fixtures.registries import node

    # A gate-kind node with id "research" beside a composite research node:
    # both would mint gate_key("research", k) (advisor Q1 P7).
    clash = PipelineGraph(
        schema_version=1,
        nodes=[node("researcher", "research"), node("research", "gate.architecture")],
        edges=[],
    )
    codes = {(p.code, p.node) for p in executable(clash, ALL_TYPES)}
    assert ("gate_name_collision", "research") in codes


def test_build_run_input_templates_validates_and_strips():
    cfg = e2e_config()
    cfg.max_gate_rounds = 3
    inp = build_run_input(greenfield_idea(), cfg, registry_roles=roles(), handler_types=ALL_TYPES)
    assert {e.max_traversals for e in inp.graph.edges if e.max_traversals} == {3}
    assert inp.seeded is None and inp.cfg is cfg


def test_build_run_input_rejects_zero_gate_rounds():
    cfg = PipelineConfig(max_gate_rounds=0)
    with pytest.raises(GraphStartError, match="max_gate_rounds"):
        build_run_input(greenfield_idea(), cfg, registry_roles=roles(), handler_types=ALL_TYPES)


@pytest.mark.parametrize(
    ("name", "research"), [("default", False), ("default-research", True), ("seeded", False)]
)
def test_projection_over_shipped_graphs_is_identity(name, research):
    cfg = e2e_config()
    cfg.research_enabled = research
    graph = SHIPPED[name]
    for n in graph.nodes:
        assert (
            project_cfg(cfg, n, NODE_TYPES[n.type], research_in_graph=graph_has_research(graph))
            == cfg
        ), n.id
