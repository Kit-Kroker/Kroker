# Roadmap update: absorbing the 2026-09-11 external platform analysis (design)

| | |
|---|---|
| Date | 2026-09-11 |
| Status | Reviewer-approved (r1: `.workspace/tmp/reviewer-roadmap-2026-09-11-r1.md`, one count correction applied). **User gate passed 2026-09-11**; all five open questions ruled as recommended (§10) |
| Phase | herd-plan, planner seat. Deliverable is a **docs-only** change; no product code |
| Base | `main` @ `5534b16` |
| Input | The third source, a verbatim capture of a third-party analysis of Kroker (a ChatGPT conversation the user supplied, in Russian), at `.workspace/tmp/2026-09-11-external-platform-analysis.md` (gitignored; see OQ-4). Ten candidate directions plus a DESIGN / EXECUTE / EVALUATE / OPTIMIZE product framing |
| Consulted | advisor: `.workspace/tmp/advisor-roadmap-1.md`, `advisor-roadmap-2.md` (consensus on every point below); reviewer pre-review: `.workspace/tmp/reviewer-roadmap-2026-09-11.md` |
| Convention | Every claim below was checked against files on `main`, not taken from the brief. "**Designed**" means an unbuilt roadmap design; "**built**" means code on `main`. Real paths only |

## 1. Recommendation

1. **Record the third source in the existing register** (`docs/reports/external-ideas-2026-09.md`) as a new section **H. Platform direction**, rows H1–H10. No new roadmap group file, no new E-numbers, nothing admitted to scope. The register stays the user's roadmap input, as its header says.
2. **Of the ten candidates:** two are already *designed but unbuilt* (E-72…E-76), five *extend* built mechanisms, one is *new* (subflows), one is *new and not recommended* (dynamic model routing), and one is a *product decision* (self-optimizing workflows).
3. **The most actionable finding is not in the analysis.** The dashboard's run-detail and inbox views are "implemented in Plan 2" stubs that no plan ever filled. ROADMAP marks FR-601 `[x]`, but only the fleet view is real. Run replay (H5) and the evidence view (H4) land on a page that does not exist yet, and building it needs none of E-72…E-77. Ranked first.
4. **Section 14 (E-72…E-77)**, the analysis's top pick: **do not sequence it in this phase.** Record the analysis as priority pressure and state three prerequisites: a PRD line for FR-1200, OQ-10 settled, and P2's exit demonstrated. This is the user's call (OQ-1).
5. **Fix six tracker defects** that the verification exposed, in the same docs change (§4).

## 2. What the verification changed

| Brief hypothesis | Verified result |
|---|---|
| E-72…E-74 cover FlowSpec (#2), E-76 covers the builder (#1) | **Confirmed as design only.** `src/sdlc/graph/` does not exist; `PipelineGraph`/`GraphRouter`/`GraphWorkflow` have 0 hits in `src/` and `tests/`. FR-1200…FR-1206 have **no PRD line** (0 `FR-12xx` in `PRD.md`), and ROADMAP §2 has no FR-1200 block. |
| Subflows (#7) may or may not fit that model | Not designed. **Expressible** as a subgraph node type; the 2026-08-06 decision rejected composite nodes as the *branching* primitive, not a subgraph node. |
| Benchmark lab (#3) overlaps E-30…E-39; the new part may be the experiment object | Narrower than hypothesised: an `Experiment` model **already exists** (`src/sdlc/benchmarks/experiments.py`). What is new is a declared, launched experiment matrix; a Pareto view; and a workflow axis. |
| Evidence UI (#4) overlaps FR-106/FR-803/E-51/E-52; the new part is a matrix UI | **Corrected.** E-51/E-52 are unbuilt (`[ ]`, FR-918/FR-921) and belong to the *assessment* product. The feature-run chain has a **data gap**: no per-criterion outcome is recorded, so the UI cannot come first. |
| Run replay (#5) vs FR-704/E-22/E-23/E-38/E-75 | The data exists; **the view is a stub**; ROADMAP's FR-704 row is stale. |
| Simulation (#6) vs E-73 `validate.py` + FR-701 | E-73 is unbuilt, so the structural half today is F2 `sdlc doctor`. The forecast is new and has a hard bound (the planner decides the task count). |
| Policy engine (#8) vs GateConfig and G1 | Lands on the open register rows **B1 + B3**; one clause is blocked on identity. |
| Router (#9) vs per-role models and sweeps | As hypothesised: the static half is built; dynamic routing is new. |
| Self-optimization (#10) vs F3 and E-4 | Conflicts with a recorded stance (BENCHMARK §0, `experiments.py`); F3 is the compatible form. |
| Brief path `docs/BENCHMARK.md` | **Wrong.** The file is root `BENCHMARK.md`. `docs/BENCHMARK.md` has never existed (the B0 plan recorded this and fixed AGENTS.md only). |
| Reviewer pre-review line counts (ROADMAP 446, register 115, largest group file 387) | **Wrong.** The authority (`scripts/check_file_size.py:75`, newline count) gives 512, 143 and 421 (`filesystem-first.md`). |

## 3. Verdicts: the section H rows

New register Status, added to "What Status means": **`Designed`**. An unbuilt roadmap design already specifies the candidate; the row adds no work of its own, only priority pressure. The alternative, overloading `Extends`, would claim a built mechanism that does not exist.

| # | Candidate | Status | Where it lands (evidence) |
|---|---|---|---|
| H1 | **Visual workflow builder**: a canvas that edits the workflow rather than holding separate logic | Designed · E-76 | `docs/roadmap/pipeline-as-data.md` E-76 is this design: `@vue-flow/core` + dagre, one renderer in run-state or editable mode, and no editing of a running graph. Once E-72 exists, the analysis's node palette would map onto it: Condition = one-output-port branching, Parallel/Merge = fan-out/collect, Retry = `max_traversals`, Gate = a node carrying `GateConfig`. Tool and Benchmark node types have no E-72 counterpart (Subflow → H7). Needs E-72 → E-74 first. |
| H2 | **FlowSpec**: workflow-as-code; YAML, CLI, API and GUI run the same spec | Designed · E-72…E-74 | E-72 `PipelineGraph` + node registry; E-73 `validate.py` as the single legality source; E-74 `GraphWorkflow` *interpreting* a graph pinned as workflow input (no codegen, no per-edit `patched()`). None built. **Not admitted:** no FR-1200 PRD line, and `ordering.md` keeps the group deliberately unsequenced. The analysis's untyped YAML is not adopted over E-72's typed ports (objection (b), decided 2026-08-06). |
| H3 | **Benchmark lab**: an experiment as a first-class object; a declared matrix; comparison; a Pareto quality-vs-cost frontier | Extends | Built: `src/sdlc/benchmarks/matrix.py` (case × harness × arm; ADR-6 judge check at expansion), per-role arms (E-37), held-out oracle (E-31), per-role $ (E-33), the five grids of `sdlc benchmark score` (E-36), `src/sdlc/benchmarks/sc_rollup.py`, and `src/sdlc/benchmarks/experiments.py` (`Experiment`: axis, baseline vs candidate `DeltaRow`s, `NOISE_FLOOR = 3`, committed to git, human-written verdict). New: a Pareto view (no precedent in `docs/` or `src/`); an experiment that declares and launches its matrix (today an experiment diffs two existing evidence sets, and the matrix is declared per case in `CaseSpec.arms`); a workflow axis, which needs E-77's `graph_sha`. Limit: `benchmarks/cases/` holds 10 case directories, the 9 E-79 counted plus E-88's `crew-probe` (a mechanical probe whose quality is not graded, `docs/roadmap/crew.md`). That is the bottom of OQ-B1's 10–30 estimate for a trustworthy signal. |
| H4 | **Evidence / traceability view**: criterion → task → files → tests → evidence → PASS | Extends · data gap first | Built: the frozen `ValidationContract` (FR-803, `stages/architecture/models.py:45`), the Analyst's `CriterionTrace` (`stages/analyze/models.py:10`: task, criterion, test names; completeness enforced, FR-106), F4 Markdown renders. **Prerequisite:** nothing records a per-test or per-criterion outcome. `QAReport` is task-level and cannot tell failed from never-ran (ROADMAP P2, 2026-08-19), so a PASS column today would present a task-level boolean as a per-criterion verdict, an FR-915-class misstatement. The view belongs on the run-detail page (H5). E-51/E-52 (unbuilt) are the assessment product's bundle, not the landing site. |
| H5 | **Run replay**: a per-run timeline; each step opens model, tokens, cost, duration, input/output, tools, diff, tests | Extends · gap verified | Data built: `RunEvent` trace → `events.jsonl`/`report.html` (E-22/E-23 inside E-32, `src/sdlc/observability/export.py`), `RunSummary.roles` (E-33), `HarnessSession` (E-38), dashboard `GET /runs/{id}` and `/events` (E-10, `src/sdlc/dashboard/api.py`), board tasks/events (E-78). **View missing:** `interfaces/dashboard/frontend/src/views/RunView.vue` is a stub, and so is `InboxView.vue`. Both have been placeholders since dashboard Plan 1 (`ac9344e`); Plan 2 never landed. A linear timeline needs none of E-72…E-77. The graph-shaped replay comes later via E-75 + E-76's run-state mode. Closed runs render only within Temporal retention (OQ-13). |
| H6 | **Workflow simulation / dry-run**: validate before a costly run; forecast cost, time, calls and gates | Extends | Today: F2 `sdlc doctor` (registry, crew layouts, harness CLIs, binaries, env, Temporal) and boot-time `validate_registry`. **When E-73 lands**, `validate.py` adds reachability, bounded cycles and port types. New: a forecast. Nothing estimates today; FR-701 budgets enforce, they do not forecast; benchmark records hold per-stage cost and wall time per arm. Bound: the planner decides the task count, so an honest estimate is per-stage before planning and per-task only after the plan gate. |
| H7 | **Subflows**: a reusable sub-workflow (e.g. a security review) as one node | New | Not in E-72…E-77. There is precedent for a node that runs a child workflow: `HarnessKind.CREW` → `CrewTaskWorkflow` (E-88), `DeploymentWorkflow` (E-67), the `TriageWorkflow` child (E-44/E-45). Open design points: E-73 round semantics across the boundary, `canonical_stage` for inner nodes, a composite's `graph_sha`. Recorded as **OQ-14** on the pipeline-as-data group; after E-74. The "marketplace" half is out of scope. |
| H8 | **Policy engine**: governance separate from workflow; environment and risk rules decide whether a step may run | Extends · see B1, B3 | Built: per-gate `GateConfig` (FR-301), the C7 calibration ledger, `ABSOLUTE_FLOOR` + `MERGE_REQUIRED_CHECKS` fail-closed (C3), `policy/containment.yaml` (ADR-17, C2). The remainder is **B1** (charter) + **B3** (autonomy per environment) + risk-class conditioning; no separate engine. `two_person_approval` is ⛔ blocked: operator identity is the self-asserted `X-Actor` header (OQ-11) until E-60. |
| H9 | **Cost / model router**: pick the model per task by complexity; a cheaper model first on retry | New · not recommended | Static half built: per-role model per run (`src/sdlc/agents/roles.py:175`, E-37), per-role economics (E-33; BENCHMARK §3.2 is the "few moments need frontier" result), budget gate (FR-701). Dynamic routing costs memo hit rate (the FR-103 key carries the model, so results stay correct but the cache runs colder), requires ADR-6 family inequality per routed pair, and requires a deterministic decision. **Revisit if** the H3 lab shows per-task mixes beating per-role allocation at n ≥ `NOISE_FLOOR`. |
| H10 | **Self-optimizing workflows**: the system mutates its own workflow and keeps what scores better | ⚠️ Product decision | Conflicts with a recorded stance: BENCHMARK.md §0 (a fixed, versioned instrument, changed by reviewed diff, as ADR-11 treats the DAG) and `src/sdlc/benchmarks/experiments.py` ("the tool computes the delta; the human writes the verdict"). The stance-compatible forms are registered: **F3** (constraint-tune; proposes only), the E-4 prompt eval loop, and E-36 heatmap-driven human iteration. H10 is recorded as the fork beyond F3, not a duplicate of it. Also blocked on E-77 + H3 + a corpus. |

The framing is recorded under H as context, not as a candidate: DESIGN / EXECUTE / EVALUATE / OPTIMIZE, with "workflow + evidence + evaluation" as the primary object. It is a product thesis, the one FR-1200 was already reaching for. It becomes scope only through the PRD.

## 4. Tracker defects fixed in the same change

- **T1. FR-1200 is cited but not admitted.** `pipeline-as-data.md` maps E-72…E-77 to FR-1200…FR-1206, and PRD.md has none of them. Fix: state it in the group file. This is not a PRD edit; the PRD line is the user's (OQ-1).
- **T2. Stale anchors in `pipeline-as-data.md`.** It cites `feature.py::_pipeline` at line 1625 of a 2,329-line file, with handlers `_run_clarify (:1836)` and so on. On main, `feature.py` is 772 lines with `_pipeline` at :469. The B0 migration moved the handlers into `src/sdlc/stages/<stage>/step.py` (13 files), `_dev_task`/`_merge_task` into `workflows/task_host.py`, `_revisable_stage` into `workflows/role_host.py`, and `_gate` into `workflows/gates.py`. `_run_clarify` no longer exists (it is now `clarify.step`, split into `_run_clarify_single`/`_run_clarify_fanout` in `stages/clarify/step.py`). Fix: refresh every anchor, re-verified at edit time. The "cheaper than it looks" argument gets **stronger**, since the stage bodies are already `step()` functions.
- **T3. FR-704 and NFR-4 are stale.** FR-704 is `[ ]` with "no `observability/` module", but PRD FR-704 ("render run history to `events.jsonl` + `report.html`") is met by E-32 (`src/sdlc/observability/export.py`, `activities.py`). Fix: FR-704 → `[x]` with that evidence. NFR-4 loses its false "no export" clause and **stays ⚠️**, because PRD NFR-4 also needs every decision and cost item reconstructible, and FR-304 (queryable decision log) and FR-702 (claim-check) are still open. §8 item 6 strikes E-22/E-23.
- **T4. `ordering.md` item 7 is stale.** "§1 has 8 unbuilt ones" should be 4 (§1: 11 of 15 live). "E-75 closes P2's outstanding dashboard-backend half" was superseded 2026-08-18 by E-10. The B0 note also changes the "cheap moment" argument (see §6).
- **T5. FR-601 overclaims.** `[x]` "dashboard fleet/spine/inbox", but the spine (run detail, `2026-07-05-dashboard-vue3-frontend-design.md`:17/:73/:208) and the inbox are stubs; `RunDetail.vue`/`StageSpine.vue` exist in no commit. Fix: FR-601 → `[ ]` ⚠️ "fleet ✅; run detail and inbox views are Plan-2 stubs over live backend routes" (OQ-3). Knock-on: register row F1 gets a note that its landing site is that stub.
- **T6. Dead path `docs/BENCHMARK.md`** in living docs: `ROADMAP.md:29`, `docs/roadmap/filesystem-first.md:156` and `:370`, `ARCHITECTURE.md:444`, `README.md:37` and `:130`. Fix: point each at root `BENCHMARK.md`. Historical records under `docs/superpowers/` are untouched (OQ-5 on the reach).

Recorded here and out of this phase's lane: the FR-1400 block (ROADMAP §2, `[x]` rows) also has no PRD line; BENCHMARK.md's header still says "not yet reconciled into ROADMAP.md"; and ROADMAP's `benchmarks/sc_rollup.py` shorthand is pre-existing.

## 5. Placement

**Recommended: register section H plus targeted back-links** (the edit list in §7).

- Rejected: *register only*. It leaves T1–T6 standing in living docs that describe `main`.
- Rejected: *a new `docs/roadmap/` group file*. Group files track decided work on `main`, and none of H is admitted.

No E-numbers are minted (the next free one would be E-90) and no PRD lines are drafted. Admission is the user's.

## 6. Ordering (a recommendation, not a commitment)

**Register shortlist addendum for section H**, ranked by leverage over existing seams:

1. **H5 run detail / replay view.** It fills a stub; every data source exists; it has no E-72 dependency. The same page later hosts H4 and E-76's run-state canvas, and the inbox view (F1's landing site) is the same kind of work.
2. **H4 data half, the per-criterion outcome record.** It is an integrity fix that must precede any traceability UI, and it closes the P2 "failed vs never ran" finding.
3. **H3 increments**: a Pareto view and declared experiments. Honest only at n ≥ `NOISE_FLOOR` per cell, so corpus growth (OQ-B1) is the real constraint.
4. **The section 14 decision (H1/H2/H7)**, for the user.
5. **H8** through B1/B3. H9 waits behind H3. H10 by user ruling.

**Section 14 (the analysis's top pick, "don't delay FlowSpec + Builder + Lab"):**

- **A (recommended): record only.** Sequencing waits on three prerequisites:
  - (a) a PRD FR-1200 line;
  - (b) OQ-10 (in-flight runs at cutover) settled;
  - (c) P2's exit demonstrated. The pipeline has never delivered "first brownfield feature merged via PR" (blocked by the repo-wide absolute floor, ROADMAP P2 2026-08-19). A big-bang rewrite of `_pipeline` before that moves the ground under an undemonstrated claim.

  `ordering.md`'s "cheap moment" argument (land E-72 → E-73 before §1 grows) is weaker after B0: the stage bodies are already modular `step()` functions, so waiting costs less than it did.
- **B (maximum fallback): E-72 + E-73 now, E-74 gated on P2.** Both are pure (a model and a router, no Temporal). The risk is unconsumed code under `src/sdlc/graph/` drifting before an interpreter exists.
- **C: all of section 14 now.** Not recommended, for the reasons in A.

**G1 context.** The analysis pulls toward a deeper Temporal platform, while G1 (factory-lite) pulls toward a lighter distribution without Temporal. The register already says G1 "wants a yes/no before the list is executed"; section H raises the stakes of that answer. No new question is filed; the H rows point at G1.

## 7. Concrete edits (the exec phase implements these via the plan)

| File | Section | Change | Lines now → est. |
|---|---|---|---|
| `docs/reports/external-ideas-2026-09.md` | title, header table (Date, Sources, Verification), Context paragraph | "two" → "three" 2026-09 sources. Add the third source and its nature (an analysis of Kroker itself, not a comparable factory). Add a verification pass for 2026-09-11 against `main`. | 143 → ~180 |
| same | "What Status means" | add `Designed` | |
| same | new **§H. Platform direction** after §G, before "Already covered" | rows H1–H10 as in §3, plus the framing note | |
| same | §F row F1 | append: its landing site `InboxView.vue` is a Plan-2 stub (T5) | |
| same | "Priority shortlist" | a dated "Section H addendum (2026-09-11)" with the §6 ranking, marked as a recommendation | |
| `docs/roadmap/pipeline-as-data.md` | framing + "Cheaper than it looks" | T2 anchor refresh; the T1 statement (FR-1200…1206 cited, not in PRD; decided in a brainstorm, not admitted) | 122 → ~140 |
| same | new dated note "External input 2026-09-11" | H1→E-76, H2→E-72…E-74, H5 graph replay → E-75/E-76, H6 validator half → E-73, H3 workflow axis → E-77; points to register §H | |
| same | Open questions | add **OQ-14 Subflows** (from H7) | |
| `docs/roadmap/ordering.md` | item 7 | T4 fixes; the §6 section-14 position (A + prerequisites, B as fallback), pending the user's ruling | 51 → ~58 |
| `ROADMAP.md` | header "Last verified" | prepend a 2026-09-11 entry (FR-601/FR-704/NFR-4 against `interfaces/dashboard/frontend/src/views/`, `src/sdlc/observability/`) | 512 → ~514 |
| same | §2 FR-601, FR-704; §3 NFR-4; §8 item 6 | T5, T3 | |
| same | 2026-07-19 note (:29) | T6 path | |
| `docs/roadmap/filesystem-first.md` | :156, :370 | T6 path | 421 → 421 |
| `ARCHITECTURE.md` | :444 | T6 path | 824 → 824 |
| `README.md` | :37, :130 | T6 path (OQ-5) | 175 → 175 |
| `docs/reports/2026-09-11-external-platform-analysis.md` (new, if OQ-4 = yes) | whole file | the verbatim source under a short provenance header, never edited after it lands. The register's Sources row links it. | 0 → ~752 |

**Ceiling:** every file stays under 1000 physical lines. The largest result is ARCHITECTURE.md at 824, unchanged.

**Not touched:** `PRD.md`, `BENCHMARK.md`, `src/`, `tests/`, `agents/`, `policy/`, the tier and group files not listed, and `docs/superpowers/` history.

## 8. Acceptance checks for the exec phase

1. `python scripts/check_file_size.py --full` passes.
2. Every path, `file:line` and E/FR/ADR/OQ number in new or edited text resolves on `main` at edit time; T2's anchors are re-derived, not copied from this spec.
3. `git grep -n "docs/BENCHMARK.md" -- "*.md" ":!docs/superpowers"` → 0 hits.
4. No new E-number: `git grep -nE "\bE-9[0-9]\b" -- "*.md" ":!docs/superpowers"` is unchanged vs `5534b16`.
5. The only checkbox changes in ROADMAP are FR-601 (`[x]` → `[ ]` ⚠️) and FR-704 (`[ ]` → `[x]`).
6. No sentence describes E-72…E-77 or `src/sdlc/graph/` as existing code.
7. Commits: subject and body only, no attribution trailers, `git commit -F <msgfile>`, one path per `git add` argument.

## 9. Open questions for the user gate

- **OQ-1: section 14 sequencing.** A record only (**recommended**) / B E-72+E-73 now with E-74 gated on P2 / C all now.
- **OQ-2: H10 self-optimization.** Keep the fixed-instrument stance, with F3 as the path (**recommended**), or open the stance.
- **OQ-3: FR-601 downgrade** to `[ ]` ⚠️ (**recommended**: fleet only is real).
- **OQ-4: commit the verbatim third source** at `docs/reports/2026-09-11-external-platform-analysis.md` (**recommended**, so section H has durable provenance the way sources 1 and 2 have URLs). It is user-supplied third-party text; if no, the Sources row reads "platform analysis (user-supplied, 2026-09-11; not committed)".
- **OQ-5: T6 reach.** Fix the dead path in README.md and ARCHITECTURE.md too (**recommended**; mechanical) or only in the roadmap files.

## 10. Rulings (user gate, 2026-09-11)

The gate passed on 2026-09-11. Every open question was ruled as recommended; the plan implements the spec under these rulings.

- **OQ-1: A, record only.** Section 14 (E-72…E-77) is recorded as design plus priority pressure. Sequencing waits on the three prerequisites of §6: a PRD line for FR-1200, OQ-10 settled, and P2's exit demonstrated. `ordering.md` item 7 states this position as ruled, not as pending.
- **OQ-2: keep the fixed-instrument stance** (BENCHMARK §0; the human writes the verdict). F3 is the path, and H10 is recorded as the fork beyond F3.
- **OQ-3: downgrade FR-601** to `[ ]` ⚠️ (fleet only is real).
- **OQ-4: commit the verbatim third source** at `docs/reports/2026-09-11-external-platform-analysis.md`, never edited after it lands. The register's Sources row links it.
- **OQ-5: wide reach.** Fix the dead `docs/BENCHMARK.md` path in README.md and ARCHITECTURE.md too, not only in the roadmap files.
