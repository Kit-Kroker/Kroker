# Data model — E-77 (Phase 1)

Every addition is **optional** on existing models (FR-024). New models are frozen pydantic models. Graph-layer models use `extra="forbid"`. The `core/` envelopes keep pydantic's default `extra="ignore"` (project memory: never demand `forbid` on core envelopes).

## Constants and pure functions (graph layer)

| name | module | shape | rule |
|---|---|---|---|
| `UNKNOWN_STAGE` | `sdlc/graph/node_types.py` | `"unknown"` | never a `CANONICAL_STAGES` member (test-pinned) |
| `resolve_stage(node_type, registry)` | `sdlc/graph/node_types.py` | `str` | `registry[t].canonical_stage` if registered and not `None`, else `UNKNOWN_STAGE` (FR-003/006) |
| `check_node_types(registry, *, require_mapped=True)` | same | `list[str]` | existing checks plus `"<type>: no canonical_stage"` when `require_mapped` (FR-001) |
| `PipelineGraph.document_sha()` | `sdlc/graph/model.py` | 64-hex | sha256 of the canonical JSON **with** cosmetics (`exclude_defaults=True`); layout identity (FR-019) |
| `fail_reentry(activation, state, topology)` | `sdlc/graph/run_view.py` | `int \| None` | `None` = no inbound fail back edge; `1` = an input ref `"<aid>.fail"` arrived over a fail back edge; `0` otherwise (FR-015) |
| `stage_marks(...)` | `sdlc/graph/run_view.py` | changed | unregistered/unmapped nodes contribute under `UNKNOWN_STAGE` instead of being skipped (FR-005) |
| `registry_sha(registry)` / `snapshot_registry(registry)` / `load_registry(doc)` | `sdlc/graph/store.py` | — | canonical snapshot document and its hash; `load_registry` returns `None` on any failure (FR-022/023) |

## `GraphAttribution` (new; `sdlc/benchmarks/models.py`)

Carried by `BenchmarkRecord.graph: GraphAttribution | None = None`. It is `None` for FeatureWorkflow and pre-E-77 records.

| field | type | meaning |
|---|---|---|
| `graph_sha` | `str` | the run's pinned graph sha (FR-010) |
| `activation_id` | `str \| None` | `ACTIVATION` at record time; `None` outside any activation (preamble, retro, oracle) |
| `node_id` | `str \| None` | the activation's node |
| `round` | `int \| None` | the router round of that activation (FR-014) |
| `node_stage` | `str \| None` | `resolve_stage(node.type)`: a canonical stage or `unknown` |
| `fail_reentry` | `int \| None` | the R-5 indicator captured at issue time; `None` = axis absent (FR-015/016) |

Invariants:

- When `activation_id is None`, then `node_id`, `round`, `node_stage` and `fail_reentry` are all `None`.
- When `node_stage == "unknown"`, then `record.stage == "unknown"` (G2).
- `fail_reentry ∈ {None, 0, 1}`.

## `BenchmarkRecord` (existing; `sdlc/benchmarks/models.py:135`)

- **+** `graph: GraphAttribution | None = None`
- Unchanged: `stage`, `fix_attempts` (handler count), `attempt`. `stage` is overridden only by the G2 rule.

## `RunSummary` / `RunState` (existing; `sdlc/core/models.py:477/507`)

- **+** `graph_sha: str | None = None` on both (FR-009). FeatureWorkflow leaves it `None`.
- `RunState.stage_marks` keys may now include `"unknown"` (FR-005); `DotState` values are unchanged.

## Dispatcher per-activation facts (workflow memory; `sdlc/workflows/graph_dispatch.py`)

`self._attrib: dict[str, ActivationAttrib]`, keyed by activation id and filled in `_start`, with fields `node_id`, `round`, `node_stage`, `fail_reentry`. Owner: `GraphDispatcher`. Reader: `GraphWorkflow._stamp`. It is memory only and issues no commands (FR-025). A row goes into `workflows/AGENTS.md`.

## Store files (`sdlc/graph/store.py`, root = `default_root()`)

| path | content | mutability | verified iff |
|---|---|---|---|
| `graphs/<sha>.yaml` | `to_yaml(graph)` | immutable, first write wins (as today) | parses and `content_sha == sha` |
| `graphs/<sha>/layouts/<layout_sha>.yaml` | `to_yaml(graph)` incl. cosmetics | immutable | parses, `document_sha == layout_sha` and `content_sha == sha` |
| `graphs/<sha>/latest` | one `layout_sha` line | **mutable**: written only by `save()`, via tmp + `os.replace` with bounded retry | names a verifying layout; otherwise it is ignored and `<sha>.yaml` is served |
| `graphs/registry/<registry_sha>.json` | `RegistrySnapshot` | immutable | parses, `schema == 1` and hash == name |
| `graphs/runs/<enc(run_id)>.json` | `RunGraphPointer` | replaced per run id (tmp + `os.replace`) | parses; each named file verified **independently** |

### `RegistrySnapshot` (graph layer)

`{schema: Literal[1], node_types: list[NodeTypeSpec-as-json]}`, sorted by type, with defaults included and port order kept.

### `RunGraphPointer` (graph layer)

| field | type |
|---|---|
| `schema` | `Literal[1]` |
| `run_id` | `str` |
| `graph_sha` | 64-hex |
| `layout_sha` | 64-hex |
| `registry_sha` | 64-hex \| `None` (the snapshot write failed) |
| `roles` | `dict[str, RoleConfig]` (the `GraphRunInput.roles` the run was started with) |
| `started_at` | `datetime` (client clock; informational) |

Reader contract (FR-012): any field that fails verification reads as "not recorded". The pointer is never fatal.

## Store API (`GraphStore`)

| method | behaviour |
|---|---|
| `put(graph) -> str` | unchanged identity write, **plus** a layout write; never touches `latest` |
| `save(graph) -> tuple[str, str]` | `put` + move `latest`; returns `(sha, layout_sha)` |
| `get(sha, layout=None) -> PipelineGraph \| None` | with `layout`: that layout or `None`. Without it: the `latest` layout if it verifies, else the identity file |
| `put_registry(registry) -> str` / `get_registry(registry_sha)` | snapshot write / load (`None` on failure) |
| `put_pointer(p)` / `get_pointer(run_id)` | pointer write / read (`None` if absent, unparseable or the run id is unsafe) |

## Wire (`sdlc/dashboard/graph_wire.py`)

| model | change |
|---|---|
| `SaveOk` | **+** `layout_sha: str \| None = None` (the provisional shape is otherwise kept) |
| `LoadOk` | **+** `layout_sha: str \| None = None` |
| `Capabilities` | `save=True`, `load=True`; `run_graph` and `validate` unchanged |
| `NodeRunState` | **+** `canonical_stage: str \| None = None`, filled by `resolve_stage` (US3, FR-003) |
| `GraphState` | unchanged (`graph_sha` already present) |
| `GraphStateUnavailable` (new) | `{kind: "unavailable", reason: "registry_drift" \| "retention_expired", problems: list[str]}` |

## State transitions

- **Pointer:** absent → written at client start → possibly replaced by a later run reusing the same id. There is no other transition.
- **`latest`:** absent → set by the first `save` → replaced by later `save`s. Never set by `put`, backfill or start.
- **Record `stage`:** handler value → `"unknown"` only when `node_stage == "unknown"`.
