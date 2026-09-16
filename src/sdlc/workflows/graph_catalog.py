"""Shipped graphs, graph selection and the executable check (E-74 spec §5.8, §7.1).

Graphs are read at import (a passthrough module -- the agents.roles REGISTRY
precedent), so parent workflows that start a GraphWorkflow child do no I/O.
`validate` answers "is this graph legal" for every consumer; `executable`
answers "can this worker run it today" and is applied by start sites and
GraphWorkflow.run only (skeptic F12).

WORKFLOW CALLERS must pass `registry_roles=` and `handler_types=` explicitly:
the defaults lazily import sdlc.agents.roles / graph_nodes, which is only safe
in client code, never inside the workflow sandbox (plan skeptic F8).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..core.models import IdeaBrief, PipelineConfig, RoleConfig
    from ..graph.io import from_yaml
    from ..graph.model import PipelineGraph
    from ..graph.node_types import NODE_TYPES
    from ..graph.validate import validate
    from .models import GraphRunInput, SeededWork

GRAPHS_DIR = Path(__file__).parent / "graphs"
SHIPPED_NAMES: tuple[str, ...] = ("default", "default-research", "seeded")


def _load(name: str) -> PipelineGraph:
    return from_yaml((GRAPHS_DIR / f"{name}.graph.yaml").read_text(encoding="utf-8"))


SHIPPED: Mapping[str, PipelineGraph] = MappingProxyType({n: _load(n) for n in SHIPPED_NAMES})

# The pre-code revise edges templated from cfg.max_gate_rounds (user ruling U4).
PRE_CODE_REVISE: tuple[tuple[str, str], ...] = (("architecture", "revise"), ("plan", "revise"))

NOT_EXECUTABLE: Mapping[str, str] = MappingProxyType(
    {
        "gate.research": (
            "the research refine loop is handler-internal until research-as-topology (E74-OQ-2)"
        )
    }
)
# node type -> the gate name its handler opens internally
HANDLER_INTERNAL_GATES: Mapping[str, str] = MappingProxyType({"research": "research"})


class ExecutableProblem(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: Literal["gate_name_collision", "no_handler", "not_executable"]
    node: str
    message: str


class GraphStartError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def executable(
    graph: PipelineGraph, handler_types: Iterable[str] | None = None
) -> tuple[ExecutableProblem, ...]:
    if handler_types is None:
        from .graph_nodes import HANDLERS

        handler_types = HANDLERS
    known = frozenset(handler_types)
    internal = frozenset(
        HANDLER_INTERNAL_GATES[n.type] for n in graph.nodes if n.type in HANDLER_INTERNAL_GATES
    )
    problems: list[ExecutableProblem] = []
    for n in graph.nodes:  # sorted by PipelineGraph's validator
        if n.type in NOT_EXECUTABLE:
            problems.append(
                ExecutableProblem(code="not_executable", node=n.id, message=NOT_EXECUTABLE[n.type])
            )
        elif n.type not in known:
            problems.append(
                ExecutableProblem(
                    code="no_handler", node=n.id, message=f"no handler for node type {n.type!r}"
                )
            )
        spec = NODE_TYPES.get(n.type)
        if spec is not None and spec.kind == "gate" and n.id in internal:
            problems.append(
                ExecutableProblem(
                    code="gate_name_collision",
                    node=n.id,
                    message=(
                        f"gate node id {n.id!r} collides with a handler-internal gate of the same"
                        " name"
                    ),
                )
            )
    return tuple(sorted(problems, key=lambda p: (p.code, p.node)))


def resolved_roles(
    cfg: PipelineConfig, registry_roles: Mapping[str, RoleConfig] | None = None
) -> dict[str, RoleConfig]:
    roles_map: Mapping[str, RoleConfig]
    if registry_roles is None:
        from ..agents.roles import REGISTRY

        roles_map = REGISTRY
    else:
        roles_map = registry_roles
    merged = {**roles_map, **cfg.roles}
    return {
        name: rc.model_copy(update={"instructions": None, "tool_files": []})
        for name, rc in sorted(merged.items())
    }


def select_graph(
    cfg: PipelineConfig,
    seeded: SeededWork | None,
    registry_roles: Mapping[str, RoleConfig] | None = None,
) -> PipelineGraph:
    if seeded is not None:
        return SHIPPED["seeded"]
    roles_map: Mapping[str, RoleConfig]
    if registry_roles is None:
        from ..agents.roles import REGISTRY

        roles_map = REGISTRY
    else:
        roles_map = registry_roles
    if cfg.research_enabled and "research" in roles_map:  # feature.py:535 guard
        return SHIPPED["default-research"]
    return SHIPPED["default"]


def template_revise_bounds(graph: PipelineGraph, bound: int) -> PipelineGraph:
    edges = [
        e.model_copy(update={"max_traversals": bound})
        if (e.source, e.source_port) in PRE_CODE_REVISE and e.max_traversals is not None
        else e
        for e in graph.edges
    ]
    return PipelineGraph(schema_version=graph.schema_version, nodes=list(graph.nodes), edges=edges)


def build_run_input(
    idea: IdeaBrief,
    cfg: PipelineConfig,
    seeded: SeededWork | None = None,
    *,
    registry_roles: Mapping[str, RoleConfig] | None = None,
    handler_types: Iterable[str] | None = None,
) -> GraphRunInput:
    if cfg.max_gate_rounds < 1:
        raise GraphStartError(
            [f"max_gate_rounds must be >= 1 on the graph path (got {cfg.max_gate_rounds})"]
        )
    graph = template_revise_bounds(select_graph(cfg, seeded, registry_roles), cfg.max_gate_rounds)
    roles = resolved_roles(cfg, registry_roles)
    report = validate(graph, NODE_TYPES, roles=roles)
    problems = [f"{p.code}: {p.message}" for p in report.problems]
    problems += [f"{p.code}: {p.message}" for p in executable(graph, handler_types)]
    if problems:
        raise GraphStartError(problems)
    return GraphRunInput(idea=idea, cfg=cfg, graph=graph, roles=roles, seeded=seeded)
