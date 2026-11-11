# Implementation Plan: RecallSnapshot as a Persisted, Content-Addressed Stage Input (FR-402)

**Branch**: `021-recall-snapshot-artifact` (spec directory only; no branch created) | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: `spec.md` (GATE 1 approved 2026-11-11, Rulings Q1-Q3; GATE 2 cleared 2026-11-11, all five items as recommended plus FR-012 scrub), `advisor-answer-1.md`, `skeptic-answer-1.md`. References are against `main` at `067e1408`. Abbreviations: `S/` = `src/sdlc/`, `T/` = `tests/`.

## Summary

FR-402 lands as one additive PR with no new Temporal command:

- **Hash the answer.** A canonical, version-tagged hash of the recall answer, `snapshot_hash`, sits beside the unchanged `query_hash`. It is derived on the `RecallSnapshot` model, so every backend path, replayed history and test stub gets the same value (R-3).
- **Persist inside the existing activity.** `recall_snapshot` writes the snapshot to the artifact store as `<root>/<run_id>/recall/<hash>.json`. The file bytes are the hashed bytes. Recalled items are scrubbed first: FR-012. Today only retain scrubs (R-1, R-2, R-8).
- **Write failures degrade.** A write failure becomes a degraded, item-free snapshot that is never raised, including the double-fault case (R-5, ruling Q3).
- **Declared input.** `snapshot_hash` joins the memo-key slot alongside the watermark through a new `recall_ref` kwarg. Memory-off keys stay byte-identical (R-4, ruling Q1).
- **Stage record.** A `memory_recalled` trace event carries hash, uri and flags, never items. It fires from `MemoryHost._recall`, so cache-hit stages are covered (R-6, ruling Q2).
- **Reader.** `read_recall_snapshot(ref)` reads a snapshot back and checks its content address (R-7).

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: `temporalio` (activities, `Replayer`), pydantic v2 (`model_validator`)
**Storage**: `LocalFileStore` (`S/artifacts/store.py`); no new backend
**Testing**: `pytest`, using the fast tier plus `-m temporal` for replay and golden
**Target Platform**: Linux worker (compose)
**Project Type**: Temporal pipeline service (library + worker)
**Performance Goals**: one extra small file write per recall, at most `RECALL_KEEP` items; no added network calls
**Constraints**:
- recall never raises (`S/memory/activities.py:61`);
- no new workflow command;
- FR-007 byte identity for memory-off runs.
**Scale/Scope**:
- `src`: 12 `.py` files (9 in Phases A/B, plus the 3 stage `step.py` files in T030-T032);
- tests: 9 files edited (7 distinct in T040, plus T041 and T042) and 3 new (T043-T045);
- docs: 4 files, plus the 3 stage `<stage>.md` contracts.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template. The binding rules are root `AGENTS.md`, `S/workflows/AGENTS.md` and the stage `AGENTS.md` files.

| Rule (source) | How the plan complies | Status |
|---|---|---|
| Memory is I/O; workflow code never touches a backend (`ARCHITECTURE.md` §2) | Persistence and scrubbing live in the activity. Workflow code only reads `snapshot_hash` and `ref` from the recorded result. | PASS |
| Replay safety / no unpatched command change (`S/workflows/AGENTS.md`) | No activity is added or removed. The new model fields are defaulted. `RecallInput.run_id` is an input field, and Temporal does not compare activity inputs on replay. `_emit` is pure state. T050 proves this on `research_retain_grounded.json`. | PASS |
| Attribute ownership (`S/workflows/AGENTS.md` rules 1-3) | No new attribute. `MemoryHost._recall` calling `ReportHost._emit` is a new cross-host call, recorded in the table (T060). | PASS |
| Artifact boundary: behaviour change updates `<stage>.md` in the same diff (root `AGENTS.md`) | T035 updates the memo-key clauses in `clarify.md`, `plan.md` and `architecture.md`. `scripts/check_clauses.py` runs in T070. | PASS |
| Cross-stage imports banned (stage `AGENTS.md`) | Stages read `snapshot.snapshot_hash` from what `ctx.recall` returns and import nothing new. | PASS |
| Goldens never hand-edited (SG-3) | No golden changes (no memory-on golden scenario). `MEMO_PARITY_KEYS` is a test constant, re-pinned from a capture run (T041). | PASS |

**Post-design re-check**: no violations. Complexity Tracking is empty.

## Phases

### Phase A: memory package (no workflow change)

- **T010** `S/memory/query_hash.py`: add `recall_snapshot_canonical(bank, watermark, query_hash, items, degraded) -> bytes` and `recall_snapshot_hash(...) -> str` (sha256 of those bytes), per data-model "Canonical content". `recall_query_hash` stays as is (FR-003).
- **T011** `S/memory/models.py:23`: on `RecallSnapshot`, add `snapshot_hash: str = ""`, `ref: ArtifactRef | None = None` (import from `S/core/models.py:92`; no cycle) and `persist_failed: bool = False`. Add a `model_validator(mode="after")` that fills `snapshot_hash` when it is empty and `query_hash or degraded`. Rewrite the docstring to describe the real behaviour.
- **T012** `S/artifacts/store.py:22`: add `"recall_snapshot": "recall"` to `_SUBDIRS`.
- **T013** `S/memory/activities.py`:
  - add `run_id: str = ""` to `RecallInput` (`:51`);
  - in `recall_snapshot` (`:61`), scrub each item with `scrub()` (`S/memory/scrub.py:18`) before building the snapshot;
  - route both the healthy and the degraded result through a new `_persisted(snap, run_id)`. It returns `snap` with `ref` set. If `run_id == ""` it returns `snap` unchanged. On any `put` exception it logs and returns `RecallSnapshot(query_hash, bank, watermark, items=[], degraded=True, persist_failed=True)`. It never raises.
  - The outer `except` keeps its current degraded construction.
- **T014** `S/artifacts/read.py`: add `read_recall_snapshot(ref: ArtifactRef) -> RecallSnapshot`. It is a plain function, not an activity. It checks the kind, verifies that sha256(bytes) == `ref.sha256` (`ValueError` otherwise), then rebuilds the snapshot from the canonical array.

### Phase B: workflow and stage plumbing

- **T020** `S/observability/trace.py:16`: add `MEMORY_RECALLED = "memory_recalled"`.
- **T021** `S/workflows/memory_host.py:47`:
  - pass `run_id=workflow.info().workflow_id` in `RecallInput`;
  - after the activity returns, call `emit = getattr(self, "_emit", None)`, and if `emit` is set, emit `MEMORY_RECALLED` with `stage=filters.get("stage")` and data `snapshot_hash`, `snapshot_uri=snap.ref.uri if snap.ref else ""`, and `degraded` and `persist_failed` as `"true"`/`"false"`;
  - the disabled branch (`:50-51`) is unchanged and emits nothing (FR-007).
- **T022** `S/workflows/role_host.py:88`: `_cached_stage` gains the keyword-only `recall_ref: str = ""`. Compute `wm = getattr(self, "_memory_watermark", None) or "none"`, then pass `f"{wm}|{recall_ref}" if recall_ref else wm` as the fifth `content_key` argument (`:114-120`). Update the docstring.
- **T023** `S/core/context.py:36`: add `recall_ref: str = ""` to the `StageContext.cached_stage` Protocol signature. The `graph.py:73` binding is unchanged because it passes the method.
- **T030** `S/stages/clarify/step.py:199`: pass `recall_ref=snapshot.snapshot_hash` to `ctx.cached_stage`.
- **T031** `S/stages/plan/step.py:122`: pass `recall_ref=prep.snapshot.snapshot_hash`.
- **T032** `S/stages/architecture/step.py:204`: pass `recall_ref=prep.snapshot.snapshot_hash`. The delta-retry loop reuses the same snapshot, so both calls use the same value.
- **T035** Stage contracts, edited in the primary checkout. Add a clause to `S/stages/clarify/clarify.md` (near `:40`), `S/stages/plan/plan.md` (`:19`) and `S/stages/architecture/architecture.md` (`:19`): "the memo key's recall slot is the watermark, extended with the recall snapshot hash when memory is on [FR-402]".

### Phase C: tests

Existing tests, adapted (each change is listed, nothing else is edited):

- **T040** Stub `cached_stage` signatures gain `recall_ref: str = ""`:
  - `T/clarify/test_clarify_memo_key.py:151`
  - `T/plan/test_plan_slice_contract.py:88`
  - `T/architecture/test_architecture_slice_contract.py:87`
  - `T/plan/test_plan_step_chaos.py:72`
  - `T/plan/test_plan_step_split.py:26`
  - `T/architecture/test_architecture_step_split.py:35`

  Stub `recall` returns `SimpleNamespace(items=[])`; add `snapshot_hash=""` at:
  - `T/plan/test_plan_step_chaos.py:63`
  - `T/plan/test_plan_step_split.py:20`
  - `T/architecture/test_architecture_step_split.py:29`
  - `T/architecture/test_architect_research_deps.py:67`

  Assertions are unchanged.
- **T041** `T/replay/test_graph_golden.py:28-50,148`: re-pin `MEMO_PARITY_KEYS`. The fifth element becomes `"wm-e74|<degraded snapshot hash>"`, because that test's fake recalls degrade on `int("wm-e74")` (R-4). Replace the `args[-1] == "wm-e74"` assertion with `args[-1].startswith("wm-e74|")`. Add a comment citing 021 R-4. Capture the values by running the test with a print, then paste them in. Don't compute them by hand.
- **T042** `T/test_memory_models.py:12`: assert the new defaults (`snapshot_hash` is non-empty for a non-empty `query_hash`, `ref is None`, `persist_failed is False`). `T/test_recall_query_hash.py` and `T/test_hindsight_recall.py` stay unmodified (FR-003 evidence).

New tests:

- **T043** `T/test_recall_snapshot_artifact.py`, fast tier, with `SDLC_ARTIFACT_ROOT=tmp_path` via `monkeypatch`:
  - hash stability;
  - item-order sensitivity;
  - degraded ≠ healthy for identical bank, watermark, query and empty items;
  - the disabled snapshot has `snapshot_hash == ""`;
  - fake and Hindsight parity for identical content;
  - the persisted file sha256 equals `snapshot_hash`;
  - idempotent double persist;
  - `run_id=""` skips persistence;
  - a `put` failure gives degraded, `persist_failed`, `items=[]` and a recomputed hash;
  - a backend failure combined with a `put` failure does not raise;
  - items are scrubbed;
  - `read_recall_snapshot` round-trips and rejects a tampered file and a wrong kind.
- **T044** `T/test_recall_memo_key.py`, fast tier, against `RoleHost._cached_stage`, using the monkeypatched `content_key` pattern from `T/replay/test_graph_golden.py:121`:
  - `recall_ref=""` gives the exact pre-021 slot (`"none"`, or the watermark);
  - a non-empty ref gives `wm|ref`;
  - different items give a different key, and the same items give the same key (US2).
- **T045** `T/test_recall_snapshot_event.py`, fast tier, against `MemoryHost._recall` with a stub `execute_activity` and `workflow.info`:
  - memory on emits exactly one `memory_recalled` event with the stage from the filters and no items;
  - memory off emits nothing;
  - a cache-hit stage still has its event (the emit precedes `cached_stage`).
- **T050** `pytest -m temporal T/replay/test_research_retain_replay.py` passes **without** editing `research_retain_grounded.json` (FR-009, SC-005). This is a blocking check, not a code task.

### Phase D: docs and bookkeeping

- **T060** `S/workflows/AGENTS.md`: add the cross-host reader row (`MemoryHost._recall` → `ReportHost._emit`, `getattr`-guarded). Add a short "Recall snapshots (021)" paragraph: persistence lives in the activity, there is no patch marker and why, and `recall_snapshot/v1` is a wire tag that is never changed in place.
- **T061** (**applied at GATE 2** by user instruction and committed with the planning artifacts; the implementer only checks it) `ARCHITECTURE.md:210-229` (ADR-5 paragraph), GATE 2 ruling 1: replace "Recall is itself a cached activity keyed with a per-run memory watermark: reusing the persisted RecallSnapshot *is* the freeze … removes any need for Hindsight point-in-time reads" with the shipped behaviour. Each stage-level recall is persisted as a content-addressed snapshot, and its hash joins the watermark in the memo key. Recall itself is not cached, so a backend whose answers vary under a fixed watermark (live Hindsight) yields an explicit, hashed cache miss rather than a freeze. Pinned-watermark reuse is the follow-up `.workspace/tasks/2026-11-11-recall-snapshot-pinned-reuse.md`.
- **T062** `ROADMAP.md:327`: tick FR-402, noting "stage-level `ctx.recall` snapshots persisted, content-addressed and keyed (021); `recall_leads` excluded (GATE 2 ruling 2, card `2026-11-11-recall-leads-snapshot-and-degrade.md`); live-Hindsight re-runs miss the cache by design (card `2026-11-11-recall-snapshot-pinned-reuse.md`)".
- **T063** Update the `CLAUDE.md` SPECKIT block to point at this plan (done during planning).
- **T064** Follow-up cards: **done at GATE 2**. The four cards are in `.workspace/tasks/`: `2026-11-11-recall-snapshot-pinned-reuse.md`, `2026-11-11-recall-leads-snapshot-and-degrade.md`, `2026-11-11-memo-cache-tenant-scope.md`, `2026-11-11-fakememory-nonnumeric-watermark.md`. The implementer only checks that they exist.
- **T070** Verification gate (blocking), run as one batch:
  - `pytest` (no new failures beyond the 8 pre-existing ones on `main`);
  - `pytest -m temporal T/replay`;
  - `ruff check .`;
  - `ruff format --check .`;
  - `mypy`;
  - `python scripts/check_clauses.py`;
  - `python scripts/check_file_size.py`.

## Replay-safety analysis (FR-009)

| Execution class | What changes for it | Safe because |
|---|---|---|
| Checked-in memory-on history (`research_retain_grounded.json`) | recorded `recall_snapshot` result lacks the new fields | defaults plus the validator; no command added; T050 |
| In-flight run whose recall completed before deploy | the validator gives it a `snapshot_hash`, so its later `cache_get` input differs | cache activity inputs are not compared on replay; a one-time cache miss is acceptable (ADR-5) |
| In-flight run whose recall happens after deploy | new `RecallInput.run_id`; a file is written | an input field is not a command; the write is idempotent across the 5 `MEM_ACT` retries |
| Memory-off runs, all goldens | none: no event, empty hash, identical key | FR-007 by construction; T044 and T070 |
| Hosts without ReportHost (crew, triage, tidyup) | `_emit` absent | the `getattr` guard; they do not call `_recall` today |

## Project Structure

### Documentation (this feature)

```text
.specify/specs/021-recall-snapshot-artifact/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/recall-snapshot-artifact.md
├── advisor-*.md  skeptic-*.md
└── checklists/requirements.md  plan.md (reviewer)
```

### Source code touched

`S/memory/{query_hash,models,activities}.py`, `S/artifacts/{store,read}.py`, `S/observability/trace.py`, `S/workflows/{memory_host,role_host}.py`, `S/core/context.py`, `S/stages/{clarify,plan,architecture}/step.py` and their `<stage>.md` files.

## Traceability

| Req | Tasks | Validation |
|---|---|---|
| FR-001 | T013 | T043, Q2 |
| FR-002 | T010, T011 | T043, Q1 |
| FR-003 | T010 (no edit) | `test_recall_query_hash.py` unmodified, T042 |
| FR-004 | T021, T022, T030-T032 | T044, T045 |
| FR-005 | T013 | T043 |
| FR-006 | T011 (degraded in hash) | T043, T044 |
| FR-007 | T021, T022 | T044, T045, T070 goldens |
| FR-008 | T013, T021 | T043, T045 |
| FR-009 | T011, T013, T021 | T050 |
| FR-010 | T022 | T044 |
| FR-011 | T013, T021 | T045 (no items), contract §3 |
| FR-012 | T013 | T043 (items scrubbed before hash, file and return) |
| SC-001 | T013, T014, T021 | T043 reader, T045 |
| SC-002 | T022 | T044 |
| SC-003 | T021, T022 | T070 (goldens), T044 |
| SC-004 | T013, T011 | T043, T044 |
| SC-005 | T011, T013, T021 | T050 |

## GATE 2 rulings (2026-11-11)

All five recommendations were accepted:
1. Live-Hindsight cache misses accepted. ADR-5 corrected (T061). Card filed.
2. FR-001 and SC-001 narrowed to stage-level `ctx.recall` in spec.md. Card filed for `recall_leads`.
3. Memo-cache tenant scope: card filed. Out of scope.
4. `FakeMemory` non-numeric watermark: card filed. Out of scope. T041 re-pins against current (degraded) behaviour.
5. `cache_put` is kept for degraded-recall stages (R-5).

Extra ruling: scrub before the artifact-store write is **in scope** as spec FR-012 (T013, T043; research R-8).

## Complexity Tracking

None.
