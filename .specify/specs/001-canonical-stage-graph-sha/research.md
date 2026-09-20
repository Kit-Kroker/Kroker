# Research — E-77 (Phase 0)

Every decision below resolves an unknown in the plan's Technical Context. Anchors are main `84ac93a`. Inputs: spec (final), advisor `.workspace/tmp/advisor-e77-1.md`, skeptic `.workspace/tmp/skeptic-e77-1.md`.

## R-1 Stage resolver placement and purity

- **Decision:** `resolve_stage(node_type: str, registry) -> str` plus `UNKNOWN_STAGE = "unknown"` in `sdlc/graph/node_types.py`. It takes the registry as a parameter and never imports `CANONICAL_STAGES`. `run_view.stage_marks` calls it instead of skipping nodes.
- **Rationale:** `tests/graph/test_graph_purity.py` pins `node_types.py` module imports to stdlib, pydantic, `graph.model` and `graph.payloads`. `CANONICAL_STAGES` stays in `benchmarks/heatmap.py:25` and is imported only function-locally by `check_node_types` (`node_types.py:313`), as today. Taking the registry as a parameter makes a registry snapshot usable unchanged (R-6).
- **Alternatives rejected:** putting the resolver in `run_view.py` (records need it outside the view); moving `CANONICAL_STAGES` into `sdlc/graph` (it is the benchmark's vocabulary, and moving it opens the benchmarks ↔ graph cycle the pin exists to prevent).

## R-2 Completeness rule for shipped types (FR-001, FR-004)

- **Decision:** `check_node_types(registry=NODE_TYPES, *, require_mapped: bool = True)`. When `require_mapped` is set, a spec whose `canonical_stage is None` is a problem. The existing rule 4 already rejects `"unknown"`, because it is not in `CANONICAL_STAGES`. A test pins `UNKNOWN_STAGE not in CANONICAL_STAGES`.
- **Rationale:** Worker boot already raises when the check is non-empty (E-74 wiring), so shipped completeness is enforced where it matters. Tests of the `unknown` path build injected registries and never call the self-check with `require_mapped=True`.

## R-3 `graph_sha` on the run summary and live state (FR-009)

- **Decision:**
  - Add `RunSummary.graph_sha: str | None = None` and `RunState.graph_sha: str | None = None` (`core/models.py`).
  - `build_run_summary(..., graph_sha=None)` gains the keyword (`observability/summary.py:136`). `RunHost._retro` passes `getattr(self, "_graph_sha", "") or None`.
  - `GraphWorkflow.run_state` sets `graph_sha` on the snapshot whenever `_graph_sha` is set, independent of whether dispatch has started.
- **Rationale:** `_retro` is shared with FeatureWorkflow. The change alters only activity-argument *content*, never the command sequence; FeatureWorkflow has no `_graph_sha`, so it gets `None` and an identical summary. The U6 grace rule governs command sequence (`workflows/AGENTS.md`), so no `workflow.patched` is needed. `tests/replay/test_feature_replay.py` is the proof.

## R-4 Record stamping path (FR-007, FR-010, FR-014–016, FR-025, FR-027)

- **Decision:** `GraphWorkflow._record(cfg, record)` overrides `BenchmarkHost._record` and calls `super()._record(cfg, self._stamp(record))`. `_stamp` is a pure `model_copy` that sets `record.graph = GraphAttribution(...)` (see data-model) from:
  - `self._graph_sha`;
  - `ACTIVATION.get()`;
  - the dispatcher's per-activation facts: node id, round, resolved node stage, and the fail re-entry indicator captured at issue time (R-5).

  When the resolved node stage is `unknown`, `record.stage` becomes `unknown` too (G2). Otherwise the handler/lens stage is kept.
- **Rationale:**
  - Every stage record in both workflows flows through `ctx.record → BenchmarkHost._record` (`src/sdlc/workflows/benchmark_host.py:94-116`, wired `graph.py:69`).
  - `stage_record` (`benchmarks/record_builder.py`) is a pure builder shared with FeatureWorkflow and knows nothing of activations.
  - Stamping inside the workflow covers in-workflow children (benchmark arms).
  - `_record` already schedules `record_benchmark` with the record as argument, and the golden projection compares only activity, child and timer types (`tests/replay/projection.py:24-37`). Changing argument content adds no command.
  - The STAGE_ENDED emit uses `record.stage`, which changes only for unmapped types, and the shipped graph has none.
  - `stages/code/step.py` (979/1000 lines) is untouched.
- **Alternatives rejected:** stamping in `stage_record` (it would need a ContextVar read from a benchmarks module — the wrong direction for R1, and it would touch FeatureWorkflow paths); flat fields on `BenchmarkRecord` (re-entry dedupe needs the activation id *and* the node's stage; one optional nested model is smaller and easier to keep all-or-nothing).

## R-5 Fail-edge re-entry indicator (FR-015–018, G4)

- **Decision:** a pure `fail_reentry(activation, state, topology) -> int | None` in `sdlc/graph/run_view.py`:
  - **`None`** when no back edge whose source port is `fail` targets the activation's node. Back edges are exactly the edges carrying `max_traversals` (`topology.py:42`); `topology.edges[eid]` gives source, source port, target and target port.
  - **`1`** when a payload ref in `activation.inputs` equals the `payload_ref` of an emission on a `fail` port, and that emission's edge into this node is a fail back edge.
  - **`0`** otherwise.

  `GraphDispatcher._start` computes it next to `self._started[...]` (`graph_dispatch.py:205`) against the router state current at issue time, and keeps it with node id, round and resolved stage in a per-activation dict. Owner: `GraphDispatcher`; reader: `GraphWorkflow._stamp` (add a row to `workflows/AGENTS.md`).
- **Rationale:** `_traverse_back` increments `traversals` and places the token in the edge's slot (`router.py:345-357`). The activation that consumes it is issued later with its inputs as payload refs (`router.py:477-490`). Matching on the consumed ref identifies the entry edge exactly. It is an event, not a count, so summing cannot inflate (skeptic 1.3).
- **Feasibility (G4):** no shipped in-port accepts `NodeFailure` (`node_types.py:63-64`; nominal port equality `node_types.py:256-265`; validator `validate.py:232-234`), so the value is `None` for every legal graph today. It is exercised end-to-end through an injected test registry with an in-port of payload `NodeFailure` and a fail back edge. The dependency is named: a graph-expressed fix loop (per-task topology follow-up, E74-OQ-3).
- **Ref uniqueness (verified):** the dispatcher mints `ref = f"{aid}.{result.port}"` (`graph_dispatch.py:160`), so refs are unique per emission and name their producer and port. The match needs no store lookup; a test pins the format so a future change to ref minting breaks loudly.

## R-6 Store layout (FR-019/020, E72-OQ-7)

- **Decision:**
  - `graphs/<sha>.yaml` is unchanged: the identity file, first write wins, the existing `_verifies`.
  - New: `graphs/<sha>/layouts/<layout_sha>.yaml` holds the full `to_yaml(graph)`, where `layout_sha = PipelineGraph.document_sha()`, a sha256 of `_dumps(model_dump(mode="json", exclude_defaults=True))` with cosmetics *kept* (`graph/model.py`, beside `content_sha`). It is trusted iff it parses, `document_sha() == name` and `content_sha() == <sha>`.
  - New: `graphs/<sha>/latest` is a text file holding one `layout_sha`. It is written tmp + `os.replace` with bounded retry (5 attempts, backoff to about 100 ms) on `PermissionError`/`FileExistsError`; a final failure is logged and never raised. Reads verify the named layout and fall back to `<sha>.yaml`.
  - `GraphStore.put(graph)` keeps its behaviour and also writes the layout file.
  - Only `GraphStore.save(graph)` moves `latest`; `put` never does. That makes history backfill (`run_graph.py:114`) and run start unable to move it (skeptic 2.1).
- **Rationale:** reuses `from_yaml`, `to_yaml` and `PipelineGraph` without a layout model or merge step (advisor D-a). Hashing canonical JSON rather than YAML bytes keeps PyYAML formatting out of identity. Every immutable file follows the existing verify-on-read discipline.
- **Alternatives rejected:** a cosmetics-only layout file (needs a model, edge keys and a merge with drift cases); a timestamped directory scan for "latest" (neither content-addressed nor verifiable, and clock-dependent — skeptic 2.5).

## R-7 Registry snapshot and roles (FR-022/023, E72-OQ-8)

- **Decision:** `graphs/registry/<registry_sha>.json` holds `{"schema": 1, "node_types": [spec.model_dump(mode="json") for spec sorted by type]}`, with defaults *included* and port order preserved. `registry_sha` is the sha256 of the canonical JSON. A load failure (schema mismatch, `extra="forbid"` drift) is treated as no snapshot. Loading yields `MappingProxyType({t: NodeTypeSpec})` for `validate`, `stage_marks` and `resolve_stage`; `check_node_types` is never run on a snapshot (it imports live classes).
- **Rationale:** one file per registry version, deduplicated to almost nothing (advisor D-c). `validate` already takes the registry as a parameter (`validate.py:552-557`), so R1 holds.
- **Roles:** `validate(graph, registry, *, roles=...)` requires roles (`validate.py:556`), and today they come only from the start input (`workflows/models.py:99`). The pointer therefore inlines `roles: dict[str, RoleConfig]` (small; advisor D-b).
- **Documented limit:** the snapshot is the *client's* registry. Client and worker share one checkout here, so this is stated in the spec and not engineered around.

## R-8 Per-run pointer (FR-011/012)

- **Decision:** `graphs/runs/<enc(run_id)>.json` is a `RunGraphPointer` (data-model), written by `start_graph_run` before `client.start_workflow`, after storing the graph, the layout and the registry snapshot. `enc` is the run id when it fully matches `[A-Za-z0-9._-]{1,200}`, is not `.`/`..`, and has no leading `.`; otherwise the pointer is skipped with a warning. It is written tmp + `os.replace` (last write per id on workflow-id reuse). The client start is never blocked. Readers verify each named file and degrade that field only.
- **Rationale:** `default_root()` (`graph/store.py:34-41`) is the one root the client and dashboard already share. Run directories resolve three disagreeing roots (`observability/activities.py:28-35`, `artifacts/store.py:42-46`) and are what operators prune.
- **Alternatives rejected:** `runs/<id>/graph_pin.json` (skeptic 4; root disagreement); Temporal memo/search attributes (bounded by retention, and they change child-start command attributes).

## R-9 Oracle records (FR-010)

- **Decision:** `execute_pipeline_child(..., on_graph: Callable[[str], None] | None = None)`. The graph branch calls `on_graph(run_input.graph.content_sha())` before `execute_child_workflow`. The benchmark parent keeps the sha for the cell and passes it into `_oracle_record` / `_oracle_task_records`, which set `graph=GraphAttribution(graph_sha=...)` with every activation field `None`.
- **Rationale:** the parent does not hold the arm's graph today (`pipeline_child.py:36-44`). A callback adds no command and survives a child that later fails.

## R-10 Run graph routes: drift and retention (FR-012, FR-021, SC-008)

- **Decision:**
  - `RunGraphs.source` stops raising on `report.topology is None` (`run_graph.py:111-112`) and returns a source with `topology=None` and the problems.
  - `/runs/{id}/graph` still serves the graph.
  - `/runs/{id}/graph_state` answers a new `GraphStateUnavailable{kind:"unavailable", reason:"registry_drift", problems}`.
  - When history is gone (describe → NOT_FOUND), `source` falls back to the pointer. The graph route then serves the pinned graph and layout, validated against the pointer's registry snapshot and roles. `graph_state` answers `unavailable/retention_expired`, because no state source exists and E-75 already cannot query closed-and-expired runs.
  - With no pointer, behaviour is unchanged (`404`).
  - When history *is* present and a pointer names a registry snapshot, validation uses the snapshot, so a drifted registry still yields a topology for client-started runs.
- **Rationale:** turns SC-008's server errors into explicit results without a second legality path (skeptic 3.3 rejected, spec P11).

## R-11 Save/load routes and capabilities (FR-020)

- **Decision:**
  - `POST /graphs` goes through the existing capped `_graph_body` (`api.py:189-202`) and requires exactly `{graph}`. It uses `parse_object`: a `ParseErr` becomes 422 and nothing is written. On success it calls `store.save(graph)` and returns `SaveOk{sha, validation, layout_sha}`, where `validation` = `validation()` + `executable()` exactly like `/graphs/validate` (`api.py:224-235`).
  - `GET /graphs/{sha}` rejects a non-64-hex sha with 422 before touching disk. It returns `LoadOk{sha, graph, layout_sha}` (latest layout, falling back to the identity file), accepts an optional `?layout=<layout_sha>`, and returns `LoadMissing` for an unknown sha or layout.
  - `Capabilities.save/load` default to `True` (`graph_wire.py:119-120`). `run_graph` and `validate` stay as on main.
- **Rationale:** the provisional wire and the canvas provider already exist (`graph_wire.py:370-392`; `interfaces/dashboard/frontend/src/api/http-graph.ts:54-60`). The new fields are optional additions, so no frontend production change is needed; the flip regenerates the recorded fixtures and forces two test-only updates (FR-026). `SaveOk.validation` is the existing type.

## R-12 Heatmap fix axis (FR-017)

- **Decision:** `build_heatmap` keeps its per-record loop unchanged. After it, one pass adds 1 to `acc[(case_id, g.node_stage)]["fix"]` for each distinct `(run_id, g.activation_id)` with `g.fail_reentry == 1`. The key is created only if absent; the pass only runs when an indicator exists.
- **Rationale:** counting once per activation on the node's resolved stage removes both skeptic multiplications. When no record carries `graph.fail_reentry == 1`, the pass is a no-op, so output is byte-identical (pinned by a test over recorded records).
- **Not changed:** the pre-existing `attempt − 1` handler convention (E77-OQ-1). *(Subsequently fixed 2026-09-20 — bug `heatmap-fix-inflation`, branch `fix/heatmap-fix-inflation`: E-77's own scope stayed exactly as decided here; the heatmap now takes the counter's max per `(case_id, stage, run_id, task_id)` group, aggregate-side. E77-OQ-1 RESOLVED.)*

## R-13 Docs on landing (R5)

ROADMAP ticks FR-1206 and the E-77 row in `docs/roadmap/pipeline-as-data.md`, naming the follow-ups (canvas run mode / fleet strip, the per-task topology dependency of fail-edge counts, E77-OQ-1). ARCHITECTURE's `sdlc/graph/` line gains the store layout and registry snapshot. E-72 and E-75 get a one-line erratum each: E72-OQ-7 and OQ-8 resolved by E-77; E-75 §1.1 save/load landed.
