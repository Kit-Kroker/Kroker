# FR-702 Claim-Check Diffs + 2MB Wire Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close FR-702 — diffs travel by claim-check (`CodeArtifact` + `ArtifactRef`), the full untruncated patch lives in the artifact store, and a 2MB guard refuses oversized payloads at the wire.

**Architecture:** `get_task_diff` stores the full patch inside the activity (E-38 pattern) and returns a small `CodeArtifact`; prompt consumers materialize bounded patch text via a new `load_diff` read-back activity; `AnalyzeResult` and the stage steps carry the artifact instead of the dict; a guarded payload converter on every client/worker refuses to serialize ≥2MB payloads.

**Tech Stack:** Python 3.13, Temporalio 1.31.0 (pinned — no upgrade), Pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-fr702-claim-check-diffs-design.md` — the plan argues from it; read both. Frozen-anchor ruling **R-A** (2026-11-19) is recorded there in D8b.

## Global Constraints

- Python 3.13 floor; `uv sync --frozen --extra dev` environment.
- temporalio stays pinned at 1.31.0 — **no SDK upgrade rides along**; `sdlc_data_converter` matches the installed construction (no failure-converter argument).
- **No `workflow.patched` marker** anywhere: the change is declared incompatible with in-flight runs; before a worker built from it serves traffic, `temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='GraphWorkflow' OR WorkflowType='TidyUpWorkflow')"` must print nothing.
- File-size ceiling 1000 lines: `stages/code/step.py` is at 987 and NOT baselined — edits there land net-zero-or-negative (`scripts/check_file_size.py` is the authority).
- `ruff check .`, `ruff format .`, `mypy` clean before each commit.
- Test tiers: default `pytest` (fast) green after every task; run `pytest -m "slow or temporal"` before the corpus task; corpus/anchor work runs the full relevant set.
- Diffs stored under `kind="diff"` → `<root>/<run_id>/diffs/<label>.patch` via `LocalFileStore`; only the ref crosses workflow history. No inline-dict fallback anywhere ("store failed, return the patch inline" is the anti-goal).
- `DriftReport.patch` and prompt assembly are out of scope; prompts keep receiving bounded (≤60k chars) patch text.

## Review Focus

Spec-implied inputs no task below may leave unpinned (test named in the owning task):

1. **Diff larger than `max_chars`** — full patch stored untruncated; read-back text ends with `...[diff truncated, N chars omitted]` (Task 3).
2. **Diff exactly `max_chars`** — no marker, exact pass-through (`<=` semantics, Task 3).
3. **`CodeArtifact` with `patch_ref=None`** (propose-mode/legacy) — consumers treat it as empty patch text and never call `load_diff(None)` (Task 5).
4. **Multi-byte UTF-8 patch text sliced by chars** — read-back decodes without exploding on a cut codepoint (Task 3).
5. **Payload exactly at 2MB** — guard trips at ≥ `MAX_PAYLOAD_BYTES`, passes one byte below (Task 4).

---

### Task 1: `CodeArtifact` model + `diff` store subdir

**Files:**
- Create: `src/sdlc/vcs/models.py`
- Modify: `src/sdlc/vcs/git.py` (import the model; nothing else yet), `src/sdlc/vcs/__init__.py` (export), `src/sdlc/artifacts/store.py:23` (`_SUBDIRS`)
- Test: `tests/test_artifact_store.py`, `tests/test_vcs_models.py` (new)

**Interfaces:**
- Produces: `sdlc.vcs.models.CodeArtifact` (also exported as `sdlc.vcs.CodeArtifact`):

```python
class CodeArtifact(BaseModel):
    """ADR-3: one materialized code change, claim-checked (FR-702)."""
    files: list[str] = Field(default_factory=list)
    renames: list[list[str]] = Field(default_factory=list)
    stat: str = ""
    patch_ref: ArtifactRef | None = None
```

- Produces: `_SUBDIRS["diff"] = "diffs"` — later tasks rely on the layout `<root>/<run_id>/diffs/<name>`.

- [ ] **Step 1: Write the failing tests**

`tests/test_artifact_store.py` — extend with:

```python
def test_diff_kind_lands_under_diffs(tmp_path):
    store = LocalFileStore(root=tmp_path)
    ref = store.put("diff", "run-1", "t1-a1.patch", b"diff --git")
    assert ref.kind == "diff"
    assert (tmp_path / "run-1" / "diffs" / "t1-a1.patch").read_bytes() == b"diff --git"
```

`tests/test_vcs_models.py` (new) — defaults round-trip, `patch_ref` accepts `ArtifactRef`, empty construct is valid (the propose-mode arm):

```python
def test_code_artifact_defaults_and_roundtrip():
    art = CodeArtifact()
    assert art.files == [] and art.renames == [] and art.stat == "" and art.patch_ref is None
    ref = ArtifactRef(kind="diff", uri="file:///x.patch", sha256="a" * 64)
    art2 = CodeArtifact.model_validate(CodeArtifact(files=["a.py"], patch_ref=ref).model_dump())
    assert art2.patch_ref == ref and art2.files == ["a.py"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_artifact_store.py::test_diff_kind_lands_under_diffs tests/test_vcs_models.py -v`
Expected: FAIL (no `diff` subdir mapping; `CodeArtifact` not importable).

- [ ] **Step 3: Implement**

Create `src/sdlc/vcs/models.py` with the model above (imports: `pydantic.BaseModel`, `Field`, `..core.models.ArtifactRef` — framework-free, so `workflows/models.py` can import it in Task 6 without dragging activity definitions into agent-loader boot). Add the `_SUBDIRS` entry. Re-export `CodeArtifact` from `vcs/__init__.py` and import it in `vcs/git.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_artifact_store.py tests/test_vcs_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/vcs/models.py src/sdlc/vcs/git.py src/sdlc/vcs/__init__.py src/sdlc/artifacts/store.py tests/test_artifact_store.py tests/test_vcs_models.py
git commit -m "feat(vcs): CodeArtifact model (ADR-3) and diff store layout"
```

### Task 2: `get_task_diff` stores the full patch, returns `CodeArtifact`

**Files:**
- Modify: `src/sdlc/vcs/git.py:89-123` (`DiffInput`, `get_task_diff`)
- Modify: `src/sdlc/demo/fakes.py:168-172` (demo fake), `tests/fakes/fake_activities.py:90-95` (test fake)
- Test: `tests/test_base_worktree.py` (rewrite the `get_task_diff` tests), `tests/test_diff_scoped_fixture_tier.py:45`, `tests/test_integration_activities.py:109`

**Interfaces:**
- Consumes: `CodeArtifact`, `LocalFileStore.put`, `_SUBDIRS["diff"]` (Task 1).
- Produces:

```python
@dataclass
class DiffInput:
    worktree: str
    branch_point: str          # SHA the task branched from — NOT base_branch
    label: str | None = None   # artifact name; None -> branch_point[:12]

@activity.defn
async def get_task_diff(inp: DiffInput) -> CodeArtifact: ...
```

- Produces (fakes): `fake_get_task_diff` / demo fake return `CodeArtifact` — the fakes build a real `LocalFileStore().put("diff", run_id, f"{label}.patch", patch_bytes)` and return metadata + `patch_ref`, so the REAL `load_diff` (Task 3) reads them back; run_id via the same fallback helper.

- [ ] **Step 1: Rewrite the failing tests**

In `tests/test_base_worktree.py`: the rename-pairs test and the truncation tests become — full patch stored **untruncated** regardless of size; returned `CodeArtifact.files`/`renames`/`stat` carry today's values; artifact lands at `<root>/<run_id>/diffs/<label>.patch` with correct `sha256`; outside-worker call (direct `await get_task_diff(...)`) falls back to run id `"local"`; `label` slug survives unsafe chars (reuse the `_safe` regex pattern from `artifacts/capture.py`). `max_chars` assertions move to Task 3. Also update the two dict-shape assertions in the other two test files to artifact accessors.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_base_worktree.py tests/test_diff_scoped_fixture_tier.py tests/test_integration_activities.py -v`
Expected: FAIL (dict vs `CodeArtifact`).

- [ ] **Step 3: Implement**

In `get_task_diff`: same four git invocations; `_run_id()` helper (`activity.info().workflow_id`, `except` → `"local"`); slug the label; `ref = LocalFileStore().put("diff", run_id, f"{label}.patch", patch.encode("utf-8"))` (lazy import of the store, the slice's `max_chars` logic deleted — no truncation at the source); return `CodeArtifact(files=files, renames=renames, stat=stat, patch_ref=ref)`. Update both fakes to the same contract. A store failure simply raises — activity-error semantics identical to a git failure today; **no inline fallback**.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_base_worktree.py tests/test_diff_scoped_fixture_tier.py tests/test_integration_activities.py tests/test_artifact_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/vcs/git.py src/sdlc/demo/fakes.py tests/fakes/fake_activities.py tests/test_base_worktree.py tests/test_diff_scoped_fixture_tier.py tests/test_integration_activities.py
git commit -m "feat(vcs): get_task_diff claim-checks the full patch (FR-702)"
```

### Task 3: `load_diff` read-back activity

**Files:**
- Modify: `src/sdlc/artifacts/read.py` (add `load_diff` beside `load_session`), `src/sdlc/worker.py:37,224` (register beside `load_session`)
- Test: `tests/test_task_diff_marker_edges.py` (rewritten), `tests/test_artifact_read.py` (new or extend)

**Interfaces:**
- Consumes: Task 2's stored artifacts (`kind="diff"`).
- Produces:

```python
class LoadDiffInput(BaseModel):
    ref: ArtifactRef
    max_chars: int = 60_000

@activity.defn
async def load_diff(inp: LoadDiffInput) -> LoadSessionResult: ...  # text carries the T3 marker when cut
```

- Produces: `load_diff` registered on the worker (plain `ACT` scheduling like `load_session` — no pools.py routing; it reads the store, not a worktree).

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_task_diff_marker_edges.py` against `load_diff`: kind-assert (foreign kind raises with `load_diff reads only diffs`); exact `max_chars` pass-through with NO marker (`<=` semantics); one char over → marker `...[diff truncated, N chars omitted]` with the exact omitted count; multi-byte UTF-8 patch sliced at a codepoint decodes via `errors="replace"` without raising. Extend the store/read tests with a round-trip: `put("diff", ...)` → `load_diff` returns the stored text.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_task_diff_marker_edges.py -v`
Expected: FAIL (`LoadDiffInput` not importable).

- [ ] **Step 3: Implement**

Mirror `load_session` (read.py:42-50): assert `kind == "diff"`; read bytes; decode utf-8 `errors="replace"`; char-slice at `max_chars`; if the full text is longer, append the T3 marker (copy the exact format from current `vcs/git.py:120-122`); return `LoadSessionResult(text=..., truncated=...)`. Register in `worker.py` beside `load_session`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_task_diff_marker_edges.py tests/test_artifact_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/artifacts/read.py src/sdlc/worker.py tests/test_task_diff_marker_edges.py
git commit -m "feat(artifacts): load_diff bounded read-back with T3 marker parity"
```

### Task 4: the 2MB wire guard (`sdlc_data_converter`)

**Files:**
- Create: `src/sdlc/converter.py`
- Modify (import swap only): `src/sdlc/worker.py:30,403`, `src/sdlc/cli.py:41,532`, `src/sdlc/operator/runtime.py:22,40`, `src/sdlc/benchmarks/cli.py:283,343`, `src/sdlc/demo/__main__.py:64,72`, `tests/replay/harness.py`, `tests/replay/test_pools_replay.py`, `tests/replay/capture_provider_requests.py`, `tests/test_pinned_base_e2e.py`, `tests/test_e2e_greenfield.py`
- Test: `tests/test_wire_size_guard.py` (new; unit + two `temporal`-marked trips)

**Interfaces:**
- Produces:

```python
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024

class PayloadTooLargeError(RuntimeError): ...

sdlc_data_converter: DataConverter  # pydantic_data_converter's construction,
                                    # JSON converter swapped for the guarded subclass
```

- [ ] **Step 1: Write the failing tests**

Unit: `to_payload` passes at `MAX_PAYLOAD_BYTES - 1` bytes of data; raises `PayloadTooLargeError` at exactly `MAX_PAYLOAD_BYTES`; `from_payload` (decode) is untouched — a fat payload built by the raw converter decodes fine under `sdlc_data_converter`; the error message names the claim-check fix. Temporal-tier (`@pytest.mark.temporal`): (a) an activity whose RESULT exceeds 2MB fails its task, retries exhaust, workflow takes its failure path — NOT a silent 2MB history write; (b) a workflow scheduling an activity whose INPUT exceeds 2MB wedges: workflow stays `RUNNING` with the guard error in history (assert the error text, then terminate the run — this pins the documented D7 input-path behavior).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_wire_size_guard.py -v` (unit legs)
Expected: FAIL (`sdlc.converter` not importable).

- [ ] **Step 3: Implement `src/sdlc/converter.py`**

Subclass `PydanticJSONPlainPayloadConverter`; `to_payload` calls super, then raises `PayloadTooLargeError(f"... {len} bytes >= {MAX_PAYLOAD_BYTES}; claim-check it via ArtifactRef (FR-702)")` when `payload is not None and len(payload.data) >= MAX_PAYLOAD_BYTES`. Build `sdlc_data_converter = DataConverter(payload_converter_class=<PydanticPayloadConverter subclass with the guarded JSON converter first>)` — copy the composite's construction from the installed `temporalio/contrib/pydantic.py` verbatim; **no failure-converter argument** (1.31.0 has none; failure wire format unchanged). Swap every listed import site to `sdlc_data_converter` (mechanical; `tests/replay/projection.py` is decode-only and keeps the raw converter).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wire_size_guard.py -v && uv run pytest -m temporal tests/test_wire_size_guard.py -v`
Expected: PASS (both tiers).

- [ ] **Step 5: Run the touched suites**

Run: `uv run pytest tests/test_pinned_base_e2e.py tests/replay -m temporal -q`
Expected: PASS — histories predate this task's diff changes (Tasks 5-6 haven't landed); a red here means the converter swap broke the wire, not the corpus.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/converter.py src/sdlc/worker.py src/sdlc/cli.py src/sdlc/operator/runtime.py src/sdlc/benchmarks/cli.py src/sdlc/demo/__main__.py tests/replay/harness.py tests/replay/test_pools_replay.py tests/replay/capture_provider_requests.py tests/test_pinned_base_e2e.py tests/test_e2e_greenfield.py tests/test_wire_size_guard.py
git commit -m "feat(wire): 2MB payload guard on every client and worker (FR-702, ADR-10)"
```

### Task 5: per-task diff consumers (code stage, qa, review, handoff)

**Files:**
- Modify: `src/sdlc/stages/code/step.py` (attempt flow at :727-758, :774, :409, :977; helpers `_run_adversary` :312, `_run_deep_review` :338, `_run_handoff` :371), `src/sdlc/stages/qa/step.py` (:192-201), `src/sdlc/stages/review/step.py` (`step` :105, `run_adversary` :191, `run_deep_review` :275; delete `_get_patch` :69-71)
- Test: `tests/code/` fixtures (at least `test_task_lint_loop.py:95`, `test_attempt_records.py:80`, `test_lens_tombstones.py:221`), `tests/qa/`, `tests/review/`

**Interfaces:**
- Consumes: `get_task_diff -> CodeArtifact` (Task 2), `load_diff` (Task 3).
- Produces (new signatures — qa/review are called only from `code/step.py`; the builder check verified no other callers):

```python
# code/step.py attempt flow (once per attempt, after run_test_suite):
art = await workflow.execute_activity(get_task_diff, DiffInput(worktree=worktree, branch_point=branch_point, label=f"{task.id}-a{attempt}"), ...)
patch = art.patch_ref and await workflow.execute_activity(load_diff, LoadDiffInput(ref=art.patch_ref), **ACT)
run.diff_ref = art.patch_ref            # D6 — the claim-check rides TaskResult
patch_text = patch.text if patch else ""   # patch_ref=None (Review Focus 3) -> empty, no load_diff call

# qa/step.py:  diff: dict -> stat: str = "", patch: str = ""
# review/step.py (all three entry points): diff: dict | str -> patch: str
# code/step.py helpers: _run_adversary(..., patch: str, ...), _run_deep_review(..., patch: str, ...),
#                       _run_handoff(..., patch: str, files: list[str], ...)
```

- [ ] **Step 1: Update the stage tests first**

Mechanical rule for every fixture that builds a diff dict today: build `CodeArtifact(files=[...], stat=..., patch_ref=<real ref from LocalFileStore.put or None>)` and pass `patch=`/`stat=`/`files=` per the new signatures; where a fake intercepts `get_task_diff` by name, its return is already a `CodeArtifact` (Task 2). Add one new test (Review Focus 3): a `CodeArtifact` with `patch_ref=None` flowing through the attempt → qa/review prompts receive empty patch text, `run.diff_ref is None`, and no `load_diff` command is scheduled.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/code tests/qa tests/review -q`
Expected: FAIL (signatures).

- [ ] **Step 3: Implement**

Swap the attempt-flow block per the Interfaces block; thread `patch_text`/`art.files` into `qa_step` (`stat=art.stat, patch=patch_text`), `review_step` (`patch=patch_text`), the escalation prompt (:409), `plan_drift` (:774, `art.files`), quarantine note (:977, `art.files`), and the three helpers. Delete `_get_patch` from review. **Net-zero-or-negative line delta in `code/step.py`** — if additions outpace the deletions, move the `_run_handoff` claim-crosscheck block (pure) to `handoff.py` per the slice's `attempt_failure.py` pattern; check with `wc -l`.

- [ ] **Step 4: Run tests + line budget**

Run: `uv run pytest tests/code tests/qa tests/review -q && wc -l src/sdlc/stages/code/step.py`
Expected: PASS; ≤ 987 lines.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/stages/code/step.py src/sdlc/stages/qa/step.py src/sdlc/stages/review/step.py tests/code tests/qa tests/review
git commit -m "feat(stages): diff consumers take materialized patch + CodeArtifact (FR-702)"
```

### Task 6: integration diff — `AnalyzeResult`, analyze, postplan, merge

**Files:**
- Modify: `src/sdlc/workflows/models.py:78-86` (`AnalyzeResult`), `src/sdlc/workflows/graph_nodes/postplan.py:117-149` (`analyze_node`), `src/sdlc/stages/analyze/step.py` (:101 `diff` param, :117-122 fallback, :170-171 prompt args), `src/sdlc/stages/merge/step.py:298,326-339`
- Test: `tests/test_workflow_payload_models.py`, `tests/test_workflow_payload_chaos.py`, `tests/analyze/`, `tests/merge/`

**Interfaces:**
- Consumes: `CodeArtifact` (import in `workflows/models.py` from `..vcs.models` — framework-free path), `load_diff`.
- Produces:

```python
class AnalyzeResult(BaseModel):
    report: AnalysisReport
    untraced: list[str]
    integration_diff: CodeArtifact        # was dict[str, Any]

# analyze/step.py signature: diff: CodeArtifact | None = None, patch: str = ""
#   (fallback when diff is None: fetch get_task_diff(label="integration") + load_diff, as today's :117-122)
# analyze_node: art = get_task_diff(label="integration"); patch = load_diff(art.patch_ref);
#               analyze.step(..., diff=art, patch=patch.text); AnalyzeResult(integration_diff=art)
# merge/step.py: integration_diff: CodeArtifact | None; changed_files = art.files; renames = art.renames
```

- [ ] **Step 1: Update the tests first**

Payload model tests: `AnalyzeResult` round-trips with a `CodeArtifact` (and rejects nothing on `patch_ref=None` — chaos test's empty-construct leg maps to the propose arm). Analyze tests: pass `diff=CodeArtifact(...)` + `patch=`; merge tests: `integration_diff=CodeArtifact(files=[...], renames=[...])` and assert `changed_files`/`renames` derive from it. The chaos suite's "get_task_diff dict shape round-trips" leg is REPLACED by the artifact-shape leg (dicts no longer ride this field).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_payload_models.py tests/test_workflow_payload_chaos.py tests/analyze tests/merge -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Per the Interfaces block. `analyze_node` schedules `load_diff` with plain `ACT` (like the stage's other reads); `merge_node` (:168) passes `analysis.integration_diff` through unchanged — already the artifact. `merge/step.py`'s `isinstance(integration_diff, dict)` guards (:327, :337) are deleted along with the dict accessors.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_payload_models.py tests/test_workflow_payload_chaos.py tests/analyze tests/merge -q && uv run pytest -q`
Expected: PASS (whole fast tier).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/models.py src/sdlc/workflows/graph_nodes/postplan.py src/sdlc/stages/analyze/step.py src/sdlc/stages/merge/step.py tests/test_workflow_payload_models.py tests/test_workflow_payload_chaos.py tests/analyze tests/merge
git commit -m "feat(analyze,merge): integration diff rides as CodeArtifact (FR-702)"
```

### Task 7: replay corpus re-baseline + frozen anchors under ruling R-A

**Files:**
- Regenerated (by tooling only, never hand-edited): `tests/replay/histories/*`, `tests/replay/golden/*`, the R-A-ruled frozen fixtures under `tests/durability/fixtures/` (expected: `wire_no_override.json`, the worker-registration fixture, and any architect-era recording whose scenario crosses the code stage)
- Test: `tests/replay/`, `tests/durability/`

**Interfaces:**
- Consumes: the completed code change (Tasks 1-6); ruling R-A (spec D8b).

- [ ] **Step 1: Audit which frozen anchors cross the code stage**

Grep each fixture under `tests/durability/fixtures/` for `get_task_diff` (and note the worker-registration fixture's activity list): produce the exact list of R-A-affected anchors. Anchors NOT crossing the code stage stay frozen untouched — regenerating one that didn't need it is a defect.

- [ ] **Step 2: Re-baseline the replay corpus (Rule 2 path)**

Run: `SDLC_CAPTURE_HISTORIES=1 uv run pytest tests/replay/test_capture_graph.py -m temporal -q` (capture-twice rule enforced by the test). Save the projection diff (`check_golden_rebaseline.py` output) for the commit message / review attachment.

- [ ] **Step 3: Regenerate the ruled anchors (R-A)**

Run: `SDLSC_WIRE_REGEN=1 uv run pytest -m temporal tests/durability/test_wire_neutrality.py` and the ruled recordings' own capture path (per their test docstrings). Attach the live-vs-frozen diff to the commit message — this diff IS the ruling's record.

- [ ] **Step 4: Verify the whole recorded-history tier**

Run: `uv run pytest -m "slow or temporal" -q`
Expected: PASS. A red replay that re-capture does not clear means the command stream changed beyond the designed `load_diff` additions — STOP and reconcile against the spec's D8b before touching anything else.

- [ ] **Step 5: Commit**

```bash
git add tests/replay tests/durability
git commit -m "test(replay,durability): re-baseline corpus + R-A anchor regeneration (FR-702)"
```

### Task 8: docs + roadmap close-out

**Files:**
- Modify: `ROADMAP.md` (:356 FR-702 → `[x]` + one-sentence evidence; :464 NFR-4 → `[x]`, dropping the FR-702 clause; ADR-10 entry gains the built note; add epic **E-92** line with spec/plan links), `PRD.md:313` (landed note, FR-701 style), `docs/adr.md:98` (ADR-10 landed note, ADR-9 style), `docs/roadmap/filesystem-first.md` §9.8 (E-38's "diff claim-check deliberately not here" resolves to E-92), `docs/roadmap/agent-architecture-plan.md:44` (AP-2.7 rewords to the S3/fleet backend only), stage AGENTS clauses: `src/sdlc/stages/review/AGENTS.md` (patch arrives materialized via `load_diff`; clean-context clause unchanged), `src/sdlc/stages/analyze/AGENTS.md` (diff is `CodeArtifact`), `src/sdlc/stages/code/AGENTS.md` (claim-check fetch + `run.diff_ref`), `src/sdlc/stages/merge/AGENTS.md` (`integration_diff` is `CodeArtifact`; append this change to the replay-drain note), `docs/roadmap/last-verified-log.md` (prepend full close-out; ROADMAP cells keep the one-sentence latest)

**Interfaces:**
- Consumes: everything landed; the R-A record from Task 7's commit.

- [ ] **Step 1: Write the doc edits** — all files above; evidence sentences name real symbols (`sdlc.vcs.models.CodeArtifact`, `artifacts/read.py::load_diff`, `sdlc.converter.sdlc_data_converter`, `MAX_PAYLOAD_BYTES`). The last-verified-log entry records BOTH guard failure modes in operator terms (spec D7): oversized result → activity fails via its existing failure path; oversized input → the run wedges `Running` until terminated, detectable by the drain query.

- [ ] **Step 2: Verify gates**

Run: `uv run python scripts/check_file_size.py && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md PRD.md docs/adr.md docs/roadmap src/sdlc/stages/*/AGENTS.md
git commit -m "docs: close FR-702 and NFR-4 (claim-check diffs, 2MB wire guard, E-92)"
```

---

## Verification (whole plan)

1. `uv run pytest -q` — fast tier green after every task.
2. `uv run pytest -m "slow or temporal" -q` — green after Task 7.
3. `uv run python scripts/check_file_size.py`, `ruff`, `mypy` — green at close.
4. The drain check (Global Constraints) is an operator runbook step at deploy, not a test.
