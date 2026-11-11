# Research — 021 RecallSnapshot persisted input

Inputs: `advisor-answer-1.md` (D1-D5), `skeptic-answer-1.md` (L1-L5, probes 1-6). Each skeptic claim cited below was checked against the tree at `067e1408`.

## R-1 Persistence runs inside `recall_snapshot` (advisor D1, skeptic 5A)
- **Decision**: persist inside the existing activity (`src/sdlc/memory/activities.py:61`). No new activity, no new workflow command, no `workflow.patched`.
- **Rationale**: `research_retain_grounded.json` is the only checked-in history that schedules `recall_snapshot`, and its next command is the clarify agent. A second activity would be a NondeterminismError. New `RecallSnapshot` fields are defaulted, so the recorded result (`{"query_hash":…,"items":[],"degraded":false}`) still validates.
- **Spec erratum**: spec D3 said a payload-shape change "alters the command sequence". It doesn't. Only adding or removing commands does. Corrected in spec.md (Errata E-1).
- **Alternatives**: a separate `persist_recall_snapshot` activity (rejected: needs a patch and changes the command sequence).

## R-2 Run id travels on `RecallInput` (advisor D1, skeptic 2B)
- **Decision**: `RecallInput.run_id: str = ""`, set by `MemoryHost._recall` from `workflow.info().workflow_id`. GraphWorkflow's run id is its workflow id (`graph.py:171`). An empty `run_id` (direct unit-test calls in `tests/test_memory_activities.py:26,61`) skips persistence and leaves `ref=None` and `persist_failed=False`.
- **Rationale**: `activity.info()` raises outside an activity, and that error would be swallowed by the outer `except` and turn every direct-call test into a degraded snapshot (skeptic 2B). An explicit field is testable, and activity inputs are not compared on replay.
- **Alternatives**: `activity.info().workflow_id` inside the activity (rejected: as above); a run-independent `<root>/_recall/` path (rejected: breaks per-run layout and SC-001 "from that run").

## R-3 Content hash: one definition, derived on the model (advisor D5, skeptic 4, 5A)
- **Decision**: add `recall_snapshot_hash(bank, watermark, query_hash, items, degraded)` in `src/sdlc/memory/query_hash.py`. It hashes `json.dumps(["recall_snapshot/v1", bank, watermark, query_hash, items, degraded], separators=(",",":"), ensure_ascii=False)`. `RecallSnapshot` fills `snapshot_hash` in a `model_validator(mode="after")` when it is empty and `query_hash or degraded`.
- **Rationale**: the validator gives fake, Hindsight, degraded, replayed pre-021 results and test stubs the same hash without per-backend code. The memory-disabled snapshot (`query_hash=""`, not degraded, `memory_host.py:51`) keeps `snapshot_hash=""`, which is what makes FR-007 hold. No backend name in the hash, so fake/Hindsight parity is testable. `items` is `list[str]` (`memory/models.py:33`), so the advisor's concern about volatile item fields does not arise.
- **Persisted bytes = hashed bytes**: the artifact file holds exactly the canonical JSON that was hashed, so `ArtifactRef.sha256 == snapshot_hash` and a reader can verify the content address by re-hashing the file.
- **Alternatives**: hash in each backend (rejected: drift); include the tenant or backend in the hash (rejected for this feature; see R-9).

## R-4 Memo-key threading: `recall_ref` kwarg (advisor D2, skeptic 1A/1B)
- **Decision**: `RoleHost._cached_stage(..., *, prompt_digest="", recall_ref: str = "")`. The fifth `content_key` slot (`upstream_recall_ref`, `memoization/cache.py:42`) becomes `wm` when `recall_ref == ""`, else `f"{wm}|{recall_ref}"`, where `wm = self._memory_watermark or "none"` as today (`role_host.py:119`). The three stages pass `recall_ref=snapshot.snapshot_hash`.
- **Rationale**: memory off means `snapshot_hash == ""`, so the slot is the identical string `"none"` or the watermark (FR-007). The hash lands in the slot reserved for it. `input_json` and `prompt_digest` stay untouched, so `_clarify_memo_extra` (`clarify/step.py:196`) and its tests are unaffected. Carrying the hash on `prep.snapshot` avoids a mutable scalar on `MemoryHost` (skeptic 1B path C).
- **Consequence**: `tests/replay/test_graph_golden.py:106-148` runs memory on with `watermark="wm-e74"`. `FakeMemory.recall` raises on `int("wm-e74")` (`fake.py:44`), so that test's recalls are degraded today and their snapshot hash is non-empty after 021. `MEMO_PARITY_KEYS` (`:28-50`) and the `args[-1] == "wm-e74"` assertion (`:148`) are re-pinned deliberately (plan T041). The other memo-key pins run memory off and stay byte-identical.
- **Alternatives**: fold into `input_json` (rejected: breaks `test_clarify_memo_key.py:238` and `test_plan_step_chaos.py:194,205`, and changes keys for memory-off stubs); a scalar on MemoryHost (rejected: graph rounds re-enter `produce` after another stage's `prepare`).

## R-5 Persistence failure and the double fault (spec FR-008, skeptic 3A/3B; advisor D3)
- **Decision**: one helper, `_persisted(snap, run_id) -> RecallSnapshot`, never raises. On a `store.put` failure it returns `RecallSnapshot(query_hash, bank, watermark, items=[], degraded=True, persist_failed=True, ref=None)`; the validator recomputes the hash over the degraded content. The degraded-backend path also goes through `_persisted`, so a double fault yields the same unpersisted degraded snapshot and still does not raise.
- **Rationale**: discarding items means a stage never consumes memory that cannot be retrieved later (SC-001). `degraded` in the hash separates the key from any healthy one (FR-006).
- **`cache_put` on degraded**: kept (advisor D3) and the skeptic's skip is rejected. Keys already differ, so healthy never reads degraded. Reusing a degraded output under a degraded key is what the stage would produce again anyway, and skipping would make every outage re-pay model cost.

## R-6 Stage record = a `MEMORY_RECALLED` trace event (advisor D4, skeptic 2A)
- **Decision**: add `RunEventKind.MEMORY_RECALLED = "memory_recalled"` (`observability/trace.py:16`). `MemoryHost._recall` emits it after the activity returns (memory on only), via the cross-host `_emit` (`report_host.py:38`) guarded with `getattr(self, "_emit", None)`. Fields: `stage=filters.get("stage")`; data `snapshot_hash`, `snapshot_uri` (`""` if none), `degraded`, `persist_failed` (strings).
- **Rationale**: it fires before `cached_stage`, so cache-hit stages are covered. It covers every caller of `ctx.recall` from one place. `RunEvent.data` is `dict[str,str]`, which keeps the change additive, and events reach `events.jsonl` (`observability/activities.py:31`). The skeptic's 2A is right that `BenchmarkRecord` is dropped on non-benchmark runs (`benchmark_host.py:55,103`), which is why it isn't used. `StageOutcome` and `RunSummary` are not touched (no wire change).
- **Golden traces**: no golden scenario runs memory on (`tests/replay/golden/*.json` contain no `memory_retained` or `recall_snapshot`), so goldens are byte-identical (SC-003).
- **Alternatives**: `BenchmarkRecord`, `StageOutcome` or `RunState` fields (rejected: dropped on non-benchmark runs, or a wire change).

## R-7 Reader and shared storage (skeptic probe 3)
- **Decision**: add `read_recall_snapshot(ref) -> RecallSnapshot` in `src/sdlc/artifacts/read.py`, a plain function and not an activity. It asserts `ref.kind == "recall_snapshot"`, re-hashes the bytes against `ref.sha256` and raises on a mismatch. Register `"recall_snapshot": "recall"` in `_SUBDIRS` (`store.py:22`).
- **Out of scope**: dashboard or CLI routes, and multi-host shared volumes. These match the existing `harness_session` behaviour. The reader is the SC-001 test hook and the place a route will call later.

## R-8 Scrub recalled items (skeptic 6A; spec FR-012, GATE 2)
- **Decision**: `recall_snapshot` applies `scrub()` (`memory/scrub.py:18`) to each recalled item before the snapshot is built, so the hash, the persisted file and the prompt all see the same scrubbed text.
- **Rationale**: retain already scrubs, so this is normally a no-op. It covers externally seeded or consolidated memories and needs no extra plumbing.

## R-9 Not in this feature (skeptic 6B, probe 1, probe 5, 4A)
- **Tenant isolation of the memo cache** (6B): pre-existing. `_cache_root()` (`memoization/cache.py:31`) has no tenant scope today, and 021 does not widen it. Snapshot files are under `<root>/<run_id>/`. → card `2026-11-11-memo-cache-tenant-scope.md` (GATE 2 ruling 3).
- **Hindsight freeze** (probe 1): accepted at GATE 2 (ruling 1). Card `2026-11-11-recall-snapshot-pinned-reuse.md`.
- **`recall_leads`** (probe 5, `agents/research/tools/recall_leads.py:14`): excluded by narrowing FR-001 at GATE 2 (ruling 2). Card `2026-11-11-recall-leads-snapshot-and-degrade.md`.
- **`FakeMemory` crashes on a non-integer watermark** (4A, `fake.py:44`): pre-existing, and only reached by `test_graph_golden.py`. 021 tests use integer watermarks. → card `2026-11-11-fakememory-nonnumeric-watermark.md` (GATE 2 ruling 4).
