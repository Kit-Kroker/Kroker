"""Chaos + edge-case characterization for E-74 Task 14 (shipped graphs, catalog).

RED until ``sdlc.workflows.graph_catalog`` exists: every test imports the
catalog names IN-FUNCTION, so the file still collects and each test fails on
its own with ``ModuleNotFoundError: No module named
'sdlc.workflows.graph_catalog'`` -- the plan's own expected RED reason.
(Existing names -- core models, ``sdlc.graph``, ``validate``, fixtures,
canned fakes -- import at module level.)

Pins the edge behaviour the task specifies:
- GraphStartError: a ValueError carrying .problems (joined with "; " into the
  message); build_run_input rejects max_gate_rounds < 1 (0 and negatives)
  with the exact single-problem list, reports missing/invalid roles as the
  validator's formatted "code: message" rows, and refuses an unexecutable
  graph (a type without a handler) as a no_handler row
- select_graph: research_enabled needs the research role IN the explicit
  registry mapping, else the plain default; a seeded work wins over
  everything (even research_enabled, even a truthy non-SeededWork junk
  object -- the contract is `seeded is not None`); the seeded graph carries
  no pre-code stages at all; unknown SHIPPED names raise KeyError
- template_revise_bounds: strictly the two PRE_CODE_REVISE edges, only when
  they already carry a bound (a None stays None), non-revise bounds are
  untouched, bound < 1 is templated as-is (the plan defines no guard), a
  graph without revise edges compares equal to its input but is a fresh
  object, and the source graph is never modified
- executable: empty handler_types flags EVERY node no_handler; gate.research
  is not_executable; a gate node id colliding with a handler-internal gate
  is gate_name_collision; duplicate node ids are a VALIDATE problem
  (duplicate_node_id), not an executable one
- immutability: SHIPPED / NOT_EXECUTABLE are frozen mappings (TypeError on
  writes), shipped graphs are frozen models (ValidationError on mutation),
  and resolved_roles hands out stripped copies isolated from cfg.roles

Scope notes (environment + contract):
- registry_roles=None / handler_types=None lazily import the agents REGISTRY
  / HANDLERS; this environment fail-closes that import without EXA_API_KEY
  (RegistryError), and the module contract itself declares the defaults
  workflow-unsafe -- so every test passes the mappings explicitly.
- handler_types=None also cannot resolve until HANDLERS is assembled
  (Task 18); the empty-iterable case pins the fan-out instead.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.core.models import PipelineConfig, RoleConfig
from sdlc.graph import NODE_TYPES, PipelineGraph
from sdlc.graph.validate import validate
from sdlc.workflows.models import SeededWork
from tests.fakes.canned import ARCH, PLAN, e2e_config, greenfield_idea
from tests.graph.fixtures.registries import node, roles

SEEDED_TYPES = {"intake", "seed.spec", "seed.plan", "code", "analyze", "merge", "deploy"}
PRE_CODE_REVISE = {("architecture", "revise"), ("plan", "revise")}


def _handler_types():
    from sdlc.workflows.graph_catalog import NOT_EXECUTABLE

    return [t for t in NODE_TYPES if t not in NOT_EXECUTABLE]


def _bounds(graph):
    """max_traversals keyed by (source, source_port), including explicit 0."""
    return {
        (e.source, e.source_port): e.max_traversals
        for e in graph.edges
        if e.max_traversals is not None
    }


# ---- GraphStartError / build_run_input ---------------------------------------


def test_graph_start_error_is_a_value_error_carrying_problems():
    from sdlc.workflows.graph_catalog import GraphStartError

    assert issubclass(GraphStartError, ValueError)
    err = GraphStartError(["first problem", "second problem"])
    assert err.problems == ["first problem", "second problem"]
    assert str(err) == "first problem; second problem"


@pytest.mark.parametrize("rounds", [0, -1], ids=["zero", "negative"])
def test_build_run_input_rejects_non_positive_gate_rounds(rounds):
    from sdlc.workflows.graph_catalog import GraphStartError, build_run_input

    cfg = PipelineConfig(max_gate_rounds=rounds)

    with pytest.raises(GraphStartError, match="max_gate_rounds") as err:
        build_run_input(
            greenfield_idea(), cfg, registry_roles=roles(), handler_types=_handler_types()
        )

    assert err.value.problems == [f"max_gate_rounds must be >= 1 on the graph path (got {rounds})"]


def test_build_run_input_reports_missing_roles_as_informative_problems():
    from sdlc.workflows.graph_catalog import GraphStartError, build_run_input

    # default cfg roles are only dev/test/devops: the default graph's roled
    # stages (architect, clarify, planner) and the ADR-6 reviewer check fail
    with pytest.raises(GraphStartError) as err:
        build_run_input(
            greenfield_idea(),
            PipelineConfig(),
            registry_roles={},
            handler_types=_handler_types(),
        )

    assert err.value.problems == [
        "adr6_violation: ADR-6 check requires both 'dev' and 'reviewer' models",
        "role_not_in_registry: 'architect' needs role 'architect', which the loaded registry lacks",
        "role_not_in_registry: 'clarify' needs role 'clarify', which the loaded registry lacks",
        "role_not_in_registry: 'plan' needs role 'planner', which the loaded registry lacks",
    ]


def test_build_run_input_rejects_an_unexecutable_graph():
    from sdlc.workflows.graph_catalog import GraphStartError, build_run_input

    missing_deploy = [t for t in _handler_types() if t != "deploy"]

    with pytest.raises(GraphStartError) as err:
        build_run_input(
            greenfield_idea(),
            e2e_config(),
            registry_roles=roles(),
            handler_types=missing_deploy,
        )

    # validate is clean on roles(): the ONLY problem is the missing handler
    assert err.value.problems == ["no_handler: no handler for node type 'deploy'"]


def test_build_run_input_templates_bounds_and_keeps_cfg_identity():
    from sdlc.workflows.graph_catalog import build_run_input, resolved_roles

    cfg = e2e_config()
    cfg.max_gate_rounds = 3

    inp = build_run_input(
        greenfield_idea(), cfg, registry_roles=roles(), handler_types=_handler_types()
    )

    assert {e.max_traversals for e in inp.graph.edges if e.max_traversals} == {3}
    assert inp.cfg is cfg  # no copy: the run reads the caller's live config
    assert inp.seeded is None
    assert inp.roles == resolved_roles(cfg, roles())
    assert list(inp.roles) == sorted(inp.roles)
    assert all(rc.instructions is None and rc.tool_files == [] for rc in inp.roles.values())


def test_build_run_input_prefers_seeded_over_research_enabled():
    from sdlc.workflows.graph_catalog import build_run_input

    cfg = e2e_config()
    cfg.research_enabled = True
    seeded = SeededWork(arch=ARCH, plan=PLAN)

    inp = build_run_input(
        greenfield_idea(), cfg, seeded, registry_roles=roles(), handler_types=_handler_types()
    )

    assert inp.seeded is seeded
    assert {n.type for n in inp.graph.nodes} == SEEDED_TYPES  # skips pre-code entirely


# ---- select_graph -------------------------------------------------------------


def test_select_graph_falls_back_when_the_research_role_is_absent():
    from sdlc.workflows.graph_catalog import SHIPPED, select_graph

    assert select_graph(PipelineConfig(), None, roles()) is SHIPPED["default"]
    assert (
        select_graph(PipelineConfig(research_enabled=True), None, roles())
        is SHIPPED["default-research"]
    )
    # research_enabled without a research role in the registry: plain default
    assert (
        select_graph(PipelineConfig(research_enabled=True), None, roles(research=None))
        is SHIPPED["default"]
    )


def test_select_graph_seeded_wins_over_research_and_over_junk():
    from sdlc.workflows.graph_catalog import SHIPPED, select_graph

    seeded = SeededWork(arch=ARCH, plan=PLAN)
    assert select_graph(PipelineConfig(research_enabled=True), seeded, roles()) is SHIPPED["seeded"]
    # the contract is `seeded is not None`: any truthy object selects seeded
    assert select_graph(PipelineConfig(), object(), roles()) is SHIPPED["seeded"]


def test_seeded_graph_carries_no_pre_code_stages():
    from sdlc.workflows.graph_catalog import SHIPPED

    assert {n.type for n in SHIPPED["seeded"].nodes} == SEEDED_TYPES
    assert not {n.type for n in SHIPPED["seeded"].nodes} & {
        "research",
        "clarify",
        "architect",
        "plan",
        "gate.architecture",
        "gate.plan",
    }


def test_shipped_lookup_rejects_unknown_names_and_pins_the_catalog():
    from sdlc.workflows.graph_catalog import SHIPPED

    assert set(SHIPPED) == {"default", "default-research", "seeded"}
    with pytest.raises(KeyError):
        SHIPPED["nope"]


# ---- template_revise_bounds ---------------------------------------------------


def test_template_revise_bounds_hit_only_the_pre_code_revise_edges():
    from sdlc.workflows.graph_catalog import SHIPPED, template_revise_bounds

    out = template_revise_bounds(SHIPPED["default"], 4)

    assert _bounds(out) == {("architecture", "revise"): 4, ("plan", "revise"): 4}
    # the source graph is untouched: still the shipped 2-traversal edges
    assert _bounds(SHIPPED["default"]) == {
        ("architecture", "revise"): 2,
        ("plan", "revise"): 2,
    }


def test_template_revise_bounds_skip_unbounded_revise_edges_and_foreign_bounds():
    from sdlc.workflows.graph_catalog import template_revise_bounds

    graph = PipelineGraph(
        schema_version=1,
        nodes=[
            {"id": "architect", "type": "architect"},
            {"id": "architecture", "type": "gate.architecture"},
            {"id": "clarify", "type": "clarify"},
        ],
        edges=[
            # a PRE_CODE_REVISE slot WITHOUT a bound: must stay unbounded
            {
                "source": "architecture",
                "source_port": "revise",
                "target": "architect",
                "target_port": "guidance",
            },
            # a bound on a NON-revise edge: must survive untouched
            {
                "source": "clarify",
                "source_port": "requirements",
                "target": "architect",
                "target_port": "requirements",
                "max_traversals": 7,
            },
        ],
    )

    out = template_revise_bounds(graph, 9)

    assert _bounds(out) == {("clarify", "requirements"): 7}
    assert next(e for e in out.edges if e.source == "architecture").max_traversals is None


@pytest.mark.parametrize("bound", [0, -3], ids=["zero", "negative"])
def test_template_revise_bounds_templates_sub_one_bounds_as_is(bound):
    # the plan defines no guard: the bound flows into the two edges verbatim
    from sdlc.workflows.graph_catalog import SHIPPED, template_revise_bounds

    out = template_revise_bounds(SHIPPED["default"], bound)

    assert _bounds(out) == {("architecture", "revise"): bound, ("plan", "revise"): bound}


def test_template_revise_bounds_on_a_graph_without_revise_edges_is_a_fresh_equal_copy():
    from sdlc.workflows.graph_catalog import SHIPPED, template_revise_bounds

    out = template_revise_bounds(SHIPPED["seeded"], 4)

    assert out == SHIPPED["seeded"]
    assert out is not SHIPPED["seeded"]  # a copy: tampering cannot leak back


# ---- executable ---------------------------------------------------------------


def test_executable_with_empty_handler_types_flags_every_node():
    from sdlc.workflows.graph_catalog import SHIPPED, executable

    problems = executable(SHIPPED["default"], [])

    assert [(p.code, p.node) for p in problems] == [
        ("no_handler", node_id) for node_id in sorted(n.id for n in SHIPPED["default"].nodes)
    ]


def test_executable_flags_not_executable_types():
    from sdlc.workflows.graph_catalog import NOT_EXECUTABLE, SHIPPED, executable

    assert set(NOT_EXECUTABLE) == {"gate.research"}
    with_research_gate = PipelineGraph(
        schema_version=1,
        nodes=[*SHIPPED["default"].nodes, node("research", "gate.research")],
        edges=list(SHIPPED["default"].edges),
    )

    codes = {(p.code, p.node) for p in executable(with_research_gate, _handler_types())}

    assert ("not_executable", "research") in codes


def test_executable_flags_gate_name_collisions():
    from sdlc.workflows.graph_catalog import executable

    clash = PipelineGraph(
        schema_version=1,
        nodes=[node("researcher", "research"), node("research", "gate.architecture")],
        edges=[],
    )

    codes = {(p.code, p.node) for p in executable(clash, _handler_types())}

    assert ("gate_name_collision", "research") in codes


def test_duplicate_node_ids_are_a_validate_problem_not_an_executable_one():
    from sdlc.workflows.graph_catalog import executable

    dup = PipelineGraph(
        schema_version=1,
        nodes=[node("a", "intake"), node("a", "context")],
        edges=[],
    )

    assert executable(dup, _handler_types()) == ()  # executable does not see it
    codes = {p.code for p in validate(dup, NODE_TYPES, roles={}).problems}
    assert "duplicate_node_id" in codes


# ---- resolved_roles -----------------------------------------------------------


def test_resolved_roles_run_overrides_registry_and_strips_everywhere():
    from sdlc.workflows.graph_catalog import resolved_roles

    reg = {"architect": RoleConfig(kind="proposer", model="reg", instructions="prompt text")}
    cfg = PipelineConfig()
    cfg.roles["architect"] = RoleConfig(
        kind="proposer", model="run", instructions="cfg prompt", tool_files=["n.md"]
    )

    out = resolved_roles(cfg, reg)

    assert out["architect"].model == "run"  # run-level override wins
    assert list(out) == sorted(out)
    assert all(rc.instructions is None and rc.tool_files == [] for rc in out.values())


def test_resolved_roles_hand_out_copies_isolated_from_cfg():
    from sdlc.workflows.graph_catalog import resolved_roles

    cfg = PipelineConfig()

    out = resolved_roles(cfg, {})

    assert out["dev"] is not cfg.roles["dev"]  # a copy, not the live entry
    again = resolved_roles(cfg, {})
    assert again["dev"] is not out["dev"]  # fresh copies on every call


# ---- immutability & isolation --------------------------------------------------


def test_shipped_and_not_executable_are_frozen_mappings():
    from sdlc.workflows.graph_catalog import NOT_EXECUTABLE, SHIPPED

    with pytest.raises(TypeError):
        SHIPPED["default"] = object()
    with pytest.raises(TypeError):
        SHIPPED["extra"] = object()
    with pytest.raises(TypeError):
        NOT_EXECUTABLE["gate.plan"] = "nope"


def test_shipped_graphs_are_frozen_models():
    from sdlc.workflows.graph_catalog import SHIPPED

    with pytest.raises(ValidationError):
        SHIPPED["default"].nodes[0].id = "tampered"
    with pytest.raises(ValidationError):
        SHIPPED["default"].edges[0].max_traversals = 99


def test_tampering_with_a_templated_graph_never_pollutes_the_shipped_ones():
    from sdlc.workflows.graph_catalog import SHIPPED, template_revise_bounds

    for name in SHIPPED:
        assert template_revise_bounds(SHIPPED[name], 9) is not SHIPPED[name]

    template_revise_bounds(SHIPPED["default"], 9)
    # the shipped graph still carries the YAML's own 2-traversal bounds
    assert PRE_CODE_REVISE <= set(_bounds(SHIPPED["default"]))
    assert _bounds(SHIPPED["default"])["architecture", "revise"] == 2
    assert _bounds(SHIPPED["default"])["plan", "revise"] == 2
