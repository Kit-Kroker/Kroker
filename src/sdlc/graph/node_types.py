"""The node-type registry (E-72, spec §6).

A STATIC Python registry (spec D1): node types bind 1:1 to Python handlers
(E-74's dispatch table) and to Python model classes, so a data file would be a
second source of truth. A graph stores only a node's `type` and port NAMES and
resolves them here, against the worker's code version.

The compatibility RULE lives here (`ports_compatible`); REJECTING a graph is
E-73's validate.py (spec D5, §9 traceability). Every function that reads the
registry takes it as a parameter so E-73 can test against fixture types.

Module-level imports stay within stdlib, pydantic, sdlc.graph.model and
sdlc.graph.payloads (spec §4). check_node_types() imports benchmarks and the
agents loader INSIDE its body: both sit on the benchmarks <-> stages import
cycle (.workspace/tasks/2026-09-12-b0-lazy-step-export-shadowing.md).
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .model import TYPE_PATTERN, NodePort
from .payloads import PAYLOAD_TYPES


class NodeTypeSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str = Field(pattern=TYPE_PATTERN)
    kind: Literal["stage", "gate"]
    role: str | None  # registry ROLE name (agents.loader.KNOWN_ROLES); None = role-less
    canonical_stage: str | None  # a CANONICAL_STAGES member; None records as "unknown"
    ports: tuple[NodePort, ...]  # declaration order kept for the palette
    # E-74 D12: whether the dispatcher runs the run-budget check after this
    # type's emission -- "continuing": on a port carrying forward edges;
    # "exiting": on any port carrying no back edge; "none": never.
    budget_after: Literal["none", "continuing", "exiting"] = "none"


def _in(
    name: str,
    payload: str | None,
    *,
    required: bool = True,
    multiplicity: Literal["one", "many"] = "one",
) -> NodePort:
    return NodePort(
        name=name, direction="in", payload=payload, required=required, multiplicity=multiplicity
    )


def _out(
    name: str, payload: str | None, *, terminal: Literal["rejected", "failed"] | None = None
) -> NodePort:
    return NodePort(name=name, direction="out", payload=payload, terminal=terminal)


def _fail() -> NodePort:
    return _out("fail", "NodeFailure", terminal="failed")  # E-74 D8: every stage type


def _reject() -> NodePort:
    return _out("reject", None, terminal="rejected")


def _halt() -> NodePort:
    return _out("halt", None, terminal="failed")  # domain failure carrying a result string


def _gate(
    type_: str,
    payload: str,
    canonical_stage: str,
    budget_after: Literal["none", "continuing", "exiting"],
) -> NodeTypeSpec:
    """A revise-loop gate: artifact:T -> approve:T | revise:GateDecision | reject (terminal)."""
    return NodeTypeSpec(
        type=type_,
        kind="gate",
        role=None,
        canonical_stage=canonical_stage,
        budget_after=budget_after,
        ports=(
            _in("artifact", payload),
            _out("approve", payload),
            _out("revise", "GateDecision"),
            _out("reject", None, terminal="rejected"),
        ),
    )


# The post-plan catalog (spec §6.4, E-74 §6). Type names equal STAGE_ROLES
# stage keys where one exists, so E-74 reaches PROMPT_SHAS[type] without a
# second mapping. No gate.clarify: clarify's HITL is a Q&A channel inside its
# handler (stages/clarify/step.py:199), not approve/revise/reject. A gate's
# canonical_stage is its producer's stage (FR-1206).
_CATALOG: tuple[NodeTypeSpec, ...] = (
    # ---- pre-code (E-72 seed; E-74 adds reject/fail/brownfield ports) ----
    NodeTypeSpec(
        type="intake",
        kind="stage",
        role=None,
        canonical_stage="intake",
        # `ok` is the greenfield path (name kept from E-72 so stored graphs keep their sha).
        ports=(_out("ok", None), _out("brownfield", None), _reject(), _fail()),
    ),
    NodeTypeSpec(
        type="context",
        kind="stage",
        role=None,
        canonical_stage="context",
        ports=(_in("trigger", None), _out("map", "CodebaseMap"), _reject(), _fail()),
    ),
    NodeTypeSpec(
        type="research",
        kind="stage",
        role="research",
        canonical_stage="research",
        budget_after="continuing",
        ports=(
            _in("trigger", None, required=False),
            _in("guidance", "GateDecision", required=False),
            # Ordering only (brownfield runs map context before research, feature.py:524-535).
            _in("codebase_map", "CodebaseMap", required=False),
            _out("brief", "ResearchBrief"),
            _reject(),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="clarify",
        kind="stage",
        role="clarify",
        canonical_stage="clarify",
        budget_after="continuing",
        ports=(
            _in("trigger", None, required=False),
            _in("codebase_map", "CodebaseMap", required=False),
            _in("research", "ResearchBrief", required=False),
            _out("requirements", "ClarifiedRequirements"),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="architect",
        kind="stage",
        role="architect",
        canonical_stage="architecture",
        ports=(
            _in("requirements", "ClarifiedRequirements"),
            _in("codebase_map", "CodebaseMap", required=False),
            _in("guidance", "GateDecision", required=False),
            _out("spec", "ArchitectureSpec"),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="plan",
        kind="stage",
        role="planner",
        canonical_stage="planning",
        ports=(
            _in("spec", "ArchitectureSpec"),
            _in("requirements", "ClarifiedRequirements", required=False),
            _in("guidance", "GateDecision", required=False),
            _out("plan", "ImplementationPlan"),
            _fail(),
        ),
    ),
    _gate("gate.research", "ResearchBrief", "research", "none"),
    _gate("gate.architecture", "ArchitectureSpec", "architecture", "exiting"),
    _gate("gate.plan", "ImplementationPlan", "planning", "exiting"),
    # ---- post-plan (E-74 §6; coarse `code` per U1) ----
    NodeTypeSpec(
        type="plan_check",
        kind="stage",
        role=None,
        canonical_stage="planning",
        ports=(
            _in("plan", "ImplementationPlan"),
            _out("ok", "ImplementationPlan"),
            _halt(),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="seed.spec",
        kind="stage",
        role=None,
        canonical_stage="architecture",
        ports=(_in("trigger", None, required=False), _out("spec", "ArchitectureSpec"), _fail()),
    ),
    NodeTypeSpec(
        type="seed.plan",
        kind="stage",
        role=None,
        canonical_stage="planning",
        ports=(_in("trigger", None, required=False), _out("plan", "ImplementationPlan"), _fail()),
    ),
    NodeTypeSpec(
        type="code",
        kind="stage",
        role=None,
        canonical_stage="code",
        ports=(_in("plan", "ImplementationPlan"), _out("results", "BuildResult"), _halt(), _fail()),
    ),
    NodeTypeSpec(
        type="analyze",
        kind="stage",
        role=None,
        canonical_stage="analyze",
        budget_after="continuing",
        ports=(
            _in("results", "BuildResult"),
            _in("plan", "ImplementationPlan"),
            _out("analysis", "AnalyzeResult"),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="merge",
        kind="stage",
        role=None,
        canonical_stage="quality_gate",
        ports=(
            _in("results", "BuildResult"),
            _in("plan", "ImplementationPlan"),
            _in("spec", "ArchitectureSpec"),
            _in("analysis", "AnalyzeResult"),
            _out("pr", "PullRequest"),
            _reject(),
            _fail(),
        ),
    ),
    NodeTypeSpec(
        type="deploy",
        kind="stage",
        role=None,
        canonical_stage="deploy",
        ports=(_in("pr", "PullRequest"), _out("done", None), _fail()),
    ),
)

NODE_TYPES: Mapping[str, NodeTypeSpec] = MappingProxyType({s.type: s for s in _CATALOG})

UNKNOWN_STAGE = "unknown"
"""FR-1206's recorded-but-unmapped stage (E-77 R2): a node whose type is
unregistered or declares canonical_stage=None attributes here. Never a
CANONICAL_STAGES member; declaring it on a spec is an authoring error that
check_node_types() reports."""


def resolve_stage(node_type: str, registry: Mapping[str, NodeTypeSpec]) -> str:
    """The single stage resolver (E-77 FR-003/006): the declared
    canonical_stage of a registered type, else UNKNOWN_STAGE. Never raises:
    an absent mapping records as "unknown", it is not a validation error."""
    spec = registry.get(node_type)
    if spec is None or spec.canonical_stage is None:
        return UNKNOWN_STAGE
    return spec.canonical_stage


def find_port(spec: NodeTypeSpec, name: str, direction: Literal["in", "out"]) -> NodePort | None:
    return next((p for p in spec.ports if p.name == name and p.direction == direction), None)


def ports_compatible(out_port: NodePort, in_port: NodePort) -> bool:
    """The FR-1201 compatibility rule (spec D4): out -> in, exact nominal
    payload equality. None == None for signal ports; a named payload never
    connects to a signal port. No subtyping, no Any, no type variables."""
    return (
        out_port.direction == "out"
        and in_port.direction == "in"
        and out_port.payload == in_port.payload
    )


def _resolve_payload(name: str) -> str | None:
    """None when `name` resolves cleanly, else the problem."""
    target = PAYLOAD_TYPES.get(name)
    if target is None:
        return f"payload {name!r} is not in PAYLOAD_TYPES"
    module_name, _, class_name = target.partition(":")
    try:
        cls = getattr(importlib.import_module(module_name), class_name)
    except Exception as exc:  # noqa: BLE001 -- E-74: boot must report, never crash (inbox E-72 minor 2)
        return f"payload {name!r} does not resolve ({target}): {type(exc).__name__}: {exc}"
    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        return f"payload {name!r} ({target}) is not a pydantic model"
    if cls.__name__ != name:
        return f"payload {name!r} resolves to class {cls.__name__!r}"
    return None


def _gate_shape_problems(spec: NodeTypeSpec) -> list[str]:
    problems: list[str] = []
    if spec.role is not None:
        problems.append("gate type must be role-less")
    ins = [p for p in spec.ports if p.direction == "in"]
    outs = {p.name: p for p in spec.ports if p.direction == "out"}
    if len(ins) != 1 or ins[0].name != "artifact" or ins[0].payload is None:
        problems.append("gate type must have exactly one in-port 'artifact' with a payload")
        return problems
    artifact = ins[0].payload
    approve, reject, revise = outs.get("approve"), outs.get("reject"), outs.get("revise")
    if approve is None or approve.payload != artifact:
        problems.append(f"gate out-port 'approve' must carry the artifact payload {artifact!r}")
    if reject is None or reject.payload is not None:
        problems.append("gate out-port 'reject' must be a signal port")
    elif reject.terminal != "rejected":
        problems.append("gate out-port 'reject' must be terminal='rejected'")
    if revise is not None and revise.payload != "GateDecision":
        problems.append("gate out-port 'revise' must carry 'GateDecision'")
    extra = sorted(set(outs) - {"approve", "reject", "revise"})
    if extra:
        problems.append(f"gate type has unexpected out-port(s): {', '.join(extra)}")
    return problems


def check_node_types(
    registry: Mapping[str, NodeTypeSpec] = NODE_TYPES, *, require_mapped: bool = True
) -> list[str]:
    """Registry self-check (spec §6.3). Returns problems SORTED; [] = healthy.
    E-72 runs it from a unit test; E-74 wires it into worker boot.
    E-77 FR-001: require_mapped flags a type without a canonical_stage;
    injected/out-of-tree registries may opt out (R2)."""
    from ..agents.loader import KNOWN_ROLES
    from ..benchmarks.heatmap import CANONICAL_STAGES

    problems: list[str] = []
    resolved: dict[str, str | None] = {}
    for key in sorted(registry):
        spec = registry[key]
        if key != spec.type:
            problems.append(f"{key}: registry key does not match spec.type {spec.type!r}")
        names = [p.name for p in spec.ports]
        for dup in sorted({n for n in names if names.count(n) > 1}):
            problems.append(f"{key}: duplicate port name {dup!r}")
        for port in spec.ports:
            if port.payload is None:
                continue
            if port.payload not in resolved:
                resolved[port.payload] = _resolve_payload(port.payload)
            error = resolved[port.payload]
            if error is not None:
                problems.append(f"{key}.{port.name}: {error}")
        if spec.canonical_stage is None:
            if require_mapped:
                problems.append(f"{key}: no canonical_stage")
        elif spec.canonical_stage not in CANONICAL_STAGES:
            problems.append(f"{key}: canonical_stage {spec.canonical_stage!r} is not canonical")
        if spec.role is not None and spec.role not in KNOWN_ROLES:
            problems.append(f"{key}: role {spec.role!r} is not a known registry role")
        if spec.kind == "gate":
            problems.extend(f"{key}: {p}" for p in _gate_shape_problems(spec))
    return sorted(problems)
