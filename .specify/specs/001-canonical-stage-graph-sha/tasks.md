---
description: "Task list for E-77 — graph store + custom-graph benchmark mapping"
---

# Tasks: E-77 — graph store + custom-graph benchmark mapping

**Input**: `.specify/specs/001-canonical-stage-graph-sha/`: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md) (R-1…R-13), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: REQUIRED. Test-first is the project's exec protocol: QA seats write RED tests first, and the reviewer gates each task's diff. Every implementation task follows a RED test task that must fail for the stated reason before code is written.

**Organization**: by user story (spec US1–US5). Foundational work shared by several stories comes first. Phase order follows dependencies: US5's store work precedes US4's routes, and both are P2.

**Standing rules for every task**:
- Run ONE pytest invocation per Bash call.
- No file may exceed 1000 lines (`python scripts/check_file_size.py`); `src/sdlc/stages/code/step.py` stays untouched (FR-027).
- Every workflow module naming a new graph/benchmarks model imports it under `workflow.unsafe.imports_passed_through()`.
- Replay goldens and feature histories are never re-recorded.
- Commits carry no attribution trailers.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1…US5 from spec.md

---

## Phase 1: Setup (baseline)

**Purpose**: prove main is green on every pin E-77 must keep unchanged, before any edit.

- [X] T001 Record the green baseline on main and save the output to `.workspace/tmp/e77-baseline.txt`. Run each command separately: `pytest tests/graph`, `pytest tests/test_benchmark_heatmap.py`, `pytest tests/test_graph_fixtures_fresh.py`, `pytest -m temporal tests/replay`, `python scripts/check_file_size.py`. Any red here is reported to the orchestrator, not fixed inside E-77.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the pure resolver, the optional record/summary fields, layout identity and the store's immutable files. Every story depends on these.

**⚠️ CRITICAL**: no user-story task starts before T012 is done.

- [X] T002 [P] RED tests in `tests/graph/test_graph_node_types.py`:
  - `UNKNOWN_STAGE == "unknown"` and `UNKNOWN_STAGE not in CANONICAL_STAGES`;
  - `resolve_stage(t, NODE_TYPES)` equals each shipped type's `canonical_stage` (all 16);
  - `resolve_stage` returns `"unknown"` for a type absent from the registry and for an injected spec with `canonical_stage=None`;
  - `check_node_types()` is `[]` on the shipped registry;
  - on an injected registry with a `None` stage, `check_node_types(reg)` reports `"<type>: no canonical_stage"` and `check_node_types(reg, require_mapped=False)` does not;
  - a declared `"unknown"` is still reported as not canonical.

  Command: `pytest tests/graph/test_graph_node_types.py` (must fail on the missing names).
- [X] T003 Implement `UNKNOWN_STAGE`, `resolve_stage(node_type, registry)` and `check_node_types(registry=NODE_TYPES, *, require_mapped=True)` in `src/sdlc/graph/node_types.py` (R-1, R-2), and export them from `src/sdlc/graph/__init__.py`. No new module-level imports. Commands: `pytest tests/graph/test_graph_node_types.py`, then `pytest tests/graph/test_graph_purity.py`.
- [X] T004 [P] RED tests in `tests/test_benchmark_models.py`:
  - `GraphAttribution` is frozen, and its invariants hold (activation fields all `None` when `activation_id is None`; `fail_reentry ∈ {None,0,1}`);
  - `BenchmarkRecord.graph` defaults to `None`;
  - a record JSON without `graph` (captured from a current record) parses unchanged.

  Command: `pytest tests/test_benchmark_models.py`.
- [X] T005 [P] RED tests: in `tests/test_run_state_model.py`, `RunState.graph_sha` defaults to `None`; in `tests/test_run_summary_model.py`, `RunSummary.graph_sha` defaults to `None` and a `summary.json` payload written before E-77 (no key) parses. Both check that the envelopes still ignore unknown keys (`extra` stays pydantic's default). Commands: `pytest tests/test_run_state_model.py`, then `pytest tests/test_run_summary_model.py`.
- [X] T006 [P] Implement `GraphAttribution` and `BenchmarkRecord.graph: GraphAttribution | None = None` in `src/sdlc/benchmarks/models.py` (data-model). `fix_attempts`, `stage` and `attempt` are unchanged. Command: `pytest tests/test_benchmark_models.py`.
- [X] T007 [P] Add `graph_sha: str | None = None` to `RunSummary` and `RunState` in `src/sdlc/core/models.py`. `core/` imports nothing new (core Rule 5: `grep -rnE "from \.\.(stages|harness|memory|board|schedules)" src/sdlc/core/` stays empty). Commands: `pytest tests/test_run_state_model.py`, then `pytest tests/test_run_summary_model.py`.
- [X] T008 [P] RED tests in `tests/graph/test_graph_content_sha.py`: `document_sha()` is stable across node/edge reordering; it changes when a node `position` or `label` or an edge `label` changes, while `content_sha()` does not; it is 64-hex and deterministic across runs. Command: `pytest tests/graph/test_graph_content_sha.py`.
- [ ] T009 Implement `PipelineGraph.document_sha()` in `src/sdlc/graph/model.py`: sha256 of `_dumps(model_dump(mode="json", exclude_defaults=True))` with cosmetics kept, placed beside `content_sha` (R-6). Command: `pytest tests/graph/test_graph_content_sha.py`.
- [ ] T010 RED tests in the new `tests/graph/test_graph_store_e77.py` (keeps `test_graph_store.py` small), all with a `tmp_path` root:
  - (a) `put` writes `graphs/<sha>.yaml` unchanged and `graphs/<sha>/layouts/<document_sha>.yaml`; a second `put` with a different layout never rewrites the identity file;
  - (b) a layout file is trusted only if it parses, `document_sha == name` and `content_sha ==` its directory (tamper each, and each is rejected);
  - (c) `put_registry` returns a stable `registry_sha` (one file for two calls); `get_registry` round-trips to a mapping `validate` accepts; a truncated file, a wrong hash, `schema: 2` or an extra field each give `None`;
  - (d) `put_pointer`/`get_pointer` round-trip a `RunGraphPointer` (roles included); unsafe ids (`..`, `a/b`, `.x`, over 200 chars, a non-matching alphabet) write nothing and read `None`; a reused id replaces the pointer atomically; a pointer naming a missing layout still returns its other fields, and readers degrade only that field;
  - (e) the atomic-replace helper retries on simulated `PermissionError` (monkeypatched `os.replace` failing N<5 times, then success), gives up after 5 failures with a log line and no exception, and leaves no `.tmp` files behind.

  Command: `pytest tests/graph/test_graph_store_e77.py`.
- [ ] T011 Implement in `src/sdlc/graph/store.py` (R-6..R-8, contracts/records-and-store.md): the layout write inside `put` (never touching `latest`); `RegistrySnapshot`, `registry_sha`, `put_registry`/`get_registry`; `RunGraphPointer`, the safe-name rule and `put_pointer`/`get_pointer`; a private `_atomic_replace(tmp, target, *, attempts=5)` with bounded backoff. Amend the `store.py` allow-list in `tests/graph/test_graph_purity.py` to add exactly `sdlc.graph.node_types` and `sdlc.core.models`. Commands: `pytest tests/graph/test_graph_store_e77.py`, then `pytest tests/graph/test_graph_store.py`, then `pytest tests/graph/test_graph_purity.py`.
- [ ] T012 Foundational checkpoint: `pytest tests/graph`, then `pytest tests/test_benchmark_models.py tests/test_run_state_model.py tests/test_run_summary_model.py`, then `python scripts/check_file_size.py`.

**Checkpoint**: resolver, record/summary fields, layout identity and immutable store files are all green.

---

## Phase 3: User Story 1 — A post-mortem always names the graph that ran (P1) 🎯 MVP

**Goal**: every graph run records `graph_sha` on its live state, summary and every benchmark record (children and oracle records included). Client-started runs also get a per-run pointer written before start.

**Independent test**: spec US1. Start a non-default graph run; the pointer, `run_state`, `run_summary` and every record carry the same `graph_sha`, and it names a stored graph.

- [ ] T013 [P] [US1] RED tests in `tests/graph_workflow/test_graph_view_dispatch.py`:
  - the dispatcher's `_attrib[aid]` holds `node_id`, `round` (equal to `Activation.round`) and `node_stage` (`resolve_stage` of the node type) for every issued activation;
  - `fail_reentry` is `None` for every activation of the shipped default graph;
  - `_attrib` is written only in `_start` (grep-style pin like the existing `ACTIVATION` set-site pin).

  Command: `pytest tests/graph_workflow/test_graph_view_dispatch.py`.
- [ ] T014 [US1] Implement `ActivationAttrib` and `GraphDispatcher._attrib` in `src/sdlc/workflows/graph_dispatch.py`, filled in `_start` next to `self._started[...]` (`graph_dispatch.py:205`), with `fail_reentry=None` until T027. Memory only, no commands (FR-025). Command: `pytest tests/graph_workflow/test_graph_view_dispatch.py`.
- [ ] T015 [P] [US1] RED unit tests in the new `tests/graph_workflow/test_record_stamping.py` (pure, no Temporal: build `GraphWorkflow`, set `_graph_sha` and a stub dispatcher with `_attrib`, and drive `_stamp` with `ACTIVATION` set or unset):
  - inside an activation: `record.graph` carries `graph_sha`, `activation_id`, `node_id`, `round`, `node_stage` and `fail_reentry`;
  - outside any activation: `graph_sha` only, the other fields `None`;
  - a mapped node's handler and lens stages (`code`, `qa`, `review`, `adversary`, `handoff`, `deep_review`) are kept;
  - `node_stage == "unknown"` rewrites `record.stage` to `"unknown"` (G2);
  - `_stamp` never mutates its input.

  Command: `pytest tests/graph_workflow/test_record_stamping.py`.
- [ ] T016 [US1] Implement `GraphWorkflow._record` (override: `await super()._record(cfg, self._stamp(record))`) and `_stamp` in `src/sdlc/workflows/graph.py` (R-4). `run_state` sets `graph_sha` whenever `_graph_sha` is set, independent of marks (R-3). Import `GraphAttribution` under `imports_passed_through()`. Command: `pytest tests/graph_workflow/test_record_stamping.py`.
- [ ] T017 [P] [US1] RED test in `tests/test_run_summary_build.py`: `build_run_summary(..., graph_sha="a"*64)` sets the field, and omitting the keyword yields `None` with output otherwise identical to main. Command: `pytest tests/test_run_summary_build.py`.
- [ ] T018 [US1] Add the `graph_sha=None` keyword to `build_run_summary` in `src/sdlc/observability/summary.py`. `RunHost._retro` in `src/sdlc/workflows/run_host.py` passes `getattr(self, "_graph_sha", "") or None`; this changes content only, with no command change for FeatureWorkflow (R-3, U6). Commands: `pytest tests/test_run_summary_build.py`, then `pytest -m temporal tests/replay/test_feature_replay.py`.
- [ ] T019 [US1] Temporal RED→GREEN test in `tests/graph_workflow/test_graph_view_query.py`: a default-graph run with a scripted architecture `revise` has `run_state().graph_sha` and `run_summary().graph_sha` equal to `inp.graph.content_sha()`, and every recorded `BenchmarkRecord` carries that sha. Enable `cfg.benchmark` so `_record` schedules `record_benchmark` (`src/sdlc/workflows/benchmark_host.py:114-116`), and register a capturing `record_benchmark` stub in the test worker, as `tests/test_benchmark_workflow.py` does. The architect's records carry round 1 and then round 2. Command: `pytest -m temporal tests/graph_workflow/test_graph_view_query.py`.
- [ ] T020 [P] [US1] RED tests in the new `tests/graph/test_graph_start.py`, using a fake client that records call order:
  - `start_graph_run` writes the identity file, layout, registry snapshot and pointer **before** `client.start_workflow`;
  - the pointer names `graph_sha`, `layout_sha` = the run input graph's `document_sha()`, `registry_sha` and `roles` = `run_input.roles`;
  - a store exception, a registry-write exception, a pointer-write exception and an unsafe run id each log a warning and still start the run;
  - `latest` is never written.

  Command: `pytest tests/graph/test_graph_start.py`.
- [ ] T021 [US1] Implement it in `src/sdlc/graph/start.py` (R-8). `start.py`'s import pin stays `{stdlib, sdlc.graph.store}` (the registry comes from `sdlc.graph.node_types` through the store API; if a direct import is needed, amend the pin in `tests/graph/test_graph_purity.py` explicitly). Commands: `pytest tests/graph/test_graph_start.py`, then `pytest tests/graph/test_graph_purity.py`.
- [ ] T022 [P] [US1] RED tests:
  - `tests/graph_workflow/test_pipeline_child_upgrade.py`: `execute_pipeline_child(..., on_graph=cb)` calls `cb(run_input.graph.content_sha())` exactly once before the child starts on the graph branch, and never on the FeatureWorkflow branch;
  - `tests/test_benchmark_workflow.py`: `_oracle_record` and `_oracle_task_records` given a sha set `graph=GraphAttribution(graph_sha=sha)` with every activation field `None`, and set `graph=None` when no sha is known.

  Commands: `pytest tests/graph_workflow/test_pipeline_child_upgrade.py`, then `pytest tests/test_benchmark_workflow.py`.
- [ ] T023 [US1] Implement `on_graph` in `src/sdlc/workflows/pipeline_child.py` and oracle stamping in `src/sdlc/benchmarks/workflow.py` (R-9). The parent keeps the cell's sha from the callback; this adds no command. Commands: `pytest tests/graph_workflow/test_pipeline_child_upgrade.py`, then `pytest tests/test_benchmark_workflow.py`, then `pytest -m temporal tests/graph_workflow/test_parent_wiring.py`.
- [ ] T024 [US1] Add ownership rows to `src/sdlc/workflows/AGENTS.md`:
  - `_attrib`: owner `GraphDispatcher`, reader `GraphWorkflow._stamp`, writer `GraphDispatcher._start`;
  - the `GraphWorkflow._record` override;
  - `_graph_sha`'s new reader `RunHost._retro` (cross-host, via `getattr`).
- [ ] T025 [US1] Replay gate: `pytest -m temporal tests/replay`. It must pass with **no** re-recorded golden or history (`git status tests/replay` clean).

**Checkpoint**: US1 is complete and independently demonstrable (spec US1 AS1–5).

---

## Phase 4: User Story 2 — Every node lands on a canonical stage, or visibly on `unknown` (P1)

**Goal**: marks and records never silently drop or fold an unmapped/unregistered node.

**Independent test**: spec US2 with injected registries.

- [ ] T026 [P] [US2] RED tests in `tests/graph/test_run_view_projections.py`: `stage_marks` over a graph containing (i) a node of an injected type with `canonical_stage=None` and (ii) a node whose type is absent from the passed registry puts both under the key `"unknown"`, using the existing precedence rule. No canonical stage gains a contributor. The shipped default graph's marks are unchanged from main (compare to the value computed before the change, pinned literally). Command: `pytest tests/graph/test_run_view_projections.py`.
- [ ] T027 [US2] Change `stage_marks` in `src/sdlc/graph/run_view.py` to use `resolve_stage` instead of `continue` (`run_view.py:211-212`). Commands: `pytest tests/graph/test_run_view_projections.py`, then `pytest tests/test_dashboard_fleet_marks.py`.
- [ ] T028 [US2] RED→GREEN test in `tests/test_benchmark_heatmap.py`: records with `stage="unknown"` render in the trailing non-canonical bucket, before `oracle` (existing behaviour, now pinned for E-77). Command: `pytest tests/test_benchmark_heatmap.py`.

**Checkpoint**: US2 AS1–4, 6–7 are green (AS5, the post-mortem of a drifted stored graph, completes in T036).

---

## Phase 5: User Story 3 — Router-derived rounds and fix attempts (P2)

**Goal**: an honest fail-edge re-entry axis: absent on every graph buildable today, exact on an injected fail-edge graph. It is counted once per activation.

**Independent test**: spec US3 (i)–(iii).

- [ ] T029 [P] [US3] RED tests in the new `tests/graph/test_fail_reentry.py`, with a fixture registry built in the test: the shipped types plus an injected `fixer` stage type with `_in("failure", "NodeFailure")`, and a graph whose `code`-like node's `fail` port routes over a back edge (`max_traversals: 3`) into it:
  - the ref format `f"{aid}.{port}"` is pinned against `graph_dispatch.py`'s minting (import the dispatcher and assert on a produced ref);
  - `fail_reentry` is `None` for every node of the shipped default graph;
  - it is `0` for the first activation of a node with an inbound fail edge;
  - it is `1` for an activation whose inputs include a `"<aid>.fail"` ref that arrived over the fail back edge;
  - it is `0` when the same node is re-entered over a non-fail back edge.

  Command: `pytest tests/graph/test_fail_reentry.py`.
- [ ] T030 [US3] Implement `fail_reentry(activation, state, topology)` in `src/sdlc/graph/run_view.py` (R-5; no new imports) and export it from `src/sdlc/graph/__init__.py`. Command: `pytest tests/graph/test_fail_reentry.py`.
- [ ] T031 [US3] Wire it into `GraphDispatcher._start` in `src/sdlc/workflows/graph_dispatch.py`, replacing T014's `None`. Extend `tests/graph_workflow/test_graph_view_dispatch.py`: driving the dispatcher over the T029 fixture graph with a failing handler yields `_attrib` indicators 0, 1, 1 for three activations of the fixer. Command: `pytest tests/graph_workflow/test_graph_view_dispatch.py`.
- [ ] T032 [P] [US3] RED tests in `tests/test_benchmark_heatmap.py`:
  - (a) **byte-identity pin, written and passing before T033**: `render_heatmap_json(build_heatmap(records))` over a fixed list of current-shape records equals a committed literal;
  - (b) three activations with `fail_reentry` 0, 1, 1, each emitting two records (e.g. `code` + `qa`), add exactly 2 to the `(case, node_stage)` fix cell;
  - (c) duplicate records of one re-entered activation add 1;
  - (d) `fail_reentry=None` everywhere changes nothing.

  Command: `pytest tests/test_benchmark_heatmap.py`.
- [ ] T033 [US3] Implement the once-per-activation pass in `build_heatmap` in `src/sdlc/benchmarks/heatmap.py` (R-12). The per-record loop is unchanged; the pass is skipped when no indicator exists. Command: `pytest tests/test_benchmark_heatmap.py`.

**Checkpoint**: US3 AS1–6 and SC-007 are green. The G4 tradeoff is observable: the default graph shows no indicator.

---

## Phase 6: User Story 5 — Layouts never rewrite history (P2; before US4, whose routes use it)

**Goal**: an editor-only `latest`, run-pinned layouts, and run graph routes that survive drift and retention.

**Independent test**: spec US5 AS1–5, SC-006, SC-008.

- [ ] T034 [P] [US5] RED tests appended to `tests/graph/test_graph_store_e77.py`:
  - `save` returns `(sha, layout_sha)` and moves `latest`, while `put` never does (including a `put` of an older layout after a `save`, which simulates backfill);
  - `get(sha)` returns the latest layout; `get(sha, layout=x)` returns x or `None`;
  - a missing, empty, torn (non-hex) or dangling `latest` falls back to the identity file;
  - two threads saving different layouts leave both layout files present and `latest` naming one of them, with no torn file.

  Command: `pytest tests/graph/test_graph_store_e77.py`.
- [ ] T035 [US5] Implement `GraphStore.save` and `get(sha, layout=None)` with `latest` handling via `_atomic_replace` in `src/sdlc/graph/store.py` (R-6). Command: `pytest tests/graph/test_graph_store_e77.py`.
- [ ] T036 [P] [US5] RED tests in `tests/test_dashboard_run_graph_routes.py`, using the existing fakes:
  - (a) a history-present run whose pinned graph fails `validate` against the current registry: `/runs/{id}/graph` returns 200 with the graph, and `/runs/{id}/graph_state` returns `{"kind":"unavailable","reason":"registry_drift","problems":[...]}` (today: 500);
  - (b) the same run with a pointer naming a registry snapshot under which the graph validates: `graph_state` projects normally;
  - (c) describe → NOT_FOUND with a pointer: `/graph` serves the pointer's layout, and `/graph_state` returns `unavailable/retention_expired`;
  - (d) describe → NOT_FOUND without a pointer: 404, as today;
  - (e) a FeatureWorkflow run gives `NoGraph` on both routes, as today;
  - (f) `GraphState.nodes[*].canonical_stage` equals `resolve_stage` (and is `"unknown"` for the drift-degraded node types).

  Command: `pytest tests/test_dashboard_run_graph_routes.py`.
- [ ] T037 [US5] Implement in `src/sdlc/dashboard/run_graph.py`: remove the raise at `run_graph.py:111-112` in favour of `topology=None` plus problems; add the pointer fallback, snapshot-registry resolution and pointer roles (R-10). In `src/sdlc/dashboard/graph_wire.py`, add `GraphStateUnavailable` and `NodeRunState.canonical_stage` (filled by `resolve_stage`). In `src/sdlc/dashboard/api.py`, extend the `graph_state` response union. Commands: `pytest tests/test_dashboard_run_graph_routes.py`, then `pytest tests/test_dashboard_graph_state_wire.py`.

**Checkpoint**: US5 AS1–5, SC-006, SC-008 and US2 AS5 are green.

---

## Phase 7: User Story 4 — Save and load by identity (P2)

**Goal**: `POST /graphs`, `GET /graphs/{sha}` and live `save`/`load` capabilities, with no frontend production change.

**Independent test**: spec US4 AS1–6 (contracts/http-graphs.md).

- [ ] T038 [P] [US4] RED tests in `tests/test_dashboard_graph_routes.py`:
  - `POST /graphs` answers `SaveOk` with `sha`, `layout_sha` and `validation` equal to `/graphs/validate`'s answer for the same graph;
  - an illegal-but-schema-valid draft is saved;
  - a non-`{graph}` body, a schema failure and a body over the cap give 422/422/413 with nothing written (the store dir is unchanged);
  - `GET /graphs/{sha}` answers `LoadOk` with the latest layout, and `?layout=` selects one;
  - an unknown sha or layout gives `LoadMissing`; a non-hex sha or a bad `layout` gives 422;
  - a second save with moved nodes gives the same `sha`, a new `layout_sha`, and a GET that returns the new layout;
  - the catalog has `save` and `load` true, with `validate`/`run_graph` as on main.

  Command: `pytest tests/test_dashboard_graph_routes.py`.
- [ ] T039 [US4] Implement the routes in `src/sdlc/dashboard/api.py` (reusing `_graph_body`, `parse_object`, `validation`, `with_executable`, and the `GraphStore` via `RunGraphs`' store). In `src/sdlc/dashboard/graph_wire.py`, add `SaveOk.layout_sha`/`LoadOk.layout_sha` and set `Capabilities.save/load` defaults to `True` (R-11). Command: `pytest tests/test_dashboard_graph_routes.py`.
- [ ] T040 [US4] Regenerate the recorded fixtures with `python scripts/dump_graph_fixtures.py`. Then run `pytest tests/test_graph_fixtures_fresh.py`. Review the diff: only `catalog.json` capabilities and `run_state/graph_state.recorded.json` `canonical_stage` fields change, under `interfaces/dashboard/frontend/src/api/__fixtures__/graph/`.
- [ ] T041 [US4] Test-only frontend updates forced by the flip (FR-026):
  - in `interfaces/dashboard/frontend/src/api/http-graph.test.ts`, the refusal cases (currently lines 47-56) use an explicit no-capability catalog, as `http-graph.chaos.test.ts` does with `NO_CAPS`;
  - in `interfaces/dashboard/frontend/src/api/mock/graph.test.ts:17`, the recorded-capabilities assertion expects `save/load: true`.

  No file under `interfaces/` other than these two tests and the regenerated fixtures changes. Command: `python scripts/check_ui.py`.

**Checkpoint**: US4 AS1–6 are green; the canvas's existing save/load code is reachable against the real API.

---

## Phase 8: Polish & cross-cutting

- [ ] T042 Static gates, each run separately: `ruff check .`, then `ruff format --check .`, then `mypy` (no new errors in touched `src/` files), then `python scripts/check_file_size.py`. `git diff --stat main -- src/sdlc/stages/code/step.py` must be empty, and `git diff --stat main -- interfaces/` limited to T040/T041's files.
- [ ] T043 Full regression, each command separately: `pytest`, then `pytest -m temporal`, then `pytest tests/test_graph_fixtures_fresh.py`, then `python scripts/check_ui.py`. `git status tests/replay` must show no re-recorded goldens or histories.
- [ ] T044 Walk through `.specify/specs/001-canonical-stage-graph-sha/quickstart.md` §1–§3 and tick each row; the §4 manual smoke is optional.
- [ ] T045 Landing docs (R5, R-13), describing main only:
  - `ROADMAP.md`: tick FR-1206, and give FR-1201's partial note the stage completeness;
  - `docs/roadmap/pipeline-as-data.md`: tick E-77 with a "Landed" paragraph naming the follow-ups: canvas run mode / fleet-strip consumption of `canonical_stage` and `unknown` marks + TS mirror; the fail-edge axis waiting on graph-expressed fix loops (E74-OQ-3); E77-OQ-1 heatmap `attempt − 1` inflation;
  - `ARCHITECTURE.md`: the `sdlc/graph/` store line gains layouts, `latest`, the registry snapshot and run pointers;
  - one-line errata: `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md` §10 (E72-OQ-7/8 resolved by E-77, spec path) and `docs/superpowers/specs/2026-09-17-graph-queries-design.md` §1.1 (save/load landed in E-77).

  Command: `python scripts/check_file_size.py`.

---

## Dependencies & execution order

### Phase dependencies

- Phase 1 → Phase 2 (T002–T012) → user-story phases.
- US1 (Phase 3) needs T003, T006, T007, T011.
- US2 (Phase 4) needs T003; T027 is independent of US1, and T028 needs nothing beyond Phase 2.
- US3 (Phase 5) needs T014 and T016 (US1).
- US5 (Phase 6) needs T011; T036/T037 also need T003 and T021 (pointer written by start).
- US4 (Phase 7) needs T035 (US5).
- Polish needs all of them.

### Within each story

The RED test task comes first and must fail for the stated reason. Then implementation, then that story's checkpoint command.

### Parallel opportunities

- Phase 2: T002, T004, T005 and T008 run in parallel (different files); T006, T007 and T009 follow their RED tests, also in parallel.
- US1: T013, T015, T017, T020 and T022 are independent RED tasks.
- Across stories after Phase 2: US2 (T026–T028) can run beside US1. US5's store half (T034–T035) can run beside US1 and US3.

## Parallel example: User Story 1

```text
QA seat A: T013 (dispatcher _attrib RED)      QA seat B: T020 (start helper RED)
QA seat A: T015 (stamping RED)                QA seat B: T022 (child/oracle RED)
Executor: T014 → T016 → T018 → T019 → T021 → T023 → T024 → T025
```

## Implementation strategy

- **MVP = Phase 1 + Phase 2 + US1 (through T025)**: every graph run durably records the graph that ran; a failed run's post-mortem names its graph after history is gone. Stop and validate with quickstart §1–§2 rows for US1.
- **Increment 2 = US2**: `unknown` visible in marks and records (FR-1206's third sentence).
- **Increment 3 = US3**: the router-derived axes (rounds already shipped in US1; fail-edge indicator + heatmap).
- **Increment 4 = US5 then US4**: store layouts, drift/retention-safe routes, then save/load live.
- Each increment ends green on its checkpoint and on T025's replay gate.

## Traceability

| spec item | tasks |
|---|---|
| FR-001/002/004 | T002–T003 |
| FR-003 | T003, T027, T037 |
| FR-005 | T026–T027 |
| FR-006 | T002–T003, T026–T027, T036–T037 |
| FR-007 | T015–T016 |
| FR-008/009 | T005, T007, T016–T019 |
| FR-010 | T015–T016, T019, T022–T023 |
| FR-011 | T010–T011, T020–T021 |
| FR-012 | T036–T037 |
| FR-013 | T020–T021 |
| FR-014 | T013–T016, T019 |
| FR-015/016 | T029–T031 |
| FR-017 | T032–T033 |
| FR-018 | T029, T045 |
| FR-019 | T008–T011, T034–T035 |
| FR-020 | T034–T035, T038–T039 |
| FR-021 | T036–T037 |
| FR-022/023 | T010–T011, T036–T037 |
| FR-024 | T004–T007 |
| FR-025 | T014, T016, T018, T025 |
| FR-026 | T037, T040–T042 |
| FR-027 | T042 |
| SC-001 | T002–T003 |
| SC-002 | T026–T027 |
| SC-003 | T019–T023 |
| SC-004 | T025, T032, T043 |
| SC-005 | T019 |
| SC-006 | T034–T035 |
| SC-007 | T029–T033 |
| SC-008 | T036–T037 |

## Notes

- `[P]` = different files, no incomplete dependency.
- A reviewer `fixes-needed` on any task's diff blocks the next task.
- Commit after each task or checkpoint; no attribution trailers.
- New test files: `tests/graph/test_graph_store_e77.py`, `tests/graph/test_graph_start.py`, `tests/graph/test_fail_reentry.py`, `tests/graph_workflow/test_record_stamping.py`.
