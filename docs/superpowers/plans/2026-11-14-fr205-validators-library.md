# FR-205 Validators Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close FR-205 — a shared `src/sdlc/validators/` library enforcing proposer decision boundaries in code (plan halts: duplicate ids, DAG, requirement coverage, task size; clarify discard: evidence paths that don't exist), plus ADR-24 handoff evidence schemas.

**Architecture:** A new horizontal package (the `memoization/`/`memory/`/`vcs/` seam) holds pure workflow-safe validators and one tree-reading activity. The plan stage's scattered check migrates in; `plan_check_node` grows the halt family; the FR-113 `Requirements` artifact reaches the planner and `plan_check` through two new graph edges; clarify's merge gains a path-grounded discard behind a `workflow.patched` marker.

**Tech Stack:** Python 3.13, Pydantic, Temporal (workflow sandbox + activities), pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-fr205-validators-library-design.md` — the plan argues from it; executors read both.

## Global Constraints

- Build: `uv sync --frozen --extra dev`. Tests: `pytest` (fast tier default; this work needs no `slow`/`temporal`/`live` markers). Lint/type: `ruff check .`, `ruff format .`, `mypy` — all must pass before close.
- 1000-line physical file ceiling (root AGENTS.md); every file here starts far below.
- Workflow determinism: `validators/pure.py` has no I/O and no top-level `temporalio` import (pinned by test, Task 1); the only tree access is the `paths_exist` activity.
- Cross-stage imports are **types and renders only** (root AGENTS.md). `validators` importing `DevTask` from `stages.plan.models` and `PlanConfig` from `core.models` is legal; no stage-to-stage calls are added.
- Byte-identity rules: every "" sentinel (prompt block, digest) keeps flag-off runs byte-identical to today — pinned by characterization and memo-key tests, never broken.
- Replay discipline: new workflow behavior sits behind `workflow.patched("023-clarify-evidence-paths")` (wire name; never rename after deploy); the patch id may ship under a different round number — the string is opaque and stable, that is what matters.
- Halt strings are wire contracts: `failed:plan-validation:<reason>` — keep the existing reason texts verbatim where migrating.
- `DevTask.covers` is additive with a default — pre-existing artifact JSON deserializes unchanged (E-1 precedent).

## Review Focus

The spec implies these input classes; each is pinned by the named test in its owning task.

1. **A plan with two tasks sharing one id** must halt naming the duplicates — today it silently corrupts the scheduler's `by_id`. (Task 1 `test_ids_unique_*`; Task 3 halt-string test.)
2. **A requirements-enabled run whose tasks collectively miss an FR id** must halt naming the uncovered ids — not pass into code with a requirement silently dropped. (Task 2 `test_covers_all_*`; Task 3 wiring test.)
3. **An oversized task** (files_hint or criteria over limit) must halt naming the task and the breached limit. (Task 2 `test_task_size_*`; Task 3 wiring test.)
4. **Probe evidence citing a missing path vs an existing path vs a bare symbol** — discard / keep / keep, in brownfield fan-out runs only. (Task 5 `test_path_like_tokens_*`; Task 6 `test_merge_discards_*`.)
5. **Flag-off and greenfield runs are byte-identical to today** — no `paths_exist` command, unchanged planner prompt bytes, unchanged memo keys. (Task 4 characterization + `test_plan_memo_key`-style tests; Task 6 gating tests.)

---

### Task 1: Validators package — migrate the plan-graph check, add `ids_unique`

**Files:**
- Create: `src/sdlc/validators/__init__.py`, `src/sdlc/validators/pure.py`
- Delete: `src/sdlc/stages/plan/validation.py`
- Modify: `src/sdlc/workflows/graph_nodes/postplan.py:15` (import), `:29` (call site)
- Test: `tests/validators/test_pure.py` (new); repoint `tests/plan/test_plan_graph_validation.py:9`, `tests/plan/test_plan_validation_module.py:4`

**Interfaces:**
- Produces (later tasks rely on exactly these):
  - `ids_unique(tasks: list[DevTask]) -> str | None` — `None` = pass; failure text `duplicate task id(s): ['T1', ...]` (sorted).
  - `deps_resolve(tasks: list[DevTask]) -> str | None` — failure text verbatim from today: `task 'A' depends on unknown task id(s) ['Z']`.
  - `dag_acyclic(tasks: list[DevTask]) -> str | None` — failure text verbatim: `dependency cycle: A -> B -> A`.
  - `validate_task_graph(tasks: list[DevTask]) -> str | None` — composition `deps_resolve or dag_acyclic`; identical behavior to the deleted module.
  - `__init__.py` re-exports all four from `.pure`.

- [ ] **Step 1: Write the failing tests**

Create `tests/validators/test_pure.py`; port the bodies of `tests/plan/test_plan_graph_validation.py` and `tests/plan/test_plan_validation_module.py` to import from `sdlc.validators` (keep every assertion verbatim — they pin the migration), then add:

```python
def test_ids_unique_passes():
    assert ids_unique([_task("T1"), _task("T2")]) is None

def test_ids_unique_names_duplicates_sorted():
    tasks = [_task("T2"), _task("T1"), _task("T2"), _task("T1")]
    assert ids_unique(tasks) == "duplicate task id(s): ['T1', 'T2']"

def test_pure_module_has_no_temporalio_or_io():
    # subprocess import check, modeled on test_plan_models_does_not_import_temporalio_at_module_level
    # (tests/plan/test_plan_drift_generated.py:137-146)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/validators/test_pure.py -q`
Expected: FAIL — `ModuleNotFoundError: sdlc.validators`

- [ ] **Step 3: Implement `src/sdlc/validators/pure.py`**

Module docstring: FR-205's library; pure, workflow-safe. Move the two halves of `stages/plan/validation.py` (keep docstring content — it records the bench case) into `deps_resolve` and `dag_acyclic`; `validate_task_graph` composes them; `ids_unique` counts ids with `collections.Counter`. Duplicate the 2-line `_norm_path` only if needed here (not needed in this task — it belongs to Task 5's tokenizer); no other imports beyond `from ..stages.plan.models import DevTask` and stdlib.

- [ ] **Step 4: Repoint call sites and delete the old module**

`postplan.py:15` → `from ...validators import validate_task_graph` (inside the existing `imports_passed_through` block); call at `:29` unchanged. Both test files import `sdlc.validators`. Delete `src/sdlc/stages/plan/validation.py`. Confirm no stragglers: `grep -rn "stages.plan.validation" src/ tests/` → empty.

- [ ] **Step 5: Run tests**

Run: `pytest tests/validators/ tests/plan/ tests/graph_workflow/test_postplan_handlers_chaos.py -q`
Expected: PASS (fast tier slice)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/validators tests/validators tests/plan src/sdlc/workflows/graph_nodes/postplan.py
git rm src/sdlc/stages/plan/validation.py
git commit -m "feat(validators): FR-205 library shell — migrate plan-graph checks, add ids_unique"
```

---

### Task 2: `covers` field, `covers_all`, `task_size`, `PlanConfig`

**Files:**
- Modify: `src/sdlc/stages/plan/models.py:25-37` (`DevTask`)
- Modify: `src/sdlc/core/models.py` (new `PlanConfig`; `PipelineConfig.plan` field after `requirements`, `~:423`)
- Modify: `src/sdlc/validators/pure.py`, `__init__.py`
- Test: `tests/validators/test_pure.py` (extend)

**Interfaces:**
- Consumes: `DevTask` (Task 1).
- Produces:
  - `DevTask.covers: list[str] = Field(default_factory=list, description="FR ids from the requirements artifact this task implements")`.
  - `PlanConfig(BaseModel)` in `core/models.py`: `max_files_hint: int = 24`, `max_criteria: int = 12`; docstring: FR-205 limits, defaults generous (above every golden-case task shape), breach halts legibly.
  - `PipelineConfig.plan: PlanConfig = Field(default_factory=PlanConfig)`.
  - `covers_all(tasks: list[DevTask], requirement_ids: list[str]) -> list[str]` — uncovered requirement ids, sorted; empty = pass. Ids cited in `covers` but absent from `requirement_ids` are ignored (a `US-*` cover is legal).
  - `task_size(tasks: list[DevTask], limits: PlanConfig) -> str | None` — first breach only; text `task 'T3' exceeds plan limits: files_hint=25>24` (or `criteria=13>12`).

- [ ] **Step 1: Write the failing tests**

```python
def test_covers_all_passes_when_every_fr_covered():
    frs = ["FR-1", "FR-2"]
    tasks = [_task("T1", covers=["FR-1"]), _task("T2", covers=["FR-2", "FR-3"])]
    assert covers_all(tasks, frs) == []

def test_covers_all_names_uncovered_sorted_and_ignores_unknown_covers():
    tasks = [_task("T1", covers=["FR-1", "US-9"])]
    assert covers_all(tasks, ["FR-1", "FR-2", "FR-3"]) == ["FR-2", "FR-3"]

def test_task_size_passes_at_limits():
    limits = PlanConfig()
    assert task_size([_task("T1", files_hint=["f"] * 24, criteria=["c"] * 12)], limits) is None

def test_task_size_names_first_breach():
    big = _task("T3", files_hint=["f"] * 25, criteria=["c"] * 13)
    assert task_size([big], PlanConfig()) == "task 'T3' exceeds plan limits: files_hint=25>24"

def test_devtask_covers_defaults_empty_and_old_json_deserializes():
    assert DevTask(id="T1", title="t", description="d", acceptance_criteria=["a"]).covers == []
    legacy = json.loads(DevTask(id="T1", title="t", description="d", acceptance_criteria=["a"]).model_dump_json())
    assert "covers" in legacy and legacy["covers"] == []

def test_planconfig_defaults_pinned():
    # The false-kill guard IS the generous default — pin the wire values.
    assert PlanConfig() == PlanConfig(max_files_hint=24, max_criteria=12)
```

(`_task` grows optional `covers`/`files_hint`/`criteria` kwargs.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/validators/test_pure.py -q`
Expected: FAIL — `covers_all`/`task_size` undefined, `covers` unknown field

- [ ] **Step 3: Implement**

`DevTask.covers` after `overlaps`. `PlanConfig` beside `RequirementsConfig`. `covers_all`: `covered = {c for t in tasks for c in t.covers}; return sorted(r for r in requirement_ids if r not in covered)`. `task_size`: check `files_hint` then `acceptance_criteria` per task in list order, first breach wins.

- [ ] **Step 4: Run tests; full fast-tier sanity**

Run: `pytest tests/validators/ tests/plan/ -q && pytest -q`
Expected: PASS (whole default tier at its known baseline)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/validators src/sdlc/core/models.py src/sdlc/stages/plan/models.py tests/validators
git commit -m "feat(validators): covers field, covers_all, task_size with PlanConfig limits (FR-205)"
```

---

### Task 3: `plan_check_node` — the extended halt family

**Files:**
- Modify: `src/sdlc/workflows/graph_nodes/postplan.py:26-34` (`plan_check_node`)
- Test: `tests/graph_workflow/test_postplan_handlers_chaos.py` (extend — it already drives `plan_check_node`)

**Interfaces:**
- Consumes: `ids_unique`, `deps_resolve`, `dag_acyclic`, `covers_all`, `task_size` (Tasks 1–2); `Requirements` via `input_model(nc, act, "requirements_doc")` — absent input returns `None` (constitution precedent, `precode.py:150`).
- Produces: the halt order later docs describe — `ids_unique` → `deps_resolve` → `dag_acyclic` → `covers_all` (only when a requirements artifact with stories exists) → `task_size`; every failure `NodeResult(port="halt", result=f"failed:plan-validation:{reason}")`.

- [ ] **Step 1: Write the failing tests**

Extend the chaos test file (follow its existing node-driving harness):

```python
def test_plan_check_halts_on_duplicate_ids():        # → "failed:plan-validation:duplicate task id(s): ['T1']"
def test_plan_check_halts_on_uncovered_requirements():  # requirements_doc with FR-1..3, tasks cover FR-1 only
    # → "failed:plan-validation:requirement(s) not covered by any task: ['FR-2', 'FR-3']"
def test_plan_check_halt_order_duplicate_before_dag():  # a plan with both faults names the duplicate
def test_plan_check_halts_on_oversize_task():        # → "failed:plan-validation:task 'T1' exceeds plan limits: files_hint=25>24"
def test_plan_check_passes_without_requirements_doc():  # no requirements_doc input → coverage vacuous, clean pass
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/graph_workflow/test_postplan_handlers_chaos.py -q`
Expected: FAIL — duplicate-id plan passes (the old silent-collapse bug), etc.

- [ ] **Step 3: Implement the check chain in `plan_check_node`**

Replace the single `validate_task_graph` call with the ordered chain; FR ids for `covers_all`: `[fr.id for s in req_doc.stories for fr in s.functional]`; skip coverage when `req_doc is None or not req_doc.stories`; size from `cfg.plan`. Board sync stays last-success-only (after all checks pass), exactly as today (`postplan.py:32-34`).

- [ ] **Step 4: Run tests**

Run: `pytest tests/graph_workflow/ -q && pytest tests/validators/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/graph_nodes/postplan.py tests/graph_workflow
git commit -m "feat(plan): plan_check enforces ids/DAG/coverage/size halt family (FR-205)"
```

---

### Task 4: Requirements delivery — prompt block, memo key, graph edges

**Files:**
- Modify: `src/sdlc/prompts.py:34-50` (`planner_prompt`)
- Modify: `src/sdlc/stages/plan/step.py:99-149` (`produce`)
- Modify: `src/sdlc/workflows/graph_nodes/precode.py:212-234` (`plan_node`)
- Modify: `src/sdlc/workflows/graphs/default-requirements.graph.yaml:16-39` (two edges)
- Test: `tests/test_prompts_characterization.py` (extend); `tests/plan/test_plan_stage_wiring.py` (extend, or the file that already pins `produce`'s cache key — find with `grep -rn "cache_key" tests/plan/`)

**Interfaces:**
- Consumes: `render_requirements(c: Requirements, *, max_chars: int = 2000)` from `stages/requirements/prompts.py:38` (render import — legal); `Requirements.digest` (`stages/requirements/models.py:40`).
- Produces:
  - `planner_prompt(arch_json, memory, guidance, constitution_block="", requirements_block="")` — inserted **after** `constitution_block`, before the memory block; "" default keeps bytes identical.
  - `plan.produce(..., requirements_doc: Requirements | None = None)`; prompt gains the rendered block + one instruction line; `cache_key` gains `(requirements_doc.digest if requirements_doc is not None else "")` between `constitution_digest` and `guidance`.
  - Graph edges: `requirements → planner(requirements_doc)` and `requirements → plan_check(requirements_doc)` (Task 3 already reads the port).
  - `plan_node` passes `requirements_doc=input_model(nc, act, "requirements_doc")` (default graph: no such edge → `None` → byte-identical run).

- [ ] **Step 1: Write the failing tests**

Characterization (byte-exact, house style):

```python
def test_planner_requirements_block_inserted_after_constitution():
    out = planner_prompt(ARCH, [], None, "CONST", "REQS")
    assert out == ARCH + "\n\nCONST" + "\n\nREQS"

def test_planner_requirements_block_empty_is_byte_identical():
    assert planner_prompt(ARCH, [], None, "CONST", "") == planner_prompt(ARCH, [], None, "CONST")
```

Wiring/memo tests: `produce` with `requirements_doc=None` builds the exact cache key of today (pin the concatenation); with a doc, key contains its digest and the prompt contains `render_requirements` output plus the instruction `Each task must list the FR ids it implements in its covers field.`

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_prompts_characterization.py tests/plan/ -q`
Expected: FAIL — `planner_prompt` takes no `requirements_block`

- [ ] **Step 3: Implement**

`planner_prompt` body: `arch + (const block) + (reqs block) + memory + guidance`, each with the same `if block` guards. In `produce`: build `requirements_block = render_requirements(requirements_doc) + "\nEach task must list the FR ids it implements in its covers field."` when the doc has stories, else `""`; pass both blocks; extend `cache_key` (step.py:137). `plan_node` reads and forwards the input. Add the two edges to `default-requirements.graph.yaml` (never the pinned default graph — requirements-slice gotcha). Type imports (`Requirements`, `render_requirements`) go in `plan/step.py`'s existing `imports_passed_through` block, beside the constitution pair.

- [ ] **Step 4: Run tests incl. graph identity**

Run: `pytest tests/test_prompts_characterization.py tests/plan/ tests/graph_workflow/test_graph_catalog.py -q`
Expected: PASS; the default graph's pinned sha untouched (graph-catalog test enforces it)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/prompts.py src/sdlc/stages/plan/step.py src/sdlc/workflows/graph_nodes/precode.py src/sdlc/workflows/graphs/default-requirements.graph.yaml tests
git commit -m "feat(plan): requirements_doc reaches planner prompt, memo key and plan_check (FR-205, FR-113)"
```

---

### Task 5: `paths_exist` activity + `path_like_tokens`

**Files:**
- Create: `src/sdlc/validators/activities.py`
- Modify: `src/sdlc/validators/pure.py` (tokenizer), `__init__.py`; `src/sdlc/worker.py:130+` (registration)
- Test: `tests/validators/test_activities.py` (new), `tests/validators/test_pure.py` (extend)

**Interfaces:**
- Produces:
  - `path_like_tokens(text: str) -> list[str]` — pure; tokens containing `/` or `\`, or matching `[\w.-]+\.(py|ts|tsx|js|go|rs|md|yaml|yml|json|toml|txt|cfg|ini|sql|sh)$`, each normalized by a local copy of `_norm_path` (`plan/models.py:58-60` twin; comment cross-references it); sorted, deduped.
  - `paths_exist(repo_path: str, paths: list[str]) -> dict[str, bool]` — `@activity.defn`; `(Path(repo_path) / norm(p)).exists()` per normalized token; unknown/empty paths → `False`.
  - `ACTIVITIES = [paths_exist]`; `worker.get_worker_activities()` includes it (add beside `get_task_diff`, worker.py:179).

- [ ] **Step 1: Write the failing tests**

```python
def test_path_like_tokens_paths_and_extensions():
    assert path_like_tokens("see src/app.py and configs/prod.yaml; also README.md") == [
        "README.md", "configs/prod.yaml", "src/app.py"]  # sorted

def test_path_like_tokens_symbols_and_prose_pass_through_empty():
    assert path_like_tokens("sdlc.stages.plan.validation:26 and 'the merge step'") == []

def test_path_like_tokens_normalizes_windows_and_dot_slash():
    assert path_like_tokens(".\\src\\app.py ./lib.ts") == ["lib.ts", "src/app.py"]

def test_paths_exist_maps_existence(tmp_path):   # direct activity-function call, no worker
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "app.py").write_text("x")
    assert paths_exist(str(tmp_path), ["src/app.py", "src/missing.py"]) == {
        "src/app.py": True, "src/missing.py": False}

def test_worker_registers_paths_exist():
    from sdlc.worker import get_worker_activities
    assert any(fn.__name__ == "paths_exist" for fn in get_worker_activities())
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/validators/ -q` — Expected: FAIL, names undefined

- [ ] **Step 3: Implement**

`activities.py` imports `temporalio.activity` at module top (activities module — expected); keep it out of `pure.py`. Registration import in `worker.py` beside the vcs imports.

- [ ] **Step 4: Run tests**

Run: `pytest tests/validators/ -q` — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/validators src/sdlc/worker.py tests/validators
git commit -m "feat(validators): paths_exist activity + path_like_tokens tokenizer (FR-205)"
```

---

### Task 6: Clarify wiring — evidence-path discard, mode gate, patch marker

**Files:**
- Modify: `src/sdlc/stages/clarify/step.py` (`:76-110` `_clarify_fanout`, signature `:120+`), `src/sdlc/stages/clarify/merge.py:97-99`, `:68-74` (signature)
- Modify: `src/sdlc/workflows/graph_nodes/precode.py:154-168` (`clarify_node` passes `repo_path`)
- Test: `tests/clarify/test_clarify_merge.py` (extend), `tests/clarify/test_clarify_stage_wiring.py` (extend)

**Interfaces:**
- Consumes: `path_like_tokens`, `paths_exist` (Task 5); `ProjectMode` (core/models.py:21).
- Produces:
  - `CLARIFY_EVIDENCE_PATCH = "023-clarify-evidence-paths"` and `_evidence_paths_enabled() -> bool` in `clarify/step.py`: `False` outside a workflow; inside, `workflow.patched(CLARIFY_EVIDENCE_PATCH)` (inverse of `_DRIFT_V2`'s outside-True — a real activity call must not fire in unit tests; the 017 test file mocks instead).
  - `merge_clarification(..., missing_paths: frozenset[str] = frozenset())` — default keeps every existing test byte-identical.
  - `clarify.step(..., repo_path: str | None = None)`.
- Behavior: in the fan-out branch, when `_evidence_paths_enabled()` and `idea.mode is ProjectMode.BROWNFIELD` and `repo_path`: collect `path_like_tokens(q.evidence or "")` over route + probe questions, dedupe; if any, one `workflow.execute_activity(paths_exist, ...)` call (start-to-close 1 min, no retry — a read); pass the missing set into `merge_clarification`. All other paths: `missing_paths` empty, zero new commands.

- [ ] **Step 1: Write the failing tests**

Merge (pure):

```python
def test_merge_discards_grounded_question_citing_missing_path():
    # grounded dim question, evidence "see src/gone.py", missing_paths={"src/gone.py"}
    # → not in open_questions and not in dropped (DISCARD semantics, merge.py:7-12)

def test_merge_keeps_question_when_path_exists_or_symbol_cited():
    # missing_paths empty and evidence "module.attr" → question survives both

def test_merge_default_missing_paths_unchanged_behavior():
    # the existing merge tests already pin this; run them untouched
```

Step wiring (mock `temporalio.workflow.execute_activity` + patch `_evidence_paths_enabled`, modeled on `tests/plan/test_plan_drift_generated.py:190-224`): brownfield fan-out discards on missing path; greenfield mode never issues the activity call (`mock_act.assert_not_called()`); `_evidence_paths_enabled` returns `False` outside workflow and consults `workflow.patched("023-clarify-evidence-paths")` inside (mirror `test_drift_v2_direct_call_and_patched_workflow`, `:150-162`).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/clarify/ -q` — Expected: FAIL on the new tests

- [ ] **Step 3: Implement**

Merge: extend the line-99 filter — grounded questions survive only with evidence whose `path_like_tokens` don't intersect `missing_paths`. Step: the gating block in `_clarify_fanout` before `merge_clarification`; `imports_passed_through` gains the validators imports. `clarify_node` passes `repo_path=nc.facts.repo_path`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/clarify/ -q && pytest -q`
Expected: PASS — including every pre-existing clarify test untouched

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/stages/clarify src/sdlc/workflows/graph_nodes/precode.py tests/clarify
git commit -m "feat(clarify): brownfield evidence-path discard behind 023 patch (FR-205)"
```

---

### Task 7: Evidence schemas (ADR-24 handoff, no consumers)

**Files:**
- Create: `src/sdlc/validators/evidence.py`; modify `__init__.py`
- Test: `tests/validators/test_evidence.py`

**Interfaces:**
- Produces: `AssertionEvidence(claim: str, evidence: str, source: str = "")`, `Finding(evidence: AssertionEvidence, detail: str = "", blocking: bool = False)`, `Coverage(total: int, covered: list[str], uncovered: list[str])` — evidence fields before status fields; module docstring states: no consumers yet, ADR-24's fixed input shape.

- [ ] **Step 1: Write the failing test** — construct each model; assert `Finding.model_fields` key order is `("evidence", "detail", "blocking")`.
- [ ] **Step 2: Run to verify failure** — `pytest tests/validators/test_evidence.py -q`
- [ ] **Step 3: Implement the three models.**
- [ ] **Step 4: Run** — `pytest tests/validators/ -q` — PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(validators): ADR-24 evidence schemas (FR-205, no consumers yet)"`

---

### Task 8: Docs, contracts, and FR-205 close-out

**Files:**
- Modify: `src/sdlc/stages/plan/plan.md`, `plan/AGENTS.md` — covers/limits clauses, halt family, `validation.py` removal note, `requirements_digest` memo term
- Modify: `src/sdlc/stages/clarify/clarify.md`, `clarify/AGENTS.md` — evidence-path discard (brownfield, fan-out only), patch id, `repo_path` param
- Modify: `src/sdlc/stages/requirements/AGENTS.md` (+ `requirements.md` if it repeats it) — consumer invariant: "clarify, planner (prompt + memo), plan_check (covers_all)"; legal-import rule unchanged
- Modify: `ROADMAP.md` (FR-205 → `[x]` with evidence; Last-verified cell one sentence), `docs/roadmap/last-verified-log.md` (full entry prepended), `docs/roadmap/agent-architecture-plan.md` (AP-2.3 → `[x]`, note: library + schemas + activity/inline split delivered; factory integration remains AP-2.1's), `ARCHITECTURE.md` (validators row leaves the "Target (plan, not built)" block, §4 table + §14 tree gain `validators/` as-built with the current inventory: `ids_unique`, `deps_resolve`/`dag_acyclic`, `covers_all`, `task_size`, `path_like_tokens`, `paths_exist`; `quote_in_file`/`fragment_was_fetched` stay listed as future)
- Test: `pytest tests/plan/test_plan_slice_contract.py tests/clarify/test_clarify_slice_contract.py tests/requirements/ -q` (the slice-contract tests read these files)

- [ ] **Step 1: Update the three slice contracts + AGENTS.md files** (artifact-boundary rule: same diff as behavior — this task lands with the branch, after Tasks 1–7).
- [ ] **Step 2: Flip the trackers** — ROADMAP, last-verified-log (prepend full entry, refresh the cell to one sentence — never grow the cell), AP-2.3, ARCHITECTURE.md.
- [ ] **Step 3: Full verification**

Run: `pytest -q && ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py`
Expected: all green at the fast tier's known baseline

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/ src/sdlc/stages
git commit -m "docs: close FR-205 — slice contracts, AP-2.3, ARCHITECTURE as-built, last-verified log"
```
