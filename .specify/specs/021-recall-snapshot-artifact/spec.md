# Feature Specification: RecallSnapshot as a Persisted, Content-Addressed Stage Input (FR-402)

**Feature Branch**: `021-recall-snapshot-artifact` (spec directory only; no branch created)

**Created**: 2026-11-11

**Status**: Approved. GATE 1 cleared by the user (relayed by the orchestrator) on 2026-11-11: Q1 = recommended, Q2 = recommended, Q3 = recommended. See Rulings. GATE 2 cleared on 2026-11-11 (all five plan recommendations accepted); see GATE 2 Rulings. Scoping only; no implementation is requested by this spec.

**Input**: Orchestrator brief (2026-11-11): scope FR-402 as a short design/scope note and settle five questions. Code references are against `main` at `067e1408`.

## Context

PRD FR-402 (`PRD.md:261`): recall results SHALL be persisted as hashed `RecallSnapshot` artifacts and treated as declared stage inputs. ROADMAP (`ROADMAP.md:327`) marks it partial: `query_hash` exists, the memory watermark does the real freezing work, and a snapshot is not a separately content-addressed, persisted artifact.

What exists today:

| Piece | Where | What it does |
|---|---|---|
| `RecallSnapshot(query_hash, bank, watermark, items, degraded)` | `memory/models.py:23` | Return value of recall. Its docstring already claims "persisted, hashed". It is neither. |
| `recall_query_hash(bank, query, filters, watermark)` | `memory/query_hash.py` | Hashes the **question** (and the freeze point), never the answer (`items`). |
| Watermark | `MemoryConfig.watermark`, `graph.py:175`, `memory/fake.py`, `hindsight_client.py:183` | The freeze: entry count (fake) or worker-clock ISO time (Hindsight, enforced client-side). |
| Memo key | `role_host.py:_cached_stage`, `content_key(stage, input, prompt, model, watermark)` | Keys on watermark alone. Snapshot items are not in the key. |
| Recall activity | `memory/activities.py:recall_snapshot` | Never raises; on backend failure returns an empty snapshot with `degraded=True`. |
| Disabled path | `workflows/memory_host.py:51` | Returns an empty snapshot with `query_hash=""`; no activity runs. |
| Consumers | `stages/{clarify,plan,architecture}/step.py` | Call `ctx.recall`, splice `snapshot.items` into the prompt. |
| Artifact store | `artifacts/store.py` `LocalFileStore` | Claim-check store, `put(kind, run_id, name, data) -> ArtifactRef(sha256)`. No `recall_snapshot` kind. |

The real gap is not a missing hash of the same thing. It is that the **same** `query_hash` can return **different** items (Hindsight's recall has an LLM leg; the watermark is only a client-side time cutoff over a live, consolidating bank), and nothing records which items a stage actually saw or lets a cache key notice the difference.

## Design decisions (answers to the five brief questions)

**D1. What "content-addressed" means.** Two hashes with two jobs. `query_hash` stays as is: the identity of the *question* (the one definition, `query_hash.py`). A new `snapshot_hash` is the SHA-256 of a canonical serialization of the *answer* (`bank`, `watermark`, `query_hash`, ordered `items`, `degraded`). Hash of the query alone is not content addressing, because identical queries can differ in content. Hash of items alone loses the bank/watermark/degraded context. Item order is significant (recall ranking feeds the prompt). `recall_query_hash` remains the single question-identity definition; a sibling in the same module defines the answer hash so fake, Hindsight and degraded paths cannot diverge.

**D2. Where it is persisted and how a stage declares it.** Persist inside the recall activity (a side effect, so it belongs there, not in workflow code) to the existing artifact store as a hash-named `recall_snapshot` artifact, returning an `ArtifactRef`-style reference alongside the snapshot. A stage declares the snapshot as an input by carrying `snapshot_hash` into its memo-key inputs and its recorded stage record. No new storage backend.

**D3. Memoization, NFR-6, replay.** NFR-6: identical inputs + prompts + model + watermarked memories = cache hit; any variation is an explicit hashed input change. Today "watermarked memories" is approximated by the watermark. With FR-402 the key gains `snapshot_hash`, so a changed recall result is a visible, explicit input change rather than a silent stale hit (and an unchanged result is still a hit). Auditability stays independent of caching: the persisted artifact exists even when recompute was skipped. Replay safety: the recall activity's return value is already recorded in Temporal history, so replay never re-queries memory; persistence is idempotent (hash-named path, same bytes), so activity retry is harmless; workflow code only handles the hash string. Adding a new activity would alter the command sequence and need `workflow.patched`; adding defaulted fields to the `RecallSnapshot` payload does not (Errata E-1). The plan therefore persists inside the existing activity (research R-1). Changing the memo-key shape invalidates existing cache entries once; this is acceptable for a dev-loop cache (ADR-5).

**D4. Degraded and disabled cases.** *Degraded*: still persisted and hashed (it is what the stage saw), flagged `degraded`, and MUST NOT be served from or written to the cache under the same key as a healthy snapshot (today a degraded empty recall and a healthy one share a key, so one outage can poison the cache for that watermark). *Disabled*: no activity, no artifact, `query_hash=""` retained; the declared input is explicitly "no memory" and the memo key is byte-identical to today's, so memory-off runs keep their caches and golden traces.

**D5. Tests.** See Testing Scope below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Audit what memory a stage saw (Priority: P1)

An operator reconstructing why a stage produced its output opens the run and finds, for each stage that recalled memory, the exact snapshot (items, bank, watermark, degraded flag) addressed by hash, even when the stage output came from cache.

**Why this priority**: This is FR-402's literal requirement and NFR-6's auditability half.

**Independent Test**: Run a recall through the fake backend; assert a snapshot artifact exists whose content hash matches its address and whose items equal what the stage prompt received.

**Acceptance Scenarios**:

1. **Given** memory enabled and a healthy backend, **When** a stage recalls, **Then** a snapshot artifact is persisted, addressed by the hash of its content, and the stage record references that hash.
2. **Given** a stage output served from cache, **When** the operator inspects the run, **Then** the snapshot the cached output depended on is still retrievable.

---

### User Story 2 - Changed recall is an explicit input change (Priority: P1)

A developer re-running a fixed idea expects a cache hit when memory content is unchanged and a visible, hashed miss when recalled items differ, never a silent stale hit.

**Why this priority**: The memo key currently cannot see item changes under a fixed watermark.

**Independent Test**: Two recalls under one watermark returning different items yield different keys; identical items yield the same key.

**Acceptance Scenarios**:

1. **Given** same stage, prompt, model, watermark, **When** the recalled items differ, **Then** the memo key differs.
2. **Given** identical items, **When** the stage re-runs, **Then** the memo key is identical and the cache hits.

---

### User Story 3 - Memory outage does not poison the cache (Priority: P2)

When the backend is down, the stage proceeds on an empty degraded snapshot, and that result is neither reused later as if memory had been consulted nor allowed to shadow a healthy result.

**Why this priority**: Preserves the "never block on memory" rule while closing a correctness hole.

**Independent Test**: Force the backend to raise; assert a degraded snapshot is persisted and the stage's cache key differs from the healthy key for the same watermark.

**Acceptance Scenarios**:

1. **Given** the backend raises, **When** a stage recalls, **Then** a degraded snapshot is persisted and the run continues.
2. **Given** a prior degraded run, **When** the backend recovers and the stage re-runs, **Then** it does not hit the degraded run's cache entry.

---

### User Story 4 - Memory-off runs are unchanged (Priority: P2)

With memory disabled, behaviour, memo keys and golden traces are identical to today.

**Independent Test**: Existing golden-trace and memo-key tests pass unmodified with memory disabled.

**Acceptance Scenarios**:

1. **Given** `memory.enabled=false`, **When** a stage recalls, **Then** no artifact is written and the memo key equals the pre-FR-402 key.

### Edge Cases

- Backend returns the same items in a different order: different hash (order is part of the answer).
- Recall returns zero items on a healthy backend: still a persisted, hashed snapshot, distinct from degraded.
- Same snapshot persisted twice (activity retry, two stages with identical recall): one artifact, no error.
- Pinned `MemoryConfig.watermark` with a Hindsight result lacking timestamps: already dropped by `_within_watermark`; unchanged.
- Existing code constructing `RecallSnapshot(query_hash=..., bank=..., watermark=..., items=[])` (four stage-slice test stubs, `memory/fake.py`) must keep working: any new field needs a default.
- Snapshot size: bounded by `RECALL_KEEP` items; no new cap is needed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every **stage-level** recall (a recall made through the stage context's recall capability, `ctx.recall`) that runs against a backend, healthy or degraded, MUST produce a persisted snapshot artifact addressed by a hash of its canonical content. Agent-tool lead lookups (`recall_leads`) are out of scope (GATE 2 ruling 2).
- **FR-002**: The content hash MUST cover bank, watermark, query identity, ordered items and the degraded flag, and MUST be computed by one shared definition used by every backend path.
- **FR-003**: The existing question-identity hash MUST be unchanged for all inputs (existing hashes stay valid).
- **FR-004**: A stage that consumed a snapshot MUST record the snapshot's content hash as a declared input, and that hash MUST participate in the stage's memoization key.
- **FR-005**: Persistence MUST be idempotent: persisting identical content twice yields one artifact and no error.
- **FR-006**: A degraded snapshot MUST be persisted and flagged, and MUST NOT share a memoization key with a healthy snapshot for the same watermark.
- **FR-007**: With memory disabled, no artifact is written and the memoization key MUST be byte-identical to the pre-change key.
- **FR-008**: Persistence failure MUST NOT block the pipeline (memory is I/O and stays non-blocking). The stage continues as degraded: the failure is logged and marked on the stage record, and the degraded cache-key rule (FR-006) applies. (Ruling Q3.)
- **FR-009**: Recall results MUST come from recorded activity output on replay; no workflow-visible nondeterminism may be introduced, and in-flight histories MUST remain replayable.
- **FR-010**: `snapshot_hash` MUST join the memoization key alongside the watermark; the watermark is not removed from the key. (Ruling Q1.)
- **FR-012**: Recalled items MUST pass the PII/secret scrub hook (the same one retain uses) before they are hashed, persisted to the artifact store, or placed in a prompt, so the stored artifact, the hash and what the stage saw are the same scrubbed text. Today retain scrubs (`memory/activities.py:91`) and recall does not (`memory/activities.py:61-66`); this closes that gap for stage-level recalls.
- **FR-011**: The snapshot content MUST be stored in the artifact store only. The stage record carries the snapshot hash and an artifact reference, not the items; no copy goes into the export bundle. (Ruling Q2.)

### Key Entities

- **RecallSnapshot**: the recall answer; gains a content hash and a persisted reference; identity of the question (`query_hash`) is retained.
- **Snapshot artifact**: immutable, hash-named file in the artifact store, kind `recall_snapshot`.
- **Declared input**: the snapshot hash carried on a stage's record and memo key.

### Testing Scope

Existing tests that pin the current shape (must stay green unless the plan says otherwise):

- `tests/test_recall_query_hash.py` (4 tests): pins question-identity invariants. Must pass unmodified (FR-003).
- `tests/test_memory_models.py:12` `test_recall_snapshot_defaults_not_degraded`: pins model defaults; new fields need defaults.
- `tests/test_hindsight_recall.py:143` `test_snapshot_carries_the_pinned_watermark_and_a_query_hash` (and the neighbouring recall tests): pins the Hindsight snapshot payload.
- Stub contexts constructing `RecallSnapshot(...)` in `tests/clarify/test_clarify_slice_contract.py`, `tests/clarify/test_clarify_memo_key.py`, `tests/plan/test_plan_slice_contract.py`, `tests/architecture/test_architecture_slice_contract.py`: pin the constructor shape and that stages go through `ctx.recall`.
- Memo-key tests (`test_clarify_memo_key.py`, calibration/golden traces): pin byte-identity of keys when the flag is off (FR-007).

Added by Errata E-2 (skeptic 1A, probe 4; verified):
- `tests/replay/test_graph_golden.py:28-50,148` (`MEMO_PARITY_KEYS`) runs memory **on** and pins the recall slot; it must be re-pinned deliberately.
- `SimpleNamespace(items=[])` recall stubs in `tests/plan/test_plan_step_chaos.py:63`, `tests/plan/test_plan_step_split.py:20`, `tests/architecture/test_architecture_step_split.py:29`, `tests/architecture/test_architect_research_deps.py:67`, and six `cached_stage` stubs without `**kwargs` (plan T040).
- `tests/test_memory_activities.py` calls `recall_snapshot` directly, outside an activity context.

New tests needed: content-hash stability and order sensitivity; fake and Hindsight parity for the content hash; persistence idempotency; degraded-vs-healthy key separation; memory-disabled key byte-identity; memo-key change on differing items; a `temporal`-marked replay check showing a pre-021 memory-on history replays unpatched, without editing the history (no new activity; E-1).

## Out of Scope

- E-25 (`org_bank` writers, `docs/roadmap/filesystem-first.md:79`). **Independent of FR-402: confirmed.** FR-402 concerns the recall side (what a stage saw); E-25 concerns the retain side (nothing writes to `org_bank`, so `reflect(org)` consolidates an empty bank) and is a content/policy decision about what belongs in an org bank. They share no code path beyond `MemoryConfig`, and neither blocks the other. One soft touchpoint: if org recall is later added to a stage, it flows through the same snapshot mechanism because snapshots are per-bank and bank-agnostic. E-25 stays separate, new scope.
- A Hindsight point-in-time/as-of read, and reusing a persisted snapshot on a pinned watermark (the ADR-5 freeze). With 021, live-Hindsight re-runs usually miss the stage cache, explicitly and hashed. Accepted at GATE 2 (ruling 1); ADR-5 text corrected; follow-up `.workspace/tasks/2026-11-11-recall-snapshot-pinned-reuse.md`.
- `recall_leads` (`agents/research/tools/recall_leads.py:14`): not persisted, no degrade path, unscrubbed (GATE 2 ruling 2; `.workspace/tasks/2026-11-11-recall-leads-snapshot-and-degrade.md`).
- Tenant scoping of the stage-output memo cache, a pre-existing gap (GATE 2 ruling 3; `.workspace/tasks/2026-11-11-memo-cache-tenant-scope.md`).
- `FakeMemory` crash on a non-numeric watermark, pre-existing (GATE 2 ruling 4; `.workspace/tasks/2026-11-11-fakememory-nonnumeric-watermark.md`).
- Changing `reflect`, retention (FR-401/403) or the nightly schedule.
- Garbage collection / retention policy for snapshot artifacts (follows the artifact store's existing policy).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of stages that consumed recalled memory through a stage-level recall (`ctx.recall`) in a run, the exact items they saw are retrievable by hash from that run.
- **SC-002**: A re-run with unchanged memory content hits the cache for every unchanged upstream stage; a re-run with changed recalled items misses for the affected stage and downstream, with zero silent stale hits in the test matrix. Measured on the fake backend; live Hindsight re-runs are expected to miss because its recall is not reproducible under a fixed watermark (GATE 2 ruling 1).
- **SC-003**: Memory-disabled runs produce byte-identical memo keys and golden traces to before the change (zero diffs).
- **SC-004**: A simulated memory outage never fails a run and never causes a later healthy re-run to reuse the outage's cached output.
- **SC-005**: Replaying a pre-change in-flight run history against the new code completes without nondeterminism errors.

## Assumptions

- The artifact store (`LocalFileStore`, hash-named) is adequate; S3 arrives behind the same protocol later.
- Hindsight recall may be nondeterministic for a fixed watermark; this is the motivating case, not something this feature fixes.
- Cache invalidation of existing memo entries on the key-shape change is acceptable (dev-loop cache, ADR-5).
- Hindsight stays the only real backend; the fake backend defines expected semantics for tests.
- `workflow.patched` is the correct mechanism for GraphWorkflow command-sequence changes; the plan re-reads `src/sdlc/workflows/AGENTS.md` to confirm.

## Errata (post-GATE 1, factual corrections only; no scope change)

- **E-1** Replay: defaulted payload fields do not change the command sequence; only adding/removing activities does (advisor D1). D3 corrected.
- **E-2** Testing Scope missed four pins; added above (skeptic 1A, probe 4).
- Scope questions raised by the skeptic (FR-001 coverage of `recall_leads`, the Hindsight freeze) were settled at GATE 2; see GATE 2 Rulings.

## Rulings (GATE 1, 2026-11-11)

| # | Question | Ruling |
|---|---|---|
| Q1 | Cache key: add `snapshot_hash` alongside the watermark, or replace it? | **Alongside** (FR-010). |
| Q2 | Persistence: artifact store only, or also embedded in the stage record / export bundle? | **Artifact store only**; the stage record carries hash + reference (FR-011). |
| Q3 | Persistence failure: continue as degraded or fail the stage? | **Continue as degraded**, log it, mark it on the stage record (FR-008). |

## GATE 2 Rulings (2026-11-11)

| # | Item | Ruling |
|---|---|---|
| 1 | Live-Hindsight re-runs miss the stage cache; ADR-5's "recall is a cached activity" is untrue | **Accepted.** Correct ADR-5 text (plan T061); follow-up card filed. SC-002 measured on fake. |
| 2 | `recall_leads` bypasses snapshots | **FR-001 and SC-001 narrowed to stage-level `ctx.recall`**; card filed. |
| 3 | Memo cache not tenant-scoped (pre-existing) | Out of scope; card filed. |
| 4 | `FakeMemory` non-numeric watermark crash (pre-existing) | Out of scope; card filed. |
| 5 | Cache a stage's output when its recall degraded? | **Keep caching** (keys already differ; research R-5). |
| + | Do recalled items go through scrub before the artifact-store write? | **Yes, FR-012**: today only retain scrubs; 021 scrubs in the recall activity before hash, persist and prompt (plan T013, research R-8). |
