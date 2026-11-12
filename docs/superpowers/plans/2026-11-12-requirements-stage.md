# Requirements Stage (FR-113) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build stage 3 · requirements — an off-by-default Product drafter that proposes story-shaped `Requirements` (code-numbered US/FR/SC) from the idea + target repo, deterministically frozen and fed into clarify as an optional input.

**Architecture:** FR-112 pattern, third application: registry role `agents/product/` whose `build()` attaches read-only `FileSystem` + `RepoContext`; one bounded activity; a pure partial-freeze in workflow code; `default-requirements.graph.yaml` beside the untouched default graph; clarify gains optional object+digest seams (the ONLY consumer — architect/plan untouched).

**Tech Stack:** Python 3.13, Temporal, pydantic-ai-slim 2.61, pydantic-ai-harness 0.61 (FileSystem, RepoContext), pytest.

**Spec:** `docs/superpowers/specs/2026-11-12-requirements-stage-design.md`

## Global Constraints

- `uv run pytest` fast tier: ONLY the 8 pre-existing failures may remain (prompt-SHA pin `test_prompt_migration`, deveval ×3, read-fixtures ×2, todo-api, benchmark-stalled). Verified twice on clean main.
- `ruff check .`, `ruff format .`, `mypy`, `python scripts/check_file_size.py` clean; 1000-line ceiling.
- Cross-stage calls banned; importing the `Requirements` TYPE + `render_requirements` from `stages/requirements/` is legal (producer owns artifacts; `core/` gets only config + role plumbing).
- Wire names, never renamed: activity `draft_requirements`, agent `product_agent`, node type `requirements`, payload `"Requirements"`.
- `default.graph.yaml` byte-identical — sha256 `fec96d09f7813dfb48597f6f6ab52c0f29b5440e6efe359d7bb90fe240ab4684` (already pinned by tests/graph).
- Empty requirements digest = `""` (flag-off byte-identity sentinel); flag-off runs schedule zero new commands, memo keys unchanged.
- Capability order in `build()`: loader-supplied first, role's own after.
- Model calls activity-side only; workflow code deterministic; usage handed back as `RoleUsage(role="product", ...)`.
- `docs/` + contract + slice AGENTS.md land in the same diff as the behavior (artifact boundary rule).

## Review Focus

1. **Empty draft** (zero stories survive): degrade to empty artifact + FAIL-path event, digest `""`, nothing retained — flag-off memo keys unchanged. → T2 `test_freeze_all_dropped_degrades`, T8 `test_flag_off_zero_commands`.
2. **Duplicate FR/SC texts across stories**: global dedup — one survivor, ids renumbered densely, digest stable. → T2 `test_global_dedup_across_stories`.
3. **Brownfield story with missing/whitespace `source_ref`**: dropped with warning; whitespace-only counts as missing (strip semantics — constitution's gotcha fixed here). → T2 `test_brownfield_whitespace_source_ref_dropped`.
4. **Brownfield mode + non-directory `repo_path`**: prompt must take the greenfield line over the scratch tree — never "cite the repo" over an empty workspace (FR-112 T6 fix, pinned from birth). → T6 `test_brownfield_mode_without_repo_never_prompts_for_source_refs`.
5. **Selection precedence with multiple flags on**: research > constitution > requirements, stable and test-pinned; comments must NOT claim a nonexistent explicit-graph-pin mechanism (FR-112 final-review lesson). → T8 precedence test, T9 E2E.

---

### Task 1: Artifact models — `Story`, `Requirements`, draft output, digest

**Files:**
- Create: `src/sdlc/stages/requirements/__init__.py` (empty), `src/sdlc/stages/requirements/models.py`
- Test: `tests/requirements/__init__.py` (empty), `tests/requirements/test_models.py`

**Interfaces:**
- Produces: `FunctionalRequirement(id: str, text: str)`; `SuccessCriterion(id: str, text: str)`; `Story(id: str, narrative: str, functional: list[FunctionalRequirement], success_criteria: list[SuccessCriterion], source_ref: str | None = None)`; `Requirements(stories: list[Story], digest: str, drafted_by: Literal["agent","empty"])`; `DraftStory(narrative: str, functional: list[str], success_criteria: list[str], source_ref: str | None = None)` — NO id fields; `DraftOutput(stories: list[DraftStory])`; `requirements_digest(stories: list[Story]) -> str` — sha256 over JSON-serialized sorted `(narrative, sorted(functional texts), sorted(sc texts))` tuples, `""` for empty. House style: `stages/constitution/models.py`.

- [ ] **Step 1: Write failing tests** — `test_digest_empty_is_sentinel` (`requirements_digest([]) == ""`); `test_digest_stable_and_order_insensitive` (reordered stories + reordered texts within a story → same 64-hex digest); `test_draft_output_has_no_ids` (`"id" not in DraftStory.model_fields` and no id in nested shapes).

- [ ] **Step 2: Run** — `uv run pytest tests/requirements/test_models.py -v` — Expected: FAIL (no module).

- [ ] **Step 3: Implement `models.py`** — plain Pydantic models + digest helper; ids assigned nowhere here.

- [ ] **Step 4: Run** — Expected: PASS.

- [ ] **Step 5: Commit** — `git add src/sdlc/stages/requirements tests/requirements && git commit -m "feat(requirements): artifact models and digest"`

### Task 2: Deterministic verify — partial freeze

**Files:**
- Create: `src/sdlc/stages/requirements/verify.py`
- Test: `tests/requirements/test_verify.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces: `FreezeResult(frozen: Requirements, dropped: list[str], capped: bool, degraded: bool)`; `freeze(draft: DraftOutput, *, mode: Literal["greenfield","brownfield"], max_stories: int | None = None) -> FreezeResult`. Rules (spec §3, exact): drop whitespace-only narratives; drop whitespace-only texts from functional/SC lists; dedup exact-duplicate FR texts and SC texts **globally across the artifact**; drop stories left with zero functional entries; brownfield drops stories whose `source_ref` is missing/whitespace (`not (source_ref or "").strip()`); assign ids in surviving order (`US-1…`, `FR-1…` global, `SC-1…` global); cap at `max_stories` keeping the first (sets `capped=True`); `degraded=True` iff zero stories survive → `Requirements(drafted_by="empty", stories=[], digest="")`; pure, never raises.

- [ ] **Step 1: Write failing tests** — per Review Focus 1–3: `test_freeze_all_dropped_degrades`; `test_global_dedup_across_stories` (two stories share an FR text → one survivor, dense renumber); `test_brownfield_whitespace_source_ref_dropped`; plus `test_greenfield_allows_missing_source_ref`, `test_ids_assigned_global_across_stories`, `test_cap_keeps_first_and_flags`, `test_story_without_functional_dropped`, `test_zero_sc_survives_with_all_stories_intact` (artifact-level SC miss is NOT a drop).

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement `freeze`** — pure; mirror `stages/constitution/verify.py` structure.

- [ ] **Step 4: Run** — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(requirements): deterministic partial-freeze verify"`

### Task 3: Registry role — `agents/product/` + `STAGE_ROLES` mapping

**Files:**
- Create: `agents/product/agent.yaml` (`kind: proposer`, model mirroring research's family), `agents/product/instructions.md` (charter per spec §5), `agents/product/agent.py`, `src/sdlc/stages/requirements/deps.py` (minimal)
- Modify: `src/sdlc/agents/loader.py` (`OPTIONAL_ROLES` + `"product"`), `src/sdlc/agents/roles.py` (`STAGE_ROLES["requirements"] = "product"` with the `# optional; present iff the folder ships` comment; `t_product` alias; conditional `ALL_TEMPORAL_AGENTS` append mirroring `t_research` ~:300)
- Test: `tests/requirements/test_role.py`

**Interfaces:**
- Produces: `RequirementsDeps(BaseModel)` — `run_id: str; mode: Literal["greenfield","brownfield"]; max_stories: int = 8; max_requests: int = 6` (Task 6 may extend, not reshape). `build(model, instructions, model_settings, *, capabilities=()) -> Agent` with `name="product_agent"`, `deps_type=RequirementsDeps`, `output_type=DraftOutput`, `retries={"output": 3}`; own capabilities appended after loader's: `FileSystem(read_only=True, tools=["read_file","search_files","find_files","list_directory"])`, `RepoContext(home_dir=None)` (explicit — FR-112 parked minor not repeated). `resolve_role_model(cfg, "requirements")` works (auto: `STAGE_MODELS` and `PROMPT_SHAS` derive from `STAGE_ROLES ∩ REGISTRY`, roles.py:231, :257).
- NOTE (pins that grow additively, same as FR-112 T5): `OPTIONAL_ROLES` exact set, agent-names map, conftest synthetic registry tree, `PROMPTED_ROLES` (benchmarks/provenance.py), docs role count, `tests/test_stage_models.py` keyspaces (auto). `tests/test_prompt_migration.py` pins `PROMPT_SHAS` and is PRE-EXISTING failing — update its expected data additively so the failure diff gains NO new entries; disclose in the report.

- [ ] **Step 1: Write failing tests** — `test_role_boot`: registry loads, `KNOWN_ROLES` recognizes `product`, `RoleConfig.kind == "proposer"`, `STAGE_ROLES["requirements"] == "product"`, `"requirements" in PROMPT_SHAS`; `test_capabilities_read_only`: `build("fake:test", "charter", {})` agent carries FileSystem(read_only=True, 4 tools) then RepoContext, after loader capabilities.

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** the role dir, loader entry, roles.py entries; charter content per spec §5 (≤ max_stories; brownfield cites exactly one repo-relative path per story; never quote file contents; FR/SC single-sentence testable statements; no numbering in output).

- [ ] **Step 4: Run** — `uv run pytest tests/requirements/test_role.py tests/test_prompt_migration.py -v` — role tests PASS; prompt-migration failure diff unchanged from baseline.

- [ ] **Step 5: Commit** — `git commit -m "feat(requirements): product registry role with FileSystem+RepoContext capabilities"`

### Task 4: Node type + payload + `default-requirements.graph.yaml` + clarify in-port

**Files:**
- Modify: `src/sdlc/graph/node_types.py` (new spec after `context`'s; clarify spec gains one in-port), `src/sdlc/graph/payloads.py` (`PAYLOAD_TYPES["Requirements"]`), `src/sdlc/workflows/graph_catalog.py` (interim `NOT_EXECUTABLE` entry, comment names Task 8 as remover)
- Create: `src/sdlc/workflows/graphs/default-requirements.graph.yaml`
- Test: `tests/graph/test_requirements_node.py`

**Interfaces:**
- Produces: node spec `type="requirements"` (`kind="stage"`, `role="product"`, `canonical_stage="requirements"`, `budget_after="continuing"`, ports exactly: `_in("trigger", None, required=False)`, `_in("constitution", "Constitution", required=False)`, `_in("codebase_map", "CodebaseMap", required=False)`, `_out("requirements", "Requirements")`, `_fail()` — no reject). Clarify spec += `_in("requirements", "Requirements", required=False)`. Graph = `default.graph.yaml` byte-for-byte ⊕ node `{id: requirements, type: requirements}` ⊕ 3 edges: `intake.ok → requirements.trigger`, `intake.brownfield → requirements.trigger`, `requirements.requirements → clarify.requirements`.

- [ ] **Step 1: Write failing tests** — catalog contains the type with exactly those ports; all graph yamls (4) load + topology-validate; sha pin of `default.graph.yaml` still green; new graph carries the 3 edges; namespace pin (`"requirements"` as node type coexists with clarify's out-port named `requirements`); `PAYLOAD_TYPES` maps `"Requirements"`.

- [ ] **Step 2: Run** — Expected: FAIL (unknown node type).

- [ ] **Step 3: Implement** spec entry, in-port, payload mapping, graph yaml, interim `NOT_EXECUTABLE`; regenerate `catalog.json` and grow the chaos pin `set(NOT_EXECUTABLE)` additively — both per FR-112 T4's amended scope.

- [ ] **Step 4: Run** — `uv run pytest tests/graph -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(requirements): node type, payload, clarify in-port, default-requirements graph"`

### Task 5: Config — `RequirementsConfig` + required `project_cfg` kwarg + dispatch wiring

**Files:**
- Modify: `src/sdlc/core/models.py` (`RequirementsConfig` beside `ConstitutionConfig`; `PipelineConfig.requirements: RequirementsConfig = Field(default_factory=RequirementsConfig)`; `requirements_enabled: bool = False` beside `constitution_enabled`)
- Modify: `src/sdlc/workflows/graph_nodes/base.py` (`graph_has_requirements` helper + `project_cfg` REQUIRED kwarg `requirements_in_graph` — research's required shape, NOT constitution's defaulted bridge), `src/sdlc/workflows/graph_dispatch.py` (pass `requirements_in_graph=graph_has_requirements(graph)` at the single `project_cfg` call site ~:236)
- Test: `tests/requirements/test_config.py`

**Interfaces:**
- Produces: `RequirementsConfig(enabled: bool = False, max_stories: int = 8, max_requests: int = 6)`; off-by-default everywhere; presence overlay true only under the new graph.

- [ ] **Step 1: Write failing tests** — defaults; `requirements={"enabled": True}` + `default-requirements` graph → `project_cfg(...).requirements_enabled is True`; same cfg + default graph → `False`; `project_cfg` missing the kwarg → `TypeError` (required, pinned).

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** mirroring the research lines; dispatch wiring lands in the same task (required kwarg breaks the caller otherwise).

- [ ] **Step 4: Run** — `uv run pytest tests/requirements tests/graph -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(requirements): RequirementsConfig with required graph-presence overlay"`

### Task 6: `draft_requirements` activity

**Files:**
- Create: `src/sdlc/stages/requirements/stage.py`
- Test: `tests/requirements/test_stage.py`

**Interfaces:**
- Consumes: Task 3 agent (registry), Task 1 models.
- Produces: `DraftInput(idea_json: str, repo_path: str | None, deps: RequirementsDeps, model: str)`; `@activity.defn async def draft_requirements(inp) -> _DraftResult(draft: DraftOutput, usage: RoleUsage)` with `RoleUsage(role="product", model=inp.model, cost_usd=None)`. Workspace: ONE predicate `_repo_workspace(inp)` decides both the workspace (repo dir, else scratch `$SDLC_RUNS_ROOT/<run_id>/requirements/` created by the activity) and the prompt's mode line (FR-112 T6 fix from birth); `deps.mode` untouched by the prompt. `UsageLimitExceeded` → empty `DraftOutput`, never raise; other exceptions propagate. Model forwarding D7a. TestModel tools individually callable; no CodeMode. Pattern: `stages/constitution/stage.py`.

- [ ] **Step 1: Write failing tests** — `test_greenfield_workspace_falls_back_to_scratch`; `test_usage_handed_back` (`role=="product"`); `test_brownfield_mode_without_repo_never_prompts_for_source_refs` (positive control for the repo branch); `test_max_requests_bound` (TestModel exceeding requests → empty draft, no raise); `test_source_ref_is_path_only` (every draft `source_ref` matches `^[A-Za-z0-9_./-]+$`).

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** `stage.py`; single retry layer comes from the loader capability — do not re-add.

- [ ] **Step 4: Run** — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(requirements): draft_requirements activity with bounded read-only run"`

### Task 7: Clarify downstream seams — memo digest + prompt render

**Files:**
- Create: `render_requirements` in `src/sdlc/stages/requirements/prompts.py`
- Modify: `src/sdlc/stages/clarify/step.py` (kwargs beside `constitution`/`constitution_digest` at ~:125-126; render insertion beside ~:165; TYPE_CHECKING imports beside ~:39-40; memo-key threading beside the constitution digest)
- Test: `tests/requirements/test_prompt_render.py`, extend `tests/clarify/test_clarify_memo_key.py`

**Interfaces:**
- Produces: `render_requirements(c: Requirements, *, max_chars: int = 2000) -> str` (one `US-n` line per story with nested `FR-n`/`SC-n` lines; whole-line-first truncation; empty → `""`); clarify step kwargs `requirements: Requirements | None = None`, `requirements_digest: str = ""`, omitted while at default in memo/`content_key` serialization (FR-010). Prompt order: idea → constitution → **requirements** → codebase map → recall.

- [ ] **Step 1: Write failing tests** — `test_memo_key_empty_equals_flag_off` (digest `""` → byte-identical key); `test_memo_key_digest_flips`; `test_render_truncates_and_empty_renders_empty`; ordering pin: requirements block renders between constitution and map blocks.

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** the helper + kwargs; conditional prompt inclusion (`""`-concat identity) exactly as the constitution seam does it.

- [ ] **Step 4: Run** — `uv run pytest tests/requirements tests/clarify -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(requirements): clarify memo digest and bounded prompt render"`

### Task 8: Step + handler + interim removal + selection wiring

**Files:**
- Create: `src/sdlc/stages/requirements/step.py`
- Modify: `src/sdlc/workflows/graph_nodes/precode.py` (requirements handler; pass `requirements` object + `requirements_digest=req.digest` from the SAME payload into the clarify handler inputs), `src/sdlc/workflows/graph_nodes/__init__.py` (HANDLERS entry), `src/sdlc/stages/__init__.py` (STAGE_MODULES — mirror constitution's entries), `src/sdlc/workflows/graph_catalog.py` (remove interim `NOT_EXECUTABLE`; `SHIPPED_NAMES` += `"default-requirements"`; `select_graph` branch AFTER constitution's: `if cfg.requirements_enabled and "product" in roles_map: return SHIPPED["default-requirements"]` — comment states precedence research > constitution > requirements and must NOT claim an explicit-pin mechanism)
- Test: `tests/requirements/test_step.py`, extend chaos/catalog pins

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces: `async def step(ctx: StageContext, *, cfg: PipelineConfig, idea: IdeaBrief, repo_path: str | None) -> Requirements` — NO agent param (FR-112 fix-wave precedent). Flag off → `Requirements(drafted_by="empty", stories=[], digest="")`, zero activities, no `ctx.gate`. Flag on → `workflow.execute_activity(draft_requirements, DraftInput(idea_json=..., repo_path=..., deps=RequirementsDeps(run_id=..., mode=idea.mode, max_stories=cfg.requirements.max_stories, max_requests=cfg.requirements.max_requests), model=resolve_role_model(cfg, "requirements")))` → `freeze(draft, mode=inp.deps.mode, max_stories=cfg.requirements.max_stories)` → price usage → STAGE_ENDED direct via `ctx.emit` + warning when `dropped`/`capped` + FAIL-path event when degraded (nothing retained) → else `ctx.retain`. Slice exports `step`, `ACTIVITIES = [draft_requirements]`. Optional constitution/codebase_map payloads rendered into the drafter prompt when present (dead in the shipped graph — composed graphs' seam).

- [ ] **Step 1: Write failing tests** — `test_flag_off_zero_commands` (default graph, golden command projection unchanged; no `draft_requirements` scheduled); `test_flag_on_partial_freeze` (one grounded + one ungrounded brownfield story → 1 frozen, warning); `test_degraded_emits_fail`; `test_cap_warns`; precedence: research+requirements flags both on → `default-research`; requirements alone → `default-requirements`; `set(NOT_EXECUTABLE)` re-pinned without `"requirements"`.

- [ ] **Step 2: Run** — Expected: FAIL.

- [ ] **Step 3: Implement** step + handler + registrations + selection; usage pricing mirrors constitution's step.

- [ ] **Step 4: Run** — `uv run pytest tests/requirements tests/graph tests/graph_workflow -q` (fast-scope) — Expected: PASS except nothing new.

- [ ] **Step 5: Commit** — `git commit -m "feat(requirements): workflow step, handler, and graph selection wiring"`

### Task 9: E2E temporal test

**Files:**
- Test: `tests/graph_workflow/test_requirements_e2e.py` (mirror `test_constitution_e2e.py`'s harness)

**Interfaces:**
- Consumes: Task 8's full wiring.

- [ ] **Step 1: Write the test** — `default-requirements` graph, flag on, fake model: run completes `deployed:`; exactly one `draft_requirements` activity; `stage_ended` pass for requirements; Requirements retained; digest-salted clarify memo key PRESENT and digest-less key ABSENT (constitution E2E assertions, re-derived via production helpers).

- [ ] **Step 2: Run** — `uv run pytest -m temporal tests/graph_workflow/test_requirements_e2e.py -v` — Expected: PASS. Then `-m temporal tests/graph_workflow` whole scope green.

- [ ] **Step 3: Commit** — `git commit -m "test(requirements): flag-on E2E over default-requirements graph"`

### Task 10: Docs, same diff

**Files:**
- Create: `src/sdlc/stages/requirements/requirements.md` (numbered clauses: artifact shape, digest sentinel, freeze rules incl. whitespace source_ref + cap + global dedup, flag + graph presence, workspace resolution + mode-line-from-workspace, capability set, ports, clarify-only seam, STAGE_ENDED-direct decision), `src/sdlc/stages/requirements/AGENTS.md` (mirror constitution slice AGENTS.md structure)
- Modify: `PRD.md` (FR-113 row per spec §10 text), `SDLC-spec-v2.md` (§1 row 3 owner cell → `Product *(optional; off by default — FR-113)*`), `ROADMAP.md` (§1 stage-3 line → `[x]` landed-pointer; **15 of 15**; FR-101 → `[x]`; FR-113 row; Last verified one-sentence cell + full entry prepended to `docs/roadmap/last-verified-log.md`), `README.md` (roles table +1 proposer; reconcile the 16-vs-table count prose)
- Test: one `@pytest.mark.clause` test in `tests/requirements/test_step.py` citing a numbered `requirements.md` clause (freeze behavior)

- [ ] **Step 1: Write the failing clause test** — cite `REQUIREMENTS-<n>` for the partial-freeze rules; assert against `freeze` behavior.

- [ ] **Step 2: Run** — Expected: FAIL (file missing).

- [ ] **Step 3: Write the docs** — clauses match shipped behavior exactly; no aspiration.

- [ ] **Step 4: Verify** — `uv run pytest tests/requirements -q`; `python scripts/check_file_size.py`; `ruff check . && ruff format --check . && mypy`; `uv run pytest -m temporal tests/graph_workflow -q`.

- [ ] **Step 5: Commit** — `git commit -m "docs(requirements): contract, slice rules, FR-113 PRD/spec/ROADMAP updates"`

---

## Self-Review (done)

1. **Spec coverage:** artifact+digest (T1), freeze rules incl. cap/global-dedup/whitespace-ref (T2), role+capabilities+STAGE_ROLES/PROMPT_SHAS (T3), node/payload/graph/clarify-port/interim (T4), config+required overlay+dispatch (T5), activity+mode-line-from-workspace (T6), clarify-only seam+render+byte-identity (T7), step/handler/selection/precedence/interim-removal (T8), E2E (T9), docs+clause (T10). Follow-ups (clarify split, FR-106 re-root, combined graphs) are spec non-goals — correctly absent.
2. **Step scan:** each step one action with a checkable result; FR-112's ordering lessons baked in (role before node type; config after graph; clarify seams before handler; selection+E2E at birth).
3. **Type consistency:** `Requirements`/`DraftOutput`/`freeze`/`render_requirements`/`requirements_digest`/`RequirementsDeps`/`draft_requirements`/`product_agent` consistent across tasks; `resolve_role_model(cfg, "requirements")` (stage key) vs `RoleUsage(role="product")` (role key) pinned in T3/T6.
4. **Review Focus:** all five lines carry owning tests (T2/T6/T8/T9).
5. **Proportion:** 10 tasks ≈ FR-112's shape; signatures and test names only, no transcripted bodies.
