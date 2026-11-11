# Constitution Stage (FR-112) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build stage 1 · constitution — an off-by-default agent drafter that proposes governing principles from the target repo, deterministically validated and frozen as a `Constitution` artifact consumed by clarify/architect/planner.

**Architecture:** Research-stage pattern (FR-107): a registry role `agents/constitution/` whose `agent.py build()` attaches read-only `FileSystem` + `RepoContext` capabilities; one activity runs it; a pure `verify` does the partial freeze in workflow code; a new `default-constitution.graph.yaml` adds the node without touching `default.graph.yaml` (byte-identical replays).

**Tech Stack:** Python 3.13, Temporal, pydantic-ai-slim 2.61, pydantic-ai-harness 0.61 (FileSystem, RepoContext), pytest.

**Spec:** `docs/superpowers/specs/2026-11-11-constitution-stage-design.md`

## Global Constraints

- `pytest` default run must stay green (fast unit tier); temporal tests opt-in via `pytest -m temporal`.
- `ruff check .`, `ruff format .`, `mypy` clean; 1000-line file ceiling (`scripts/check_file_size.py`).
- Cross-stage calls banned; the constitution slice owns its artifacts; `core/` gets only config + role plumbing.
- Activity and agent names are Temporal wire contracts — once named, never renamed (`constitution_agent`, `draft_constitution`).
- `default.graph.yaml` must remain byte-identical (pin by sha in a test); empty constitution digests to `""` (research ungrounded sentinel); flag-off/default runs schedule zero new commands and leave every memo key unchanged.
- Capability order in `build()`: loader-supplied `capabilities` first, role's own after (`agents/research/agent.py` 003 contract).
- Stage agents run activity-side only; workflow code stays deterministic; usage handed back as `RoleUsage(role="constitution", ...)` priced by the workflow.
- Docs land in the same diff as the code they describe (artifact boundary rule).

## Review Focus

1. **Empty draft** (model returns zero principles): partial freeze of nothing → empty constitution, FAIL recorded, digest `""` — downstream memo keys must not change vs flag-off. → Task 2 test `test_freeze_all_dropped_degrades`, Task 8 test `test_memo_key_empty_equals_flag_off`.
2. **Duplicate statements / model-assigned ids**: the model returns near-duplicates or its own ids — code assigns ids (`CP-1`…), verify dedupes identical statements. → Task 2 test `test_ids_assigned_and_duplicates_dropped`.
3. **Brownfield principle without `source_ref`**: dropped with a warning, survivors frozen. → Task 2 test `test_brownfield_missing_source_ref_dropped`.
4. **Secret-file reads**: FileSystem denies secrets by default; a `source_ref` is a path string only — no file content may enter the artifact. → Task 5 test `test_read_only_and_secret_denial`, Task 6 test `test_source_ref_is_path_only`.
5. **Greenfield with no repo**: FileSystem requires a workspace at run start — the run resolves `repo_path` when it exists, else a guaranteed-existing scratch dir; the agent then drafts from the idea alone. → Task 6 test `test_greenfield_workspace_falls_back_to_scratch`.

---

### Task 1: Artifact models — `Principle`, `Constitution`, draft output

**Files:**
- Create: `src/sdlc/stages/constitution/__init__.py` (empty), `src/sdlc/stages/constitution/models.py`
- Test: `tests/constitution/__init__.py` (empty), `tests/constitution/test_models.py`

**Interfaces:**
- Produces: `Principle(id: str, statement: str, normative: Literal["MUST","SHOULD"], rationale: str, source_ref: str | None)`; `Constitution(principles: list[Principle], digest: str, drafted_by: Literal["agent","empty"])`; `DraftOutput(principles: list[DraftPrinciple])` where `DraftPrinciple(statement, normative, rationale, source_ref)` carries NO id (ids assigned by code, `_PlannerOutput` precedent); `constitution_digest(principles) -> str` — sha256 over sorted `(statement, normative)` pairs, `""` for an empty list.

- [ ] **Step 1: Write failing tests**

```python
# tests/constitution/test_models.py
def test_digest_empty_is_sentinel():
    assert constitution_digest([]) == ""

def test_digest_stable_and_order_insensitive():
    a = constitution_digest([p("A"), p("B")]); b = constitution_digest([p("B"), p("A")])
    assert a == b and len(a) == 64

def test_draft_output_has_no_ids():
    # DraftPrinciple must not carry an id field — ids are code-assigned.
    assert "id" not in DraftPrinciple.model_fields
```

(`p()` builds a `DraftPrinciple` with valid MUST statement.)

- [ ] **Step 2: Run, expect import failure**

Run: `pytest tests/constitution/test_models.py -v` — Expected: FAIL (no module `sdlc.stages.constitution`).

- [ ] **Step 3: Implement `models.py`** — plain Pydantic models + `constitution_digest`; ids assigned nowhere here (Task 2 does it).

- [ ] **Step 4: Run tests** — `pytest tests/constitution/test_models.py -v` — Expected: PASS.

- [ ] **Step 5: Commit** — `git add src/sdlc/stages/constitution tests/constitution && git commit -m "feat(constitution): artifact models and digest"`

### Task 2: Deterministic verify — partial freeze

**Files:**
- Create: `src/sdlc/stages/constitution/verify.py`
- Test: `tests/constitution/test_verify.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces: `FreezeResult(frozen: Constitution, dropped: list[str], degraded: bool)`; `freeze(draft: DraftOutput, *, mode: Literal["greenfield","brownfield"]) -> FreezeResult`. Rules: assign ids `CP-1…` in order; drop brownfield items with empty `source_ref`; drop exact-duplicate `statement`s; `degraded=True` iff zero principles survive (then `drafted_by="empty"`, digest `""`, FAIL noted by caller); never raises on model noise.

- [ ] **Step 1: Write failing tests** — `test_brownfield_missing_source_ref_dropped` (2 principles, 1 without ref → 1 frozen, dropped names it), `test_greenfield_allows_missing_source_ref`, `test_ids_assigned_and_duplicates_dropped` (duplicate statements → one survivor), `test_freeze_all_dropped_degrades` (digest `""`, `drafted_by="empty"`, `degraded=True`).

- [ ] **Step 2: Run** — `pytest tests/constitution/test_verify.py -v` — Expected: FAIL (no `verify`).

- [ ] **Step 3: Implement `freeze`** — pure function, no I/O; `Constitution` built from survivors.

- [ ] **Step 4: Run** — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(constitution): deterministic partial-freeze verify"`

### Task 3: Config flag — `ConstitutionConfig` + graph-presence overlay

**Files:**
- Modify: `src/sdlc/core/models.py` (beside `ResearchConfig` ~:274 and `research_enabled` ~:391)
- Modify: `src/sdlc/workflows/graph_nodes/base.py` (`project_cfg` ~:129-142)
- Test: `tests/core/test_constitution_config.py` (extend an existing core/graph test module if one is more natural)

**Interfaces:**
- Produces: `class ConstitutionConfig(BaseModel): enabled: bool = False; max_principles: int = 12; max_requests: int = 6`; `PipelineConfig.constitution_enabled: bool = False` (comment cites FR-112, off by default); `project_cfg(...)` overlay adds `constitution_in_graph` → `constitution_enabled`, mirroring the research line exactly.

- [ ] **Step 1: Write failing tests** — default config has `constitution_enabled is False`; `ConstitutionConfig()` defaults `(False, 12, 6)`; a cfg with `constitution={"enabled": True}` and a graph containing a `constitution` node yields `project_cfg` with `constitution_enabled=True`; same cfg with the default graph yields `False`.

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** — mirror the `ResearchConfig`/`research_enabled`/`project_cfg` lines; no behavior beyond the flag.

- [ ] **Step 4: Run** — Expected: PASS; also `pytest tests/graph -q` (project_cfg consumers).

- [ ] **Step 5: Commit** — `git commit -m "feat(constitution): ConstitutionConfig and graph-presence flag"`

### Task 4: Node type + `default-constitution.graph.yaml` + downstream in-ports

**Files:**
- Modify: `src/sdlc/graph/node_types.py` (catalog: constitution spec after `context` ~:118; add `_in("constitution", "Constitution", required=False)` to clarify ~:144, architect ~:157, and the plan node type — find `type="plan"` spec)
- Create: `src/sdlc/workflows/graphs/default-constitution.graph.yaml`
- Test: `tests/graph/test_constitution_node.py`

**Interfaces:**
- Produces: node type `constitution` (`kind="stage"`, `role="constitution"`, `canonical_stage="constitution"`, `budget_after="continuing"`, ports: `_in("trigger", None, required=False)`, `_out("constitution", "Constitution")`, `_fail()`); graph = `default.graph.yaml` + node `{id: constitution, type: constitution}` + edges `intake.ok → constitution.trigger`, `intake.brownfield → constitution.trigger`, `constitution.constitution → clarify.trigger`… wait — clarify's trigger is fed by intake today; constitution feeds the NEW optional `constitution` in-ports: `constitution.constitution → clarify.constitution`, `→ architect.constitution`, `→ plan.constitution`.

- [ ] **Step 1: Write failing tests** — catalog contains the type with those ports; every graph yaml (all three + new) loads and passes topology validation; sha256 of `default.graph.yaml` equals the pre-branch value (pin the literal — get it via `sha256sum` in Task 4 step 0 and paste); the new graph's clarify/architect/plan receive constitution edges.

- [ ] **Step 2: Run** — Expected: FAIL (unknown node type).

- [ ] **Step 3: Implement** the spec entry, in-ports, and the yaml (copy default, insert node + 5 edges: 2 in from intake, 3 out to clarify/architect/plan).

- [ ] **Step 4: Run** — `pytest tests/graph -q` — Expected: PASS, including the sha pin.

- [ ] **Step 5: Commit** — `git commit -m "feat(constitution): node type, in-ports, default-constitution graph"`

### Task 5: Registry role — `agents/constitution/`

**Files:**
- Create: `agents/constitution/agent.yaml` (`kind: constitution` dir; role file fields mirroring `agents/research/agent.yaml`: model + note), `agents/constitution/instructions.md`, `agents/constitution/agent.py`
- Modify: `src/sdlc/agents/loader.py` (`OPTIONAL_ROLES` + "constitution"), `src/sdlc/agents/roles.py` (`t_constitution`, appended to `ALL_TEMPORAL_AGENTS` conditionally like `t_research` ~:300)
- Test: `tests/test_agent_capabilities.py` (extend) or `tests/constitution/test_role.py`

**Interfaces:**
- Consumes: `ConstitutionDeps` (Task 6 defines it — this task may import from the slice; if preferred, define `deps.py` first here and let Task 6 consume).
- Produces: `build(model, instructions, model_settings, *, capabilities=()) -> Agent` with `name="constitution_agent"`, `deps_type=ConstitutionDeps`, `output_type=Constitution` (draft shape wrapped per Task 1), `retries={"output": 3}`, own capabilities appended after loader's: `FileSystem(read_only=True, tools=["read_file","search_files","find_files","list_directory"])`, `RepoContext()` (defaults; no `home_dir` walk-up — pass `home_dir=None`). Instructions charter: propose ≤ `max_principles`, every brownfield principle cites one `source_ref` path, never quote file contents.

- [ ] **Step 1: Write failing tests** — `test_read_only_and_secret_denial`: construct via `build("fake:test", "charter", {})`, assert the agent's capability list contains FileSystem with `read_only=True` and RepoContext, in that order after loader caps; `test_optional_role_boot`: registry loads with the role present, `KNOWN_ROLES` recognizes it, `RoleConfig.kind == "proposer"`.

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** the role dir, loader entry, and roles.py wiring; `agent.yaml` model = same registry model family rules (must differ from reviewer families — `validate_registry` at boot enforces; pick the same base model research uses).

- [ ] **Step 4: Run** — `pytest tests/constitution/test_role.py tests/test_agent_capabilities.py -v` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(constitution): registry role with FileSystem+RepoContext capabilities"`

### Task 6: Deps + `draft_constitution` activity

**Files:**
- Create: `src/sdlc/stages/constitution/deps.py`, `src/sdlc/stages/constitution/stage.py`
- Test: `tests/constitution/test_stage.py`

**Interfaces:**
- Consumes: Task 5 agent (injected via input for tests), Task 1 models.
- Produces: `ConstitutionDeps(BaseModel)`: `run_id: str`, `mode: Literal["greenfield","brownfield"]`, `max_principles: int`, `max_requests: int`; `DraftInput(idea_json: str, repo_path: str | None, deps: ConstitutionDeps, model: str)`; `@activity.defn async def draft_constitution(inp: DraftInput) -> Constitution` (plus `_DraftResult` carrying `RoleUsage` if the repo pattern wraps returns — mirror `SubQuestionInput`/return shape): resolves workspace (`LocalWorkspace(repo_path)` if it exists, else the run scratch dir under `$SDLC_RUNS_ROOT/runs/<run_id>/` created first), runs `constitution_agent` with `usage=RunUsage()` and `UsageLimits(requests=inp.deps.max_requests)`, assigns ids? No — returns the raw `DraftOutput` inside `Constitution`-adjacent wrapper for Task 7's freeze; hands usage back as `RoleUsage(role="constitution", model=inp.model, cost_usd=None)`.

- [ ] **Step 1: Write failing tests** (TestModel, tools callable directly — no CodeMode): `test_greenfield_workspace_falls_back_to_scratch` (repo_path missing → scratch dir used, run succeeds); `test_usage_handed_back` (RoleUsage fields populated); `test_source_ref_is_path_only` (returned artifact fields contain no file contents — assert every `source_ref` matches `^[A-Za-z0-9_./-]+$`); `test_max_requests_bound` (TestModel exceeding requests raises UsageLimitExceeded → activity degrades to empty draft, not raise).

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** `deps.py` + `stage.py`; single retry layer comes from the loader-supplied capability (Task 5), not re-added here.

- [ ] **Step 4: Run** — `pytest tests/constitution/test_stage.py -v` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(constitution): draft_constitution activity with bounded read-only run"`

### Task 7: Step + graph handler wiring

**Files:**
- Create: `src/sdlc/stages/constitution/step.py`
- Modify: `src/sdlc/workflows/graph_nodes/precode.py` (constitution handler; pass `constitution` + `constitution_digest` into the clarify/architect/plan handler inputs, `brief_digest` precedent ~:112-118)
- Modify: `src/sdlc/stages/constitution/AGENTS.md`-adjacent slice exports (define `ACTIVITIES = [draft_constitution]`)
- Test: `tests/constitution/test_step.py`, extend `tests/graph_workflow/` flag-off case

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: `async def step(ctx: StageContext, *, cfg: PipelineConfig, idea: IdeaBrief, repo_path: str | None, agent) -> Constitution` — flag off → `Constitution(drafted_by="empty", principles=[], digest="")` with ZERO activities scheduled; flag on → `draft_constitution` activity → `freeze()` in workflow code → emit `STAGE_ENDED` (+warning when principles dropped; FAIL event when degraded) → `ctx.retain`.

- [ ] **Step 1: Write failing tests** — `test_flag_off_zero_commands`: default graph run with constitution node absent; golden command projection unchanged vs a pinned fixture (or assert no `draft_constitution` activity call via a fake host); `test_flag_on_partial_freeze_path`: fake agent returns one grounded + one ungrounded principle (brownfield) → 1 frozen, warning emitted; `test_degraded_emits_fail`.

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** step + handler; register `ACTIVITIES` in the slice; `project_cfg` (Task 3) gates.

- [ ] **Step 4: Run** — `pytest tests/constitution tests/graph_workflow -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(constitution): workflow step with partial-freeze semantics and graph wiring"`

### Task 8: Downstream seams — memo digest + prompt render

**Files:**
- Modify: `src/sdlc/stages/clarify/step.py`, `src/sdlc/stages/architecture/step.py`, `src/sdlc/stages/plan/step.py` (accept `constitution_digest: str = ""`, thread into their `_cached_stage`/`content_key` inputs — follow how `brief_digest` threads today)
- Modify: prompt assembly in those three slices to render a bounded constitution block via new helper `render_constitution(c: Constitution, *, max_chars: int = 2000) -> str` (create in `src/sdlc/stages/constitution/prompts.py`; empty → `""`), ordered idea → constitution → codebase map → recall.
- Test: `tests/constitution/test_prompt_render.py`, one memo test per consumer slice (extend their existing memo tests)

**Interfaces:**
- Consumes: `Constitution` (Task 1).
- Produces: `render_constitution(...)`; the three steps' new optional kwarg.

- [ ] **Step 1: Write failing tests** — `test_memo_key_empty_equals_flag_off` (digest `""` leaves the memo key byte-identical to today — the kwarg default and omit-from-serializer pattern from `ResearchDeps.research_model` applies); digest change flips the key; render truncates at `max_chars`, empty constitution renders `""`.

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** the helper + kwarg threading; serializer omits `constitution_digest` while `""` (FR-010 byte-identity).

- [ ] **Step 4: Run** — `pytest tests/clarify tests/architecture tests/plan tests/constitution -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(constitution): downstream memo digest and bounded prompt render"`

### Task 9: Docs, same diff — contract, slice rules, PRD/spec/ROADMAP

**Files:**
- Create: `src/sdlc/stages/constitution/constitution.md` (numbered clauses: artifact shape, partial-freeze semantics, flag, digest sentinel, capability set, in/out ports), `src/sdlc/stages/constitution/AGENTS.md` (invariants, `ACTIVITIES`, passthrough set, Temporal notes — mirror `stages/intake/AGENTS.md` + `stages/research/AGENTS.md` structure)
- Modify: `PRD.md` (FR-112 row in FR-100 table), `SDLC-spec-v2.md` §1 row 1 → `(deterministic + optional drafter)`, `ROADMAP.md` (§1 stage-1 line; FR-101 note; FR-112 row; Last verified cell + `docs/roadmap/last-verified-log.md`), `README.md` roles table (+1 proposer)
- Test: extend `tests/constitution/test_step.py` with one `clause`-marker test citing a numbered constitution.md clause (repo has a `clause` pytest marker)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the clause-citing failing test** — e.g. `@pytest.mark.clause` asserting partial-freeze behavior matches clause N of `constitution.md` (parse the md for the clause or assert on a quoted sentence).

- [ ] **Step 2: Run** — Expected: FAIL (file missing).

- [ ] **Step 3: Write the docs** — contract clauses must match shipped behavior exactly (verification steps, digest sentinel, degradation); PRD row text: `FR-112 (new scope) constitution drafter — off by default; read-only FileSystem+RepoContext; deterministic partial freeze; Constitution artifact feeds clarify/architect/plan`.

- [ ] **Step 4: Verify** — `pytest tests/constitution -q`; `python scripts/check_file_size.py`; `ruff check . && ruff format --check . && mypy`; `pytest -m temporal tests/graph_workflow -q` if the temporal tier is runnable locally.

- [ ] **Step 5: Commit** — `git commit -m "docs(constitution): contract, slice rules, FR-112 PRD/spec/ROADMAP updates"`

---

## Self-Review (done)

1. **Spec coverage:** artifact (T1), partial freeze (T2), flag (T3), node+graph (T4), role+capabilities (T5), activity (T6), step/semantics (T7), downstream seams (T8), docs (T9). Greenfield, budget bound, usage pricing, wire names — covered. The spec's "repo charters the drafter" prompt-quality item stays in `instructions.md` (T5) — content is builder judgment, structure is pinned.
2. **Step scan:** each step names one action with a checkable result; bodies left to the implementer except where the spec pins values.
3. **Type consistency:** `Constitution`/`DraftOutput`/`freeze`/`render_constitution`/`constitution_digest` names match across tasks; `ConstitutionDeps` defined in T6 but consumed by T5's `build()` — noted in T5 Interfaces that deps may be defined first if the import order bites.
4. **Review Focus:** all five lines carry their tests in T2/T5/T6/T8.
5. **Proportion:** 9 tasks for a stage slice ≈ the research stage's shape; no transcripted bodies.
