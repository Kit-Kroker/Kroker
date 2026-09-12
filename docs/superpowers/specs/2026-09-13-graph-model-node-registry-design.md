# E-72 — `PipelineGraph` model + node-type registry (FR-1201) — design

| | |
|---|---|
| Epic | E-72 (pipeline-as-data, Phase 0) → FR-1201 |
| Date | 2026-09-13 |
| Status | reviewer-approved (2026-09-13); pending user gate on E72-OQ-1..E72-OQ-8 |
| Normative text | `PRD.md` §6 FR-1201 (FR-1202/FR-1203 for boundary only) |
| Framing | `docs/roadmap/pipeline-as-data.md` (2026-08-06 decisions are binding) |
| Consultation log | `.workspace/tmp/e72-consult-q1.md` … `e72-consult-q8.md` (planner↔advisor, uncommitted scratch); reviewer pane approved after one fix round |

## 1. Purpose and deliverable

E-72 freezes the graph **schema**: the contract that E-73 (router + validator)
and E-76 (canvas) build against in parallel. The deliverable is schema
stability, not breadth. E-72 ships:

1. The stored models `PipelineGraph` / `GraphNode` / `GraphEdge` and the
   registry model `NodePort`.
2. `content_sha()`: the graph's identity, computed from a canonical form that
   excludes canvas cosmetics.
3. A static node-type registry: the mechanism, a self-check, the port
   compatibility rule, and a seed catalog.
4. A deterministic YAML serializer/deserializer for the `graphs/<sha>.yaml`
   storage shape. Storage itself is out of scope.

It changes no existing behaviour. Nothing in `src/` outside the new package
imports it until E-74.

## 2. Decisions (user-approved, advisor consensus)

| # | Decision |
|---|---|
| D1 | **Static Python registry.** `NODE_TYPES` in `sdlc/graph/node_types.py`. No YAML registry, and no decorators on handlers. |
| D2 | **Self-check timing.** `check_node_types()` runs from a unit test in E-72. Wiring it into worker boot, together with `set(NODE_TYPES) == dispatch table`, lands in E-74, the first runtime consumer. Not in `sdlc doctor`. |
| D3 | **Port model.** Ports declare `name`, `direction`, `payload` (a model-name string, or `None` for a signal port), `required` and `multiplicity`. Payload names resolve through an explicit allowlist, `PAYLOAD_TYPES`. |
| D4 | **Compatibility.** Exact nominal payload equality from an out-port to an in-port, with `None == None` for signal ports. No subtyping, no `Any`, no type variables. |
| D5 | **Parsing vs legality.** Parsing is shape-only. Every referential or legality check belongs to E-73's `validate.py`, so the canvas can still load a broken draft in order to show its errors. E-72 ships the predicate that *defines* compatibility. `validate.py` is the only place that rejects a well-shaped graph on legality grounds. `from_yaml` rejects only text that is not a well-shaped graph (§7.2). |
| D6 | **Node role.** `GraphNode.role: RoleConfig \| None` has the exact semantics of a `PipelineConfig.roles` entry for the node type's registry role. Prompts stay in `agents/<role>/instructions.md`. |
| D7 | **Gates are node types**, one concrete type per gated payload, each carrying `GraphNode.gate: GateConfig \| None` with `PipelineConfig.gates`-entry semantics. A gate's identity is its node id. Handler-internal HITL (clarify Q&A, `task:<id>`, `tool_approval`, `deploy_failed`, `budget`) stays inside handlers. |
| D8 | **Catalog scope.** E-72 ships the mechanism plus a seed catalog for the typed pre-code half. The post-plan half, including decomposing `code`, belongs to E-74. Run context is never a port. Every function that reads the registry takes `registry=NODE_TYPES` as a parameter. |
| D9 | **Canonical form.** `exclude_defaults`, cosmetics stripped, nodes and edges sorted, keys sorted, then sha256. `schema_version: Literal[1]` is required. Additive optional fields do not bump the version. |
| D10 | **PipelineConfig boundary.** E-72 touches nothing in `PipelineConfig`, reserves no settings slot, and forbids an untyped `params`. |

## 3. Verified anchors (and one corrected hypothesis)

- `RoleConfig` is `src/sdlc/core/models.py:176`, `GateConfig` is `:57`, `gate_key` is `:228`. `core/` imports no stage and no horizontal package.
- **Correction to the brief:** `config/agents.yaml` does not exist. The registry is the `agents/` directory (`agents/registry.yaml` plus one `agents/<role>/` per role), loaded by `src/sdlc/agents/loader.py`. `load_registry()` validates at import of `agents/roles.py` (`REGISTRY = load_registry()`). `_validate_pipeline_mirror` asserts that `PipelineConfig().roles` equals the registry's harness roles.
- `PROMPT_SHAS` (`agents/roles.py:196`) is keyed by **stage** through `STAGE_ROLES` (for example plan→planner). The memo key (`workflows/role_host.py:_cached_stage`) is `content_key(stage, input_json, PROMPT_SHAS[stage]+digest, resolve_role_model(cfg, stage), watermark)`. No graph identity enters a memo key. So "a canvas tidy invalidates nothing" holds structurally. "A role edit invalidates exactly that role's memos" holds as long as E-74 projects `node.role` into the cfg that `resolve_role_model` reads (§9, E-74 obligations).
- `CANONICAL_STAGES` is `benchmarks/heatmap.py:25`. `heatmap` imports `benchmarks.models`, which imports `agents.loader`, `harness.models` and `stages.plan.models`: the open cycle in `.workspace/tasks/2026-09-12-b0-lazy-step-export-shadowing.md`. `graph/` therefore never imports `benchmarks` at module level. Note that the list spells the stages `planning` and `architecture`, not `plan`/`architect`.
- `RoleConfig` and `GateConfig` use pydantic's default `extra="ignore"`. Verified: `RoleConfig.model_validate({"modle": "x", "model": "m"})` silently drops `modle`.
- Handler IO is not yet port-shaped. Many `step()` parameters are `Any`, several return a status `str`/`None`, and inputs mix artifacts with run state. Converging on `(Activation, PipelineConfig) -> Emission` is E-74's job.

## 4. Package layout and import rules

A new horizontal package, `src/sdlc/graph/`. It serves the whole pipeline and is not a stage slice, so it does not appear in AGENTS.md's stage table.

| module | contents | allowed module-level imports |
|---|---|---|
| `model.py` | `NodePosition`, `NodePort`, `GraphNode`, `GraphEdge`, `PipelineGraph`, `canonical_json()`, `PipelineGraph.content_sha()` | stdlib, `pydantic`, `sdlc.core.models` |
| `payloads.py` | `PAYLOAD_TYPES: Mapping[str, str]` | stdlib only |
| `node_types.py` | `NodeTypeSpec`, `NODE_TYPES`, `find_port()`, `ports_compatible()`, `check_node_types()` | stdlib, `pydantic`, `sdlc.graph.model`, `sdlc.graph.payloads` |
| `io.py` | `to_yaml()`, `from_yaml()`, `GraphSchemaError` | stdlib, `yaml`, `sdlc.graph.model` |
| `__init__.py` | eager re-exports of the names above | the four modules only |

`check_node_types()` performs its heavy imports **inside the function body**:
`importlib` for payload classes, `sdlc.benchmarks.heatmap.CANONICAL_STAGES`,
and `sdlc.agents.loader.KNOWN_ROLES`. It must never import `sdlc.agents.roles`,
which builds agents at import. An AST purity test (§8) pins the
**module-level** import sets. It follows the idiom of
`tests/test_change_scope.py::test_module_is_pure`, but inspects only
top-level statements so that the function-local imports stay legal.

## 5. Stored schema (`model.py`)

All stored models use `ConfigDict(frozen=True, extra="forbid")`.

```python
_ID = r"^[a-z][a-z0-9_]*$"                          # node ids, port names
_TYPE = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"   # "architect", "gate.plan"

class NodePosition(BaseModel):          # cosmetic
    x: float
    y: float

class GraphNode(BaseModel):
    id: str = Field(pattern=_ID)
    type: str = Field(pattern=_TYPE)
    role: RoleConfig | None = None      # D6
    gate: GateConfig | None = None      # D7
    position: NodePosition | None = None  # cosmetic
    label: str | None = None              # cosmetic

class GraphEdge(BaseModel):
    source: str = Field(pattern=_ID)
    source_port: str = Field(pattern=_ID)
    target: str = Field(pattern=_ID)
    target_port: str = Field(pattern=_ID)
    max_traversals: int | None = Field(default=None, ge=1)  # data for E-73
    label: str | None = None                                  # cosmetic

class PipelineGraph(BaseModel):
    schema_version: Literal[1]          # required, no default
    nodes: list[GraphNode]
    edges: list[GraphEdge]
```

**Why the id regex.** A gate node's id becomes its gate name (D7). That name
appears in `gate_key(name, round)` (`"name#round"`), `GateDecision.gate`, the
calibration bucket and CLI arguments. So `#`, `:` and `.` are excluded by
shape. The regex is a property of a single string, not a referential check,
which is why it runs at parse time (D5).

**Parse-time checks (the complete list):**

1. Field types, required fields and the regexes above.
2. `extra="forbid"` on the four graph models.
3. `schema_version` must be `1`.
4. A `mode="before"` validator on `GraphNode` rejects unknown keys under
   `role` and `gate`. It compares the raw mapping's keys against
   `RoleConfig.model_fields` and `GateConfig.model_fields`. This closes the
   silent-ignore hole (§3) without modifying the core models, which D6/D7
   require to be verbatim. It has to happen at parse time: once pydantic has
   dropped a key, `validate.py` cannot see it. Because the check lives on the
   model, it covers YAML and E-75 JSON alike.

**Order normalization.** Field validators on `PipelineGraph.nodes` and `edges`
return sorted copies:

- nodes by `(id, cosmetic-stripped JSON of the node, full JSON of the node)`;
- edges by `(source, source_port, target, target_port, cosmetic-stripped JSON, full JSON)`.

Both JSON tiebreaks use `mode="json", exclude_defaults=True, sort_keys`.
Together they make the order total even for an illegal draft with duplicate
ids or edges, which `validate.py` will reject later. The cosmetic-stripped key
comes first so that the sha never depends on layout, even for such a draft. Sorting is
normalization, not a check. After it, two graphs that differ only in author
order compare `==`, serialize identically and hash identically.

**Everything else goes to `validate.py` (E-73), explicitly not E-72:**

- unique node ids, and no duplicate edges;
- edge endpoints that name existing nodes;
- `node.type ∈ registry`, and ports that exist with the right direction;
- port compatibility, via `ports_compatible`;
- required in-ports connected;
- `role` set only on a type with `NodeTypeSpec.role`, and `gate` only on `kind == "gate"`;
- `role.instructions is None and role.tool_files == []` (loader-owned fields);
- `node.role.kind == REGISTRY[NodeTypeSpec.role].kind`, plus the loader's
  per-kind invariants that `validate_registry` already enforces. Today the
  only one is that a `kind="research"` override must name a `provider`
  (`agents/loader.py` `validate_registry`). Every role in today's registry
  also has `harness` set only when `kind: harness`, but the loader does not
  enforce that, and E-72 does not invent it.
  `RoleConfig()` defaults to `kind="harness"`, so without this clause a
  proposer node could carry a harness-kind entry that no existing constructor
  produces (`cli_roles.build_role_overrides` and `benchmarks/workflow.py` both
  set `kind` explicitly);
- a node whose type's `NodeTypeSpec.role` is an `OPTIONAL_ROLES` member
  absent from the loaded registry (for example `research` on a tree without
  `agents/research/`) is rejected, whether or not it carries `role`. This is
  today's `t_research is not None` guard expressed as topology. It is a
  rejection, never a `KeyError` on `REGISTRY[...]`;
- reachability, bounded cycles, exactly one entry node.

**Semantics carried verbatim (contract for E-74, not implemented here):**

- `node.role is None` means the registry default. A non-None `node.role`
  *replaces* the `PipelineConfig.roles[NodeTypeSpec.role]` entry for that
  node's activation. Readers keep picking fields exactly as today; for
  example, `resolve_role_model` reads `.model`. Note that `role: {}` (an
  explicit all-defaults `RoleConfig`) is **not** equivalent to an absent
  `role`. It hashes differently (verified). For a proposer or research type,
  the kind-consistency rule above makes `validate.py` reject it.
- `node.gate is None` falls back exactly as today:
  `PipelineConfig.gates[node.id]`, else `default_gate_policy`. A node's `gate`
  accepts only the mapping form. `PipelineConfig.gates`' bare-policy shorthand
  (`plan: soft`, coerced by `GateConfig._coerce`, `core/models.py:70-76,342-347`)
  is **deliberately not accepted** on graph nodes. "Entry semantics" means
  resolution and meaning, not input coercion parity, and E-74 must not assume
  coercion parity.
- `edge.max_traversals`: `None` means the edge itself is unbounded. Which
  cycles must carry a bound, and what exhaustion does, is E-73's.

## 6. Registry, payloads, compatibility (`node_types.py`, `payloads.py`)

### 6.1 Models

```python
class NodePort(BaseModel):              # in model.py; frozen, extra="forbid"
    name: str = Field(pattern=_ID)
    direction: Literal["in", "out"]
    payload: str | None                 # PAYLOAD_TYPES key; None = signal port
    required: bool = True               # meaningful on in-ports only
    multiplicity: Literal["one", "many"] = "one"   # "many" = collect; in-ports only

class NodeTypeSpec(BaseModel):          # frozen, extra="forbid"
    type: str = Field(pattern=_TYPE)
    kind: Literal["stage", "gate"]
    role: str | None                    # registry ROLE name (KNOWN_ROLES), None = role-less
    canonical_stage: str | None         # CANONICAL_STAGES member; None records as "unknown"
    ports: tuple[NodePort, ...]         # declaration order kept for the palette

NODE_TYPES: Mapping[str, NodeTypeSpec]  # key == spec.type
```

`NodePort` validator: an out-port with `multiplicity="many"` or
`required=False` is a construction error. It is safe to reject this eagerly
because `NodePort` is authored in code and never stored.

The registry is Python code, not stored data. A graph stores only `type` and
port **names**, and it resolves them against the registry of the worker's code
version. `NodePort` and `NodeTypeSpec` can therefore gain fields (for example
palette `display_name`/`description` for E-76) without any change to the graph
schema.

### 6.2 Payload allowlist

`PAYLOAD_TYPES` maps a model name to `"module.path:ClassName"`. The seed:

| name | target |
|---|---|
| `CodebaseMap` | `sdlc.context.models:CodebaseMap` |
| `ResearchBrief` | `sdlc.stages.research.models:ResearchBrief` |
| `ClarifiedRequirements` | `sdlc.stages.clarify.models:ClarifiedRequirements` |
| `ArchitectureSpec` | `sdlc.stages.architecture.models:ArchitectureSpec` |
| `ImplementationPlan` | `sdlc.stages.plan.models:ImplementationPlan` |
| `GateDecision` | `sdlc.core.models:GateDecision` |

A port names the class its consumer needs, and it must live in a `models`
module. So research's port is `ResearchBrief`, not the `ResearchOutcome`
subclass defined in `stages/research/step.py`.

### 6.3 Functions

```python
def find_port(spec: NodeTypeSpec, name: str, direction: Literal["in","out"]) -> NodePort | None
def ports_compatible(out_port: NodePort, in_port: NodePort) -> bool
    # out_port.direction == "out" and in_port.direction == "in"
    # and out_port.payload == in_port.payload   (None == None; named vs None -> False)
def check_node_types(registry: Mapping[str, NodeTypeSpec] = NODE_TYPES) -> list[str]
```

`check_node_types` returns problem strings **sorted**, with an empty list
meaning healthy. E-74's boot wiring will raise when the list is non-empty.
Checks, iterating `sorted(registry)`:

1. Each key equals `spec.type`.
2. Port names are unique within a type, across both directions, so a canvas
   handle name is unambiguous.
3. Every non-None `payload` is a `PAYLOAD_TYPES` key. Each referenced entry
   resolves through `importlib` to a class whose `__name__` equals the key and
   which subclasses `pydantic.BaseModel`.
4. `canonical_stage` is `None` or a member of `CANONICAL_STAGES`.
5. `role` is `None` or a member of `agents.loader.KNOWN_ROLES`.
6. Gate-kind shape:
   - `role is None`;
   - exactly one in-port `artifact` with payload T ≠ None;
   - an out-port `approve` with payload T;
   - an out-port `reject` with payload `None`;
   - optionally an out-port `revise` with payload `GateDecision`;
   - no other ports.

   The router and canvas can then treat every gate uniformly without generics.

### 6.4 Seed catalog

Type names equal `STAGE_ROLES` stage keys where one exists (`clarify`,
`architect`, `plan`, `research`), so E-74 can reach `PROMPT_SHAS[type]`
without a second mapping.

| type | kind | role | canonical_stage | in-ports (payload, required?) | out-ports |
|---|---|---|---|---|---|
| `intake` | stage | — | intake | — | `ok: None` |
| `context` | stage | — | context | `trigger: None` | `map: CodebaseMap` |
| `research` | stage | research | research | `trigger: None`; `guidance: GateDecision` (opt) | `brief: ResearchBrief` |
| `clarify` | stage | clarify | clarify | `trigger: None` (opt); `codebase_map: CodebaseMap` (opt); `research: ResearchBrief` (opt) | `requirements: ClarifiedRequirements` |
| `architect` | stage | architect | architecture | `requirements: ClarifiedRequirements`; `codebase_map: CodebaseMap` (opt); `guidance: GateDecision` (opt) | `spec: ArchitectureSpec` |
| `plan` | stage | planner | planning | `spec: ArchitectureSpec`; `requirements: ClarifiedRequirements` (opt); `guidance: GateDecision` (opt) | `plan: ImplementationPlan` |
| `gate.research` | gate | — | research | `artifact: ResearchBrief` | `approve: ResearchBrief`; `revise: GateDecision`; `reject: None` |
| `gate.architecture` | gate | — | architecture | `artifact: ArchitectureSpec` | `approve: ArchitectureSpec`; `revise: GateDecision`; `reject: None` |
| `gate.plan` | gate | — | planning | `artifact: ImplementationPlan` | `approve: ImplementationPlan`; `revise: GateDecision`; `reject: None` |

Notes:

- **No `gate.clarify`.** `stages/clarify/step.py:199` reads
  `cfg.gates["clarify"].policy` only to choose between auto-filled suggested
  answers and `ctx.ask_and_wait` Q&A. That is handler-internal HITL (D7), so
  clarify's policy stays run-scoped in `PipelineConfig.gates["clarify"]`.
- **Trigger ports.** `trigger` signal in-ports let a graph express ordering
  for types with no required data input, because run context is not a port
  (D8). What activates a node whose connected in-ports are all optional is
  E-73's call (E72-OQ-5).
- **Gate stages.** A gate's `canonical_stage` is its producer's stage, so a
  pending architecture gate shows on the architecture column (FR-1206: the
  right canonical stage, not a silent default).
- **Research loop.** Research's revise loop is handler-internal today
  (`stages/research/step.py:298-343`). `gate.research` is expressible now;
  unwinding the handler loop is E-74's.

## 7. Identity and storage shape (`content_sha`, `io.py`, versioning)

### 7.1 Canonical form

```python
_COSMETIC = {"nodes": {"__all__": {"position", "label"}}, "edges": {"__all__": {"label"}}}

def canonical_json(graph: PipelineGraph) -> str:
    data = graph.model_dump(mode="json", exclude_defaults=True, exclude=_COSMETIC)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

PipelineGraph.content_sha(self) -> str:   # sha256(canonical_json(self).encode("utf-8")).hexdigest()
```

- **Node and edge order** is already normalized (§5).
- **Inner lists** such as `RoleConfig.extra_args` keep author order, because
  order is meaningful there.
- **`schema_version`** has no default and is therefore always hashed.

Why `exclude_defaults`:

- **Full dump:** adding any optional field to `GraphNode`, `RoleConfig` or
  `GateConfig` would silently re-sha every stored graph.
- **`exclude_unset`:** depends on the construction path, so an explicit
  `policy: hard` and an omitted one would give two shas for one meaning.
- **`exclude_defaults`:** gives one sha per meaning, and additive optional
  fields stay sha-stable.

**Stated property, not a defect.** Changing a *default* inside `RoleConfig` or
`GateConfig` changes behaviour under an unchanged sha. The sha identifies
authored content. Behaviour already also depends on the worker's code and on
the agents registry.

### 7.2 YAML

- **`to_yaml(graph) -> str`:**
  `yaml.safe_dump(graph.model_dump(mode="json", exclude_defaults=True), sort_keys=False, allow_unicode=True, default_flow_style=False)`.
  - Cosmetics are **included**, since the canvas needs them.
  - Key order follows model field order, and node/edge order is normalized.
  - Output is deterministic.
- **`from_yaml(text) -> PipelineGraph`:** raises exactly one exception type,
  `GraphSchemaError` (a `ValueError` subclass), for every way the text fails
  to become a graph. E-75/E-76 get a single catch contract.
  - `yaml.safe_load`; a `yaml.YAMLError` is re-raised as `GraphSchemaError`
    (chained);
  - a non-mapping document raises `GraphSchemaError`;
  - a `schema_version` other than `1` raises
    `GraphSchemaError("unsupported graph schema_version …; this worker reads 1")`
    before model validation, mirroring the version check on `agents/registry.yaml`;
  - otherwise `PipelineGraph.model_validate`; a `pydantic.ValidationError` is
    re-raised as `GraphSchemaError` (chained with `from`, so the structured
    errors stay reachable via `__cause__`).
- **`graphs/<sha>.yaml`:** the file name is `content_sha()`, and the content is
  `to_yaml()`. Writing, reading and lookup belong to E-75/E-77.

### 7.3 Versioning policy

- `schema_version: Literal[1]` is required. No migration machinery ships
  until a v2 exists.
- **No bump:** adding an optional field with a default to `PipelineGraph`,
  `GraphNode` or `GraphEdge`. This is sha-stable under §7.1.
- **Bump:** removing or renaming a field, or changing what an existing field
  means.
- **Migrations:** a migration produces a **new** graph with a **new** sha.
  Stored files are immutable, and runs keep their pinned sha (FR-1203).
  Readers for old versions are retained for as long as E-77 must render runs
  that used them.
- **Registry changes** (new types, new `NodePort` fields) never touch
  `schema_version`.

## 8. Testing

Tests go under `tests/graph/`, fast tier, no markers. Fixture:
`tests/graph/fixtures/pre_code.graph.yaml`, a greenfield-with-research
pre-code graph: intake → research → gate.research → clarify → architect →
gate.architecture → plan → gate.plan. It has revise edges back to each
producer's `guidance` with `max_traversals: 2`, plus positions and labels.

| test file | pins |
|---|---|
| `test_model.py` | Shape rejections: bad id or port regex; extra key on each of the four models; typo under `role` (`modle`) and under `gate`; missing `schema_version`. Parse is shape-only: a graph with a dangling edge, unknown type, duplicate ids and incompatible ports **parses**. Order normalization: permuted construction compares `==`. `role: {}` ≠ absent `role`. |
| `test_content_sha.py` | **Golden sha** for the fixture (a literal hex, so any accidental change to the canonical form fails). **NFR-10 order independence:** sha and `canonical_json` byte-identical across `itertools.permutations` of nodes × edges on a small 4-node/4-edge graph. Invariant under `position`/`label` edits. Changes under an edit of `role.model`, `gate.policy`, `max_traversals`, `type`, or any edge endpoint. Explicit default equals omitted (`policy: hard`). |
| `test_io.py` | `from_yaml(to_yaml(g)) == g`. Fixpoint: `to_yaml(from_yaml(to_yaml(g))) == to_yaml(g)`. NFR-10: `to_yaml` byte-identical across permutations. Malformed YAML, a non-mapping document, `schema_version: 2`, and a shape failure (bad id, `role` typo) all raise `GraphSchemaError`. For the shape failure, `__cause__` is a `pydantic.ValidationError`. The fixture file round-trips. |
| `test_node_types.py` | `check_node_types() == []` for the seed. Injected broken registries yield the expected sorted problems (unknown payload, payload name/class mismatch, bad `canonical_stage`, unknown role, duplicate port name, malformed gate, key ≠ type). NFR-10: result identical across registry insertion-order permutations. `ports_compatible` truth table (named/named equal, named/named different, None/None, named/None, wrong directions). `NodePort` rejects out-port `many` or `required=False`. |
| `test_graph_purity.py` | Top-level imports of each `sdlc/graph/*.py` stay within §4's sets. A cold `import sdlc.graph` in a subprocess leaves `sdlc.benchmarks`, `sdlc.stages`, `sdlc.agents` and `temporalio` absent from `sys.modules`. |

The standard gates also apply: `ruff check`, `ruff format --check`, `mypy`,
and `scripts/check_file_size.py`.

## 9. Boundaries

**FR-1201 traceability.** Each clause and where it is discharged:

| FR-1201 clause | discharged by |
|---|---|
| expressible as a `PipelineGraph` of typed nodes and edges | E-72 (§5, §6) |
| nodes carry `RoleConfig` and `GateConfig` verbatim | E-72 stores them unmodified (§5). Keeping registry validation, ADR-6 and `PROMPT_SHAS` working depends on E-74 obligation 1 below and on E72-OQ-1. |
| ports declare payload types by existing model name | E-72 (§6.1, §6.2) |
| an edge between incompatible ports SHALL be rejected | **Jointly.** E-72 ships the definition (`ports_compatible`, §6.3) and its truth-table tests. **Enforcement is FR-1202's `validate.py` (E-73).** E-72's acceptance criteria claim no rejection behaviour (parsing a graph with incompatible ports succeeds by design, §8), and E-73 cannot close without it. |
| graph identity is a `content_sha()` excluding `position` and `label` | E-72 (§7.1) |
| tidying the layout never invalidates a memoization | Structural: no graph identity enters `content_key` (§3). E-72 pins the sha invariance under cosmetics. |

**Out of scope:**

- E-73: routing, activation, rounds, `validate.py`;
- E-74: the interpreter, handler convergence, `default.graph.yaml`, boot wiring, post-plan catalog;
- E-75: API;
- E-76: canvas;
- E-77: store, `graph_sha` on runs;
- OQ-14: subflows.

**Obligations handed to E-74** (recorded so the freeze is honest):

1. Project `node.role` into the cfg that `resolve_role_model` / `_cached_stage`
   read, so a role edit moves exactly that stage's memo key.
2. Wire `check_node_types()` into worker boot and assert
   `set(NODE_TYPES) == set(dispatch table)`.
3. Catalogue the post-plan half.

**Unchanged by E-72:** `PipelineConfig`, `resolve_role_model`,
`agents/loader.py`, `agents/roles.py`, all stages, `benchmarks/`.

**Docs on landing** (docs describe `main`): tick the E-72 row in
`docs/roadmap/pipeline-as-data.md` and its ROADMAP mirror, and add
`sdlc/graph/` to ARCHITECTURE's component list. No stage clause changes.

## 10. Open questions (for the user gate)

- **E72-OQ-1 — ADR-6 over graphs (owner E-73).** The schema allows two nodes of one type with different `role.model` values. `validate_run_roles` takes one model per role. Should the validator collapse (for example, every reviewer model must differ from every dev model), or reject?
- **E72-OQ-2 — gate rename (owner E-73/E-76).** Gate identity is the node id, so renaming a gate node changes its signal name and CLI argument and resets its calibration history `(gate, author_model)`. Options: accept this, have the canvas warn on renaming a gate node, or add a stable `gate_name` later (an additive field).
- **E72-OQ-3 — post-plan catalog and `code` decomposition (owner E-74; see OQ-14).** Covers code, analyze, merge + `gate.merge`, deploy + `gate.deploy`, retro. `code` spans seven roles, and `max_fix_attempts → max_traversals` needs the task loop as topology. A per-task chain touches E-73 fan-out and possibly subflows.
- **E72-OQ-4 — failure port (owner E-74).** "Exceptions become `fail` emissions" needs a `fail` out-port convention and a payload model that doesn't exist yet. Adding it is additive to the registry.
- **E72-OQ-5 — activation semantics (owner E-73).** What activates a node whose connected in-ports are all optional (`trigger`, `clarify`)? What does `multiplicity: "one"` mean when several edges target it across rounds?
- **E72-OQ-6 — role precedence (owner E-74).** Which wins when `node.role` and a run-level `cfg.roles` override (CLI `--role-model`, benchmark arms) are both set?
- **E72-OQ-7 — cosmetic last-write-wins (owner E-77).** Two layouts of one graph share `graphs/<sha>.yaml`, so re-saving a tidy overwrites the layout for every run pinned to that sha.
- **E72-OQ-8 — registry drift vs pinned graphs (owner E-77).** A stored graph resolves types and ports against the current worker's registry. If a later registry change renames or removes a port, a post-mortem render of an old graph can fail validation. Should the store snapshot the resolved port specs next to the graph?
