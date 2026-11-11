# Skeptic Audit 1 — 021 `RecallSnapshot` as a Persisted, Content-Addressed Stage Input

Audited against `main` (`067e1408`) and `.specify/specs/021-recall-snapshot-artifact/spec.md`.

---

## Part I — Pressure-Test of Locked Decisions (L1–L5)

### L1 (Q1): `snapshot_hash` joins the memo key ALONGSIDE the watermark (FR-010); memory-off key byte-identical to today (FR-007)

* **Concrete Failure Scenario 1A (`MEMO_PARITY_KEYS` pin breakage on `pytest -m temporal`):**
  * **Inputs / State:** `tests/replay/test_graph_golden.py:106-148` (`test_memo_key_inputs_match_the_pinned_keys`) runs `GraphWorkflow` with `cfg.memoization_enabled = True` and `cfg.memory = MemoryConfig(enabled=True, backend="fake", watermark="wm-e74")` (`test_graph_golden.py:126-127`). It monkeypatches `role_host.content_key` (`test_graph_golden.py:121`) and asserts `seen == MEMO_PARITY_KEYS` (`test_graph_golden.py:28-50, 147`) and `all(args[-1] == "wm-e74" for args in seen)` (`test_graph_golden.py:148`). (Note also: `"wm-e74"` causes `FakeMemory.recall` at `src/sdlc/memory/fake.py:44` to raise `ValueError: invalid literal for int() with base 10: 'wm-e74'`, so `recall_snapshot` at `src/sdlc/memory/activities.py:67-76` silently takes the `degraded=True` branch in that test!)
  * **Wrong Outcome:** Any change to the arguments passed to `role_host.content_key` when `memory.enabled=True` (whether adding a 6th parameter, joining `f"{watermark}:{snapshot_hash}"` into the 5th parameter `upstream_recall_ref` at `src/sdlc/workflows/role_host.py:114-120`, or appending `snapshot_hash` to `input_json` in the stage slices) breaks `test_memo_key_inputs_match_the_pinned_keys` (`tests/replay/test_graph_golden.py:147-148`). `spec.md:138` missed this test because it assumed all memo-key pin tests run with memory off.
  * **Likelihood:** **Certain (100%)** on `pytest -m temporal`.
  * **Required Mitigation:** The plan must explicitly decide how `test_memo_key_inputs_match_the_pinned_keys` (`tests/replay/test_graph_golden.py:28-50, 106-148`) is updated (and whether `FakeMemory.recall` at `src/sdlc/memory/fake.py:44` should stop crashing on non-integer watermarks like `"wm-e74"`), and specify the exact `content_key` slot where `snapshot_hash` lands when `cfg.memory.enabled=True` vs `False`.

* **Concrete Failure Scenario 1B (Plumbing `snapshot_hash` from `ctx.recall` to `ctx.cached_stage` breaks existing slice/chaos tests or MRO rules):**
  * **Inputs / State:** `RoleHost._cached_stage` (`src/sdlc/workflows/role_host.py:88-120`) and `StageContext.cached_stage` (`src/sdlc/core/context.py:36-45`) do not accept a `snapshot` or `snapshot_hash` argument today; `clarify/step.py:199-206`, `architecture/step.py:204-206`, and `plan/step.py:122-129` call `ctx.recall` first and `ctx.cached_stage` later.
    * **Path A (Appending `snapshot_hash` to `input_json` in stage `step.py`):** In `tests/clarify/test_clarify_memo_key.py:146-149`, `_StubContext.recall` returns `RecallSnapshot(query_hash="qh", bank=bank, watermark="wm", items=[])` even when `cfg = PipelineConfig()` (`memory.enabled=False`), and line `238` asserts `assert call["key"] == idea.model_dump_json()`. Similarly, `tests/plan/test_plan_step_chaos.py:194, 205` asserts `ctx.cache_keys == [ARCH.model_dump_json()]`. Appending `snapshot_hash` to `input_json` breaks both tests and violates FR-007 if `snapshot_hash` is non-empty on a stub with `cfg.memory.enabled=False`.
    * **Path B (Adding a keyword argument `snapshot_hash` to `ctx.cached_stage`):** Six test stubs (`tests/clarify/test_clarify_memo_key.py:151`, `tests/plan/test_plan_slice_contract.py:88`, `tests/architecture/test_architecture_slice_contract.py:87`, `tests/plan/test_plan_step_chaos.py:72`, `tests/plan/test_plan_step_split.py:26`, `tests/architecture/test_architecture_step_split.py:35`) define `async def cached_stage(self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest="")` without `**kw`. Passing a new kwarg raises `TypeError: cached_stage() got an unexpected keyword argument`.
    * **Path C (Stashing `self._last_snapshot_hash` on `MemoryHost`):** In `GraphWorkflow`, `architect_node` (`src/sdlc/workflows/graph_nodes/precode.py:134-142`) and `plan_node` (`precode.py:161-165`) call `prepare()` (which calls `ctx.recall`) only on round 1 (`if "prep" not in carry:`), while `produce()` (which calls `ctx.cached_stage`) re-runs on later gate-revision rounds, and `finish()` (`src/sdlc/workflows/graph_nodes/gate.py:83-85`) runs inside `gate_node`. In any custom graph (FR-1201) that interleaves or re-enters stages after another stage's `prepare()` has run, a single scalar `self._last_snapshot_hash` on `MemoryHost` will be overwritten by the later stage's recall, causing `produce()` or `finish()` to read the wrong stage's `snapshot_hash`! Furthermore, adding an attribute on `MemoryHost` without updating `src/sdlc/workflows/AGENTS.md:16-48` violates the MRO Attribute-Ownership contract.
  * **Likelihood:** **High** (every one of the three naive plumbing options breaks either existing tests or multi-round graph execution).
  * **Required Mitigation:** The plan must specify the exact mechanism connecting `snapshot` to `_cached_stage` and `stage_record`:
    1. If `snapshot_hash` is carried on `prep.snapshot` (and local `snapshot` in `clarify`), any new parameter on `StageContext.cached_stage` must either update the 6 test stubs or only be passed when `cfg.memory.enabled` is `True` (or `MemoryHost` must key stashed snapshots by `stage` / `prep` rather than a single mutable scalar, and register the attribute in `src/sdlc/workflows/AGENTS.md`).
    2. When `cfg.memory.enabled` is `False`, the 5th argument to `content_key` (`src/sdlc/memoization/cache.py:42-47`) MUST remain the exact string `"none"` (`src/sdlc/workflows/role_host.py:119`), never `"none:"` or `"none|..."`, to preserve FR-007 byte-identity.

---

### L2 (Q2): Snapshot content lives in the artifact store only (`src/sdlc/artifacts/store.py`); stage record carries hash + ref, no items (FR-011)

* **Concrete Failure Scenario 2A (`BenchmarkRecord` is silently dropped in 100% of non-benchmark runs, violating US1 and SC-001):**
  * **Inputs / State:** A normal (non-benchmark) pipeline run executes with `cfg.memory.enabled = True` and `cfg.benchmark.case_id = None` (the default at `src/sdlc/core/models.py:230`). Each stage calls `await ctx.record(cfg, stage_record(...))`.
  * **Wrong Outcome:** Look at `BenchmarkHost._record` (`src/sdlc/workflows/benchmark_host.py:103-125`):
    ```python
    if not self._benchmarking(cfg):
        return
    await workflow.execute_activity(record_benchmark, record, **RECORD_ACT)
    ```
    When `cfg.benchmark.case_id is None`, `self._benchmarking(cfg)` (`benchmark_host.py:55-56`) is `False`: **`record_benchmark` never runs and the `BenchmarkRecord` is discarded in memory!** Only `RunEventKind.STAGE_ENDED` (`benchmark_host.py:105-121`) is emitted to `self._trace` (which feeds `events.jsonl` at `src/sdlc/observability/activities.py:31` and `StageOutcome` in `summary.json` / `RunSummary` via `src/sdlc/observability/summary.py:20-36`). If `snapshot_hash` and `snapshot_ref` are only added to `BenchmarkRecord` (`src/sdlc/benchmarks/models.py:275`) and not projected into `STAGE_ENDED` / `StageOutcome` (`src/sdlc/core/models.py:437-456`), then an operator inspecting a non-benchmark run has **zero record** of which `snapshot_hash` or `ArtifactRef` any stage saw — failing User Story 1 (`spec.md:46-55`) and SC-001 (`spec.md:153`) for all normal runs.
  * **Likelihood:** **Certain (100%)** for all non-benchmark runs unless `STAGE_ENDED` and `StageOutcome` are also wired.
  * **Required Mitigation:** The plan must thread `snapshot_hash` and `snapshot_ref` (or `snapshot_uri`) not only onto `BenchmarkRecord` (`src/sdlc/benchmarks/models.py:275`) and `stage_record()` (`src/sdlc/benchmarks/record_builder.py:27-51`), but also into `BenchmarkHost._record`'s `STAGE_ENDED` event data (`src/sdlc/workflows/benchmark_host.py:105-121`, conditionally when set so memory-off traces are unchanged) and `StageOutcome` (`src/sdlc/core/models.py:437-456`, `src/sdlc/observability/summary.py:20-36`).

* **Concrete Failure Scenario 2B (`recall_snapshot` activity lacks `run_id` and crashes or degrades when called outside a Temporal activity context):**
  * **Inputs / State:** `LocalFileStore.put(self, kind: str, run_id: str, name: str, data: bytes)` (`src/sdlc/artifacts/store.py:48-54`) requires `run_id` to build `<root>/<run_id>/<subdir>/<name>`. However, `RecallInput` (`src/sdlc/memory/activities.py:50-58`) has no `run_id` field. In `tests/test_memory_activities.py:38, 56, 69`, tests invoke `await recall_snapshot(RecallInput(...))` directly as a Python coroutine without a Temporal worker/activity context.
  * **Wrong Outcome:** If `recall_snapshot` (`src/sdlc/memory/activities.py:61`) calls `activity.info().workflow_id` unconditionally to obtain `run_id` for `LocalFileStore().put(...)`, `activity.info()` raises `RuntimeError: Not in activity context`. Because `recall_snapshot` wraps its body in `except Exception:` (`src/sdlc/memory/activities.py:67`), that `RuntimeError` is caught and **turns every direct unit test call in `tests/test_memory_activities.py:38, 56` into a degraded empty snapshot (`degraded=True, items=[]`)**, failing the existing test suite! Furthermore, if `LocalFileStore().put(...)` writes to the default `./runs/pipeline/` during unit tests without a tmpdir fixture, `pytest` pollutes the repo checkout.
  * **Likelihood:** **High** (standard pitfall in this repo; compare `src/sdlc/stages/plan/step.py:48-52` `_workflow_id()`).
  * **Required Mitigation:**
    1. Resolve `run_id` inside `recall_snapshot` via `activity.info().workflow_id if activity.in_activity() else "direct-execution"` (or optional `run_id: str = ""` on `RecallInput` falling back to the same guard).
    2. Register `"recall_snapshot"` in `_SUBDIRS` (`src/sdlc/artifacts/store.py:22-27`) and ensure `tests/conftest.py` or memory activity tests point `SDLC_ARTIFACT_ROOT` at `tmp_path`.

---

### L3 (Q3): A persistence failure continues as degraded, logged and marked (FR-008); degraded never shares a key with healthy (FR-006)

* **Concrete Failure Scenario 3A (Stage consumes unpersisted `items` or hashes `degraded=False` before `store.put` raises `OSError`):**
  * **Inputs / State:** `memory.recall(...)` (`src/sdlc/memory/activities.py:66`) succeeds and returns `RecallSnapshot(items=["m1", "m2"], degraded=False)` with `snapshot_hash = H_healthy`. Next, `LocalFileStore().put(...)` raises `OSError(ENOSPC / EACCES)`.
  * **Wrong Outcome (Two-way trap):**
    1. If `recall_snapshot` catches the `OSError`, sets `degraded=True`, but **keeps `items=["m1", "m2"]`**, then the stage prompt (`src/sdlc/stages/clarify/step.py:166`, `architecture/step.py:181`, `plan/step.py:108`) injects `"m1", "m2"` into the LLM prompt even though **no artifact exists in `LocalFileStore`** and FR-011 forbids storing `items` on the stage record. The run's stage output now depends on memory items that are permanently unretrievable from anywhere — directly violating **SC-001** (`spec.md:153`: *"For 100% of stages that consumed recalled memory in a run, the exact items they saw are retrievable by hash from that run"*) and **NFR-4 / ADR-5** (`ARCHITECTURE.md:211-212`).
    2. If `snapshot_hash` was computed *before* `store.put()` (with `degraded=False`) and is not recomputed after flipping `degraded=True` (and clearing `items=[]`), the degraded snapshot still carries `H_healthy`, colliding with the healthy memo key and violating **FR-006** and **FR-008**.
  * **Likelihood:** **High** whenever `store.put` fails after `memory.recall` succeeds.
  * **Required Mitigation:** On persistence failure (`FR-008`), `recall_snapshot` must discard `items` (`items=[]`), set `degraded=True` and `ref=None`, and **recompute `snapshot_hash` over `(bank, watermark, query_hash, items=[], degraded=True)`** so the stage never consumes unpersisted items (preserving SC-001) and the key is guaranteed distinct from any healthy snapshot (preserving FR-006).

* **Concrete Failure Scenario 3B (Double fault — backend fails, then persisting the degraded snapshot also fails, crashing the activity):**
  * **Inputs / State:** Disk is full or `SDLC_ARTIFACT_ROOT` is read-only, AND the memory backend raises `ConnectionError` (`src/sdlc/memory/activities.py:66`).
  * **Wrong Outcome:** `recall_snapshot` enters `except Exception:` (`src/sdlc/memory/activities.py:67-76`) to construct the degraded `RecallSnapshot(items=[], degraded=True)`. Per FR-001 and FR-006 (*"A degraded snapshot MUST be persisted and flagged"*), it calls `store.put(...)` for the degraded snapshot. That `store.put(...)` raises `OSError` *inside* the `except` block (or after it), escaping `recall_snapshot` as an unhandled activity failure, burning all 5 `MEM_ACT` retries (`src/sdlc/workflows/memory_host.py:35-37`), and killing the workflow — violating `recall_snapshot`'s `"Never raises"` contract (`src/sdlc/memory/activities.py:61`) and **FR-008**.
  * **Likelihood:** **Medium-High** (container/host storage or permission misconfiguration affects both local services and `LocalFileStore`).
  * **Required Mitigation:** Wrap the `store.put(...)` step in its own inner `try/except Exception:` that logs the persistence failure, sets `degraded=True`, `items=[]`, `ref=None`, recomputes `snapshot_hash` with `degraded=True`, and returns without raising. Additionally, in `RoleHost._cached_stage` (`src/sdlc/workflows/role_host.py:121-128`), do **not** call `cache_put` when the stage's recall was `degraded=True` (otherwise a transient outage caches a degraded stage output that subsequent degraded runs reuse without even trying the stage).

---

### L4 (D1): Content hash covers `[bank, watermark, query_hash, ordered items, degraded]`; `query_hash` (`src/sdlc/memory/query_hash.py`) unchanged (FR-003)

* **Concrete Failure Scenario 4A (`watermark` mismatch between `FakeMemory`, `HindsightMemory`, and degraded path diverges `query_hash` and `snapshot_hash`):**
  * **Inputs / State:** Compare how `watermark` is normalized across the three callers of `recall_query_hash`:
    1. `FakeMemory.recall` (`src/sdlc/memory/fake.py:44, 50-53`): converts `watermark=None` to `cutoff = len(self._entries[bank])`, then calls `recall_query_hash(bank, query, filters, str(cutoff))` and sets `RecallSnapshot.watermark = str(cutoff)`.
    2. `HindsightMemory.recall` (`src/sdlc/memory/hindsight_client.py:236-240`): calls `recall_query_hash(bank, query, filters, watermark)` (passing `None` when `watermark is None`), and then sets `RecallSnapshot.watermark = watermark or _now_iso()`!
    3. `activities.py:69-75` (degraded fallback): calls `recall_query_hash(inp.bank, inp.query, inp.filters, inp.watermark)` and sets `RecallSnapshot.watermark = inp.watermark or "unknown"`.
    4. Worse: when `watermark` is a non-integer string (e.g., an ISO timestamp `"2026-08-02T00:00:00+00:00"` or `"wm-e74"` in `tests/replay/test_graph_golden.py:127`), `FakeMemory.recall` (`src/sdlc/memory/fake.py:44`) executes `int(watermark)` and crashes with `ValueError`!
  * **Wrong Outcome:**
    * Under `watermark=None`, `HindsightMemory` hashes `watermark=None` in `query_hash` but hashes `watermark="<wall-clock-iso>"` in `snapshot_hash`, whereas `FakeMemory` hashes `str(cutoff)` in both.
    * Under any ISO or string watermark (`"wm-e74"`), `FakeMemory.recall` cannot even compute a healthy snapshot (`int(watermark)` raises `ValueError`), making it impossible to test fake-vs-Hindsight parity (`spec.md:140`) on realistic pinned watermarks!
  * **Likelihood:** **High**.
  * **Required Mitigation:**
    1. Define `recall_snapshot_hash(bank: str, watermark: str, query_hash: str, items: Sequence[str], degraded: bool) -> str` in `src/sdlc/memory/query_hash.py` using `json.dumps([bank, watermark, query_hash, list(items), degraded], separators=(",", ":"), ensure_ascii=False)` (mirroring `recall_query_hash` at `src/sdlc/memory/query_hash.py:17-20` so delimiter injection is impossible).
    2. Fix `FakeMemory.recall` (`src/sdlc/memory/fake.py:44`) so a non-integer watermark (like `"wm-e74"` or an ISO timestamp when pinned externally) does not raise `ValueError` (e.g., parse `int(watermark)` when `.isdigit()`, else treat as a pinned opaque watermark that includes current entries up to `len(self._entries[bank])` and preserves `watermark` verbatim on `RecallSnapshot`).

---

### L5 (FR-009) & Probe (2): Replay of `tests/replay/histories/research_retain_grounded.json` and any memory-enabled golden if the `RecallSnapshot` payload or `cache_get` input changes

* **Concrete Failure Scenario 5A (Replaying `research_retain_grounded.json` deserializes a pre-021 `RecallSnapshot` lacking `snapshot_hash` and `ref`):**
  * **Inputs / State:** `tests/replay/histories/research_retain_grounded.json` is the committed `GraphWorkflow` replay fixture with `cfg.memory.enabled = True` (`tests/replay/research_retain.py:80`, tested by `tests/replay/test_research_retain_replay.py:68`). In that fixture, **Event 79 (`recall_snapshot`, completed at Event 84)** embeds the recorded activity result payload:
    ```json
    {"query_hash":"01cbc4dd98fbeffc782b45ed1d07c400c47cf261f9f85df77622f7a37fa802cc","bank":"project:default","watermark":"0","items":[],"degraded":false}
    ```
    (No other committed history in `tests/replay/histories/*.json` schedules `recall_snapshot`, `cache_get`, or `cache_put`.)
  * **Wrong Outcome:**
    1. During `Replayer().replay_workflow(history)` (`tests/replay/test_research_retain_replay.py:79`), `pydantic_data_converter` deserializes Event 84's JSON into `RecallSnapshot` (`src/sdlc/memory/models.py:24`). If `snapshot_hash` or `ref` on `RecallSnapshot` lacks a default, replay fails immediately with `ValidationError`.
    2. If persistence is implemented as a *separate* activity scheduled by `MemoryHost._recall` (`src/sdlc/workflows/memory_host.py:52`) rather than inside `recall_snapshot` (`src/sdlc/memory/activities.py:61`), Event 87 in `research_retain_grounded.json` expects `clarify_agent` next — scheduling a new activity without `workflow.patched` raises `NondeterminismError`.
    3. Even with defaults `snapshot_hash: str = ""` and `ref: ArtifactRef | None = None`, when Event 84 is deserialized on replay (or in an in-flight workflow whose `recall_snapshot` completed before deploy, `SC-005`), `snap.snapshot_hash` will be `""` unless `RecallSnapshot` computes `snapshot_hash` in a `@model_validator(mode="after")` when `snapshot_hash == ""` and `(self.query_hash != "" or self.degraded)`! If `snap.snapshot_hash` stays `""` on replay while post-021 workflow code branches on `if snap.snapshot_hash:` or computes a different `cache_get` key on retry/continue, the replayed workflow diverges from a live run.
  * **Likelihood:** **Certain (100%)** on `research_retain_grounded.json` if defaults are omitted or a new activity is scheduled unpatched; **High** for in-flight pre-021 histories (`SC-005`) if `snapshot_hash` is not derived on model validation.
  * **Required Mitigation:**
    1. Keep persistence strictly inside `recall_snapshot` (`src/sdlc/memory/activities.py:61`) — schedule **zero** new activities from workflow code (`src/sdlc/workflows/memory_host.py:47-63`).
    2. Give `RecallSnapshot` (`src/sdlc/memory/models.py:24-35`) defaulted fields `snapshot_hash: str = ""` and `ref: ArtifactRef | None = None`, plus a `@model_validator(mode="after")` that populates `self.snapshot_hash = recall_snapshot_hash(...)` whenever `not self.snapshot_hash and (self.query_hash or self.degraded)`. That makes:
       * Disabled snapshots (`query_hash=""`, `degraded=False` at `src/sdlc/workflows/memory_host.py:51`) keep `snapshot_hash == ""`;
       * Pre-021 replayed histories (`research_retain_grounded.json` Event 84), `FakeMemory.recall`, `HindsightMemory.recall`, and 4-arg test stubs automatically receive the exact canonical `snapshot_hash`!

---

## Part II — Specific Probes (1)–(6)

### Probe (1): Does Hindsight recall nondeterminism under a fixed watermark make the new key miss on EVERY re-run (memoization effectively dead with memory on — is that acceptable under NFR-6 / ADR-5, `ARCHITECTURE.md:210`)?

* **Concrete Failure Scenario:**
  * **Inputs / State:** An operator runs a feature with `cfg.memory.enabled=True`, `cfg.memory.backend="hindsight"`, `cfg.memoization_enabled=True`, and pins `cfg.memory.watermark="2026-08-02T00:00:00+00:00"`, then edits the `plan` prompt and re-runs, expecting `clarify` and `architecture` to hit the cache per ADR-5 (`ARCHITECTURE.md:213-224`) and User Story 2 (`spec.md:60-70`).
  * **Wrong Outcome:** Look at what `ARCHITECTURE.md:219-224` actually specifies for ADR-5:
    > *"Recall is itself a cached activity keyed with a **per-run memory watermark**: reusing the persisted RecallSnapshot **is** the freeze, so nightly `reflect` churn no longer busts caches. Default re-run reuses the watermark (reproducible, cache-warm); an explicit 'refresh memory' advances it. This also removes any need for Hindsight point-in-time reads."*
    Today, `recall_snapshot` (`src/sdlc/memory/activities.py:61-66`) is **NOT** cached by `query_hash`! Every run calls `HindsightMemory.recall` (`src/sdlc/memory/hindsight_client.py:216-241`) live over HTTP:
    1. Each live Hindsight recall takes **~42 seconds** (`src/sdlc/memory/activities.py:24`), because Hindsight runs an internal LLM leg (~30s/call).
    2. Because Hindsight's LLM leg is nondeterministic across calls AND nightly `reflect` (`/consolidate`, `hindsight_client.py:250`) rewrites/consolidates bank entries in place with new timestamps and text, re-querying live Hindsight under the same `watermark` returns different `items` (or different ranking).
    3. Adding `snapshot_hash` to `content_key` without caching `recall_snapshot` by `query_hash` (when `watermark` is pinned) means: (a) every re-run still pays ~42s × 3 stages = ~2 minutes of live Hindsight LLM calls, (b) LLM ranking jitter or nightly `reflect` changes `snapshot_hash` on every re-run, **killing stage memoization (`_cached_stage`) with memory on**, and (c) `spec.md:145` (*"Out of Scope: A Hindsight point-in-time/as-of read (ARCHITECTURE.md ADR-5 says the persisted snapshot removes the need)"*) is **contradicted**, because persisting a snapshot you never read back on a pinned watermark cannot freeze a mutating bank!
  * **Likelihood:** **High** on live Hindsight (`backend="hindsight"`), and **100% certain** after a nightly `reflect` consolidation.
  * **Required Mitigation:** The plan must either:
    1. **(Recommended, honours ADR-5 `ARCHITECTURE.md:219-224`):** When `inp.watermark is not None` (a pinned watermark), have `recall_snapshot` check for an existing healthy persisted `RecallSnapshot` keyed by `query_hash` (or memo-cache entry) before calling live Hindsight, so reusing the pinned watermark actually reuses the frozen `RecallSnapshot` as ADR-5 states; **OR**
    2. Explicitly amend `spec.md:145, 162` and `ARCHITECTURE.md:219-224` to acknowledge that `recall_snapshot` itself is uncached, meaning Hindsight LLM jitter / `reflect` consolidation under a pinned watermark will intentionally cause a stage cache miss (and pay the 42s recall latency) rather than freeze the bank at the watermark.

### Probe (2): Replay of `tests/replay/histories/research_retain_grounded.json` and any memory-enabled golden if the `RecallSnapshot` payload or `cache_get` input changes

* Covered in **L5 (Scenario 5A)** and **L1 (Scenario 1A)** above. Summary of exact files/events affected:
  * `tests/replay/histories/research_retain_grounded.json` (Event 5 `capture_watermark`, Event 79/84 `recall_snapshot`) is the only committed history with `memory.enabled=True`. It has `memoization_enabled=False`, so `cache_get` is not in any committed `tests/replay/histories/*.json` or `tests/replay/golden/*.json`.
  * `tests/replay/test_graph_golden.py:28-50, 106-148` (`test_memo_key_inputs_match_the_pinned_keys`) is the live capture test with both `memory.enabled=True` and `memoization_enabled=True`; it pins `MEMO_PARITY_KEYS` and `args[-1] == "wm-e74"` and **will fail** unless updated in the plan.

### Probe (3): The artifact store being local-disk per worker (`LocalFileStore`) — a ref written by worker A unreadable from worker B / the dashboard

* **Concrete Failure Scenario:**
  * **Inputs / State:** Under multi-worker deployment (`NFR-2`, `PRD.md:611-613`) or Docker Compose (`README.md`), Worker A executes `recall_snapshot` (`src/sdlc/memory/activities.py:61`) and calls `LocalFileStore().put("recall_snapshot", run_id, f"{snapshot_hash}.json", data)` (`src/sdlc/artifacts/store.py:48-54`). `put()` returns `ArtifactRef(kind="recall_snapshot", uri=path.resolve().as_uri(), sha256=snapshot_hash)` where `uri` is `file:///worker-A-local-fs/runs/pipeline/<run_id>/recall_snapshot/<snapshot_hash>.json`.
  * **Wrong Outcome:**
    1. **Cross-worker / Dashboard unreadability:** When the dashboard (`src/sdlc/board/api.py`), MCP operator tool (`src/sdlc/operator/tools.py`), or Worker B attempts to dereference `ref` via `ref_to_path(ref)` (`src/sdlc/artifacts/store.py:30-32`), it looks up Worker A's absolute path on its own filesystem and raises `FileNotFoundError` unless `SDLC_ARTIFACT_ROOT` is a shared volume mounted at the **exact same absolute path** on every container/worker.
    2. **Even on a single machine — NO reader endpoint or helper exists for `kind="recall_snapshot"`:** Look at all callers of `ref_to_path` in `src/`:
       * `src/sdlc/artifacts/read.py:35` (`load_session`): `assert inp.ref.kind == "harness_session"` — rejects `recall_snapshot`!
       * `src/sdlc/board/api.py:127-159` and `src/sdlc/operator/tools.py:257-299`: only read board artifacts registered in SQLite `BoardStore` (`board.sqlite3`) — `recall_snapshot` is not in `BoardStore`!
       Thus, even on a single host, nothing in `src/sdlc/` provides a reader function or API route to retrieve a `RecallSnapshot` from its `ArtifactRef` or `snapshot_hash` (`SC-001`)!
  * **Likelihood:** **Certain (100%)** in multi-container deployments without a shared mount at identical absolute paths; **Certain (100%)** that no reader helper exists in `src/sdlc/artifacts/` today.
  * **Required Mitigation:**
    1. Add a reader helper (e.g. `read_recall_snapshot(ref: ArtifactRef) -> RecallSnapshot` or `LocalFileStore.get(ref)` in `src/sdlc/artifacts/store.py`) that validates `ref.kind == "recall_snapshot"` and verifies `hashlib.sha256(data).hexdigest() == ref.sha256` on read (content-address integrity check!).
    2. Resolve relative to `LocalFileStore().root / run_id / ...` when `ref_to_path(ref)` does not exist (so differing mount roots across worker vs dashboard containers still resolve when sharing a volume), and document the shared-volume requirement alongside `spec.md:161`.

### Probe (4): Whether anything consumes `RecallSnapshot` fields positionally or by equality (`tests/test_hindsight_recall.py:143`, stage stubs) such that a new field breaks them

* **Concrete Failure Scenario:**
  * **Inputs / State:** While all `RecallSnapshot(...)` constructors in `src/` and `tests/` use keyword arguments (`tests/test_hindsight_recall.py:143-150` asserts field-by-field `.watermark`, `.bank`, `.query_hash`, `.degraded`), **three test suites do NOT return `RecallSnapshot` from `ctx.recall` at all**:
    * `tests/plan/test_plan_step_chaos.py:60-63`: `async def recall(self, cfg, bank, query, filters): ... return SimpleNamespace(items=[])`
    * `tests/plan/test_plan_step_split.py:18-20`: `async def recall(self, cfg, bank, query, filters): ... return SimpleNamespace(items=[])`
    * `tests/architecture/test_architecture_step_split.py:27-29`: `async def recall(self, cfg, bank, query, filters): ... return SimpleNamespace(items=[])`
  * **Wrong Outcome:** `spec.md:105, 137` missed all three of these files! When `src/sdlc/stages/plan/step.py` (`prepare` / `produce` / `finish`) or `src/sdlc/stages/architecture/step.py` (`prepare` / `produce` / `finish`) accesses `prep.snapshot.snapshot_hash`, `prep.snapshot.ref`, or `prep.snapshot.degraded` directly on `prep.snapshot`, **all three test modules fail with `AttributeError: 'types.SimpleNamespace' object has no attribute 'snapshot_hash'`** (over 20 test failures in the default fast unit tier).
  * **Likelihood:** **Certain (100%)** if stage slices use direct attribute access `snapshot.snapshot_hash` / `snapshot.ref` without updating those 3 stubs or using `getattr`.
  * **Required Mitigation:** Either use `getattr(snapshot, "snapshot_hash", "")` / `getattr(snapshot, "ref", None)` in `src/sdlc/stages/{clarify,architecture,plan}/step.py` or update the `SimpleNamespace(items=[])` stubs in `tests/plan/test_plan_step_chaos.py:63`, `tests/plan/test_plan_step_split.py:20`, and `tests/architecture/test_architecture_step_split.py:29` (in addition to the four `RecallSnapshot(...)` stubs listed in `spec.md:137`).

### Probe (5): Multiple recalls in one stage or recall outside the three stages (grep `ctx.recall` / `_recall` callers)

* **Concrete Failure Scenario:**
  * **Inputs / State:** Grep of all `.recall` / `_recall` callers in `src/` and `agents/` reveals **four** call sites, not three:
    1. `src/sdlc/stages/clarify/step.py:130` (`await ctx.recall(...)`)
    2. `src/sdlc/stages/architecture/step.py:103` (`await ctx.recall(...)` in `prepare`)
    3. `src/sdlc/stages/plan/step.py:82` (`await ctx.recall(...)` in `prepare`)
    4. **`agents/research/tools/recall_leads.py:14-17` (`recall_leads` tool):**
       ```python
       backend = _backend(ctx.deps.memory_base_url, ctx.deps.memory_backend)
       snap = await backend.recall(
           ctx.deps.memory_bank, query, {"stage": "research"}, ctx.deps.memory_watermark
       )
       return snap.items[:max_results]
       ```
  * **Wrong Outcome:**
    1. `recall_leads` (`agents/research/tools/recall_leads.py:14-17`) is called by `research_agent` both during the **`research` stage** (`src/sdlc/stages/research/stage.py:277-308`, across up to `max_sub_questions=4` parallel sub-questions, multiple tool calls per sub-question) AND mid-run during the **`architecture` stage** when `architect_agent` invokes its `research` tool (`src/sdlc/stages/research/toolset.py:92-102`, `src/sdlc/stages/architecture/step.py:152-171`).
    2. Because `recall_leads` calls `_backend(...).recall(...)` directly instead of `recall_snapshot`, **none of its recalls are persisted to the artifact store**, **none have a fallback when Hindsight is unreachable** (`backend.recall` raises an unhandled httpx error inside the research tool instead of degrading!), and **none of its `snapshot_hash`es are recorded on the `research` or `architecture` stage records** — violating **FR-001** (*"Every recall that runs against a backend (healthy or degraded) MUST produce a persisted snapshot artifact"*) and **SC-001**!
    3. Furthermore, even within `architecture` alone (`src/sdlc/stages/architecture/step.py:177-235`), if `codebase_map is not None` and `check_brownfield_delta` (`step.py:211-219`) fails on attempt 1, the `while True:` loop in `produce()` (`step.py:177`) calls `ctx.cached_stage` a **second time** in the same stage with `delta_guidance` set (`step.py:204-206`), or raises `ApplicationError` at `step.py:224` before `architecture.finish()` ever writes a stage record!
  * **Likelihood:** **Certain (100%)** whenever `research_agent` invokes `recall_leads`.
  * **Required Mitigation:** The plan must explicitly address `agents/research/tools/recall_leads.py:14-17`: either route `recall_leads` through the shared persist-and-degrade helper (passing `ctx.deps.run_id` so its snapshots are persisted under the run, and gating on whether memory is enabled) or explicitly scope `FR-001`/`SC-001` in the plan to workflow-level `ctx.recall` stage inputs vs. agent-tool lead lookups.

### Probe (6): PII — recalled items persisted to disk in plaintext; they were scrubbed at retain (`src/sdlc/memory/scrub.py`), is that enough per NFR-5 / NFR-8 tenant isolation?

* **Concrete Failure Scenario 6A (Unscrubbed Hindsight memories persisted to disk in plaintext without retention cleanup — NFR-5):**
  * **Inputs / State:** `src/sdlc/memory/scrub.py:10-21` runs only inside `retain()` (`src/sdlc/memory/activities.py:91`) and only strips 4 narrow regex patterns (`sk-...`, `AKIA...`, email, `password|token|secret[:=]\S+`). Its own docstring (`scrub.py:1-4`) warns: *"Best-effort secret/PII redaction before anything is retained. Not a security boundary by itself"*. Hindsight banks (`project:default`, `org`) also hold memories synthesized by Hindsight's LLM consolidation (`/consolidate`, `src/sdlc/memory/hindsight_client.py:250`) or seeded externally.
  * **Wrong Outcome:** `recall_snapshot` (`src/sdlc/memory/activities.py:61-66`) writes `snap.items` to `LocalFileStore` (`./runs/pipeline/<run_id>/recall_snapshot/<hash>.json`) **without calling `scrub()` on the recalled items**. Worse, unlike `harness_session` artifacts — which `capture_session` (`src/sdlc/artifacts/capture.py:68`) scrubs fail-closed *immediately before* `store.put` and which `apply_session_retention` (`src/sdlc/artifacts/retention.py:35-43`) deletes on clean-green runs — `spec.md:147` leaves `recall_snapshot` files on disk indefinitely with no scrub-before-put and no retention purge.
  * **Likelihood:** **Medium-High** whenever Hindsight bank entries come from consolidation, external tools, or contain secrets missed by retain-time scrubbing.
  * **Required Mitigation:** Run `scrub(item)` (`src/sdlc/memory/scrub.py:18`) over every recalled item before constructing/persisting `RecallSnapshot` (fail-closed before `store.put`, matching `src/sdlc/artifacts/capture.py:68`), so no unscrubbed byte ever touches disk or the prompt.

* **Concrete Failure Scenario 6B (Cross-tenant cache hit and un-namespaced `snapshot_hash` / `LocalFileStore` — NFR-8 & FR-1001):**
  * **Inputs / State:** Two tenants (`SDLC_MEMORY_TENANT=tenant-a` and `SDLC_MEMORY_TENANT=tenant-b`, `src/sdlc/memory/activities.py:41`) run on the same worker host/checkout. Both use the default `PipelineConfig.memory.project_bank = "project:default"` (`src/sdlc/core/models.py:270`).
  * **Wrong Outcome:**
    1. `tenant` (`SDLC_MEMORY_TENANT`) is **absent** from `recall_query_hash(bank, query, filters, watermark)` (`src/sdlc/memory/query_hash.py:14-20`), **absent** from L4 D1's `snapshot_hash` (`[bank, watermark, query_hash, ordered items, degraded]`), **absent** from `content_key` (`src/sdlc/memoization/cache.py:42-47`), and **absent** from `LocalFileStore.put` (`src/sdlc/artifacts/store.py:48-54`, which writes to `<root>/<run_id>/...` with no tenant prefix).
    2. When Tenant A and Tenant B run the same idea template (or both experience a degraded/empty recall under `bank="project:default"` and watermark `"unknown"` / `"0"`), they produce the **exact same `query_hash`, the exact same `snapshot_hash`, and the exact same `content_key`**, causing Tenant B's `_cached_stage` (`src/sdlc/workflows/role_host.py:121-123`) to read Tenant A's cached stage output from `/tmp/sdlc/memo_cache/<checkout_id>/<key>.json` (`src/sdlc/memoization/cache.py:31-39`)! This directly violates **FR-1001** (`PRD.md:477-480`: *"Every workflow, artifact, and memory bank SHALL be scoped to a tenant by namespace, store prefix, and bank namespace"*) and **NFR-8** (`PRD.md:631-633`: *"no data path SHALL exist between tenants"*).
  * **Likelihood:** **High** in any multi-tenant worker deployment sharing a checkout/host.
  * **Required Mitigation:** Include the memory tenant (when non-default, e.g. `os.environ.get("SDLC_MEMORY_TENANT", "default")`) or scope `LocalFileStore` / `_cache_root()` (`src/sdlc/memoization/cache.py:31-39`) by tenant so two tenants with `project_bank="project:default"` can never share a memo cache directory or artifact store prefix.
