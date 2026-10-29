"""GET /api/graphs/shipped (018 T057; R-7, read-routes.md, data-model §2.2).

The v5 Graphs catalog: one card row per shipped graph, plus the one
PipelineConfig panel's three checks and five sections. Read-only
(read-routes rule 1) — the graphs come from SHIPPED, the checks read the
live registry and the shipped graphs' node types at request time, and the
sections come from resolved_roles, the proposer registry, the default
PipelineConfig and the containment policy. A value with no source is
None, which the panel renders as "not measured" (FR-045).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from ..agents import roles
from ..agents.loader import PROPOSER_ROLES, RegistryError, validate_run_roles
from ..core.models import PipelineConfig
from ..graph import NODE_TYPES
from ..harness.containment import load_policy
from ..workflows.graph_catalog import SHIPPED, SHIPPED_NAMES, resolved_roles


class ShippedGraphWire(BaseModel):
    name: str
    sha: str
    description: str | None = None
    when: str | None = None
    nodes: int
    gates: int
    edges: int


class ConfigCheckWire(BaseModel):
    name: Literal["validate_run_roles", "check_node_types", "containment"]
    state: Literal["pass", "fail", "off"]
    text: str


class ConfigRowWire(BaseModel):
    k: str
    v: str | None = None  # None renders `not measured`


class ConfigSectionWire(BaseModel):
    title: str
    note: str
    rows: list[ConfigRowWire]


class ShippedGraphsWire(BaseModel):
    graphs: list[ShippedGraphWire]
    checks: list[ConfigCheckWire]
    sections: list[ConfigSectionWire]


def _gate_count(graph: Any) -> int:
    return sum(
        1
        for n in graph.nodes
        if NODE_TYPES.get(n.type) is not None and NODE_TYPES[n.type].kind == "gate"
    )


def _graph_rows() -> list[ShippedGraphWire]:
    return [
        ShippedGraphWire(
            name=name,
            sha=SHIPPED[name].content_sha(),
            nodes=len(SHIPPED[name].nodes),
            gates=_gate_count(SHIPPED[name]),
            edges=len(SHIPPED[name].edges),
        )
        for name in SHIPPED_NAMES
    ]


def _roles_check() -> ConfigCheckWire:
    """ADR-6 over the LIVE registry, read at request time (V8: the
    same-weights note comes from check_adversary_model's copy). The text
    carries the registry's real dev and reviewer ids (CONSOLE-37)."""
    role_models = {name: cfg.model for name, cfg in roles.REGISTRY.items() if cfg.model is not None}
    try:
        validate_run_roles(role_models)
    except RegistryError as e:
        return ConfigCheckWire(name="validate_run_roles", state="fail", text=str(e))
    dev = role_models.get("dev", "unknown")
    reviewer = role_models.get("reviewer", "unknown")
    return ConfigCheckWire(
        name="validate_run_roles",
        state="pass",
        text=f"pass: dev {dev}, reviewer {reviewer} — families differ, the adversary "
        "is its own model (a shared model_id would read same weights)",
    )


def _node_types_check() -> ConfigCheckWire:
    unknown = sorted(
        {
            n.type
            for graph in SHIPPED.values()
            for n in graph.nodes
            if NODE_TYPES.get(n.type) is None
        }
    )
    if unknown:
        return ConfigCheckWire(
            name="check_node_types",
            state="fail",
            text=f"node types without a catalog entry: {', '.join(unknown)}",
        )
    return ConfigCheckWire(
        name="check_node_types",
        state="pass",
        text="every node type the shipped graphs use is served by the catalog",
    )


def _containment_check() -> ConfigCheckWire:
    try:
        policy = load_policy()
    except Exception as e:  # noqa: BLE001 - the panel shows the reason, never a 500
        return ConfigCheckWire(name="containment", state="fail", text=str(e))
    layers = sorted({rule.layer.value for rule in policy.rules})
    return ConfigCheckWire(
        name="containment",
        state="pass",
        text=f"containment policy v{policy.version}: {len(policy.rules)} rules "
        f"across {', '.join(layers)}",
    )


def _roles_section() -> ConfigSectionWire:
    cfg = PipelineConfig()
    rows = [
        ConfigRowWire(
            k=name,
            v=f"{(role.harness.value if role.harness is not None else 'api')} × {role.model}",
        )
        for name, role in sorted(resolved_roles(cfg).items())
    ]
    return ConfigSectionWire(
        title="Roles",
        note="the resolved role map for a default run (harness × model)",
        rows=rows,
    )


def _proposer_section() -> ConfigSectionWire:
    rows = [
        ConfigRowWire(k=name, v=roles.REGISTRY[name].model)
        for name in sorted(PROPOSER_ROLES)
        if name in roles.REGISTRY
    ]
    return ConfigSectionWire(
        title="Proposer roles",
        note="model ids of the crew's proposing roles",
        rows=rows,
    )


def _gates_section() -> ConfigSectionWire:
    gates = PipelineConfig().gates
    rows = [
        ConfigRowWire(
            k=name, v=f"{gate.policy} · threshold {gate.threshold} · on_timeout {gate.on_timeout}"
        )
        for name, gate in sorted(gates.items())
    ]
    return ConfigSectionWire(
        title="Gates",
        note="gate policy, threshold and on_timeout for a default run",
        rows=rows,
    )


#: Every scalar limit the panel shows; a field absent from PipelineConfig
#: (the per-gate schedule fields) renders None, never a fabricated number.
_LIMITS = (
    "max_fix_attempts",
    "max_tool_escalations",
    "max_gate_rounds",
    "gate_timeout_hours",
    "clarify_question_cap",
    "coverage_threshold",
    "run_budget_usd",
    "remind_after_hours",
    "escalate_after_hours",
)


def _limits_section() -> ConfigSectionWire:
    cfg = PipelineConfig()
    rows: list[ConfigRowWire] = []
    for key in _LIMITS:
        value = getattr(cfg, key, None)
        rows.append(ConfigRowWire(k=key, v=None if value is None else str(value)))
    return ConfigSectionWire(
        title="Limits",
        note="the default run's scalar limits; None reads not measured",
        rows=rows,
    )


def _arms_section() -> ConfigSectionWire:
    by_arm: dict[tuple[str, str], list[str]] = {}
    for name, role in sorted(resolved_roles(PipelineConfig()).items()):
        if role.harness is None or role.model is None:
            continue
        key = (role.harness.value, role.model)
        by_arm.setdefault(key, []).append(name)
    rows = [
        ConfigRowWire(k=f"{harness} × {model}", v=", ".join(sorted(members)))
        for (harness, model), members in sorted(by_arm.items())
    ]
    return ConfigSectionWire(
        title="Arms",
        note="the harness arms a default run executes on, and the roles each carries",
        rows=rows,
    )


def shipped_graphs() -> ShippedGraphsWire:
    return ShippedGraphsWire(
        graphs=_graph_rows(),
        checks=[_roles_check(), _node_types_check(), _containment_check()],
        sections=[
            _roles_section(),
            _proposer_section(),
            _gates_section(),
            _limits_section(),
            _arms_section(),
        ],
    )
