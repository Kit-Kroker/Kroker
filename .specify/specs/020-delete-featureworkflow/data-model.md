# Data model: 020 delete FeatureWorkflow

This feature adds no persisted entities. It changes one wire model, adds one
error type, and changes how test fixtures are made.

## 1. `LegacyRun` (new wire model, `src/sdlc/dashboard/fleet.py`)

| Field | Type | Source | Notes |
|---|---|---|---|
| `run_id` | `str` | visibility `wf.id` | |
| `status` | `str` | `wf.status.name.lower()`, or `"unknown"` | never queried from the worker |
| `start_time` | `datetime \| None` | `wf.start_time` | `None` on fakes |
| `close_time` | `datetime \| None` | `wf.close_time` | `None` on fakes |

`FleetSnapshot.closed_legacy: list[LegacyRun]` defaults to `[]`. Contract:
[contracts/fleet-legacy-row.md](contracts/fleet-legacy-row.md).

## 2. `ClosedRef` (internal to `fleet.py`)

`ClosedRef(id, type, status, start_time, close_time)` replaces the
`(id, type)` tuple that `_scan_closed` returns today. It is not serialised.

Partition rule:
- `type == "FeatureWorkflow"` becomes a `LegacyRun`;
- `type == "GraphWorkflow"` takes the queried path plus marks;
- any other type, including `None`, takes the queried path.

## 3. `LegacyRunError` (new, `src/sdlc/channels/transport.py`)

`LegacyRunError(run_id: str)` subclasses `Exception`. It is raised only
after a failed query **and** a `describe()` that reports
`workflow_type == "FeatureWorkflow"`. The surfaces map it to:
- dashboard: HTTP 410;
- CLI: exit 1;
- operator: a tool error.

## 4. Replay fixtures (`tests/replay/`)

| Fixture | Before | After |
|---|---|---|
| `histories/<scenario>.json` (18) | `workflow: FeatureWorkflow` | re-captured, `workflow: GraphWorkflow`, new `source_commit` |
| `golden/<scenario>.json` (18) | `workflow: FeatureWorkflow` | `workflow: GraphWorkflow`, new `source_commit`; `commands`, `close` and `trace` **byte-identical** |
| `histories/research_retain_grounded.json` | FeatureWorkflow | re-captured, GraphWorkflow |
| `histories/benchmark_one_cell.json`, `histories/assessment_discover_risk.json`, `histories/architect_research_usage.json`, `golden/assessment_discover_risk.json` (AssessmentWorkflow) | unchanged | unchanged |
| `tests/durability/fixtures/priced_usage_pre_e74.json` | — | new: `price_usage` tuples extracted from the old Feature `greenfield_happy` before the re-capture |
| memo_parity expected keys | computed live from FeatureWorkflow | pinned constant in `test_graph_golden.py` |

## 5. State transitions: grace lifecycle

```text
grace (today)
  → PR-1 merged
  → gate run 1 PASS
  → PR-2 commits
  → PR-2 merged
  → gate run 2 PASS
  → worker restarted without FeatureWorkflow   (irreversible)
```

The `e74-graph-child` patch also moves on:
`patched` (today) → `deprecate_patch` (PR-2) → removed (no date: a standing
item).
