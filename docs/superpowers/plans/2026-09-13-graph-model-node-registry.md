# E-72 PipelineGraph Model + Node-Type Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `src/sdlc/graph/`: the frozen, stored `PipelineGraph` schema, its `content_sha()` identity, deterministic YAML io, and a static node-type registry with a seed pre-code catalog and the port-compatibility predicate. FR-1201, Phase 0 of pipeline-as-data.

**Architecture:** This is a new horizontal package that nothing else imports until E-74. It has four modules:
- `model.py`: stored models and the canonical form;
- `io.py`: YAML;
- `payloads.py`: the model-name allowlist;
- `node_types.py`: the registry, the predicate, and the self-check.

Parsing is shape-only. Every legality check belongs to E-73's `validate.py`, which is not built here. Module-level imports are pinned so the package cannot open a new route into the `benchmarks ↔ stages` import cycle.

**Tech Stack:** Python ≥ 3.11, pydantic v2, PyYAML, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md` (user-approved, D1–D10). This plan implements the spec, not the planner brief. Read both documents. Where this plan quotes the spec, the spec wins, except for the four named deviations below.

## Global Constraints

- **Python.** Target `py311` syntax (`[tool.ruff] target-version = "py311"`). Ruff `line-length = 100`, lint `select = ["E", "F", "I", "UP", "B"]`.
- **File size.** Hard ceiling of 1000 physical lines per file (`scripts/check_file_size.py`).
- **Module-level imports of `src/sdlc/graph/*.py`** (spec §4). Pinned by Task 5.
  - `model.py`: stdlib, `pydantic`, `sdlc.core.models`.
  - `payloads.py`: stdlib only.
  - `node_types.py`: stdlib, `pydantic`, `sdlc.graph.model`, `sdlc.graph.payloads`.
  - `io.py`: stdlib, `yaml`, `sdlc.graph.model`.
  - `__init__.py`: the four modules only.
  - `check_node_types()` imports `sdlc.agents.loader` and `sdlc.benchmarks.heatmap` **inside its body only**. It never imports `sdlc.agents.roles`.
- **Stored models.** `PipelineGraph`, `GraphNode`, `GraphEdge` and `NodePosition` use `ConfigDict(frozen=True, extra="forbid")`. `schema_version: Literal[1]` is required, with no default.
- **Canonical form** (spec §7.1). `model_dump(mode="json", exclude_defaults=True)`, minus node `position`/`label` and edge `label`. Then `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and sha256 hex.
- **Untouched** (spec §9). `PipelineConfig`, `resolve_role_model`, `src/sdlc/agents/loader.py`, `src/sdlc/agents/roles.py`, every `src/sdlc/stages/*`, `src/sdlc/benchmarks/*`, `src/sdlc/core/*`.
- **Out of scope** (spec §9). Do **not** build `validate.py`, a router, boot wiring, `default.graph.yaml`, a graph store or an API. Do **not** decide E72-OQ-1…E72-OQ-8. They stay with their recorded owners.
- **Determinism.** Iterate sorted everywhere. Every pure module gets an NFR-10 order-independence test (`itertools.permutations`, byte-identical results).
- **Commits.** Subject and body only. **No attribution trailers of any kind**: no `Co-Authored-By:` in any form, no session links, no generated-by footers. Commit with `git commit -F <msgfile>` and use one path per `git add` invocation. Put message files under `.workspace/tmp/`, which is not committed.
- **Test runs.** Never chain two `pytest` runs in one shell call.

## Named deviations from the spec (reviewer: judge these explicitly)

1. **Test file names are prefixed `test_graph_`.** The spec's §8 names are `test_model.py`, `test_content_sha.py`, `test_io.py`, `test_node_types.py` and `test_graph_purity.py`.
   - **Why:** the test-module directories under `tests/` carry no `__init__.py` (only the helper packages `tests/fakes/` and `tests/docs_site/` have one), and `tests/graph/` gets none. pytest's default rootdir/prepend import mode therefore keys test modules by basename. The repo's own slices prefix theirs for that reason (`tests/context/test_context_*.py`).
   - **Contents:** they follow spec §8's rows, with one relocation. The `NodePort` out-port rejection test sits in `test_graph_model.py`, because `NodePort` lives in `model.py`; spec §8 lists it under the node_types row.
   - **Cost:** the slowest of these tests measure ≤ 2.5 s (`test_seed_registry_is_healthy`, dominated by the first import of benchmarks/stages, and `test_to_yaml_is_order_independent`). `test_check_node_types_is_order_independent` iterates 7! = 5040 registry orders in 0.27 s.
2. **`schema_version` gets a `mode="before"` validator requiring an exact `int`.**
   - Verified: pydantic's lax `Literal[1]` accepts `True` and `1.0`, and `Field(strict=True)` raises `RuntimeError: Unable to apply constraint 'strict' to schema of type 'literal'`.
   - This enforces what spec §5/§7.2 intend: the version is the integer 1.
   - `from_yaml` also checks `type(version) is int`, because `bool` is an `int` subclass.
3. **`from_yaml` catches `ValueError`, not `pydantic.ValidationError`, around `model_validate`.** `ValidationError` subclasses `ValueError`. Importing pydantic in `io.py` would break §4's import set for that module. The test pins that `__cause__` is a `pydantic.ValidationError`, so the spec's "chained ValidationError" contract holds.
4. **`check_node_types(registry=NODE_TYPES)` keeps the spec's single parameter.** The payload-failure tests monkeypatch `sdlc.graph.node_types.PAYLOAD_TYPES` rather than adding a second parameter.

## Provenance of the code in this plan

Every code block below was executed before the plan was written, in a scratch copy of `src/` plus `tests/graph/`:
- 105 tests pass on Python 3.14.3 (the repo's dev interpreter);
- `mypy src/sdlc/graph --follow-imports=silent` is clean;
- `ruff check` and `ruff format --check` are clean with the repo's `pyproject.toml`;
- each task's tests were re-run against a snapshot holding **only that task's code**, so the TDD order below is proven. Every "Expected: FAIL" was observed as stated.

Not run on Python 3.11, because this machine's 3.11 has no test dependencies. No syntax newer than 3.11 is used (`sys.stdlib_module_names` is 3.10+). The golden sha in Task 3 was computed from this exact canonical form and fixture.

Editable installs don't auto-discover new modules. pytest resolves `sdlc.graph` through `pythonpath = [".", "src"]`, but if a plain `python -c "import sdlc.graph"` fails with `ModuleNotFoundError`, run `pip install -e .` (AGENTS.md).

## File Structure

| path | responsibility | task |
|---|---|---|
| `src/sdlc/graph/__init__.py` | eager re-exports (grows per task) | 1–4 |
| `src/sdlc/graph/model.py` | `NodePosition`, `NodePort`, `GraphNode`, `GraphEdge`, `PipelineGraph` (T1); `canonical_json`, `PipelineGraph.content_sha` (T3) | 1, 3 |
| `src/sdlc/graph/io.py` | `GraphSchemaError`, `to_yaml`, `from_yaml` | 2 |
| `src/sdlc/graph/payloads.py` | `PAYLOAD_TYPES` allowlist | 4 |
| `src/sdlc/graph/node_types.py` | `NodeTypeSpec`, seed `NODE_TYPES`, `find_port`, `ports_compatible`, `check_node_types` | 4 |
| `tests/graph/fixtures/pre_code.graph.yaml` | canonical-form fixture: the pre-code graph | 2 |
| `tests/graph/test_graph_model.py` | shape rejections, shape-only parse, order normalization | 1 |
| `tests/graph/test_graph_io.py` | round-trip, fixpoint, NFR-10, single exception type | 2 |
| `tests/graph/test_graph_content_sha.py` | golden sha, NFR-10, cosmetics invariance, sensitivity | 3 |
| `tests/graph/test_graph_node_types.py` | seed catalog, allowlist, truth table, self-check, NFR-10 | 4 |
| `tests/graph/test_graph_purity.py` | module-level import pins + cold-import subprocess | 5 |
| `docs/roadmap/pipeline-as-data.md`, `ROADMAP.md`, `ARCHITECTURE.md` | landing docs (docs describe `main`) | 6 |

Work on a feature branch cut from `main` at or after `dac11d8`, the spec commit. The orchestrator's exec phase names the branch and worktree.

---

### Task 1: Stored schema — `model.py` (shape-only parsing, order normalization)

**Files:**
- Create: `src/sdlc/graph/model.py`
- Create: `src/sdlc/graph/__init__.py`
- Test: `tests/graph/test_graph_model.py`

**Interfaces:**
- Consumes: `sdlc.core.models.RoleConfig`, `sdlc.core.models.GateConfig` (unmodified).
- Produces:
  - `ID_PATTERN: str`, `TYPE_PATTERN: str`
  - `class NodePosition(BaseModel)`: `x: float`, `y: float`
  - `class NodePort(BaseModel)`: `name: str`, `direction: Literal["in","out"]`, `payload: str | None`, `required: bool = True`, `multiplicity: Literal["one","many"] = "one"`. An out-port must be `required=True, multiplicity="one"`.
  - `class GraphNode(BaseModel)`: `id`, `type`, `role: RoleConfig | None`, `gate: GateConfig | None`, `position: NodePosition | None`, `label: str | None`
  - `class GraphEdge(BaseModel)`: `source`, `source_port`, `target`, `target_port`, `max_traversals: int | None (ge=1)`, `label: str | None`
  - `class PipelineGraph(BaseModel)`: `schema_version: Literal[1]`, `nodes: list[GraphNode]`, `edges: list[GraphEdge]`. Nodes and edges are sorted on construction.
  - private helpers reused by Task 3: `_dumps(data) -> str`, `_element_json(element, exclude) -> str`, `_NODE_COSMETIC`, `_EDGE_COSMETIC`

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_graph_model.py`:

```python
"""E-72 stored schema: parsing is shape-only (spec §5, D5)."""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError
from sdlc.graph import GraphEdge, GraphNode, NodePort, PipelineGraph


def _node(**kw):
    return {"id": "architect", "type": "architect", **kw}


def _edge(**kw):
    return {
        "source": "architect",
        "source_port": "spec",
        "target": "architecture",
        "target_port": "artifact",
        **kw,
    }


def _graph(nodes=None, edges=None, **kw):
    return {
        "schema_version": 1,
        "nodes": nodes if nodes is not None else [_node()],
        "edges": edges if edges is not None else [],
        **kw,
    }


@pytest.mark.parametrize("bad_id", ["", "Architect", "1st", "arch#1", "arch:x", "arch.x", "a-b"])
def test_node_id_shape(bad_id):
    with pytest.raises(ValidationError):
        GraphNode.model_validate(_node(id=bad_id))


@pytest.mark.parametrize("good_type", ["architect", "gate.plan", "gate.architecture"])
def test_node_type_accepts_one_dot(good_type):
    assert GraphNode.model_validate(_node(type=good_type)).type == good_type


@pytest.mark.parametrize("bad_type", ["Gate.plan", "gate..plan", "a.b.c", "gate.", ""])
def test_node_type_shape(bad_type):
    with pytest.raises(ValidationError):
        GraphNode.model_validate(_node(type=bad_type))


@pytest.mark.parametrize("field", ["source", "source_port", "target", "target_port"])
def test_edge_endpoint_shape(field):
    with pytest.raises(ValidationError):
        GraphEdge.model_validate(_edge(**{field: "Bad#Name"}))


def test_edge_max_traversals_is_positive():
    with pytest.raises(ValidationError):
        GraphEdge.model_validate(_edge(max_traversals=0))
    assert GraphEdge.model_validate(_edge(max_traversals=1)).max_traversals == 1


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (GraphNode, _node(params={"model": "x"})),
        (GraphEdge, _edge(weight=1)),
        (PipelineGraph, _graph(name="x")),
        (GraphNode, _node(position={"x": 1, "y": 2, "z": 3})),
    ],
)
def test_extra_keys_forbidden(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_role_typo_is_rejected_not_dropped():
    with pytest.raises(ValidationError, match="unknown role key"):
        GraphNode.model_validate(_node(role={"modle": "anthropic:x"}))


def test_gate_typo_is_rejected_not_dropped():
    with pytest.raises(ValidationError, match="unknown gate key"):
        GraphNode.model_validate(_node(type="gate.plan", gate={"polcy": "soft"}))


def test_gate_bare_policy_shorthand_not_accepted():
    """Spec §5: PipelineConfig.gates' `plan: soft` coercion is NOT mirrored."""
    with pytest.raises(ValidationError):
        GraphNode.model_validate(_node(type="gate.plan", gate="soft"))


def test_role_and_gate_carry_core_models_verbatim():
    node = GraphNode.model_validate(
        _node(role={"kind": "proposer", "model": "m"}, gate={"policy": "soft"})
    )
    assert node.role is not None and node.role.model == "m"
    assert node.gate is not None and node.gate.policy.value == "soft"


@pytest.mark.parametrize("version", [None, 2, 0, True, 1.0, "1"])
def test_schema_version_must_be_int_one(version):
    data = _graph()
    if version is None:
        del data["schema_version"]
    else:
        data["schema_version"] = version
    with pytest.raises(ValidationError):
        PipelineGraph.model_validate(data)


def test_parse_is_shape_only():
    """Dangling edge, unknown type, duplicate ids and incompatible ports all
    PARSE -- rejecting them is validate.py's (E-73)."""
    graph = PipelineGraph.model_validate(
        _graph(
            nodes=[_node(), _node(), _node(id="x", type="no.such_type")],
            edges=[
                _edge(target="missing_node"),
                _edge(source_port="spec", target="x", target_port="guidance"),
            ],
        )
    )
    assert len(graph.nodes) == 3 and len(graph.edges) == 2


def test_models_are_frozen():
    node = GraphNode.model_validate(_node())
    with pytest.raises(ValidationError):
        node.id = "other"  # type: ignore[misc]


def test_order_normalization():
    nodes = [_node(id="c"), _node(id="a", label="A"), _node(id="b")]
    edges = [_edge(source="c"), _edge(source="a"), _edge(source="a", target_port="z")]
    graphs = [
        PipelineGraph.model_validate(_graph(nodes=list(ns), edges=list(es)))
        for ns in itertools.permutations(nodes)
        for es in itertools.permutations(edges)
    ]
    assert all(g == graphs[0] for g in graphs)
    assert [n.id for n in graphs[0].nodes] == ["a", "b", "c"]
    assert [(e.source, e.target_port) for e in graphs[0].edges] == [
        ("a", "artifact"),
        ("a", "z"),
        ("c", "artifact"),
    ]


def test_explicit_empty_role_differs_from_absent_role():
    assert GraphNode.model_validate(_node(role={})) != GraphNode.model_validate(_node())


def test_out_port_cannot_be_optional_or_collect():
    with pytest.raises(ValidationError):
        NodePort(name="spec", direction="out", payload="ArchitectureSpec", required=False)
    with pytest.raises(ValidationError):
        NodePort(name="spec", direction="out", payload="ArchitectureSpec", multiplicity="many")
    port = NodePort(name="spec", direction="in", payload=None, required=False, multiplicity="many")
    assert port.multiplicity == "many"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_graph_model.py -q`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'sdlc.graph'`.

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/graph/model.py`:

```python
"""The stored pipeline graph (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.

Parsing is SHAPE-ONLY (spec D5): field types, id/type regexes, forbidden
extra keys, the schema version, and unknown keys under `role`/`gate`. Every
referential or legality check -- unique ids, dangling edges, unknown types,
port compatibility -- belongs to E-73's validate.py, so the canvas can load a
broken draft to show its errors.

Module-level imports stay within stdlib, pydantic and sdlc.core.models
(spec §4; pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.models import GateConfig, RoleConfig

# Node ids become gate names, gate_key "name#round" and CLI args (spec §5),
# so '#', ':' and '.' are excluded by shape. Port names share the pattern.
ID_PATTERN = r"^[a-z][a-z0-9_]*$"
# Node TYPE names may carry one dot: "architect", "gate.plan".
TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"

_STORED = ConfigDict(frozen=True, extra="forbid")

# Canvas cosmetics: excluded from identity (FR-1201), kept in storage.
_NODE_COSMETIC: frozenset[str] = frozenset({"position", "label"})
_EDGE_COSMETIC: frozenset[str] = frozenset({"label"})


def _dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _element_json(element: BaseModel, exclude: frozenset[str]) -> str:
    return _dumps(element.model_dump(mode="json", exclude_defaults=True, exclude=set(exclude)))


class NodePosition(BaseModel):
    """Canvas coordinates. Cosmetic: never part of content_sha()."""

    model_config = _STORED

    x: float
    y: float


class NodePort(BaseModel):
    """A port declared by a node TYPE in the registry (spec §6.1).

    Authored in code and never stored in a graph, so it can gain fields
    without a graph schema_version bump.
    """

    model_config = _STORED

    name: str = Field(pattern=ID_PATTERN)
    direction: Literal["in", "out"]
    payload: str | None  # a PAYLOAD_TYPES key; None = signal port
    required: bool = True  # meaningful on in-ports only
    multiplicity: Literal["one", "many"] = "one"  # "many" = collect; in-ports only

    @model_validator(mode="after")
    def _out_ports_are_plain(self) -> NodePort:
        if self.direction == "out" and (self.multiplicity != "one" or not self.required):
            raise ValueError(
                f"out-port {self.name!r} must be required with multiplicity 'one' "
                f"(optional and collect apply to in-ports only)"
            )
        return self


class GraphNode(BaseModel):
    """One node. `role`/`gate` carry the core models verbatim (spec D6/D7):
    a PipelineConfig.roles / PipelineConfig.gates ENTRY's semantics, resolved
    by E-74 -- nothing here interprets them."""

    model_config = _STORED

    id: str = Field(pattern=ID_PATTERN)
    type: str = Field(pattern=TYPE_PATTERN)
    role: RoleConfig | None = None
    gate: GateConfig | None = None
    position: NodePosition | None = None  # cosmetic
    label: str | None = None  # cosmetic

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_role_gate_keys(cls, data: Any) -> Any:
        """RoleConfig/GateConfig use pydantic's default extra='ignore', so a
        typo like `modle:` would be dropped silently -- and once dropped,
        validate.py can never see it. Checked here, at the model, so YAML and
        E-75 JSON are covered alike, without touching core/models.py."""
        if not isinstance(data, dict):
            return data
        for field, model in (("role", RoleConfig), ("gate", GateConfig)):
            value = data.get(field)
            if isinstance(value, dict):
                unknown = sorted(str(k) for k in set(value) - set(model.model_fields))
                if unknown:
                    raise ValueError(f"unknown {field} key(s): {', '.join(unknown)}")
        return data


class GraphEdge(BaseModel):
    """A directed connection. Identity is the endpoint 4-tuple (no id field);
    duplicates are validate.py's to reject."""

    model_config = _STORED

    source: str = Field(pattern=ID_PATTERN)
    source_port: str = Field(pattern=ID_PATTERN)
    target: str = Field(pattern=ID_PATTERN)
    target_port: str = Field(pattern=ID_PATTERN)
    # Stored data only: which cycles need a bound and what exhaustion does
    # are E-73's. None = this edge itself is unbounded.
    max_traversals: int | None = Field(default=None, ge=1)
    label: str | None = None  # cosmetic


class PipelineGraph(BaseModel):
    """The whole graph. Nodes and edges are normalized into a total order on
    construction, so author order never affects equality, YAML or sha."""

    model_config = _STORED

    schema_version: Literal[1]
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_is_an_int(cls, v: Any) -> Any:
        # A lax Literal[1] accepts `true` and `1.0` (and Field(strict=True)
        # cannot apply to a literal schema); type() because bool is an int.
        if type(v) is not int:
            raise ValueError(f"schema_version must be an integer, got {type(v).__name__}")
        return v

    @field_validator("nodes")
    @classmethod
    def _sort_nodes(cls, nodes: list[GraphNode]) -> list[GraphNode]:
        # The cosmetic-stripped tiebreak comes first so that even an illegal
        # duplicate-id draft never hashes differently by layout.
        return sorted(
            nodes,
            key=lambda n: (
                n.id,
                _element_json(n, _NODE_COSMETIC),
                _element_json(n, frozenset()),
            ),
        )

    @field_validator("edges")
    @classmethod
    def _sort_edges(cls, edges: list[GraphEdge]) -> list[GraphEdge]:
        return sorted(
            edges,
            key=lambda e: (
                e.source,
                e.source_port,
                e.target,
                e.target_port,
                _element_json(e, _EDGE_COSMETIC),
                _element_json(e, frozenset()),
            ),
        )
```

Create `src/sdlc/graph/__init__.py`:

```python
"""Pipeline as data -- the graph schema and node-type registry (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.
Nothing outside this package imports it until E-74.
"""

from __future__ import annotations

from .model import GraphEdge, GraphNode, NodePort, NodePosition, PipelineGraph

__all__ = [
    "GraphEdge",
    "GraphNode",
    "NodePort",
    "NodePosition",
    "PipelineGraph",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_graph_model.py -q`
Expected: PASS (all tests).

Run: `ruff check src/sdlc/graph tests/graph`, then `ruff format --check src/sdlc/graph tests/graph`
Expected: `All checks passed!` and every file already formatted.

Run: `mypy src/sdlc/graph --follow-imports=silent`
Expected: `Success: no issues found`.

- [ ] **Step 5: Commit**

Write `.workspace/tmp/e72-t1-msg.txt`:

```text
feat(graph): E-72 stored PipelineGraph schema

Add sdlc.graph.model: NodePosition, NodePort, GraphNode, GraphEdge and
PipelineGraph, all frozen with extra="forbid". Parsing is shape-only
(spec D5): regexes on ids/types/ports, schema_version exactly the int 1,
and unknown keys under role/gate rejected so RoleConfig's extra=ignore
cannot drop a typo. Nodes and edges are sorted into a total order on
construction; legality checks stay with E-73's validate.py.
```

```bash
git add src/sdlc/graph/model.py
git add src/sdlc/graph/__init__.py
git add tests/graph/test_graph_model.py
git commit -F .workspace/tmp/e72-t1-msg.txt
```

---

### Task 2: YAML storage shape — `io.py` + the fixture

**Files:**
- Create: `src/sdlc/graph/io.py`
- Create: `tests/graph/fixtures/pre_code.graph.yaml`
- Modify: `src/sdlc/graph/__init__.py` (full replacement below)
- Test: `tests/graph/test_graph_io.py`

**Interfaces:**
- Consumes: `PipelineGraph` (Task 1).
- Produces:
  - `class GraphSchemaError(ValueError)`
  - `to_yaml(graph: PipelineGraph) -> str`
  - `from_yaml(text: str) -> PipelineGraph`: raises only `GraphSchemaError`, chaining the underlying `yaml.YAMLError` / `ValidationError`
  - fixture `tests/graph/fixtures/pre_code.graph.yaml`, already in `to_yaml` canonical form

- [ ] **Step 1: Write the fixture and the failing test**

Create `tests/graph/fixtures/pre_code.graph.yaml` with exactly this content (LF line endings, trailing newline):

```yaml
schema_version: 1
nodes:
- id: architect
  type: architect
  role:
    kind: proposer
    model: anthropic:claude-opus-4-1
  position:
    x: 800.0
    y: 0.0
- id: architecture
  type: gate.architecture
  gate: {}
  position:
    x: 1000.0
    y: 0.0
- id: clarifier
  type: clarify
  position:
    x: 600.0
    y: 0.0
- id: intake
  type: intake
  position:
    x: 0.0
    y: 0.0
- id: plan
  type: gate.plan
  gate:
    policy: soft
    threshold: 0.75
  position:
    x: 1400.0
    y: 0.0
  label: Plan gate
- id: planner
  type: plan
  position:
    x: 1200.0
    y: 0.0
- id: research
  type: gate.research
  position:
    x: 400.0
    y: 0.0
  label: Research gate
- id: researcher
  type: research
  role:
    kind: research
    provider: fake
  position:
    x: 200.0
    y: 0.0
edges:
- source: architect
  source_port: spec
  target: architecture
  target_port: artifact
- source: architecture
  source_port: approve
  target: planner
  target_port: spec
- source: architecture
  source_port: revise
  target: architect
  target_port: guidance
  max_traversals: 2
- source: clarifier
  source_port: requirements
  target: architect
  target_port: requirements
- source: clarifier
  source_port: requirements
  target: planner
  target_port: requirements
- source: intake
  source_port: ok
  target: researcher
  target_port: trigger
- source: plan
  source_port: revise
  target: planner
  target_port: guidance
  max_traversals: 2
- source: planner
  source_port: plan
  target: plan
  target_port: artifact
- source: research
  source_port: approve
  target: clarifier
  target_port: research
- source: research
  source_port: revise
  target: researcher
  target_port: guidance
  max_traversals: 2
  label: refine
- source: researcher
  source_port: brief
  target: research
  target_port: artifact
```

What the fixture exercises:
- A greenfield-with-research pre-code graph. Gate nodes keep the legacy gate names (`research`, `architecture`, `plan`); producers take other ids.
- Revise edges carry `max_traversals: 2`.
- `researcher` and `architect` carry `role` overrides.
- `architecture` carries `gate: {}`. That is an explicit `policy: hard` collapsed by `exclude_defaults`, and it is not the same as an absent gate.
- `plan` carries `policy: soft, threshold: 0.75`.
- Two nodes and one edge carry labels.

Create `tests/graph/test_graph_io.py`:

```python
"""E-72 YAML storage shape (spec §7.2)."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from pydantic import ValidationError
from sdlc.graph import GraphSchemaError, PipelineGraph, from_yaml, to_yaml

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _fixture_text() -> str:
    # read_text uses universal newlines, so a CRLF checkout still reads as LF.
    return FIXTURE.read_text(encoding="utf-8")


def test_fixture_is_in_canonical_yaml_form():
    """The committed fixture is byte-identical to to_yaml of itself."""
    text = _fixture_text()
    assert to_yaml(from_yaml(text)) == text


def test_round_trip_equality():
    graph = from_yaml(_fixture_text())
    assert from_yaml(to_yaml(graph)) == graph


def test_to_yaml_is_a_fixpoint():
    once = to_yaml(from_yaml(_fixture_text()))
    assert to_yaml(from_yaml(once)) == once


def test_yaml_keeps_cosmetics():
    text = _fixture_text()
    assert "position:" in text and "label: Plan gate" in text
    graph = from_yaml(text)
    assert any(n.label == "Plan gate" for n in graph.nodes)


def test_to_yaml_is_order_independent():
    """NFR-10, per-module pattern: byte-identical across input order."""
    data = from_yaml(_fixture_text()).model_dump(mode="json", exclude_defaults=True)
    nodes, edges = data["nodes"][:4], data["edges"][:4]
    expected = to_yaml(PipelineGraph.model_validate({**data, "nodes": nodes, "edges": edges}))
    for ns in itertools.permutations(nodes):
        for es in itertools.permutations(edges):
            graph = PipelineGraph.model_validate({**data, "nodes": list(ns), "edges": list(es)})
            assert to_yaml(graph) == expected


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("schema_version: 1\nnodes: [\n", "not valid YAML"),
        ("- just\n- a list\n", "must be a mapping"),
        ("", "must be a mapping"),
        ("schema_version: 2\nnodes: []\nedges: []\n", "unsupported graph schema_version 2"),
        ("schema_version: true\nnodes: []\nedges: []\n", "unsupported graph schema_version True"),
        ("nodes: []\nedges: []\n", "unsupported graph schema_version None"),
    ],
)
def test_from_yaml_document_errors(text, match):
    with pytest.raises(GraphSchemaError, match=match):
        from_yaml(text)


@pytest.mark.parametrize(
    "text",
    [
        "schema_version: 1\nnodes:\n- id: Bad#Id\n  type: architect\nedges: []\n",
        "schema_version: 1\nnodes:\n- id: a\n  type: architect\n  role:\n    modle: x\nedges: []\n",
    ],
)
def test_from_yaml_shape_failure_is_one_exception_type(text):
    with pytest.raises(GraphSchemaError) as info:
        from_yaml(text)
    assert isinstance(info.value.__cause__, ValidationError)


def test_graph_schema_error_is_a_value_error():
    assert issubclass(GraphSchemaError, ValueError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_graph_io.py -q`
Expected: FAIL at collection with `ImportError: cannot import name 'GraphSchemaError' from 'sdlc.graph'`.

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/graph/io.py`:

```python
"""YAML storage shape for `graphs/<sha>.yaml` (E-72, spec §7.2).

Serialize/deserialize only -- writing, reading and lookup of the store are
E-75/E-77. `from_yaml` raises exactly one exception type, GraphSchemaError,
for every way text fails to become a graph: one catch contract for E-75/E-76.
"""

from __future__ import annotations

import yaml

from .model import PipelineGraph

_SCHEMA_VERSION = 1


class GraphSchemaError(ValueError):
    """Graph text is not a well-shaped PipelineGraph (bad YAML, not a
    mapping, unsupported schema_version, or a model shape failure).
    Legality of a well-shaped graph is validate.py's (E-73), not this."""


def to_yaml(graph: PipelineGraph) -> str:
    """Deterministic: model field order, normalized node/edge order,
    exclude_defaults. Cosmetics are INCLUDED -- the canvas needs them."""
    return yaml.safe_dump(
        graph.model_dump(mode="json", exclude_defaults=True),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def from_yaml(text: str) -> PipelineGraph:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise GraphSchemaError(f"graph text is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise GraphSchemaError(f"graph document must be a mapping, got {type(data).__name__}")
    version = data.get("schema_version")
    # type() not isinstance(): bool is an int subclass, and `true` is not 1.
    if type(version) is not int or version != _SCHEMA_VERSION:
        raise GraphSchemaError(
            f"unsupported graph schema_version {version!r}; this worker reads {_SCHEMA_VERSION}"
        )
    try:
        return PipelineGraph.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise GraphSchemaError(f"graph does not match the schema: {exc}") from exc
```

Replace `src/sdlc/graph/__init__.py` with:

```python
"""Pipeline as data -- the graph schema and node-type registry (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.
Nothing outside this package imports it until E-74.
"""

from __future__ import annotations

from .io import GraphSchemaError, from_yaml, to_yaml
from .model import GraphEdge, GraphNode, NodePort, NodePosition, PipelineGraph

__all__ = [
    "GraphEdge",
    "GraphNode",
    "GraphSchemaError",
    "NodePort",
    "NodePosition",
    "PipelineGraph",
    "from_yaml",
    "to_yaml",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/graph -q`
Expected: PASS (Task 1 and Task 2 tests).

Run: `ruff check src/sdlc/graph tests/graph`, then `ruff format --check src/sdlc/graph tests/graph`, then `mypy src/sdlc/graph --follow-imports=silent`
Expected: all clean.

- [ ] **Step 5: Commit**

Write `.workspace/tmp/e72-t2-msg.txt`:

```text
feat(graph): E-72 deterministic YAML io for graphs/<sha>.yaml

Add sdlc.graph.io: to_yaml (model field order, normalized node/edge
order, exclude_defaults, cosmetics kept) and from_yaml, which raises a
single GraphSchemaError type for bad YAML, a non-mapping document, an
unsupported schema_version, or a shape failure (ValidationError chained
as __cause__). Storage itself is E-75/E-77. Adds the pre-code fixture
graph in canonical form.
```

```bash
git add src/sdlc/graph/io.py
git add src/sdlc/graph/__init__.py
git add tests/graph/fixtures/pre_code.graph.yaml
git add tests/graph/test_graph_io.py
git commit -F .workspace/tmp/e72-t2-msg.txt
```

---

### Task 3: Graph identity — `canonical_json()` and `PipelineGraph.content_sha()`

**Files:**
- Modify: `src/sdlc/graph/model.py` (three edits below)
- Modify: `src/sdlc/graph/__init__.py` (full replacement below)
- Test: `tests/graph/test_graph_content_sha.py`

**Interfaces:**
- Consumes: `PipelineGraph`, `_dumps`, `_NODE_COSMETIC`, `_EDGE_COSMETIC` (Task 1); `from_yaml` and the fixture (Task 2).
- Produces:
  - `canonical_json(graph: PipelineGraph) -> str`
  - `PipelineGraph.content_sha(self) -> str` (64-char lowercase sha256 hex)
  - the golden sha `9bc61539a897be2744030e2d1147ce5083dcb776b7d6f97fe273281527009fa1` for the fixture

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_graph_content_sha.py`:

```python
"""E-72 graph identity: content_sha() over the canonical form (spec §7.1)."""

from __future__ import annotations

import copy
import itertools
from pathlib import Path

import pytest
from sdlc.graph import PipelineGraph, canonical_json, from_yaml

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"

# Pinned on purpose: ANY change to the canonical form (field set, exclusion
# rules, sort order, JSON separators) re-shas every stored graph. If this
# fails, that is a schema decision (spec §7.3), not a test to update blindly.
GOLDEN_SHA = "9bc61539a897be2744030e2d1147ce5083dcb776b7d6f97fe273281527009fa1"

SMALL = {
    "schema_version": 1,
    "nodes": [
        {"id": "architect", "type": "architect", "role": {"kind": "proposer", "model": "m1"}},
        {"id": "architecture", "type": "gate.architecture", "gate": {"policy": "hard"}},
        {"id": "planner", "type": "plan", "position": {"x": 3, "y": 4}},
        {"id": "plan", "type": "gate.plan", "label": "Plan gate"},
    ],
    "edges": [
        {
            "source": "architect",
            "source_port": "spec",
            "target": "architecture",
            "target_port": "artifact",
        },
        {
            "source": "architecture",
            "source_port": "approve",
            "target": "planner",
            "target_port": "spec",
        },
        {
            "source": "architecture",
            "source_port": "revise",
            "target": "architect",
            "target_port": "guidance",
            "max_traversals": 2,
        },
        {
            "source": "planner",
            "source_port": "plan",
            "target": "plan",
            "target_port": "artifact",
            "label": "x",
        },
    ],
}


def _small(mutate=None) -> PipelineGraph:
    data = copy.deepcopy(SMALL)
    if mutate is not None:
        mutate(data)
    return PipelineGraph.model_validate(data)


def test_golden_sha_for_fixture():
    assert from_yaml(FIXTURE.read_text(encoding="utf-8")).content_sha() == GOLDEN_SHA


def test_sha_is_sha256_hex_of_canonical_json():
    import hashlib

    graph = _small()
    assert graph.content_sha() == hashlib.sha256(canonical_json(graph).encode()).hexdigest()


def test_canonical_json_is_compact_sorted_and_cosmetic_free():
    text = canonical_json(_small())
    assert " " not in text.replace("Plan gate", "")
    assert '"position"' not in text and '"label"' not in text
    assert text.index('"edges"') < text.index('"nodes"') < text.index('"schema_version"')


def test_sha_is_order_independent():
    """NFR-10, per-module pattern: byte-identical across input order."""
    expected_json = canonical_json(_small())
    expected_sha = _small().content_sha()
    for ns in itertools.permutations(SMALL["nodes"]):
        for es in itertools.permutations(SMALL["edges"]):
            graph = PipelineGraph.model_validate(
                {"schema_version": 1, "nodes": list(ns), "edges": list(es)}
            )
            assert canonical_json(graph) == expected_json
            assert graph.content_sha() == expected_sha


def _set_position(d):
    d["nodes"][0]["position"] = {"x": 999, "y": -1}


def _move_position(d):
    d["nodes"][2]["position"] = {"x": 0, "y": 0}


def _drop_position(d):
    del d["nodes"][2]["position"]


def _relabel_node(d):
    d["nodes"][3]["label"] = "Renamed"


def _label_edge(d):
    d["edges"][0]["label"] = "tidy"


@pytest.mark.parametrize(
    "cosmetic", [_set_position, _move_position, _drop_position, _relabel_node, _label_edge]
)
def test_cosmetics_never_change_sha(cosmetic):
    assert _small(cosmetic).content_sha() == _small().content_sha()


def _role_model(d):
    d["nodes"][0]["role"]["model"] = "m2"


def _gate_policy(d):
    d["nodes"][1]["gate"]["policy"] = "soft"


def _max_traversals(d):
    d["edges"][2]["max_traversals"] = 3


def _node_type(d):
    d["nodes"][2]["type"] = "architect"


def _edge_target(d):
    d["edges"][1]["target_port"] = "requirements"


def _drop_role(d):
    del d["nodes"][0]["role"]


def _empty_role(d):
    d["nodes"][2]["role"] = {}


@pytest.mark.parametrize(
    "edit",
    [_role_model, _gate_policy, _max_traversals, _node_type, _edge_target, _drop_role, _empty_role],
)
def test_semantic_edits_change_sha(edit):
    assert _small(edit).content_sha() != _small().content_sha()


def test_explicit_default_hashes_like_omitted():
    """`gate: {policy: hard}` and `gate: {}` mean the same -> one sha."""

    def omit_policy(d):
        d["nodes"][1]["gate"] = {}

    def explicit_threshold(d):
        d["nodes"][1]["gate"]["threshold"] = 0.8

    assert _small(omit_policy).content_sha() == _small().content_sha()
    assert _small(explicit_threshold).content_sha() == _small().content_sha()


def test_extra_args_order_is_meaningful():
    def args(order):
        def mutate(d):
            d["nodes"][0]["role"]["extra_args"] = order

        return mutate

    assert _small(args(["-a", "-b"])).content_sha() != _small(args(["-b", "-a"])).content_sha()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_graph_content_sha.py -q`
Expected: FAIL at collection with `ImportError: cannot import name 'canonical_json' from 'sdlc.graph'`.

- [ ] **Step 3: Write the implementation**

Edit `src/sdlc/graph/model.py`. Make these three changes and nothing else.

(a) In the stdlib import block, add `import hashlib` directly above `import json`:

```python
import hashlib
import json
from typing import Any, Literal
```

(b) Append this method to the end of `class PipelineGraph`, after `_sort_edges`:

```python
    def content_sha(self) -> str:
        """Graph identity (FR-1201): sha256 of canonical_json(). Tidying the
        canvas (position, label) never changes it."""
        return hashlib.sha256(canonical_json(self).encode("utf-8")).hexdigest()
```

(c) Append this function at the end of the module:

```python
def canonical_json(graph: PipelineGraph) -> str:
    """The canonical form (spec §7.1): exclude_defaults, cosmetics stripped,
    keys sorted, compact separators. Node/edge order is already normalized;
    inner lists (RoleConfig.extra_args) keep author order on purpose."""
    data = graph.model_dump(
        mode="json",
        exclude_defaults=True,
        exclude={
            "nodes": {"__all__": set(_NODE_COSMETIC)},
            "edges": {"__all__": set(_EDGE_COSMETIC)},
        },
    )
    return _dumps(data)
```

After the edit, `src/sdlc/graph/model.py` is exactly:

```python
"""The stored pipeline graph (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.

Parsing is SHAPE-ONLY (spec D5): field types, id/type regexes, forbidden
extra keys, the schema version, and unknown keys under `role`/`gate`. Every
referential or legality check -- unique ids, dangling edges, unknown types,
port compatibility -- belongs to E-73's validate.py, so the canvas can load a
broken draft to show its errors.

Module-level imports stay within stdlib, pydantic and sdlc.core.models
(spec §4; pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.models import GateConfig, RoleConfig

# Node ids become gate names, gate_key "name#round" and CLI args (spec §5),
# so '#', ':' and '.' are excluded by shape. Port names share the pattern.
ID_PATTERN = r"^[a-z][a-z0-9_]*$"
# Node TYPE names may carry one dot: "architect", "gate.plan".
TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"

_STORED = ConfigDict(frozen=True, extra="forbid")

# Canvas cosmetics: excluded from identity (FR-1201), kept in storage.
_NODE_COSMETIC: frozenset[str] = frozenset({"position", "label"})
_EDGE_COSMETIC: frozenset[str] = frozenset({"label"})


def _dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _element_json(element: BaseModel, exclude: frozenset[str]) -> str:
    return _dumps(element.model_dump(mode="json", exclude_defaults=True, exclude=set(exclude)))


class NodePosition(BaseModel):
    """Canvas coordinates. Cosmetic: never part of content_sha()."""

    model_config = _STORED

    x: float
    y: float


class NodePort(BaseModel):
    """A port declared by a node TYPE in the registry (spec §6.1).

    Authored in code and never stored in a graph, so it can gain fields
    without a graph schema_version bump.
    """

    model_config = _STORED

    name: str = Field(pattern=ID_PATTERN)
    direction: Literal["in", "out"]
    payload: str | None  # a PAYLOAD_TYPES key; None = signal port
    required: bool = True  # meaningful on in-ports only
    multiplicity: Literal["one", "many"] = "one"  # "many" = collect; in-ports only

    @model_validator(mode="after")
    def _out_ports_are_plain(self) -> NodePort:
        if self.direction == "out" and (self.multiplicity != "one" or not self.required):
            raise ValueError(
                f"out-port {self.name!r} must be required with multiplicity 'one' "
                f"(optional and collect apply to in-ports only)"
            )
        return self


class GraphNode(BaseModel):
    """One node. `role`/`gate` carry the core models verbatim (spec D6/D7):
    a PipelineConfig.roles / PipelineConfig.gates ENTRY's semantics, resolved
    by E-74 -- nothing here interprets them."""

    model_config = _STORED

    id: str = Field(pattern=ID_PATTERN)
    type: str = Field(pattern=TYPE_PATTERN)
    role: RoleConfig | None = None
    gate: GateConfig | None = None
    position: NodePosition | None = None  # cosmetic
    label: str | None = None  # cosmetic

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_role_gate_keys(cls, data: Any) -> Any:
        """RoleConfig/GateConfig use pydantic's default extra='ignore', so a
        typo like `modle:` would be dropped silently -- and once dropped,
        validate.py can never see it. Checked here, at the model, so YAML and
        E-75 JSON are covered alike, without touching core/models.py."""
        if not isinstance(data, dict):
            return data
        for field, model in (("role", RoleConfig), ("gate", GateConfig)):
            value = data.get(field)
            if isinstance(value, dict):
                unknown = sorted(str(k) for k in set(value) - set(model.model_fields))
                if unknown:
                    raise ValueError(f"unknown {field} key(s): {', '.join(unknown)}")
        return data


class GraphEdge(BaseModel):
    """A directed connection. Identity is the endpoint 4-tuple (no id field);
    duplicates are validate.py's to reject."""

    model_config = _STORED

    source: str = Field(pattern=ID_PATTERN)
    source_port: str = Field(pattern=ID_PATTERN)
    target: str = Field(pattern=ID_PATTERN)
    target_port: str = Field(pattern=ID_PATTERN)
    # Stored data only: which cycles need a bound and what exhaustion does
    # are E-73's. None = this edge itself is unbounded.
    max_traversals: int | None = Field(default=None, ge=1)
    label: str | None = None  # cosmetic


class PipelineGraph(BaseModel):
    """The whole graph. Nodes and edges are normalized into a total order on
    construction, so author order never affects equality, YAML or sha."""

    model_config = _STORED

    schema_version: Literal[1]
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_is_an_int(cls, v: Any) -> Any:
        # A lax Literal[1] accepts `true` and `1.0` (and Field(strict=True)
        # cannot apply to a literal schema); type() because bool is an int.
        if type(v) is not int:
            raise ValueError(f"schema_version must be an integer, got {type(v).__name__}")
        return v

    @field_validator("nodes")
    @classmethod
    def _sort_nodes(cls, nodes: list[GraphNode]) -> list[GraphNode]:
        # The cosmetic-stripped tiebreak comes first so that even an illegal
        # duplicate-id draft never hashes differently by layout.
        return sorted(
            nodes,
            key=lambda n: (
                n.id,
                _element_json(n, _NODE_COSMETIC),
                _element_json(n, frozenset()),
            ),
        )

    @field_validator("edges")
    @classmethod
    def _sort_edges(cls, edges: list[GraphEdge]) -> list[GraphEdge]:
        return sorted(
            edges,
            key=lambda e: (
                e.source,
                e.source_port,
                e.target,
                e.target_port,
                _element_json(e, _EDGE_COSMETIC),
                _element_json(e, frozenset()),
            ),
        )

    def content_sha(self) -> str:
        """Graph identity (FR-1201): sha256 of canonical_json(). Tidying the
        canvas (position, label) never changes it."""
        return hashlib.sha256(canonical_json(self).encode("utf-8")).hexdigest()


def canonical_json(graph: PipelineGraph) -> str:
    """The canonical form (spec §7.1): exclude_defaults, cosmetics stripped,
    keys sorted, compact separators. Node/edge order is already normalized;
    inner lists (RoleConfig.extra_args) keep author order on purpose."""
    data = graph.model_dump(
        mode="json",
        exclude_defaults=True,
        exclude={
            "nodes": {"__all__": set(_NODE_COSMETIC)},
            "edges": {"__all__": set(_EDGE_COSMETIC)},
        },
    )
    return _dumps(data)
```

Replace `src/sdlc/graph/__init__.py` with:

```python
"""Pipeline as data -- the graph schema and node-type registry (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.
Nothing outside this package imports it until E-74.
"""

from __future__ import annotations

from .io import GraphSchemaError, from_yaml, to_yaml
from .model import (
    GraphEdge,
    GraphNode,
    NodePort,
    NodePosition,
    PipelineGraph,
    canonical_json,
)

__all__ = [
    "GraphEdge",
    "GraphNode",
    "GraphSchemaError",
    "NodePort",
    "NodePosition",
    "PipelineGraph",
    "canonical_json",
    "from_yaml",
    "to_yaml",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/graph -q`
Expected: PASS (Tasks 1–3), including `test_golden_sha_for_fixture`.

If the golden sha test alone fails, **stop**. Do not edit `GOLDEN_SHA`. Diff `model.py` and the fixture against this plan: the pinned value is the canonical-form contract (spec §7.3), and a mismatch means the implementation drifted from it. Report the mismatch to the orchestrator.

Run: `ruff check src/sdlc/graph tests/graph`, then `ruff format --check src/sdlc/graph tests/graph`, then `mypy src/sdlc/graph --follow-imports=silent`
Expected: all clean.

- [ ] **Step 5: Commit**

Write `.workspace/tmp/e72-t3-msg.txt`:

```text
feat(graph): E-72 content_sha over the canonical form

Add canonical_json() and PipelineGraph.content_sha(): exclude_defaults,
node position/label and edge label stripped, sorted keys, compact
separators, sha256 hex (spec §7.1). Canvas cosmetics never move the sha;
an explicit default hashes like an omitted one; RoleConfig.extra_args
order stays meaningful. A golden sha for the fixture pins the canonical
form so any accidental change fails loudly.
```

```bash
git add src/sdlc/graph/model.py
git add src/sdlc/graph/__init__.py
git add tests/graph/test_graph_content_sha.py
git commit -F .workspace/tmp/e72-t3-msg.txt
```

---

### Task 4: Registry — `payloads.py`, `node_types.py` (seed catalog, predicate, self-check)

**Files:**
- Create: `src/sdlc/graph/payloads.py`
- Create: `src/sdlc/graph/node_types.py`
- Modify: `src/sdlc/graph/__init__.py` (full replacement below)
- Test: `tests/graph/test_graph_node_types.py`

**Interfaces:**
- Consumes: `NodePort`, `TYPE_PATTERN` (Task 1); `from_yaml` and the fixture (Task 2); and, lazily inside `check_node_types` only, `sdlc.agents.loader.KNOWN_ROLES` and `sdlc.benchmarks.heatmap.CANONICAL_STAGES`.
- Produces (the surface E-73 and E-76 build against):
  - `PAYLOAD_TYPES: Mapping[str, str]` (read-only `MappingProxyType`)
  - `class NodeTypeSpec(BaseModel)`: `type: str`, `kind: Literal["stage","gate"]`, `role: str | None`, `canonical_stage: str | None`, `ports: tuple[NodePort, ...]`
  - `NODE_TYPES: Mapping[str, NodeTypeSpec]` (read-only). Keys: `intake`, `context`, `research`, `clarify`, `architect`, `plan`, `gate.research`, `gate.architecture`, `gate.plan`.
  - `find_port(spec: NodeTypeSpec, name: str, direction: Literal["in","out"]) -> NodePort | None`
  - `ports_compatible(out_port: NodePort, in_port: NodePort) -> bool`
  - `check_node_types(registry: Mapping[str, NodeTypeSpec] = NODE_TYPES) -> list[str]` (sorted; `[]` means healthy)

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_graph_node_types.py`:

```python
"""E-72 node-type registry, payload allowlist and compatibility rule (spec §6)."""

from __future__ import annotations

import itertools
from pathlib import Path
from types import MappingProxyType

import pytest
from sdlc.graph import (
    NODE_TYPES,
    PAYLOAD_TYPES,
    NodePort,
    NodeTypeSpec,
    check_node_types,
    find_port,
    from_yaml,
    ports_compatible,
)
from sdlc.graph import node_types as node_types_module

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _in(name, payload, **kw):
    return NodePort(name=name, direction="in", payload=payload, **kw)


def _out(name, payload):
    return NodePort(name=name, direction="out", payload=payload)


def _stage(type_, *ports, role=None, canonical_stage="architecture"):
    return NodeTypeSpec(
        type=type_, kind="stage", role=role, canonical_stage=canonical_stage, ports=ports
    )


def test_seed_registry_is_healthy():
    assert check_node_types() == []


def test_seed_catalog_types():
    assert sorted(NODE_TYPES) == [
        "architect",
        "clarify",
        "context",
        "gate.architecture",
        "gate.plan",
        "gate.research",
        "intake",
        "plan",
        "research",
    ]
    assert "gate.clarify" not in NODE_TYPES  # clarify's HITL is handler-internal (spec §6.4)


@pytest.mark.parametrize(
    ("type_", "kind", "role", "canonical_stage"),
    [
        ("intake", "stage", None, "intake"),
        ("context", "stage", None, "context"),
        ("research", "stage", "research", "research"),
        ("clarify", "stage", "clarify", "clarify"),
        ("architect", "stage", "architect", "architecture"),
        ("plan", "stage", "planner", "planning"),
        ("gate.research", "gate", None, "research"),
        ("gate.architecture", "gate", None, "architecture"),
        ("gate.plan", "gate", None, "planning"),
    ],
)
def test_seed_catalog_metadata(type_, kind, role, canonical_stage):
    spec = NODE_TYPES[type_]
    assert (spec.kind, spec.role, spec.canonical_stage) == (kind, role, canonical_stage)


def _port_table(type_):
    return {
        (p.direction, p.name): (p.payload, p.required, p.multiplicity)
        for p in NODE_TYPES[type_].ports
    }


def test_seed_catalog_ports():
    gd = "GateDecision"
    assert _port_table("intake") == {("out", "ok"): (None, True, "one")}
    assert _port_table("context") == {
        ("in", "trigger"): (None, True, "one"),
        ("out", "map"): ("CodebaseMap", True, "one"),
    }
    assert _port_table("research") == {
        ("in", "trigger"): (None, True, "one"),
        ("in", "guidance"): (gd, False, "one"),
        ("out", "brief"): ("ResearchBrief", True, "one"),
    }
    assert _port_table("clarify") == {
        ("in", "trigger"): (None, False, "one"),
        ("in", "codebase_map"): ("CodebaseMap", False, "one"),
        ("in", "research"): ("ResearchBrief", False, "one"),
        ("out", "requirements"): ("ClarifiedRequirements", True, "one"),
    }
    assert _port_table("architect") == {
        ("in", "requirements"): ("ClarifiedRequirements", True, "one"),
        ("in", "codebase_map"): ("CodebaseMap", False, "one"),
        ("in", "guidance"): (gd, False, "one"),
        ("out", "spec"): ("ArchitectureSpec", True, "one"),
    }
    assert _port_table("plan") == {
        ("in", "spec"): ("ArchitectureSpec", True, "one"),
        ("in", "requirements"): ("ClarifiedRequirements", False, "one"),
        ("in", "guidance"): (gd, False, "one"),
        ("out", "plan"): ("ImplementationPlan", True, "one"),
    }
    for gate, payload in [
        ("gate.research", "ResearchBrief"),
        ("gate.architecture", "ArchitectureSpec"),
        ("gate.plan", "ImplementationPlan"),
    ]:
        assert _port_table(gate) == {
            ("in", "artifact"): (payload, True, "one"),
            ("out", "approve"): (payload, True, "one"),
            ("out", "revise"): (gd, True, "one"),
            ("out", "reject"): (None, True, "one"),
        }


def test_payload_allowlist_seed():
    assert dict(PAYLOAD_TYPES) == {
        "ArchitectureSpec": "sdlc.stages.architecture.models:ArchitectureSpec",
        "ClarifiedRequirements": "sdlc.stages.clarify.models:ClarifiedRequirements",
        "CodebaseMap": "sdlc.context.models:CodebaseMap",
        "GateDecision": "sdlc.core.models:GateDecision",
        "ImplementationPlan": "sdlc.stages.plan.models:ImplementationPlan",
        "ResearchBrief": "sdlc.stages.research.models:ResearchBrief",
    }


def test_registries_are_read_only():
    with pytest.raises(TypeError):
        NODE_TYPES["x"] = NODE_TYPES["intake"]  # type: ignore[index]
    with pytest.raises(TypeError):
        PAYLOAD_TYPES["x"] = "y"  # type: ignore[index]


def test_find_port():
    spec = NODE_TYPES["architect"]
    assert find_port(spec, "spec", "out") is not None
    assert find_port(spec, "spec", "in") is None
    assert find_port(spec, "nope", "out") is None


@pytest.mark.parametrize(
    ("out_port", "in_port", "expected"),
    [
        (_out("spec", "ArchitectureSpec"), _in("spec", "ArchitectureSpec"), True),
        (_out("spec", "ArchitectureSpec"), _in("plan", "ImplementationPlan"), False),
        (_out("ok", None), _in("trigger", None), True),
        (_out("spec", "ArchitectureSpec"), _in("trigger", None), False),
        (_out("ok", None), _in("spec", "ArchitectureSpec"), False),
        (_in("spec", "ArchitectureSpec"), _in("spec", "ArchitectureSpec"), False),
        (_out("spec", "ArchitectureSpec"), _out("spec", "ArchitectureSpec"), False),
        (_in("spec", "ArchitectureSpec"), _out("spec", "ArchitectureSpec"), False),
    ],
)
def test_ports_compatible_truth_table(out_port, in_port, expected):
    assert ports_compatible(out_port, in_port) is expected


def test_fixture_graph_is_port_compatible_against_seed():
    """Cross-check the fixture against the registry with the E-72 predicate.
    Not validate.py (E-73) -- only types exist and every edge's ports match."""
    graph = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    types = {n.id: n.type for n in graph.nodes}
    assert set(types.values()) <= set(NODE_TYPES)
    for edge in graph.edges:
        out_port = find_port(NODE_TYPES[types[edge.source]], edge.source_port, "out")
        in_port = find_port(NODE_TYPES[types[edge.target]], edge.target_port, "in")
        assert out_port is not None and in_port is not None, edge
        assert ports_compatible(out_port, in_port), edge


def _broken_registry() -> dict[str, NodeTypeSpec]:
    return {
        "bad_key": _stage("architect", _out("spec", "ArchitectureSpec"), role="architect"),
        "dup": _stage("dup", _in("x", None), _out("x", None)),
        "unknown_payload": _stage("unknown_payload", _out("y", "NoSuchModel")),
        "bad_stage": _stage("bad_stage", _out("ok", None), canonical_stage="plan"),
        "bad_role": _stage("bad_role", _out("ok", None), role="architecht"),
        "gate.bad": NodeTypeSpec(
            type="gate.bad",
            kind="gate",
            role="reviewer",
            canonical_stage="planning",
            ports=(
                _in("artifact", "ImplementationPlan"),
                _out("approve", "ArchitectureSpec"),
                _out("revise", "ImplementationPlan"),
                _out("escalate", None),
            ),
        ),
        "gate.no_artifact": NodeTypeSpec(
            type="gate.no_artifact",
            kind="gate",
            role=None,
            canonical_stage=None,
            ports=(_in("input", None), _out("approve", None)),
        ),
    }


EXPECTED_BROKEN = sorted(
    [
        "bad_key: registry key does not match spec.type 'architect'",
        "dup: duplicate port name 'x'",
        "unknown_payload.y: payload 'NoSuchModel' is not in PAYLOAD_TYPES",
        "bad_stage: canonical_stage 'plan' is not canonical",
        "bad_role: role 'architecht' is not a known registry role",
        "gate.bad: gate type must be role-less",
        "gate.bad: gate out-port 'approve' must carry the artifact payload 'ImplementationPlan'",
        "gate.bad: gate out-port 'reject' must be a signal port",
        "gate.bad: gate out-port 'revise' must carry 'GateDecision'",
        "gate.bad: gate type has unexpected out-port(s): escalate",
        "gate.no_artifact: gate type must have exactly one in-port 'artifact' with a payload",
    ]
)


def test_check_node_types_reports_every_problem_sorted():
    assert check_node_types(_broken_registry()) == EXPECTED_BROKEN


def test_check_node_types_is_order_independent():
    """NFR-10, per-module pattern: identical across registry insertion order."""
    items = list(_broken_registry().items())
    for perm in itertools.permutations(items):
        assert check_node_types(MappingProxyType(dict(perm))) == EXPECTED_BROKEN


def test_payload_resolution_failures(monkeypatch):
    monkeypatch.setattr(
        node_types_module,
        "PAYLOAD_TYPES",
        {
            "Renamed": "sdlc.stages.plan.models:ImplementationPlan",
            "Missing": "sdlc.no_such_module:Thing",
            "NotAModel": "sdlc.core.models:gate_key",
            "NoAttr": "sdlc.core.models:NoSuchClass",
        },
    )
    registry = {
        "t": _stage(
            "t",
            _out("a", "Renamed"),
            _out("b", "Missing"),
            _out("c", "NotAModel"),
            _out("d", "NoAttr"),
        )
    }
    problems = check_node_types(registry)
    assert problems[0] == "t.a: payload 'Renamed' resolves to class 'ImplementationPlan'"
    assert problems[1].startswith("t.b: payload 'Missing' does not resolve (sdlc.no_such_module:")
    assert (
        problems[2]
        == "t.c: payload 'NotAModel' (sdlc.core.models:gate_key) is not a pydantic model"
    )
    assert problems[3].startswith("t.d: payload 'NoAttr' does not resolve (sdlc.core.models:")
    assert len(problems) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_graph_node_types.py -q`
Expected: FAIL at collection with `ImportError: cannot import name 'NODE_TYPES' from 'sdlc.graph'`.

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/graph/payloads.py`:

```python
"""The payload allowlist (E-72, spec §6.2).

Port payloads are model NAMES; this table maps each name to
"module.path:ClassName". Strings, not imports: resolving them here would pull
stage slices (and the benchmarks <-> stages cycle) into sdlc.graph's import
closure. check_node_types() resolves them lazily.

A port names the class its CONSUMER needs, living in a models module -- hence
ResearchBrief, not the ResearchOutcome subclass defined in research/step.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

PAYLOAD_TYPES: Mapping[str, str] = MappingProxyType(
    {
        "ArchitectureSpec": "sdlc.stages.architecture.models:ArchitectureSpec",
        "ClarifiedRequirements": "sdlc.stages.clarify.models:ClarifiedRequirements",
        "CodebaseMap": "sdlc.context.models:CodebaseMap",
        "GateDecision": "sdlc.core.models:GateDecision",
        "ImplementationPlan": "sdlc.stages.plan.models:ImplementationPlan",
        "ResearchBrief": "sdlc.stages.research.models:ResearchBrief",
    }
)
```

Create `src/sdlc/graph/node_types.py`:

```python
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


def _out(name: str, payload: str | None) -> NodePort:
    return NodePort(name=name, direction="out", payload=payload)


def _gate(type_: str, payload: str, canonical_stage: str) -> NodeTypeSpec:
    """A revise-loop gate: artifact:T -> approve:T | revise:GateDecision | reject."""
    return NodeTypeSpec(
        type=type_,
        kind="gate",
        role=None,
        canonical_stage=canonical_stage,
        ports=(
            _in("artifact", payload),
            _out("approve", payload),
            _out("revise", "GateDecision"),
            _out("reject", None),
        ),
    )


# The seed catalog (spec §6.4): the typed pre-code half. Type names equal
# STAGE_ROLES stage keys where one exists, so E-74 reaches PROMPT_SHAS[type]
# without a second mapping. No gate.clarify: clarify's HITL is a Q&A channel
# inside its handler (stages/clarify/step.py:199), not approve/revise/reject.
# A gate's canonical_stage is its producer's stage (FR-1206).
_SEED: tuple[NodeTypeSpec, ...] = (
    NodeTypeSpec(
        type="intake",
        kind="stage",
        role=None,
        canonical_stage="intake",
        ports=(_out("ok", None),),
    ),
    NodeTypeSpec(
        type="context",
        kind="stage",
        role=None,
        canonical_stage="context",
        ports=(_in("trigger", None), _out("map", "CodebaseMap")),
    ),
    NodeTypeSpec(
        type="research",
        kind="stage",
        role="research",
        canonical_stage="research",
        ports=(
            _in("trigger", None),
            _in("guidance", "GateDecision", required=False),
            _out("brief", "ResearchBrief"),
        ),
    ),
    NodeTypeSpec(
        type="clarify",
        kind="stage",
        role="clarify",
        canonical_stage="clarify",
        ports=(
            _in("trigger", None, required=False),
            _in("codebase_map", "CodebaseMap", required=False),
            _in("research", "ResearchBrief", required=False),
            _out("requirements", "ClarifiedRequirements"),
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
        ),
    ),
    _gate("gate.research", "ResearchBrief", "research"),
    _gate("gate.architecture", "ArchitectureSpec", "architecture"),
    _gate("gate.plan", "ImplementationPlan", "planning"),
)

NODE_TYPES: Mapping[str, NodeTypeSpec] = MappingProxyType({s.type: s for s in _SEED})


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
    except (ImportError, AttributeError) as exc:
        return f"payload {name!r} does not resolve ({target}): {exc}"
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
    if revise is not None and revise.payload != "GateDecision":
        problems.append("gate out-port 'revise' must carry 'GateDecision'")
    extra = sorted(set(outs) - {"approve", "reject", "revise"})
    if extra:
        problems.append(f"gate type has unexpected out-port(s): {', '.join(extra)}")
    return problems


def check_node_types(registry: Mapping[str, NodeTypeSpec] = NODE_TYPES) -> list[str]:
    """Registry self-check (spec §6.3). Returns problems SORTED; [] = healthy.
    E-72 runs it from a unit test; E-74 wires it into worker boot."""
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
        if spec.canonical_stage is not None and spec.canonical_stage not in CANONICAL_STAGES:
            problems.append(f"{key}: canonical_stage {spec.canonical_stage!r} is not canonical")
        if spec.role is not None and spec.role not in KNOWN_ROLES:
            problems.append(f"{key}: role {spec.role!r} is not a known registry role")
        if spec.kind == "gate":
            problems.extend(f"{key}: {p}" for p in _gate_shape_problems(spec))
    return sorted(problems)
```

Replace `src/sdlc/graph/__init__.py` with:

```python
"""Pipeline as data -- the graph schema and node-type registry (E-72, FR-1201).

Spec: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md.
Nothing outside this package imports it until E-74.
"""

from __future__ import annotations

from .io import GraphSchemaError, from_yaml, to_yaml
from .model import (
    GraphEdge,
    GraphNode,
    NodePort,
    NodePosition,
    PipelineGraph,
    canonical_json,
)
from .node_types import (
    NODE_TYPES,
    NodeTypeSpec,
    check_node_types,
    find_port,
    ports_compatible,
)
from .payloads import PAYLOAD_TYPES

__all__ = [
    "NODE_TYPES",
    "PAYLOAD_TYPES",
    "GraphEdge",
    "GraphNode",
    "GraphSchemaError",
    "NodePort",
    "NodePosition",
    "NodeTypeSpec",
    "PipelineGraph",
    "canonical_json",
    "check_node_types",
    "find_port",
    "from_yaml",
    "ports_compatible",
    "to_yaml",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/graph -q`
Expected: PASS (Tasks 1–4), including `test_seed_registry_is_healthy` (`check_node_types() == []`) and `test_fixture_graph_is_port_compatible_against_seed`.

Run: `ruff check src/sdlc/graph tests/graph`, then `ruff format --check src/sdlc/graph tests/graph`, then `mypy src/sdlc/graph --follow-imports=silent`
Expected: all clean.

- [ ] **Step 5: Commit**

Write `.workspace/tmp/e72-t4-msg.txt`:

```text
feat(graph): E-72 node-type registry, payload allowlist, compatibility

Add sdlc.graph.payloads (PAYLOAD_TYPES name -> "module:Class") and
sdlc.graph.node_types: NodeTypeSpec, the seed catalog for the typed
pre-code half (intake, context, research, clarify, architect, plan and
gate.research/architecture/plan; no gate.clarify), find_port, the
exact-nominal ports_compatible predicate, and check_node_types, which
resolves payloads, canonical stages and roles lazily and returns sorted
problems. Rejecting graphs stays with E-73's validate.py; boot wiring
lands with E-74.
```

```bash
git add src/sdlc/graph/payloads.py
git add src/sdlc/graph/node_types.py
git add src/sdlc/graph/__init__.py
git add tests/graph/test_graph_node_types.py
git commit -F .workspace/tmp/e72-t4-msg.txt
```

---

### Task 5: Import-rule pins — `test_graph_purity.py`

**Files:**
- Test: `tests/graph/test_graph_purity.py`

**Interfaces:**
- Consumes: the five modules of `src/sdlc/graph/` (Tasks 1–4).
- Produces: a regression pin. Any new module-level import outside spec §4's sets, any new module in `sdlc/graph/` without an `ALLOWED` entry, or a cold `import sdlc.graph` that loads `sdlc.benchmarks` / `sdlc.stages` / `sdlc.agents` / `temporalio` fails the suite.

This task guards code that already conforms, so a first run passes. Step 2 proves the pin actually catches a violation before you trust it.

- [ ] **Step 1: Write the test**

Create `tests/graph/test_graph_purity.py`:

```python
"""E-72 import rules (spec §4): sdlc.graph must not open a new route into the
benchmarks <-> stages import cycle, so its MODULE-LEVEL imports are pinned.
Function-local imports (check_node_types) are legal and not inspected."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sdlc.graph

GRAPH_DIR = Path(sdlc.graph.__file__).parent
STDLIB = "<stdlib>"

ALLOWED: dict[str, set[str]] = {
    "model.py": {STDLIB, "pydantic", "sdlc.core.models"},
    "payloads.py": {STDLIB},
    "node_types.py": {STDLIB, "pydantic", "sdlc.graph.model", "sdlc.graph.payloads"},
    "io.py": {STDLIB, "yaml", "sdlc.graph.model"},
    "__init__.py": {
        STDLIB,
        "sdlc.graph.io",
        "sdlc.graph.model",
        "sdlc.graph.node_types",
        "sdlc.graph.payloads",
    },
}


def _classify(module: str) -> str:
    root = module.split(".")[0]
    if root == "__future__" or root in sys.stdlib_module_names:
        return STDLIB
    if root == "sdlc":
        return module
    return root


def _top_level_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            found |= {_classify(a.name) for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = "sdlc.graph".split(".")[: 2 - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            found.add(_classify(module))
    return found


def test_every_module_is_covered():
    assert {p.name for p in GRAPH_DIR.glob("*.py")} == set(ALLOWED)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_module_level_imports_are_pinned(name):
    imported = _top_level_imports(GRAPH_DIR / name)
    assert imported <= ALLOWED[name], sorted(imported - ALLOWED[name])


def test_cold_import_pulls_in_no_heavy_packages():
    code = (
        "import sys, sdlc.graph; "
        "heavy = ('sdlc.benchmarks', 'sdlc.stages', 'sdlc.agents', 'temporalio'); "
        "print(sorted(m for m in sys.modules "
        "if any(m == h or m.startswith(h + '.') for h in heavy)))"
    )
    src_root = str(GRAPH_DIR.parents[1])
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([src_root, os.environ.get("PYTHONPATH", "")]),
    }
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    assert proc.stdout.strip() == "[]", proc.stdout + proc.stderr
```

- [ ] **Step 2: Prove the pin bites, then revert**

Temporarily add this line at module level in `src/sdlc/graph/payloads.py`, directly below `from types import MappingProxyType`:

```python
from sdlc.benchmarks.heatmap import CANONICAL_STAGES  # noqa: F401  TEMPORARY
```

Run: `pytest tests/graph/test_graph_purity.py -q`
Expected: FAIL in two tests, `test_module_level_imports_are_pinned[payloads.py]` (reporting `['sdlc.benchmarks.heatmap']`) and `test_cold_import_pulls_in_no_heavy_packages` (non-empty module list).

Remove the temporary line, then confirm `git diff --stat src/sdlc/graph/payloads.py` prints nothing.

- [ ] **Step 3: Run the test to verify it passes**

Run: `pytest tests/graph/test_graph_purity.py -q`
Expected: PASS.

Run: `ruff check tests/graph`, then `ruff format --check tests/graph`
Expected: clean.

- [ ] **Step 4: Commit**

Write `.workspace/tmp/e72-t5-msg.txt`:

```text
test(graph): E-72 pin sdlc.graph module-level imports

AST-check each sdlc/graph module's top-level imports against spec §4's
allowed sets (function-local imports stay legal), require every module
to have an entry, and assert a cold `import sdlc.graph` in a subprocess
loads no sdlc.benchmarks, sdlc.stages, sdlc.agents or temporalio -- so
the package cannot open a new route into the benchmarks <-> stages
import cycle.
```

```bash
git add tests/graph/test_graph_purity.py
git commit -F .workspace/tmp/e72-t5-msg.txt
```

---

### Task 6: Landing docs + full verification gate

**Files:**
- Modify: `docs/roadmap/pipeline-as-data.md` (the E-72 row, lines 57–64)
- Modify: `ROADMAP.md` (the FR-1201 line, line 396)
- Modify: `ARCHITECTURE.md` (§14 repository layout, after the `memoization/` line, line 785)

**Interfaces:**
- Consumes: Tasks 1–5 landed on the branch.
- Produces: docs that describe `main` once the branch fast-forwards (docs-describe-main convention). FR-1201 is **partial**: rejecting incompatible edges is enforced by FR-1202's `validate.py` (E-73), per the spec's §9 traceability table.

- [ ] **Step 1: Tick the E-72 row**

In `docs/roadmap/pipeline-as-data.md`, change the first line of the E-72 row from:

```markdown
- [ ] **E-72 — `PipelineGraph` model + node-type registry** → FR-1201.
```

to:

```markdown
- [x] **E-72 — `PipelineGraph` model + node-type registry** → FR-1201.
```

Then append this paragraph as the row's last lines, directly after the line ending in ``node type's ports, payload types and `canonical_stage`.``, keeping the row's two-space continuation indent:

```markdown
  **Landed** (spec `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md`,
  plan `docs/superpowers/plans/2026-09-13-graph-model-node-registry.md`): `sdlc/graph/`
  ships the frozen schema, `content_sha()`, YAML io and a seed registry for the typed
  pre-code half (no `gate.clarify`). Rejecting incompatible edges is E-73's
  `validate.py`; the post-plan catalog and `code` decomposition are E-74's
  (E72-OQ-3). Open questions E72-OQ-1…8 live in the spec §10.
```

- [ ] **Step 2: Mark FR-1201 partial in ROADMAP.md**

Replace the line:

```markdown
- [ ] **FR-1201** typed `PipelineGraph` + node-type registry; nodes carry `RoleConfig`/`GateConfig` verbatim; ports typed by existing model name; `content_sha()` excludes canvas cosmetics (E-72).
```

with:

```markdown
- [ ] ⚠️ **FR-1201** typed `PipelineGraph` + node-type registry; nodes carry `RoleConfig`/`GateConfig` verbatim; ports typed by existing model name; `content_sha()` excludes canvas cosmetics (E-72). Partial: E-72 landed the schema, `content_sha()`, YAML io and the seed registry with the `ports_compatible` rule; *rejecting* incompatible edges is enforced by FR-1202's `validate.py` (E-73).
```

- [ ] **Step 3: Add the package to ARCHITECTURE.md §14**

Directly below the line

```text
│   ├── memoization/           # content-addressed activity cache (ADR-5)
```

insert, with the `#` in the same column:

```text
│   ├── graph/                 # PipelineGraph schema, node-type registry, content_sha, YAML io (E-72)
```

- [ ] **Step 4: Full verification gate**

Run each command separately (never two pytest runs in one call):

- `pytest`. Expected: the fast tier passes, with no failures in `tests/graph/`. Compare any non-graph failure against `main` before claiming a regression.
- `ruff check .`. Expected: `All checks passed!`
- `ruff format --check .`. Expected: no files would be reformatted.
- `mypy src/sdlc/graph --follow-imports=silent`. Expected: `Success: no issues found in 5 source files`.
- `mypy`. Expected: no error line mentions `src/sdlc/graph` (the repo carries a known deferred baseline elsewhere).
- `python scripts/check_file_size.py`. Expected: exit 0.
- `git diff --stat main -- src/sdlc/core src/sdlc/agents src/sdlc/stages src/sdlc/benchmarks`. Expected: empty (spec §9, untouched).

- [ ] **Step 5: Commit**

Write `.workspace/tmp/e72-t6-msg.txt`:

```text
docs: E-72 landed -- PipelineGraph schema and seed registry

Tick E-72 in the pipeline-as-data roadmap with pointers to its spec and
plan, mark FR-1201 partial in ROADMAP (rejecting incompatible edges is
FR-1202's validate.py, E-73), and add sdlc/graph/ to the ARCHITECTURE
repository layout.
```

```bash
git add docs/roadmap/pipeline-as-data.md
git add ROADMAP.md
git add ARCHITECTURE.md
git commit -F .workspace/tmp/e72-t6-msg.txt
```

---

## Spec coverage map (self-review)

| spec § | requirement | task |
|---|---|---|
| §4 | package layout; module-level import sets; lazy imports in `check_node_types`; AST purity + cold import | 1–4 (layout), 5 (pins) |
| §5 | frozen/forbid models; id/type/port regexes; `max_traversals ge=1`; required `schema_version`; unknown role/gate keys rejected; mapping-only `gate`; shape-only parse; total-order normalization with cosmetic-stripped tiebreak first; `role: {}` ≠ absent | 1 |
| §5 | validate.py list, kind-consistency, optional-role rule, semantics carried verbatim | **not implemented by design**: E-73/E-74 contracts; E-72 only stores the data (Global Constraints) |
| §6.1 | `NodePort` (out-port plain), `NodeTypeSpec`, `NODE_TYPES` read-only | 1 (`NodePort`), 4 |
| §6.2 | `PAYLOAD_TYPES` seed (6 entries) | 4 |
| §6.3 | `find_port`, `ports_compatible`, `check_node_types` checks 1–6, sorted problems, `registry=` injection | 4 |
| §6.4 | seed catalog: 9 types, kinds/roles/canonical stages/ports; no `gate.clarify` | 4 |
| §7.1 | canonical form, `content_sha`, golden sha, explicit default = omitted, `extra_args` order kept | 3 |
| §7.2 | `to_yaml` deterministic with cosmetics; `from_yaml` single `GraphSchemaError`; version pre-check | 2 |
| §7.3 | versioning policy | documentary; pinned by golden sha (3) and `schema_version` tests (1, 2) |
| §8 | test matrix rows: model / content_sha / io / node_types / purity; fixture | 1, 3, 2, 4, 5 |
| §9 | untouched modules; docs on landing | 6 |
| §10 | E72-OQ-1…8 | not decided (Global Constraints) |
