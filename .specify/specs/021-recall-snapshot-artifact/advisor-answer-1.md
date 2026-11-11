# Advisor answer 1 — 021 RecallSnapshot persisted input

Read: spec.md, memory/activities.py, memory/query_hash.py, workflows/memory_host.py, workflows/role_host.py (`_cached_stage`), memoization/cache.py (`content_key`), core/context.py, stages/clarify/step.py:180-215, artifacts/store.py (grep only), the workflows AGENTS.md excerpt. Items marked UNVERIFIED were not checked and the planner should confirm them.

## D1 — Persistence location: (a), inside `recall_snapshot`

**Recommendation:** (a). Result model gains `snapshot_hash: str = ""` and `ref: <ArtifactRef-like> | None = None`.

**Reason:** it adds no workflow command, so no `workflow.patched` is needed, and the recorded history replays as is.

- **No patch for (a).** `recall_snapshot` is already one scheduled activity. Replay matches commands by type and sequence, and a recorded result missing the new fields deserializes with their defaults. `research_retain_grounded.json` contains `recall_snapshot` once (grep count). (b) schedules a second activity after it, which changes the command sequence and needs `workflow.patched`.
- **Spec correction.** spec D3 says "changing the RecallSnapshot payload shape alters the command sequence". It doesn't. Only adding or removing an activity does. Defaulted fields are replay-safe. Plan the `temporal` replay test as "old history replays unpatched", not "replays behind a patch".
- **Run id without changing `RecallInput`.** Inside the activity, `activity.info().workflow_id` is available. If Kroker's `run_id` equals the workflow id, store per run with `store.put("recall_snapshot", run_id, f"{hash}.json", data)`. UNVERIFIED: that `run_id == workflow_id` for GraphWorkflow. If not, add `run_id: str = ""` to `RecallInput`. It is a defaulted field, so no replay impact, and the workflow already knows its run id.
- **Hash-named, run-independent path.** I'd avoid `<root>/_recall/<hash>.json`. SC-001 says "retrievable from that run", and `LocalFileStore` and the export root are laid out per run. A global directory also escapes whatever per-run cleanup exists and breaks the "all artifacts of a run live under the run" invariant. Per-run, hash-named files are still idempotent: the same bytes go to the same path, and two stages with identical recall collapse to one file.
- **Failure handling (FR-008).**
  - Compute `snapshot_hash` after the recall (healthy or degraded).
  - Wrap `put` in its own try/except.
  - On a put failure, return the snapshot with `degraded=True`, recompute the hash over the degraded content, leave `ref=None`, and log it. This is how "persistence failed" falls out of FR-006 for free: the degraded flag is in the hashed content, so the key is already separated.
  - Don't reuse the outer `except`. A persistence error must not discard a healthy recall's items that the stage could still use. The stage uses the items but is keyed as degraded. If you'd rather keep the items and not degrade, that contradicts the FR-008 ruling, so don't.
- **Retries.** `MEM_ACT` allows 5 attempts and `put` is idempotent, so a retry is harmless.

## D2 — Memo-key threading: (a)

**Recommendation:** (a). `recall_ref: str = ""` kwarg on `_cached_stage`, `StageContext.cached_stage` (core/context.py) and the `graph.py:73` binding.

**Reason:** the key slot is `watermark` when empty and `f"{watermark}|{snapshot_hash}"` otherwise, so memory-off keys are byte-identical, and the clarify fan-out extra isn't touched.

- **Slot value.**
  - Inside `_cached_stage`, compute `wm = getattr(self, "_memory_watermark", None) or "none"`.
  - Then `slot = f"{wm}|{recall_ref}" if recall_ref else wm`.
  - The memory-disabled snapshot has `snapshot_hash == ""`, so stages pass `""` and the key equals today's. FR-007 holds by construction, and the existing memo-key tests stay green.
- **Why not (b).**
  - `_clarify_memo_extra` (step.py:196) is already folded into `input_json`. Adding the hash there changes the clarify key shape in a place its tests pin, and plan and architecture would each need their own fold-in.
  - Folding into `prompt_digest` mixes a data input into the prompt-identity term. `content_key`'s docstring already warns against putting load-bearing terms in a field named for something else.
  - (a) keeps the hash in the field named `upstream_recall_ref`, which is what it was reserved for.
- **Cost of (a).**
  - Three call sites (`clarify/step.py:199`, `plan/step.py:122`, `architecture/step.py:204`) pass `recall_ref=snapshot.snapshot_hash`.
  - The `StageContext` Protocol, the `graph.py` wiring and any stub contexts in the slice-contract tests need the new keyword. Stubs that ignore it must accept `**kwargs` or the explicit param.
  - Keep it keyword-only with a default so existing callers are unaffected.
- **Replayed snapshots.** A replayed old history yields `snapshot_hash == ""` from the defaulted field, so the key falls back to the watermark-only form. That is the old key, which is the right behavior for in-flight runs.

## D3 — Degraded key separation: (a) only

**Recommendation:** (a). Don't skip `cache_put`.

**Reason:** `degraded` is inside the hashed content, so a degraded key can never equal a healthy one. FR-006 and SC-004 are met, and (b) adds a branch for no extra safety.

- Skipping `cache_put` on degraded would make every repeated outage re-pay the full model cost for a result that is identical in kind.
- The no-poisoning guarantee is already one-directional-safe: healthy never reads degraded entries, because the keys differ.
- The one scenario (b) would help is "same degraded key hit on a later outage". That output is what the stage would produce again with no memory anyway, so reuse is acceptable.
- Add a test that pins the invariant, "healthy and degraded snapshots with the same bank, watermark, query and empty items hash differently", because everything rests on it.

## D4 — Stage record: trace event data keys, nothing else

**Recommendation:** put `recall_snapshot_hash`, `recall_snapshot_ref` and `recall_persist_failed` as `data` keys on a `ctx.emit` event in the stage step, right after `ctx.recall` returns. Do not touch `RunState`, `BenchmarkRecord` or `RunSummary`.

**Reason:** `RunEvent.data` is `dict[str, str]` (report_host.py:38-44), so adding keys is non-breaking, and it fires before `cached_stage`, so cache-hit stages are covered (SC-001).

- **Why the others are wrong.**
  - `BenchmarkRecord` is a persisted benchmark wire model with many consumers. It is only written by some paths, not on every stage, so it can't satisfy SC-001.
  - `RunSummary` is per run, not per stage. It can't say which stage saw which snapshot.
  - `RunState` adds a new query surface.
- **Which event.** Emit on an existing kind such as `STAGE_STARTED` or `STAGE_ENDED`, with `stage=` set, so one stage maps to one snapshot. UNVERIFIED: I did not read `RunEventKind` or its consumers. If the enum tolerates additive members, a dedicated kind such as `RECALL_SNAPSHOT_RECORDED` would be cleaner. Check the dashboard and export consumers for exhaustive matches before choosing. Otherwise use data keys on an existing kind.
- **Do not mutate the trace for memory-off runs.** Emit only when `snapshot_hash` is non-empty or persistence failed. This keeps golden traces byte-identical (FR-007, SC-003).
- **FR-011.** The event carries the hash and ref string only, never items.
- **Determinism.** `emit` is pure workflow state (seq plus `workflow.now()`), and `snapshot_hash` and `ref` come from the recorded activity result, so this is replay-safe. It does add trace events to new runs only. If a golden-trace test covers memory-on runs, update it deliberately.

## D5 — Hash definition: sibling function, no backend name

**Recommendation:** yes to a sibling in `memory/query_hash.py`, e.g. `recall_snapshot_hash(bank, watermark, query_hash, items, degraded)`, same `json.dumps(..., separators=(",", ":"), ensure_ascii=False)` then sha256 pattern. No backend name.

**Reason:** the module exists to make fake and Hindsight snapshots comparable. Putting the backend name in the hash defeats that and the planned parity test.

- **Domain tag.** Make the first list element a version tag, e.g. `"recall_snapshot/v1"`. Without it, a hash over `[bank, watermark, query_hash, items, degraded]` is structurally unrelated to `recall_query_hash`'s payload, but a tag is cheap insurance against cross-type collisions and lets you version the canonical form later.
- **Items.** Serialize each via `item.model_dump(mode="json")` in list order (order is significant, per the spec edge case). UNVERIFIED: I did not read `memory/models.py`. Check the item fields. If an item carries volatile data such as a retrieval timestamp, a per-call score or a generated id, the hash would never repeat and the cache would never hit. In that case hash only the stable fields (text, kind, source ids) and say so in the docstring. Make the plan list the exact fields hashed.
- **Floats.** `json.dumps` repr of floats is stable within a CPython version. If items hold floats, consider rounding, or exclude them.
- **Degraded watermark.** The degraded path uses `inp.watermark or "unknown"`. Hash whatever the snapshot carries, so the degraded hash is deterministic for a given input.
- **One call site rule.** Compute `snapshot_hash` in exactly one place, the activity after recall (or after the degraded fallback), not in each backend. Backends keep returning `snapshot_hash=""`. This is simpler than D2 of the spec's "every backend path" and removes the chance of divergence. FR-002's "one shared definition" is satisfied by the single function.

## Risks the skeptic may raise

1. **Hindsight nondeterminism makes the hash change every run.** That is the stated purpose (an explicit miss), but it means memory-on Hindsight runs will rarely hit the cache. Say so in the plan and don't treat it as a regression. SC-002 is measured against fake or pinned-content backends.
2. **Existing cache entries.** The key shape changes only when `snapshot_hash` is non-empty, so memory-off entries survive. Memory-on entries miss once. Acceptable per ADR-5.
3. **`RecallSnapshot` constructors in stubs.** New fields need defaults (`snapshot_hash=""`, `ref=None`), as the spec already notes. `test_recall_snapshot_defaults_not_degraded` should gain assertions for the new defaults.
