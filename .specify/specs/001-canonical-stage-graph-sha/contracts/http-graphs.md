# Contract — graph save/load and run graph routes (E-77)

Surface: the dashboard API router (`src/sdlc/dashboard/api.py`), localhost-bound and unauthenticated (OQ-11 containment, unchanged). Wire models live in `src/sdlc/dashboard/graph_wire.py`. Every body goes through the existing capped `_graph_body` (413 above `MAX_GRAPH_BYTES`).

## GET /graphs/catalog (changed)

`capabilities`: `{"validate": <as main>, "save": true, "load": true, "run_graph": <as main>}`. Nothing else changes. The recorded `__fixtures__/graph/catalog.json` is regenerated accordingly (FR-026).

## POST /graphs (new)

- Request: exactly `{"graph": <object>}`.

| condition | status | body |
|---|---|---|
| body is not `{graph}` / not JSON | 422 | detail |
| graph fails `parse_object` (schema) | 422 | detail; **nothing written** |
| stored | 200 | `SaveOk` |
| store I/O failure | 500 | detail (nothing is half-visible: every file is tmp + replace) |

`SaveOk` = `{"ok": true, "sha": <64hex>, "layout_sha": <64hex>, "validation": ValidationWire}`, where `validation` = `with_executable(validation(graph, roles=resolved_roles(PipelineConfig())), executable(graph))`, identical to `/graphs/validate`. A graph that fails legality is still saved (drafts); legality comes only from the single validator.

Effect: the identity file (first write wins), the layout file, and `latest := layout_sha`.

## GET /graphs/{sha} (new)

- Path: `sha` must fully match `[0-9a-f]{64}`, else 422 (no disk access).
- Query: optional `layout=<64hex>`; anything else is 422.

| condition | status | body |
|---|---|---|
| found | 200 | `LoadOk{"ok": true, "sha", "layout_sha", "graph"}`: the `layout` if given, else the verifying `latest`, else the identity file (whose `layout_sha` is its own `document_sha`) |
| unknown sha or layout | 200 | `LoadMissing{"ok": false, "reason": "not_found"}` (the provisional shape the canvas already handles) |
| stored file corrupt | 500 | detail (`GraphStoreCorrupt`, as E-75) |

## GET /runs/{run_id}/graph (changed)

| source | result |
|---|---|
| FeatureWorkflow run | `NoGraph{legacy_run}` (unchanged) |
| history present | `GraphResponse` from the start input (unchanged). **No longer 500** when the pinned graph does not validate against the resolving registry |
| history gone, pointer present | `GraphResponse` of the pointer's layout (else the identity file) |
| history gone, no pointer | 404 (unchanged) |

Resolving registry: the pointer's registry snapshot when present and loadable, else `NODE_TYPES`. Roles: the start input's roles, else the pointer's.

## GET /runs/{run_id}/graph_state (changed)

Response union: `GraphState | NoGraph | GraphStateUnavailable`.

- The pinned graph does not validate → `{"kind": "unavailable", "reason": "registry_drift", "problems": [...]}` (today: 500).
- History gone but pointer present → `{"kind": "unavailable", "reason": "retention_expired", "problems": []}`.
- `GraphState.nodes[*]` gains `canonical_stage` (a canonical stage or `"unknown"`).

`GraphState` is FINAL (E-75): the additive field re-records its wire fixtures from the real projection. The TS mirror amendment and consumption stay with the canvas follow-up (`run_graph` capability unchanged, so no shipped frontend path reads it).
