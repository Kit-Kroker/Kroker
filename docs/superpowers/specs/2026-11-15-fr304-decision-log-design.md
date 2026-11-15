# FR-304 — full-field decision records, queryable per run

**Date:** 2026-11-15
**Satisfies:** FR-304 (whole); removes the FR-304 clause from NFR-4's ⚠️ note
**Approach picked:** A — enrich the existing record spine, no second store (conversation, 2026-11-15)

## Intent

Every decision is already captured on the typed `GateDecision`, but the durable
per-run record drops `outcome` (collapsed to `approved: bool` — `revise` and
`reject` are indistinguishable), `comments`, `reviewer`, and `decided_at`, and
nothing queries the result. FR-304 closes when the durable record carries the
full field set and a surface answers "what did this run / gate / human decide".

## Goals

1. The durable decision record — `GATE_DECIDED` event, `GateOutcomeSummary`,
   `summary.json`, `events.jsonl`, `report.html` — carries the full FR-304 set:
   outcome (3-valued), decider, `(gate, round)`, comments, reviewer, timestamp.
2. `decided_at` is stamped on every decide path (human signals already stamp at
   signal time; SOFT-auto, policy, and timeout decisions get stamped where they
   are created).
3. `sdlc decisions` — an offline CLI verb over the retro exports, filterable by
   run, gate, and decider. The read-side twin of calibration's
   `gate_decisions_from_exports`.
4. Pre-change exports and recorded results parse unchanged (defaulted fields —
   the E-1 / 021 replay-safety precedent).

## Non-goals

- Real authenticated principals in `reviewer` — E-60 / FR-1004's scope
  (`docs/roadmap/service-platform.md:27`).
- A dashboard decision-history surface (explicitly declined with approach B+C).
- Crashed-run coverage beyond Temporal history: the accepted
  `gate_decisions_from_exports` limitation ("runs that closed AND exported")
  carries over verbatim. A second store was the alternative and was rejected.
- The `GATE_FEEDBACK` memory text blob stays — it feeds recall, not audit.

## Approaches

- **A (picked) — enrich the spine, read it back.** The repo's stated philosophy
  (`calibration/store.py`: "No second store is built beside it"). Additive model
  fields + one CLI verb; no new activity, no workflow command changes.
- **B (rejected) — first-class SQLite decision log** at decision time
  (dispositions-store pattern). Audit-grade coverage of crashed runs, but a
  second store beside Temporal history + exports, a new activity on the decision
  path, ~2-3× scope, for coverage Temporal history already holds.
- **C (rejected) — Temporal-queries-only.** Full fidelity, no store, but every
  query needs a live worker, N RPCs per fleet sweep, and it is useless for
  offline exports and benchmark contexts where the CLI must answer.

## Design

### 1. `core/models.py` — `GateOutcomeSummary` gains defaulted fields

`outcome: GateOutcome | None = None`, `comments: str | None = None`,
`reviewer: str | None = None`, `decided_at: datetime | None = None`.
`approved` stays (SC rollup, demo, and calibration read it). `None` on every
pre-change record — old `summary.json` and old recorded results deserialize
unchanged.

### 2. `workflows/gates.py` — stamp `decided_at` at the choke point

In `GateHost._gate`, immediately before the `_on_gate_decided` hook call:
`decision.decided_at = decision.decided_at or workflow.now()`. One line covers
SOFT-auto, policy-OFF, and timeout decisions; the human path's signal-time
stamp (set in `submit_gate_decision`, the more accurate time) is preserved
untouched. `workflow.now()` is deterministic — replay-safe.

### 3. `workflows/run_host.py` — emit the full field set

`RunHost._on_gate_decided` adds to the `GATE_DECIDED` event:
`outcome=decision.outcome.value` (always present), plus `reviewer`, `comments`,
`decided_at` only-when-set — the established `confidence`/`author_model`
`**({...} if x else {})` pattern.

### 4. `observability/summary.py` — read the fields; dedup becomes enrich

`_gate_outcome` reads the new keys (`GateOutcome` parsed when present).
The `(gate, round)` dedup changes from last-wins-replace to field-wise enrich:
on a repeat key, a field present on the later event wins; an absent optional
field keeps the earlier record's value. This is what keeps merge's enriched
re-emit (`stages/merge/step.py:565` — carries `overrides`, not the new fields)
from clobbering them, and protects any future re-emitter the same way. Pure
function, pinned by tests.

### 5. `observability/export.py` — report.html gates table

Columns: gate, round, policy, decided_by, reviewer, outcome, confidence,
overrides, decided_at (short form), comments. `summary.json` remains the data
of record; the html is the human view of the same object.

### 6. New `observability/decisions.py` — the read surface

The producer of `summary.json` owns reading it back as a decision log (the
same reader-lives-with-the-export precedent as `gate_decisions_from_exports`,
file I/O included, mirroring `calibration/store.py`):

- `DecisionLogRow(BaseModel)` — one decision with its run context: `run_id`,
  `title`, `project_key` (all `None`-able for pre-change exports), plus the
  full field set.
- `decisions_from_exports(root=None, *, run=None, gate=None, decided_by=None,
  limit=None)` — the `gate_decisions_from_exports` discipline verbatim:
  root defaults to `SDLC_EXPORT_ROOT` / `./runs/pipeline`; missing root is an
  empty answer, not an error; a malformed/truncated `summary.json` is skipped,
  never fatal to the sweep; sorted glob.
- `render_decisions(rows) -> str` — a deterministic table, the
  `_render_gates_list` / `calibration/cli.py` rendering style.

### 7. `cli.py` — `sdlc decisions`

`sub.add_parser("decisions")` with `--run`, `--gate`, `--decided-by`,
`--limit`, `--root`; registered in the `local_only` set (no Temporal client);
handler prints `render_decisions(decisions_from_exports(...))`. Mirrors the
`calibration` verb end to end.

### 8. Tests

- Stamping: SOFT-auto / policy / timeout decisions carry `decided_at`; a human
  decision's signal-time stamp is not overwritten.
- Emit: the `GATE_DECIDED` event carries the full set.
- Summary: `_gate_outcome` reads the fields; the enrich-dedup merges merge's
  re-emit correctly (full first, overrides-only second → one merged record);
  a pre-change `summary.json` (no new keys) parses to `None` fields.
- Reader: filters, missing root, malformed-skip, limit, determinism.
- CLI: arg wiring + render golden.
- Export: the enriched table renders.

### 9. Close-out (same diff)

ROADMAP.md FR-304 → `[x]` with evidence; NFR-4's ⚠️ note drops the FR-304
clause (FR-702 clause stays); full entry prepended to
`docs/roadmap/last-verified-log.md`. No stage contract (`<stage>.md`) is
edited — the change is confined to `core/`, `workflows/`, `observability/`,
and `cli.py`.

## Replay safety

No new activity; no workflow command changes; no `workflow.patched` marker.
Event-data keys are added only-when-set from deterministic inputs;
`GateOutcomeSummary` fields are `None`-defaulted. Old recorded results and
exports deserialize unchanged; in-flight runs replay without divergence.

## Left to the builder

Exact column widths/truncation of the two rendered tables; test file placement
(extend existing observability/summary tests vs. new files).
