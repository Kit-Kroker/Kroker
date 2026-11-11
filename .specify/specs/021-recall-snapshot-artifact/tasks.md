# Tasks: RecallSnapshot as a Persisted, Content-Addressed Stage Input (round 021, FR-402)

**Status**: Reviewer-approved (tasks checklist, pass 2, 2026-11-11). Pass 1 found one gap: the FR-001 traceability cell. Record: [checklists/tasks.md](checklists/tasks.md). After approval, T031 was turned into a check because the ADR-5 text was applied at GATE 2 by user instruction. Do not implement before GATE 3.

**Input**: `.specify/specs/021-recall-snapshot-artifact/`:
- spec.md (GATE 1 Q1-Q3; Errata E-1, E-2; GATE 2 rulings 1-5 + FR-012);
- plan.md (plan ids T010-T070, approved pass 2);
- research.md (R-1 to R-9);
- data-model.md;
- contracts/recall-snapshot-artifact.md (§1-§4);
- quickstart.md (Q1-Q8).

The ids below are sequential (T001 and up). Each task names the plan id it implements as `(plan Txxx)`. Paths are repo-relative; `S/` = `src/sdlc/`, `T/` = `tests/`.

**Tests**: required. Each new behaviour gets its test written first, and the test is seen failing for the expected reason before the implementation. Adaptations of existing tests are listed exactly; no other existing test is edited.

**Rules for the implementer**:
- No new Temporal activity and no `workflow.patched` anywhere (research R-1, spec E-1). If a step seems to need one, STOP and report.
- `T/test_recall_query_hash.py`, `T/test_hindsight_recall.py`, `T/replay/histories/*.json` and `T/replay/golden/*.json` are never edited.
- Stage `<stage>.md` contracts are edited in the primary checkout, never by a sandboxed harness (root `AGENTS.md`, sandbox boundary).
- Only T008, T026, T028, T029 and T036 run `pytest -m temporal`. No task runs the `temporal` CLI.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1-US4 from spec.md

---

## Phase 1: Setup

- [x] T001 Record the baseline: run `pytest -q` from the repo root and save the list of failing test ids to `.specify/specs/021-recall-snapshot-artifact/baseline-failures.txt`. Expect the 8 pre-existing fast-tier failures on `main`; any other failure is a STOP. (plan T070 baseline)

---

## Phase 2: Foundational (blocks every story)

**Purpose**: the hash definition, the model fields, the store subdir and the event kind. Nothing here changes runtime behaviour on its own.

- [x] T002 [P] Write failing tests in new file `T/test_recall_snapshot_artifact.py` (section "hash") for `recall_snapshot_canonical` / `recall_snapshot_hash` in `S/memory/query_hash.py`:
  - the same inputs give the same hash;
  - swapping two items changes the hash;
  - `degraded=True` vs `False` with an identical bank, watermark, query_hash and `items=[]` gives different hashes;
  - `sha256(recall_snapshot_canonical(...)) == recall_snapshot_hash(...)`;
  - the canonical bytes decode to a JSON array whose first element is `"recall_snapshot/v1"`.

  (plan T043, T010)
- [x] T003 Implement `recall_snapshot_canonical(bank, watermark, query_hash, items, degraded) -> bytes` and `recall_snapshot_hash(...) -> str` in `S/memory/query_hash.py`, per data-model.md "Canonical content". Leave `recall_query_hash` byte-for-byte unchanged (FR-003). T002 must pass. (plan T010)
- [x] T004 Write failing tests in `T/test_recall_snapshot_artifact.py` (section "model") and extend `T/test_memory_models.py:12` (`test_recall_snapshot_defaults_not_degraded`):
  - `RecallSnapshot(query_hash="q", bank="b", watermark="w")` gets a non-empty `snapshot_hash` equal to `recall_snapshot_hash("b","w","q",[],False)`, with `ref is None` and `persist_failed is False`;
  - the disabled shape `RecallSnapshot(query_hash="", bank="b", watermark="unknown")` keeps `snapshot_hash == ""`;
  - `RecallSnapshot(query_hash="", ..., degraded=True)` gets a hash;
  - an explicitly passed `snapshot_hash` is kept;
  - `RecallSnapshot.model_validate_json('{"query_hash":"01cb","bank":"project:default","watermark":"0","items":[],"degraded":false}')` (the pre-021 shape recorded in `T/replay/histories/research_retain_grounded.json`) validates and gets a hash.

  (plan T042, T011)
- [x] T005 Add `snapshot_hash: str = ""`, `ref: ArtifactRef | None = None` (import `ArtifactRef` from `S/core/models.py:92`) and `persist_failed: bool = False` to `RecallSnapshot` in `S/memory/models.py:23`. Add a `model_validator(mode="after")` that sets `snapshot_hash` via `recall_snapshot_hash` when it is empty and `query_hash or degraded`. Rewrite the class docstring to describe the persisted, hashed behaviour. T004 must pass. (plan T011)
- [x] T006 [P] Add `"recall_snapshot": "recall"` to `_SUBDIRS` in `S/artifacts/store.py:22`. (plan T012)
- [x] T007 [P] Add `MEMORY_RECALLED = "memory_recalled"` to `RunEventKind` in `S/observability/trace.py:16`, next to `MEMORY_RETAINED`. (plan T020)
- [x] T008 Checkpoint:
  - run `pytest -q T/test_recall_query_hash.py T/test_memory_models.py T/test_hindsight_recall.py T/test_recall_snapshot_artifact.py T/test_memory_activities.py`, which must be green with the first three files unedited (except `T/test_memory_models.py`, by T004);
  - run `pytest -m temporal -q T/replay/test_research_retain_replay.py`, which must pass without editing the history (FR-009 early signal).

  (plan T050)

**Checkpoint**: the model can carry a content hash. No behaviour has changed yet.

---

## Phase 3: User Story 1, audit what memory a stage saw (P1) 🎯 MVP

**Goal**: every stage-level `ctx.recall` persists a scrubbed, content-addressed snapshot, records it on the trace, and the snapshot can be read back verified (FR-001, FR-002, FR-005, FR-011, FR-012, SC-001).

**Independent test**: `pytest -q T/test_recall_snapshot_artifact.py T/test_recall_snapshot_event.py`.

- [x] T009 [P] [US1] Write failing tests in `T/test_recall_snapshot_artifact.py` (section "persist"). Use `monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))`. Call `recall_snapshot(RecallInput(..., run_id="run-1"))` directly, against a `FakeMemory` seeded via `retain`, with an integer watermark. Assert:
  - the file `tmp_path/run-1/recall/<snapshot_hash>.json` exists;
  - its sha256 equals `snapshot_hash` and `ref.sha256`;
  - `ref.kind == "recall_snapshot"`;
  - a second identical call leaves exactly one file with identical bytes (FR-005);
  - `run_id=""` writes nothing and returns `ref is None`, `persist_failed is False`;
  - a seeded item containing `sk-` plus 20+ chars comes back scrubbed, and the persisted bytes contain the scrubbed text, not the secret (FR-012).

  (plan T043, T013)
- [x] T010 [US1] In `S/memory/activities.py`:
  - add `run_id: str = ""` to `RecallInput` (`:51`);
  - in `recall_snapshot` (`:61`), map `scrub()` (`S/memory/scrub.py:18`) over the backend snapshot's items and rebuild it with `snapshot_hash=""`, so the validator re-hashes the scrubbed content;
  - add a module-level `_persisted(snap: RecallSnapshot, run_id: str) -> RecallSnapshot` that writes `recall_snapshot_canonical(...)` with `LocalFileStore().put("recall_snapshot", run_id, f"{snap.snapshot_hash}.json", data)` and returns `snap.model_copy(update={"ref": ref})`;
  - `_persisted` returns `snap` unchanged when `run_id == ""`;
  - route the healthy return through `_persisted`.

  Failure handling is done in T025 (US3). T009 must pass. (plan T013)
- [x] T011 [US1] Write failing tests in `T/test_recall_snapshot_artifact.py` (section "reader") for `read_recall_snapshot` in `S/artifacts/read.py`:
  - it round-trips a snapshot persisted by T010 to an equal `RecallSnapshot` (same items, hash and flags);
  - it raises `ValueError` when one byte of the file is altered;
  - it raises `ValueError` for a ref with `kind="harness_session"`.

  (plan T043, T014)
- [x] T012 [US1] Add the plain function `read_recall_snapshot(ref: ArtifactRef) -> RecallSnapshot` to `S/artifacts/read.py`. It is not an `@activity.defn`. It checks the kind, verifies `hashlib.sha256(bytes).hexdigest() == ref.sha256`, then rebuilds the snapshot from the canonical array, per contract §2. T011 must pass. (plan T014)
- [x] T013 [P] [US1] Write failing tests in new file `T/test_recall_snapshot_event.py` for `MemoryHost._recall` (`S/workflows/memory_host.py:47`):
  - monkeypatch `workflow.execute_activity` to capture the `RecallInput` and return a fixed healthy `RecallSnapshot` with a `ref`;
  - monkeypatch `workflow.info` to return an object with `workflow_id="run-1"`;
  - give the host a stub `_emit` that records calls;
  - assert `RecallInput.run_id == "run-1"`;
  - assert exactly one `MEMORY_RECALLED` event with `stage="clarify"` (from `filters={"stage": "clarify"}`) and data keys exactly `{snapshot_hash, snapshot_uri, degraded, persist_failed}`, with no item text anywhere in the event (FR-011);
  - a host without `_emit` does not raise.

  (plan T045, T021)
- [x] T014 [US1] In `S/workflows/memory_host.py:47`:
  - pass `run_id=workflow.info().workflow_id` in `RecallInput`;
  - after `execute_activity` returns, call `emit = getattr(self, "_emit", None)`, and if `emit` is set, emit `RunEventKind.MEMORY_RECALLED` with `stage=filters.get("stage")`, `snapshot_hash=snap.snapshot_hash`, `snapshot_uri=snap.ref.uri if snap.ref else ""`, and `degraded` and `persist_failed` as `"true"`/`"false"`;
  - leave the disabled branch (`:50-51`) untouched.

  T013 must pass. (plan T021)
- [x] T015 [US1] Run `pytest -q T/test_recall_snapshot_artifact.py T/test_recall_snapshot_event.py T/test_memory_activities.py`, which must be green. (quickstart Q1, Q2, Q4)

**Checkpoint**: US1 is independently demonstrable. The stage memo key is not yet changed.

---

## Phase 4: User Story 2, changed recall is an explicit input change (P1)

**Goal**: `snapshot_hash` joins the watermark in the memo-key recall slot (FR-004, FR-010, SC-002), and the stage contracts say so.

**Independent test**: `pytest -q T/test_recall_memo_key.py T/clarify T/plan T/architecture`.

- [x] T016 [P] [US2] Write failing tests in new file `T/test_recall_memo_key.py` for `RoleHost._cached_stage` (`S/workflows/role_host.py:88`). Follow the monkeypatched `content_key` pattern of `T/replay/test_graph_golden.py:121`, and stub `cache_get`/`cache_put` via `workflow.execute_activity`. Assert:
  - with `recall_ref=""` and `_memory_watermark=None`, the fifth `content_key` arg is exactly `"none"`;
  - with `recall_ref=""` and `_memory_watermark="5"`, it is exactly `"5"`;
  - with `recall_ref="abc"` and `_memory_watermark="5"`, it is `"5|abc"`;
  - two `RecallSnapshot`s with the same bank, watermark and query_hash but different items, passed as `recall_ref=snap.snapshot_hash`, give different keys, and identical items give identical keys.

  (plan T044, T022)
- [x] T017 [US2] Add the keyword-only `recall_ref: str = ""` to `RoleHost._cached_stage` in `S/workflows/role_host.py:88`. Compute `wm = getattr(self, "_memory_watermark", None) or "none"` and pass `f"{wm}|{recall_ref}" if recall_ref else wm` as the fifth `content_key` argument (`:114-120`). Add `recall_ref: str = ""` after `prompt_digest` in the `StageContext.cached_stage` Protocol (`S/core/context.py:36-45`). Update the `_cached_stage` docstring. T016 must pass. (plan T022, T023)
- [x] T018 [US2] Adapt the existing stubs (signature and attribute only; assertions unchanged) so the stage edits in T019-T021 do not break them (plan T040).

  Add `recall_ref: str = ""` to each stub `cached_stage` signature:
  - `T/clarify/test_clarify_memo_key.py:151`
  - `T/plan/test_plan_slice_contract.py:88`
  - `T/architecture/test_architecture_slice_contract.py:87`
  - `T/plan/test_plan_step_chaos.py:72`
  - `T/plan/test_plan_step_split.py:26`
  - `T/architecture/test_architecture_step_split.py:35`

  Add `snapshot_hash=""` to each `SimpleNamespace(items=[])` recall stub:
  - `T/plan/test_plan_step_chaos.py:63`
  - `T/plan/test_plan_step_split.py:20`
  - `T/architecture/test_architecture_step_split.py:29`
  - `T/architecture/test_architect_research_deps.py:67`
- [x] T019 [P] [US2] Pass `recall_ref=snapshot.snapshot_hash` to `ctx.cached_stage` in `S/stages/clarify/step.py:199`. (plan T030)
- [ ] T020 [P] [US2] Pass `recall_ref=prep.snapshot.snapshot_hash` to `ctx.cached_stage` in `S/stages/plan/step.py:122`. (plan T031)
- [ ] T021 [P] [US2] Pass `recall_ref=prep.snapshot.snapshot_hash` to `ctx.cached_stage` in `S/stages/architecture/step.py:204`. The delta-retry loop reuses the same `prep.snapshot`, so do not re-recall. (plan T032)
- [ ] T022 [US2] In the primary checkout, add one clause to each stage contract, worded: "The memo key's recall slot is the run's memory watermark, extended with the stage's recall snapshot hash when memory is on. [FR-402, 021]". Locations:
  - `S/stages/clarify/clarify.md` (after `:40`);
  - `S/stages/plan/plan.md` (after `:19`);
  - `S/stages/architecture/architecture.md` (after `:19`).

  (plan T035)
- [ ] T023 [US2] Run `pytest -q T/test_recall_memo_key.py T/clarify T/plan T/architecture`, which must be green. (quickstart Q3)

**Checkpoint**: US1 and US2 together deliver FR-402.

---

## Phase 5: User Story 3, a memory outage does not poison the cache (P2)

**Goal**: a persistence failure or backend failure becomes an item-free, degraded, distinctly hashed snapshot, and the activity never raises (FR-006, FR-008, SC-004; GATE 1 Q3; GATE 2 ruling 5 keeps `cache_put`).

**Independent test**: `pytest -q T/test_recall_snapshot_artifact.py -k "fail or degraded"`.

- [ ] T024 [P] [US3] Write failing tests in `T/test_recall_snapshot_artifact.py` (section "failure"):
  - (a) monkeypatch `LocalFileStore.put` to raise `OSError`, with a healthy seeded `FakeMemory`. The result has `degraded is True`, `persist_failed is True`, `items == []`, `ref is None`, and `snapshot_hash == recall_snapshot_hash(bank, wm, qh, [], True)`, which differs from the healthy hash.
  - (b) make the backend raise and `put` raise. `recall_snapshot` returns (does not raise) a degraded, `persist_failed` snapshot.
  - (c) make the backend raise while `put` works. The degraded snapshot is persisted, with `ref` set and `persist_failed is False`.
  - (d) `T/test_memory_activities.py:61` (`test_recall_snapshot_degrades_on_backend_error`) still passes unedited.

  (plan T043, T013)
- [ ] T025 [US3] In `S/memory/activities.py`, wrap the `put` inside `_persisted` in its own `try/except Exception`. On failure, log a warning with `exc_info` and return `RecallSnapshot(query_hash=snap.query_hash, bank=snap.bank, watermark=snap.watermark, items=[], degraded=True, persist_failed=True)`, letting the validator hash it. Route the outer-`except` degraded snapshot through `_persisted` as well. `recall_snapshot` must still never raise. T024 must pass. (plan T013)
- [ ] T026 [US3] Run `pytest -q T/test_recall_snapshot_artifact.py T/test_memory_activities.py` (green), then `pytest -m temporal -q T/replay/test_research_retain_replay.py` (green, history unedited). (quickstart Q2, Q5; plan T050)

---

## Phase 6: User Story 4, memory-off runs are unchanged (P2)

**Goal**: memory-off keys, traces and goldens are byte-identical (FR-007, SC-003). The one memory-on memo pin is re-pinned deliberately.

**Independent test**: `pytest -m temporal -q T/replay/test_graph_golden.py`.

- [ ] T027 [P] [US4] Extend `T/test_recall_snapshot_event.py`: with `cfg.memory.enabled=False`, `MemoryHost._recall` emits no event, schedules no activity, and returns `snapshot_hash == ""`. Extend `T/test_recall_memo_key.py`: feeding that snapshot's `snapshot_hash` as `recall_ref` yields the exact pre-021 slot `"none"`. These tests pass on arrival (they pin T014 and T017), so record that in the commit message instead of a red run. (plan T044, T045)
- [ ] T028 [US4] Re-pin `MEMO_PARITY_KEYS` in `T/replay/test_graph_golden.py:28-50` (plan T041; spec E-2; research R-4):
  - add a temporary `print(seen)` in `test_memo_key_inputs_match_the_pinned_keys`;
  - run `pytest -m temporal -q -s T/replay/test_graph_golden.py -k memo_key_inputs`;
  - paste the captured tuples, whose fifth element is now `"wm-e74|<hash>"` (the recalls are degraded because `FakeMemory` cannot parse `"wm-e74"`; card `.workspace/tasks/2026-11-11-fakememory-nonnumeric-watermark.md`);
  - replace the assertion at `:148` with `assert all(args[-1].startswith("wm-e74|") for args in seen)`;
  - remove the print and add a comment citing 021 R-4 and that card.

  Do not compute the hashes by hand.
- [ ] T029 [US4] Run `pytest -m temporal -q T/replay`. All goldens must pass with `git diff --exit-code T/replay/golden T/replay/histories`, and `T/replay/test_graph_golden.py` is the only edited replay test file. (quickstart Q6)

---

## Phase 7: Polish and cross-cutting

- [ ] T030 [P] In `S/workflows/AGENTS.md`, add a cross-host row for `MemoryHost._recall` → `ReportHost._emit` (`getattr`-guarded) to the ownership table. Add a "Recall snapshots (021)" paragraph covering three points: persistence lives inside `recall_snapshot`, so there is no new command and no patch marker; why the defaulted fields are replay-safe; and that `recall_snapshot/v1` is a wire tag never changed in place. (plan T060)
- [ ] T031 [P] Check that the ADR-5 paragraph in `ARCHITECTURE.md:210-229` already carries the GATE 2 ruling 1 correction ("Recall itself is **not** a cached activity …", citing `.workspace/tasks/2026-11-11-recall-snapshot-pinned-reuse.md`). It was applied and committed with the planning artifacts. Edit it only if the shipped behaviour differs from that text. (plan T061; GATE 2 ruling 1)
- [ ] T032 [P] In `ROADMAP.md:327`, change `- [ ] ⚠️ **FR-402**` to `- [x] **FR-402**` and replace its note with the text given in plan T062. (plan T062; GATE 2 ruling 2)
- [ ] T033 [P] Check that the four GATE 2 cards exist in `.workspace/tasks/`:
  - `2026-11-11-recall-snapshot-pinned-reuse.md`
  - `2026-11-11-recall-leads-snapshot-and-degrade.md`
  - `2026-11-11-memo-cache-tenant-scope.md`
  - `2026-11-11-fakememory-nonnumeric-watermark.md`

  If any is missing, STOP. (plan T064)
- [ ] T034 Check that `CLAUDE.md`'s `<!-- SPECKIT START -->` block points at `.specify/specs/021-recall-snapshot-artifact/plan.md` (already applied during planning). (plan T063)
- [ ] T035 Run `ruff check . && ruff format --check . && mypy && python scripts/check_clauses.py && python scripts/check_file_size.py`, which must be clean. (plan T070; quickstart Q8)
- [ ] T036 Final gate (blocking):
  - `pytest -q` must show no failures beyond `baseline-failures.txt` from T001;
  - `pytest -m temporal -q T/replay` must be green.

  STOP and report on any deviation. (plan T070, T050; quickstart Q7)

---

## Dependencies

```text
T001 → Phase 2 (T002→T003; T004→T005; T006, T007 independent) → T008
T008 → US1 (T009→T010; T011→T012 [needs T010]; T013→T014) → T015
T015 → US2 (T016→T017→T018→T019|T020|T021→T022) → T023
T010 → US3 (T024→T025) → T026          # US3 needs only US1's _persisted
T014, T017 → US4 (T027, T028) → T029
T023, T026, T029 → Polish (T030-T034 parallel) → T035 → T036
```

- US1 is the MVP and depends only on Phase 2.
- US2 needs US1's `snapshot_hash` on recalled snapshots (T005) and the trace event to be meaningful, but compiles after Phase 2. Keep this order so that the stage memo key only moves once persistence exists.
- US3 and US2 touch disjoint files (`S/memory/activities.py` vs `role_host.py`, the stages and their stubs), so they can run in parallel after T015.
- US4 runs last among the stories because T028 pins keys produced by T017 and T019-T021.

## Parallel examples

- Phase 2: T002 ∥ T006 ∥ T007 (three different files). T004 follows T002 because both write `T/test_recall_snapshot_artifact.py`.
- US1: T009 ∥ T013 (different test files). T011 follows T009 (same test file).
- US2: T019 ∥ T020 ∥ T021 (three stage files).
- Polish: T030 ∥ T031 ∥ T032 ∥ T033.

## Traceability

| Req | Tasks |
|---|---|
| FR-001 | T009, T010, T024, T025 |
| FR-002 | T002, T003, T004, T005 |
| FR-003 | T003 (no edit), T008 |
| FR-004 | T013, T014, T016-T021 |
| FR-005 | T009, T010 |
| FR-006 | T002, T024, T025 |
| FR-007 | T027, T029 |
| FR-008 | T024, T025 |
| FR-009 | T004, T008, T026, T036 |
| FR-010 | T016, T017 |
| FR-011 | T013, T014 |
| FR-012 | T009, T010 |
| SC-001 | T011, T012, T013, T014 |
| SC-002 | T016 |
| SC-003 | T029 |
| SC-004 | T024, T025 |
| SC-005 | T008, T026 |

## Implementation strategy

1. **MVP**: Phases 1-3 (US1). Snapshots are persisted, scrubbed, recorded and readable. Memo keys are unchanged, so nothing moves in the cache.
2. **FR-402 complete**: add US2. The memo key declares the snapshot.
3. **Hardening**: add US3 (failure paths), then US4 (identity pins and the re-pin).
4. One branch, fast-forwarded to `main` after T036, per the round-020 integration convention. Commits follow the phase boundaries.
