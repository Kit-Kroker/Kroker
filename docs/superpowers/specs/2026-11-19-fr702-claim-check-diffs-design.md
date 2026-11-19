# FR-702 close-out — claim-check diffs, `CodeArtifact`, 2MB payload guard

| | |
|---|---|
| Status | Approved 2026-11-19 (approach 1; drain-first posture; frozen-anchor ruling **R-A**) |
| Anchors | PRD FR-702, ADR-3 (`CodeArtifact` union), ADR-10 (claim-check, 2MB forcing-function), ADR-16 / E-38 (the store + ref pattern this copies), ROADMAP NFR-4 |
| Out of scope | `S3ArtifactStore` + fleet offload (AP-2.7 stays plan), propose-mode `files[]` producer, prompt claim-check (prompts stay inline under the 007 proposer guard), `DriftReport.patch`, diff retention/TTL, report.html diff rendering |

## Intent

Close FR-702 honestly: payloads through workflow history stay under 2MB
*because the platform refuses to write them*, and diffs stop traveling inline.
The three open clauses in ROADMAP.md:356 are all required —

1. diffs travel by claim-check (store → `ArtifactRef`), not inline dicts;
2. the ADR-3 `CodeArtifact` union exists as a real model;
3. a 2MB size guard exists (ADR-10's "design forcing-function" becomes a
   mechanism).

Secondary win: the 60k-char truncation currently applied inside
`get_task_diff` destroys the diff tail (marker only). Claim-check stores the
**full untruncated** patch; truncation survives only as a bounded *read-back*
for prompts, where it is a context budget, not a storage limit.

## Why now

Sessions (E-38) made the store real but left diffs as the last inline
traveler; NFR-4's only remaining partial clause is "claim-check is not
load-bearing (FR-702)". Every pattern this design needs is already landed:
`capture_session` (store inside the producing activity, return only the ref),
`load_session` (kind-asserted, byte-capped read-back), `read_recall_snapshot`
(verified read-back). This design adds no new architecture — it applies the
E-38 pattern to diffs and adds the guard ADR-10 always implied.

## Goals

- `get_task_diff` returns a `CodeArtifact`: `files`/`renames`/`stat` inline
  (small), full patch stored via `LocalFileStore` (`kind: "diff"`), referenced
  by `patch_ref: ArtifactRef`.
- Prompt consumers materialize the patch through a bounded `load_diff`
  activity (mirrors `load_session`; keeps the T3 truncation-marker semantics).
- `AnalyzeResult.integration_diff` becomes a `CodeArtifact`; merge reads only
  the inline metadata.
- `HarnessRunResult.diff_ref` is finally populated.
- A payload guard refuses to serialize any payload ≥ 2MB at the one
  serialization chokepoint, on every client and worker (src and test harness).
- Roadmap/PRD/ADR/stage-clause close-out in the same diff (the artifact
  boundary rule).

## Non-goals

- No S3 backend — `LocalFileStore` remains the only backend (filesystem-first
  deployment; AP-2.7 owns fleet scale).
- No propose-mode (`files[]`) producer — the ADR-3 arm is typed but nothing
  populates it yet; greenfield runs go through the harness path today.
- Prompts are NOT claim-checked. Reviewers are clean-context proposers
  (ADR-6); the patch must be in the prompt, and the 007 proposer payload
  guard (1 MiB) already bounds that crossing. This design keeps prompt slices
  ≤ 60k chars as today.
- `DriftReport.patch` (bounded 60k) stays inline — small, single consumer.
- No diff retention policy — diffs are run evidence (NFR-4 auditability);
  they stay. TTL is OQ-B7's neighborhood, not this one.

## Anti-goals

- Leaving the inline dict path alive "for compatibility" — dual shapes would
  preserve exactly the hazard FR-702 exists to close.
- A guard with an env escape hatch. If a legitimate payload hits 2MB, the run
  fails loudly and the payload gets claim-checked — that is the discipline.

## Constraints

- **E-38 pattern fidelity**: store inside the producing activity; only the
  ref crosses history; read-backs are kind-asserted activities.
- **core/ layering (Rule 5/6/7)**: `CodeArtifact` is a producer artifact —
  it lives in `vcs` beside `DiffInput`/`DriftReport`, not in `core/`
  (Rule 7) — and references `core.models.ArtifactRef`. Stages and
  `workflows/models.py` import the type (imports are not cross-stage calls).
- **Replay**: changing `get_task_diff`'s return shape and
  `AnalyzeResult.integration_diff` breaks in-flight runs replaying through
  new code. Posture: **declared incompatible, no `workflow.patched`** — the
  diff-scoped-gates precedent (merge AGENTS). Deploy drains running
  `GraphWorkflow`/`TidyUpWorkflow` executions first.
- **Oracle parity (T3)**: a cut patch carries the visible
  `...[diff truncated, N chars omitted]` marker, char-sliced, `<=` passes
  through. The marker moves with the truncation into `load_diff`; the pinned
  edge tests move with it.
- **No activity adds/removes on the workflow command path beyond the new
  `load_diff` calls** — `get_task_diff` and the stage steps keep their names
  and scheduling; only payload shapes change.
- **File-size ceiling**: `stages/code/step.py` sits at 987/1000 lines and is
  **not** baselined — D4's edits there must land net-zero or negative
  (retiring `_get_patch` and the dict plumbing pays for the additions; if
  not, a pure helper moves out per the slice's `attempt_failure.py`
  pattern). `scripts/check_file_size.py` is the authority.

## Approaches considered

1. **Full claim-check + platform guard (picked).** `CodeArtifact` from
   `get_task_diff`, full patch stored, `load_diff` read-back for prompts,
   `AnalyzeResult` carries the artifact, and a 2MB refuse-to-serialize guard
   at the payload-converter chokepoint on every client/worker. Closes all
   three clauses; every piece mirrors a landed E-38/E-39 pattern.
2. **Guard only.** Add the 2MB guard; diffs stay inline-but-capped. One
   clause of three; FR-702 could not honestly close. Rejected.
3. **Claim-check + per-seam asserts.** Approach 1 without the converter
   guard — assert sizes at assembly sites instead. The "guard" is only as
   good as the seams remembered; ADR-10 asks for a forcing-function, not
   good intentions. Rejected.

## Design

### D1 — `CodeArtifact` (new model, `vcs/git.py` beside its producer)

```python
class CodeArtifact(BaseModel):
    """ADR-3: one materialized code change, claim-checked (FR-702).

    Harness mode fills patch_ref (the FULL untruncated patch stored by
    get_task_diff); files/renames/stat are inline metadata (small).
    Propose mode (direct file writes, greenfield test files) would fill
    files as the artifact itself — typed per ADR-3, no producer yet.
    """
    files: list[str] = Field(default_factory=list)
    renames: list[list[str]] = Field(default_factory=list)
    stat: str = ""
    patch_ref: ArtifactRef | None = None
```

Exported from `sdlc.vcs`. No either/or validator in v1 (the propose-mode arm
is reserved; `files` legitimately doubles as changed-path metadata in
harness mode).

### D2 — `get_task_diff` stores, returns the artifact

- `DiffInput` gains `label: str | None = None` (artifact name; callers pass
  `f"{task_id}-a{attempt}"` or `"integration"`; default derives from
  `branch_point`).
- Inside the activity: run the same four git invocations; `LocalFileStore()`
  `.put("diff", run_id, f"{safe_label}.patch", patch.encode("utf-8"))` where
  `run_id = activity.info().workflow_id` with the established non-worker
  fallback (direct-call unit tests). `stat` stays inline (it is metadata);
  the **stored bytes are the full patch, untruncated**.
- Return `CodeArtifact(files=..., renames=..., stat=..., patch_ref=ref)`.
  `max_chars` leaves `DiffInput` (nothing left to truncate at the source).
- `_SUBDIRS["diff"] = "diffs"` in `artifacts/store.py`.
- Registration lists (`pools.py`, `worker.py`) unchanged — same activity,
  new result type. `demo/fakes.py` and `tests/fakes/fake_activities.py`
  return `CodeArtifact`.

### D3 — `load_diff` read-back (`artifacts/read.py`, beside `load_session`)

```python
class LoadDiffInput(BaseModel):
    ref: ArtifactRef
    max_chars: int = 60_000

@activity.defn
async def load_diff(inp: LoadDiffInput) -> LoadSessionResult: ...
```

Kind-asserted (`"diff"`), reads the stored patch, char-slices at
`max_chars`, appends the T3 marker on a cut (`<=` passes through, char
semantics, oracle parity), returns `LoadSessionResult(text=..., truncated=...)`
(reuse the existing result type — same shape, zero new wire types).
Registered wherever `load_session` is registered today.

### D4 — consumers

The code stage fetches **once per attempt**, then passes materialized text +
metadata down (stage steps keep clean-context inputs; only the parameter
types change):

- `stages/code/step.py`: `art = await get_task_diff(...)`; then
  `patch = await load_diff(LoadDiffInput(ref=art.patch_ref))`; set
  `run.diff_ref = art.patch_ref` before the result rides `TaskResult`.
  `plan_drift` uses `art.files`; the escalation prompt and quarantine note
  use `patch.text` / `art.files` as today.
- `stages/qa/step.py`: `diff: dict` → `stat: str, patch: str` (prompt inputs
  unchanged in content).
- `stages/review/step.py`: `diff` → `patch: str` on the three lens entry
  points (`_get_patch` retires). The clean-context invariant (assertions +
  deterministic QA output + materialized patch only) is unchanged — this
  design changes *how the patch text arrives*, not *what the lens sees*.
- `stages/analyze/step.py`: `diff: dict | None` → `diff: CodeArtifact | None`;
  the `diff is None` fallback fetches both artifact and patch via the
  activities. Prompt content identical.
- `stages/merge/step.py`: `integration_diff: dict | None` → `CodeArtifact |
  None`; `changed_files = art.files`, `renames = art.renames`.

### D5 — `AnalyzeResult` carries the artifact

`workflows/models.py`: `integration_diff: dict[str, Any]` →
`integration_diff: CodeArtifact` (import from `..vcs`, same pattern as the
existing stage-artifact imports). `postplan.analyze_node` fetches artifact +
one `load_diff` for the analyst prompt; `merge_node` passes
`analysis.integration_diff` through unchanged. The payload that rides the
node result is now metadata + ref.

### D6 — `HarnessRunResult.diff_ref` populated

At the D4 site, after the artifact is fetched: `run.diff_ref = art.patch_ref`.
The run record now shows the claim-check; `session_ref`/`diff_ref` finally
symmetric.

### D7 — the 2MB payload guard

New module `src/sdlc/converter.py`:

```python
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024  # PRD FR-702: payloads stay under 2MB

class _GuardedJSONPlainPayloadConverter(PydanticJSONPlainPayloadConverter):
    def to_payload(self, value):
        payload = super().to_payload(value)
        if payload is not None and len(payload.data) >= MAX_PAYLOAD_BYTES:
            raise PayloadTooLargeError(len(payload.data))
        return payload

sdlc_data_converter = DataConverter(
    payload_converter_class=<composite with the guarded JSON converter first>,
)
```

Match the **installed** construction verbatim: temporalio is pinned 1.31.0,
where `pydantic_data_converter = DataConverter(payload_converter_class=
PydanticPayloadConverter)` — no failure-converter argument exists in that
module and none is added here. The failure converter and the failure wire
format are untouched; **no SDK upgrade is in scope** (a bump would change the
failure wire format and replay surface — it does not ride along inside a
payload-converter change). Decode is untouched — old events replay fine.

Why the payload converter and not a `PayloadCodec`: `to_payload` is the one
chokepoint every serialization in-process passes through (activity inputs
scheduled from workflow code, activity results, signals, start args);
payload codecs are applied by RPC-path helpers and are not guaranteed on all
write paths. `PayloadTooLargeError` names the fix in its message ("claim-check
it via ArtifactRef"). No escape hatch.

**Failure modes, both accepted (my call, builder-check Q2).** Where the raise
fires decides what the operator sees:

- *Activity result oversized*: the activity task fails; retries re-produce
  the same result and exhaust; the workflow takes its existing failure path.
  Loud, terminal, by design.
- *Input oversized* (activity args, signals, continue-as-new carries): the
  **workflow task** fails, and Temporal retries workflow tasks indefinitely —
  the run wedges `Running` until an operator terminates it. This is not a
  regression: an input over ~2MB is already doomed today, rejected by the
  server's own payload cap with an opaque retryable error and the identical
  wedge. The guard converts that into a local, labeled failure at the same
  threshold. D8's drain query is the detection net for runs wedged this way,
  and the operator notes must say exactly this — "fails at the guard" for
  results, "wedges until terminated" for inputs.

Both paths get their own temporal-tier guard test (results exhaust and fail;
inputs wedge with the guard's error in history).

**Wiring:** every `pydantic_data_converter` import site swaps to
`sdlc_data_converter` — src (`worker.py`, `cli.py`, `operator/runtime.py`,
`benchmarks/cli.py`, `demo/__main__.py`) and tests (`replay/harness.py`,
`test_pinned_base_e2e.py`, `test_pools_replay.py`, `test_e2e_greenfield.py`,
`capture_provider_requests.py`). `tests/replay/projection.py` decodes
history — it may keep the raw converter (read path) or swap; builder's call.
Wire format is unchanged (`json/plain`, same encoding name) — old and new
processes interoperate; only writes over the limit fail.

Known consequence to document in the operator notes: if a monster
`PipelineGraph` or any future payload ever crosses 2MB, the run fails at the
guard until it is claim-checked. That is ADR-10 working as intended.

### D8 — replay / deploy posture

Declared incompatible with in-flight runs; **no `workflow.patched` marker**
(diff-scoped-gates precedent: a patched branch would keep the retired dict
path alive as a second code path, and could not protect the payload change
anyway). Deploy procedure, recorded in this spec and the plan:

```bash
temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='GraphWorkflow' OR WorkflowType='TidyUpWorkflow')"
```

must print nothing before a worker built from this change serves traffic;
terminate or finish those runs first. `MaintenanceWorkflow` does not call
`get_task_diff`; it is unaffected but draining is harmless.

### D8b — recorded-history corpus and frozen anchors (governance)

Two distinct bodies of recorded history are affected, with two different
rules (`tests/replay/AGENTS.md`):

1. **The replay corpus** (`tests/replay/histories/` + `golden/`, ~23
   scenarios): old histories cannot replay through the new code — the
   recorded `get_task_diff` dict deserializes into `CodeArtifact` with
   `patch` silently dropped (pydantic ignores extras) and `patch_ref=None`,
   and the new `load_diff` commands are absent from the recordings. There is
   no keep-the-old-fixtures option. The sanctioned path is Rule 2:
   **deliberate re-baseline from the capture tests only** (capture-twice,
   `SDLC_CAPTURE_HISTORIES=1`, projection diff attached to the review,
   `scripts/check_golden_rebaseline.py` gating). This is in scope as a
   first-class plan work item, not a cleanup.

2. **The frozen durability anchors** (`tests/durability/fixtures/`, e.g.
   `wire_no_override.json` and the architect-era recordings under
   `test_inflight_resume.py` / `test_priced_usage_parity.py`): SG-2 says
   these are never re-recorded to silence a red — drift is **escalated and
   ruled on** (the 2026-11-10 ruling forbade re-recording). This change
   makes the drift deliberate: a live wire stream that now includes
   `load_diff` beside `get_task_diff`, and recorded results whose shapes
   the new code no longer produces. **This section is the escalation.**
   The ruling options:

   - **R-A (ruled 2026-11-19): one-time supervised regeneration.** Exactly the
     anchors whose scenario crosses the code stage are re-recorded once
     (`SDLSC_WIRE_REGEN=1` and the recordings' own capture path), with the
     live-vs-frozen diff attached to the review and the ruling recorded in
     this spec's close-out entry. Anchors that do not cross the code stage
     stay frozen untouched.
   - **R-B: anchors stay frozen, affected tests xfail** with an open SG-2
     note. Cheaper, but leaves permanently-red-or-skipped durability tests
     — the opposite of what anchors are for.
   - **R-C: preserve wire neutrality by design** — have `get_task_diff`
     return the capped patch inline (no `load_diff` activity). Rejected:
     that is today's inline-diff status quo with extra steps; it reopens
     the exact clause FR-702 closes.

   The plan's first implementation step is the **anchor audit**: list which
   frozen fixtures' scenarios actually cross `get_task_diff`/`load_diff`
   (grep the fixtures' activity names), so the ruling is applied to exactly
   those and nothing else.

### D9 — close-out (same diff, per the artifact boundary rule)

- `ROADMAP.md`: FR-702 → `[x]` with one-sentence evidence
  (`CodeArtifact` claim-check from `get_task_diff` via `artifacts/store.py`,
  `load_diff` read-back, 2MB guard `sdlc.converter`); NFR-4 → `[x]` (its
  last partial clause was FR-702); ADR-10 entry gains the built note;
  §9.8-adjacent epic line **E-92** for this work; prepend the full entry to
  `docs/roadmap/last-verified-log.md` (cell keeps the one-sentence latest).
- `PRD.md` FR-702: add the landed note (FR-701 style).
- `docs/adr.md` ADR-10: append the landed note (ADR-9 style).
- Stage AGENTS clauses touched by behaviour: `stages/review/AGENTS.md`
  (patch arrives materialized via `load_diff`; clean-context clause
  unchanged), `stages/analyze/AGENTS.md` (diff is `CodeArtifact`),
  `stages/code/AGENTS.md` (diff fetch/store note), `stages/merge/AGENTS.md`
  (integration_diff is `CodeArtifact`; replay note names this change too).
- `docs/roadmap/filesystem-first.md` §9.8: E-38's "diff claim-check
  deliberately not here" note now resolves to E-92.
- `docs/roadmap/agent-architecture-plan.md` AP-2.7: reword to the S3/fleet
  backend only (FR-702's local discipline no longer blocks it).

## What's left to the builder

- Exact import/type edits per test file (the shape churn is mechanical but
  broad: `test_base_worktree.py` truncation tests move to `load_diff`,
  `test_task_diff_marker_edges.py` marker tests follow, `test_workflow_payload_models.py`
  / `test_workflow_payload_chaos.py` pin the new `AnalyzeResult`,
  stage test fixtures pass `CodeArtifact`).
- The composite-converter subclass details (match the contrib module's
  construction verbatim; the SDK version's shape is authoritative).
- Where `load_diff` registration joins `load_session` (same lists).
- Guard test: a temporal-tier test that a >2MB activity result fails loudly,
  plus a fast unit test over `to_payload`.
- Whether `tests/replay/projection.py` keeps the raw converter (read-only).

## Test impact (summary)

New: store layout for `kind="diff"`; `load_diff` kind-assert + marker edges;
`CodeArtifact` round-trip; guard unit tests plus **two** temporal-tier trips
(result path exhausts-and-fails; input path wedges with the guard error in
history); `diff_ref` populated. Moved: truncation/marker edge tests (from
`get_task_diff` to `load_diff`). Updated: every fake and fixture that builds
a diff dict; `AnalyzeResult` chaos tests; stage signature tests. Re-baselined:
the replay corpus per D8b-1, plus the anchors ruled under D8b-2. All tiers
that touch the converter (`temporal`, `slow`, `live` as present) should be
run in the plan's verification steps.
