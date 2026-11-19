# Org-bank promotion in nightly reflect (E-25, FR-404 org half)

| | |
|---|---|
| Requirements | FR-404 (org half), E-25 (§9.3), AP-5.5 (promotion half) |
| Prior art | `docs/reports/Kroker Agent Architecture & Implementation Plan.md` §"Use `org_bank` for stack knowledge" |
| Supersedes | none — 021 and 023b both explicitly scoped E-25 out |
| Size | small change (one mechanism, one new module, small edits) |

## Intent

Give `org_bank` curated writers so `reflect(org)` consolidates a real bank,
closing FR-404. The org bank holds **cross-project stack knowledge only**: a
gotcha that recurs in 2+ project banks is promoted by the nightly reflect
job; project-specific facts stay project-side. This is the prior art's rule,
unchanged.

## Goals

- A gotcha (kind `gotcha`) recalled from ≥2 distinct project banks is
  retained into `org_bank` with provenance, then org is consolidated.
- Promotion is idempotent: re-running on unchanged banks upserts (Hindsight
  document id is content-addressed) rather than duplicates.
- A failed promotion is **visible** — it fails the nightly workflow like a
  bank-reflect failure already does. No silent no-op.
- FR-404 flips `[x]`; E-25 closes; stale "org has no writers" notes across
  ROADMAP/BENCHMARK refresh in the same diff.

## Non-goals

- `incident_lesson` promotion (023b's deferred org writer). It rides this
  mechanism later by widening the promotable-kind list; not now.
- Fuzzy/embedding recurrence matching — deterministic normalized-hash only.
- Org *recall* wiring into stages (what a stage reads from org is separate).
- Per-run org reflect in the retro stage — org consolidation stays nightly.
- Pruning by use (AP-5.5's other half).

## Constraints

- **One project bank exists today** (`project:default`). Promotion cannot
  *fire* until a second project bank runs with memory on; FR-404 closes on
  the mechanism, with that caveat recorded in ROADMAP.
- `reflect` is an activity; Temporal Schedules start workflows — the
  ReflectWorkflow wrapper stays the orchestrator.
- Hindsight has no list endpoint; recall with `filters={"kind": "gotcha"}`
  is the only read path (kind is in `_FILTERABLE` via the `kind:` tag).
- Hindsight recall returns LLM-extracted text, so cross-bank texts are
  rarely byte-identical: a missed promotion is possible, a false positive is
  impossible (hash equality is strict).
- Schedule assets are server-side mutable state; the asset changes only via
  the normal `sdlc schedules apply` diff.

## Approaches (settled in conversation)

1. **Promotion in the nightly job — chosen.** Curated, matches prior art,
   no per-run cost. Recurrence detection is heuristic first cut.
2. Verified-incident promotion only — smaller surface, but covers DAPER
   incidents, not ordinary-run gotchas. Rejected.
3. Dual-write at retain time — org becomes a project mirror; the
   cross-project signal SC-4/SC-6 need never accrues. Rejected (prior art
   says project-specific facts stay project-side).

## Design

### New promotion pass (`src/sdlc/memory/promote.py` + activity)

Pure grouping logic in `memory/promote.py` (the horizontal memory package
owns it; no stage involvement):

- For each project bank: recall with `filters={"kind": "gotcha"}`,
  `watermark=None`.
- Normalize each item: lowercase, collapse whitespace, strip
  non-alphanumerics → sha256. Group by hash across banks; count **distinct
  banks**, not occurrences.
- Hashes seen in ≥ `promote_min_projects` (default 2) banks promote:
  representative raw text = lexicographically smallest occurrence
  (deterministic → idempotent across runs); retained into `org_bank` with
  kind `gotcha`, metadata `promoted_from: "project:a,project:b"` (sorted,
  comma-joined). Text is scrubbed before retain, same as the `retain`
  activity.

New activity `promote_org_learnings(PromoteInput)` in
`memory/activities.py` — project_banks, org_bank, promote_min_projects,
backend, base_url — registered beside the existing memory activities on the
worker (`worker.py`).

### ReflectWorkflow extension

`ReflectScheduleInput` (and the asset's `ReflectAction`) gain
`org_bank: str | None = None` and `promote_min_projects: int = 2`. When
`org_bank` is set, after the project banks reflect: run
`promote_org_learnings`, then reflect the org bank. Promotion failure
appends to the same fail-visible `ApplicationError` path. Defaults keep old
assets and live schedules decoding identically (`from_temporal`
revalidation unaffected).

### Asset change

`schedules/nightly-reflect.yaml` gains `org_bank: "org"`. The
`to_temporal(<nightly-reflect asset>)` byte-pin test is refreshed in the
same diff — the pin guards against *accidental* change; this one is the
feature.

### Test-double fidelity fix

`FakeMemory._Entry` drops `kind` today, so kind-filtered recall — the
promotion read path — cannot be exercised on the double. `_Entry` keeps
`kind`; recall honors `kind` in filters alongside metadata, matching
Hindsight's `_FILTERABLE` set. Without this the double silently diverges
from the real backend on exactly the filter promotion depends on.

### Docs sweep (same diff)

- `ROADMAP.md`: FR-404 → `[x]`; §9.3 E-25 → `[x]`; stage-14 note (line 302)
  drops "org half stays E-25".
- `BENCHMARK.md`: refresh the three "org bank has no writers" notes.
- `docs/roadmap/filesystem-first.md` E-25 entry closes; SC-4 note updated.
- `docs/roadmap/agent-architecture-plan.md` AP-5.5 annotated (promotion
  landed; verified-only retention and pruning still open).
- PRD text unchanged — the requirement already reads "nightly (project) and
  cross-project (org)".

## Testing

- `promote.py` unit tests: grouping, distinct-bank counting, threshold,
  representative choice, provenance metadata, one-bank → no promotion,
  second run over unchanged banks yields identical items (idempotence).
- `FakeMemory` kind-filter tests (filter present/absent).
- Activity test on the fake backend end-to-end (recall → promote → org
  entries present).
- ReflectWorkflow test: org path schedules promotion before org reflect;
  promotion failure fails the run.
- Schedules: asset with `org_bank` loads; `to_temporal` pin refreshed;
  `from_temporal` round-trips the new fields; old decoded input (no org
  fields) still validates.

## Left to the builder

- Exact normalization byte-details and the recall query string (the double
  ignores it; Hindsight needs *some* query — pick and pin a generic one).
- Where the pin test lives and its refresh mechanics.
- Whether promotion and org-reflect share one activity timeout or get
  their own (REFLECT_ACT's 10 min is the natural first choice).
