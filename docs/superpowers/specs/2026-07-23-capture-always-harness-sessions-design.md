# E-38 — Capture-always harness sessions (ADR-16)

| | |
|---|---|
| Date | 2026-07-23 |
| Status | Approved design |
| Roadmap | E-38 **(new scope; ADR-16)** — §9.8 |
| Anchors | ADR-16 (ARCHITECTURE §12), FR-702 (first real claim-check consumer), FR-704/NFR-4, BENCHMARK §4.3/OQ-B7 |
| PRD | Needs the new-scope line: **FR-109** capture-always harness sessions |
| Out of scope | Migrating diffs onto the store (FR-702 proper), report.html session rendering (E-36's home), `deep_review` (E-39), full-transcript TTL (OQ-B7's one open sub-point) |

## Problem

The factory grades *what* a harness produced (diff, tests, oracle) but keeps
nothing about *how* it was produced. The transcript — tool calls, file
reads/writes, commands and their exit status, model turns — is the richest
signal the diff hides (BENCHMARK §4.3: rewrite churn, failed commands,
re-reads), the substrate for the anti-cheat "read the run" check, the
`deep_review` lens (E-39), the error heatmap (E-36), and P5 trajectory
harvesting. Today it is discarded: claude's adapter captures only the final
JSON payload, opencode's event stream is parsed for totals and thrown away,
`ArtifactRef` is never constructed anywhere, and `HarnessRunResult` has no
place to carry a session.

## Decisions (settled during brainstorming)

1. **Transcript source = stdout streams.** claude switches to
   `--output-format stream-json` (requires `--verbose` in print mode); the
   final `result` event carries the same fields `parse()` reads today.
   opencode's `--format json` stdout already is the event stream. No
   dependence on harness-internal storage layouts (`~/.claude/...`).
2. **First claim-check store = `file://` behind a seam.** A small
   `ArtifactStore` protocol with one local-filesystem backend beside the
   E-32 export root. S3 is a later backend behind the same interface.
3. **Retention = capture full always, downgrade at retro.** The capture
   activity cannot know a run will end clean-green; the retro stage can.
   One mechanism also serves the future TTL purge.
4. **Scope = sessions only.** The store lands generic, but diffs stay
   inline (follow-on), and no report rendering here.
5. **Pipeline shape = adapter normalises, activity captures** (approach A).
   Normalisation is the adapter's job (ADR-16); scrub/store/digest happen in
   `run_harness_task`, the only place holding both the raw stream and
   activity-side filesystem rights.
6. **Logfire = minimal env-gated slice inside E-38.** Live telemetry
   complements, never replaces, the durable artifact. Metadata only — the
   unscrubbed transcript must never reach Logfire, by the same reasoning as
   scrub-before-store.

## Design

### 1. Data model (`models.py`, beside `HarnessRunResult`)

```python
class SessionEvent(BaseModel):
    kind: str          # model_turn | tool_call | tool_result | file_read
                       # | file_write | command | compaction | result
    tool: str | None = None
    target: str | None = None    # file path or command line (scrubbed)
    exit_code: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    text: str | None = None      # payload (scrubbed)

class HarnessSession(BaseModel):
    harness: HarnessKind
    session_id: str | None
    model: str | None
    events: list[SessionEvent]
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None

class SessionDigest(BaseModel):
    tool_calls: int = 0
    file_reads: int = 0
    file_rereads: int = 0        # same path read >1x
    files_written: int = 0
    rewrite_churn: int = 0       # files written >1x
    failed_commands: int = 0     # command events with exit_code != 0
    model_turns: int = 0
    compacted: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    decision_skeleton: list[str] = []   # ordered "tool target", no payloads,
                                        # capped (SKELETON_MAX = 200 entries)
```

`HarnessRunResult` gains:

- `session_ref: ArtifactRef | None` — the full scrubbed transcript,
  claim-checked. The `HarnessSession` itself **never enters workflow
  state**.
- `session_digest: SessionDigest | None` — inline; small and bounded, so
  the workflow, retro `RunSummary`, and future heatmap can read waste
  without dereferencing.

### 2. Adapter normalisation (`harness/adapters.py`, `harness/session.py`)

Each adapter grows a pure `normalise_session(stdout: str) -> HarnessSession`
beside its existing `parse()` — it already walks that exact stream.

- **claude:** `build_cmd` emits `--output-format stream-json --verbose`.
  `parse()` changes from "last line" to "find the `result` event" (same
  fields: `session_id`, `total_cost_usd`, `usage`, `result`). The
  normaliser maps `assistant` `tool_use` blocks → `tool_call`, refined by
  tool name (`Read` → `file_read`, `Write`/`Edit` → `file_write`,
  `Bash` → `command`); `user` `tool_result` blocks → `tool_result` with
  exit codes where present; assistant text blocks → `model_turn`.
- **opencode:** normaliser maps `step_start`/`step_finish`/`text` (and
  tool-level events where the stream carries them) onto the same schema.
  **Plan-time verification:** capture one real `opencode run --format json`
  stream and confirm which tool events it emits. Normalisers are
  best-effort per harness; the canonical schema is the contract.
- `digest_of(session: HarnessSession) -> SessionDigest` — one pure shared
  function in `harness/session.py`.

### 3. Capture pipeline (in `run_harness_task`, after `harness.run()`)

```
normalise → scrub (fail-closed) → digest (pre-truncation) → store full + attach
```

1. `normalise_session(raw_stdout)` — pure.
2. **Scrub, fail-closed:** every `SessionEvent.text` and `.target` passes
   through `memory/scrub.scrub()`. Any exception → **nothing stored**,
   `session_ref=None`, `session_digest=None`, warning logged + Logfire
   event. Fail-closed w.r.t. **storage**: the dev task itself still
   succeeds — an observability bug must not block delivery; SC-5-style
   strictness applies to what gets *stored*, mirroring ADR-16's "a scrub
   failure stores nothing regardless of outcome".
3. `digest_of(scrubbed_session)` — computed **pre-truncation**, so waste
   aggregates exist for every run including ones later downgraded.
4. Serialize the scrubbed session to JSONL (one `SessionEvent` per line,
   header line with session metadata) and `put()` it; write the digest
   JSON beside it. Attach `session_ref` + inline digest to the result.

The raw (unscrubbed) stdout never leaves the activity and is never written
to disk.

### 4. ArtifactStore seam (`src/sdlc/artifacts/store.py`)

```python
class ArtifactStore(Protocol):
    def put(self, kind: str, run_id: str, name: str, data: bytes) -> ArtifactRef: ...
    def delete(self, ref: ArtifactRef) -> None: ...
```

One backend now: `LocalFileStore(root)`, rooted at `SDLC_ARTIFACT_ROOT`
(default: the E-32 export root, `./runs`). Layout:

```
runs/<workflow_run_id>/sessions/<task>-a<attempt>.jsonl        # full transcript
runs/<workflow_run_id>/sessions/<task>-a<attempt>.digest.json  # always kept
```

`ArtifactRef{kind: "harness_session", uri: "file://...", sha256: <hex>}`.
The run id comes from `activity.info().workflow_run_id` — no change to the
harness-task input shape. Task label + attempt come from fields the input
already carries (verified at plan time).

### 5. Retention at retro (`apply_session_retention` activity)

The workflow already holds every `HarnessRunResult`. On the terminal path
(where E-32 builds `RunSummary`), it calls `apply_session_retention` with:
the collected `session_ref`s, terminal outcome, total fix-loop attempts,
and the benchmark flag.

Policy (OQ-B7, decided): **clean-green ∧ attempts = 0 ∧ not benchmark →
delete the full `.jsonl`, keep `.digest.json`.** Everything else keeps the
full transcript. "Green after a retry" keeps full — how the agent
recovered is the point. Best-effort like the E-32 export: a retention
failure logs, never fails the run.

The benchmark flag travels on `PipelineConfig`, set by `BenchmarkWorkflow`
when starting children (exact field verified at plan time — must not
perturb memo keys; if it would, it travels as a separate workflow input).

Full-transcript TTL stays **open** (OQ-B7's one remaining sub-point); this
activity is the mechanism a TTL purge would later reuse.

### 6. Logfire slice (env-gated)

- `worker.py` boot: `logfire.configure()` iff `LOGFIRE_TOKEN` (or
  equivalent env gate) is present; otherwise no-op — no new hard
  dependency on a run.
- `logfire.instrument_pydantic_ai()` — the eight proposer roles trace for
  free.
- Spans on `run_harness_task` and each capture step (normalise / scrub /
  store), attributes limited to counts, durations, byte sizes, session_id,
  harness kind. **Never transcript payloads.**
- Implementation follows the `logfire:logfire-instrumentation` skill.

## Testing

- **Normalisers:** fixture-driven — one captured claude `stream-json`
  fixture, one opencode `--format json` fixture (harvested during the
  plan-time verification run); assert event mapping + that `parse()` still
  extracts the same totals.
- **`digest_of`:** pure-function tests (rereads, churn, failed commands,
  skeleton cap).
- **Scrub fail-closed:** patched `scrub()` raises → no file on disk,
  `session_ref is None`, activity result still returned.
- **Scrub effectiveness:** a fixture containing a planted `sk-...` key
  asserts the stored JSONL contains `[REDACTED_API_KEY]`.
- **`LocalFileStore`:** put/delete round-trip, sha256 correctness,
  `file://` URI shape on Windows paths.
- **Retention matrix:** (green|fail) × (attempts 0|>0) × (benchmark
  yes|no) → full kept/deleted, digest always present. (Matrix applies to
  captured sessions; a scrub-failed run stored nothing and has nothing to
  retain.)
- **Workflow:** existing fake-harness workflow tests extended to assert
  `session_ref`/`session_digest` propagate and retro invokes retention.

## Docs on landing

- PRD: add **FR-109** (capture-always sessions) — the roadmap's "(new
  scope) needs a PRD line" rule.
- ROADMAP: mark E-38 landed; note TTL still open under OQ-B7.
- BENCHMARK.md OQ-B7: mark the decided half implemented.
- ARCHITECTURE ADR-16 already written — verify it matches what landed.
