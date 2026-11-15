VERDICT: approve

# Pass 2 (2026-11-15) — re-verification of the six fixes

Every fix was re-checked against the artifacts and the tree; pass-1 checks were not re-run blindly — spot re-reads confirmed no regressions elsewhere (R2/R5–R12 unchanged, data-model §pools/truth-table/field-list unchanged, contracts/worker-boot.md unchanged, quickstart §0/§2–§4 unchanged, plan phases/disposition/project-structure otherwise unchanged).

1. **Gap 1 (blocking) — RESOLVED.** research §R1 "Rollback differs by input family" is now accurate against the code: the 7-of-8 benign list matches a tree-wide grep (none of those files set `extra="forbid"`), and the maintenance family's loud refusal is cited exactly (`S/maintenance/models.py:3, 93, 174, 192` — :192 re-verified as `ConfigDict(extra="forbid")`). Plan Risk 5 is restated correctly; E2 carries the remedy; R1 notes routing-off rollback is safe for every family. **Residual (non-blocking, new gap 7):** R1 and Risk 5 both say the item "is surfaced at GATE 2", but plan §Constitution's "Surfaced for GATE 2" list still has only two entries (check_test_drift, L2 rebuttal). Add the third bullet — one line, can land with tasks.md.
2. **Gap 2 — RESOLVED.** R3's ceiling paragraph now names `assessment.py` (843) and `benchmarks/models.py` (721, verified by `wc -l`) with honest line budgets (`cli.py` ≈ 12 lines → ≈ 971). The constitution table row matches R3.
3. **Gap 3 — RESOLVED.** quickstart §5 ("Compose and manual smoke") carries the exact required command `docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q` marked "Required for P-FR-010 (no daemon needed)", and the P-FR-010 traceability row cites it verbatim.
4. **Gap 4 — RESOLVED.** quickstart §1 is split §1a (024-i: pools, classification, boot plan, doctor, bench ids, janitor lock, axis prune) / §1b (024-ii: `test_inputs_omit_none`, AST walk), with the expected list annotated per subsection. F3 now runs "§1a, §3 and §4, plus the C3 proof `uv run pytest -q -m temporal tests/test_pools_failfast.py::test_poller_freshness`" — fully explicit.
5. **Gap 5 — RESOLVED.** routing-wire W-2 names "the nine workflow types with harness-class sites" and adds "`ReflectWorkflow`, the tenth registered type, ... trivially all-core" (matches reflect.py: one core `reflect` activity). R4's dynamic list now includes the deploy leg; H3 and the P-FR-006 row match.
6. **Gap 6 — RESOLVED.** R1 records the D1 hash check with the correct evidence (`provenance.py:154` hashes `cfg.instructions` only; memoization `content_key` hashes stage-input JSON — consistent with pass-1 code verification). data-model §Inheritance now cites `pipeline_child.py:53, 82`, matching the code.

**New gaps:** 7 (above) — non-blocking. **Blocking gaps: none.** The plan, its research, contracts, data model and quickstart now satisfy the checklist method: all P-FR-001..013 and SC-001..007 traced to steps and validations (with explicit commands), steps concrete, no placeholders, paths exact, and the routing-off byte-identity / determinism story verified against the installed pydantic 2.14.1 and temporalio 1.31.0.

---

# Pass 1 record (2026-11-15) — superseded verdict: fixes-needed

# Gaps (fix before /speckit-tasks or at GATE 2)

1. **[BLOCKING] False rollback claim for maintenance inputs — `research.md` §R1 ("Rollback is benign"), `plan.md` §Risks item 5, and the D1/D1-alt disposition rows.** R1 justifies "a pre-024 worker given a routing-on input drops the unknown key" with "no input sets `extra="forbid"` (grep of `S/core/models.py`)" — a grep scoped to one file. In fact `src/sdlc/maintenance/models.py` is `extra="forbid"` **throughout** (package docstring at :3 says so; `MaintenanceConfig`'s `model_config` at :93, `MaintenanceKickInput`'s at :174), and `MaintenanceConfig` is one of the 8 root inputs that R1 itself gives the `harness_queue` field. A pre-024 worker decoding a routing-on `MaintenanceKickInput`/`MaintenanceState` (including one baked into a schedule by `schedules/apply.py`, or carried by `continue_as_new`) fails validation loudly; it does not silently route off. The design (field on inputs) is unaffected, but R1's verified-claim is false, plan Risk 5 repeats it, and it would propagate into the E2/J1 operator docs. Fix: restate the rollback risk (benign-drop for 7 of 8 inputs; loud validation refusal for the maintenance family, with the remedy), and surface it next to the `check_test_drift` item for GATE 2.
2. **[non-blocking] R3 ceiling-paragraph factual slip — `research.md` §R3 ("Ceiling").** "No other touched file is above 700 lines except `S/cli.py` (959)" is wrong: `src/sdlc/workflows/assessment.py` is 843 lines and is touched (G2 field at :131, G4 child copy at :371). No ceiling risk (843 + ~2 « 1000; baseline file has no entry for it), but the sentence should be corrected. Adjacent nit: the constitution table's "`S/cli.py` gets ≤ 6 lines" budget is optimistic for three H1 sites ("do the same" × 3), though nowhere near the ceiling.
3. **[non-blocking] P-FR-010 validation missing from the quickstart — `plan.md` §Traceability (P-FR-010 row) vs `quickstart.md` §0–§5.** The row's "the overlay reviewed; `docker compose -f … config` validates" is elided and appears nowhere in the quickstart (§5 smoke omits it). Add the exact command (e.g. `docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q`) so tasks.md carries an explicit validation.
4. **[non-blocking] "quickstart §1 (024-i subset)" is not enumerated — `plan.md` §024-i close-out (F3) vs `quickstart.md` §1.** §1 lists seven test files; `test_pools_call_sites.py` (G5) and `test_pools.py::test_inputs_omit_none` (G2) are 024-ii work. Name the subset (or split §1's header) so the 024-i close-out command is explicit.
5. **[non-blocking] "9 workflow types" vs 10 registered — `contracts/routing-wire.md` W-2, `plan.md` H3, vs `src/sdlc/worker.py:292-307`.** The worker registers `ReflectWorkflow` as a 10th. It schedules only the core `reflect` activity (`workflows/reflect.py:44`) and its only start path is the schedule action already guarded at `schedules/apply.py`, so there is no routing hole — but W-2 should name it (trivially all-core) or say "the nine types with harness-class sites". Likewise R4's dynamic-recorder list omits the deployment leg that H3's nine include; H3 governs — align R4.
6. **[non-blocking] D1's hash re-confirmation not recorded — `research.md` §R1 vs advisor D1.** D1 asked the plan to "re-confirm for memoization keys and benchmark config ids"; R1 records no such check. Code-side it holds (`benchmarks/provenance.py:154` hashes `cfg.instructions` only; `memoization/cache.py` `content_key` hashes stage input JSON, not cfg dumps), but since the D1 disposition row claims adoption, record the check as done.

---

# Plan Quality Checklist: Round 024 — two worker pools (E-91)

**Purpose**: Validate the plan (and its research/data-model/contracts/quickstart annexes) by the checklist method — traceability, concreteness, placeholders, exact paths, explicit test commands — against the 024 artifacts and the repository.
**Created**: 2026-11-15 (plan pass 1) | **Actor**: SPEC & PLAN REVIEWER | **Depth**: formal gate
**Inputs**: spec.md (GATE 1 record binding), plan.md (A1–J2), research.md (R1–R12), data-model.md, quickstart.md §0–§5, contracts/{worker-boot,routing-wire}.md, consults/{advisor,skeptic}.md.

## Traceability & Coverage

- [x] CHK001 - Is every functional requirement P-FR-001..013 mapped to ≥1 plan step and ≥1 named validation? [Traceability, plan §Traceability] — verified: all 13 rows present, each validation resolves to a quickstart section or named test.
- [x] CHK002 - Is every success criterion SC-001..007 mapped to steps and a validation, incl. SC-007 → `scripts/check_file_size.py` in quickstart §4? [Traceability, plan §Traceability; quickstart §4] — verified.
- [x] CHK003 - Does every advisor/skeptic finding (D1–D7, L1–L6, incl. sub-findings) have an explicit disposition row, adopt or not-adopt, with a reason? [Coverage, plan §Skeptic/advisor disposition] — verified: 15 rows, no silent drops; D4.3 and the memo/interceptor alternative carry recorded rejections.
- [x] CHK004 - Are the GATE 1 rulings carried into plan decisions (Q1 two pools; Q2 no pinning + shared store; Q3 wall-clock unchanged; Q4 numbering)? [Consistency, plan §Split decision, E1/E2, J1] — verified, incl. the pre-authorized split being recorded as GATE 1 required.
- [x] CHK005 - Is R9's partial rebuttal of skeptic L2 sound, so the Q2 ruling stands as written? [Ambiguity/Assumption, research §R9 vs consults/skeptic §L2] — verified against code: one `HOME` under many concurrent CLIs is today's status quo (`harness/base.py` env allowlist + `create_subprocess_exec`); same-host containers share one kernel, so POSIX locks on a local named volume hold; the `auth.json` `:ro` bind (`docker-compose.override.example.yml:17`) is preserved by mounting the storage *subpaths*; the "one host only" boundary text is in J1. The rebuttal is evidence-grounded and the ruling is honoured.

## Step Concreteness

- [x] CHK006 - Is every step A1..J2 concrete (names files, functions and the tests that prove them)? [Clarity, plan §Phases] — verified; G3 anchors to the R3 table, G4 to data-model §Inheritance.
- [x] CHK007 - Are the cited file paths and lines exact? [Clarity; research R1/R3/R6, data-model §Inheritance] — verified in-tree: 8/8 R1 root-input class lines; 33/33 R3 call-site lines (each is a harness-class activity call); all inheritance sites (benchmark `workflow.py:373`/`:90`, tidyup `:194/204/229`, assessment `:371`, maintenance `:189`, maintenance_execute `:260/491/505`, `code/step.py:280`, `deploy/step.py:138`, `pipeline_child.py:53/82` — data-model's `:52/:78` off by one, calls uniquely identified); all R6 start-path sites; `worker.py:292-307` (10 workflows), `:313` (janitor), `:273/:279` (boot checks). Two accuracy defects exist elsewhere — see Gaps 2 and 6.
- [x] CHK008 - Are quickstart §1–§4 test commands explicit and runnable as written? [Clarity, quickstart §1–§4] — verified, with two exceptions recorded as Gaps 3 and 4.
- [x] CHK009 - Are there any placeholders (TODO/TKTK/???/`[NEEDS CLARIFICATION]`/unfilled template sections) in any 024 artifact? [Completeness] — none found (grep across the dir; the only "NEEDS CLARIFICATION" hit is GATE 1's record that none were used).

## Scope Honesty

- [x] CHK010 - Is routing-off byte-identity specified at all three layers, each pinned by a check? [Consistency, R1 + R3 + routing-wire W-1; H3 routing-off leg; quickstart §1/§3] — verified: payload layer `Field(exclude_if=)` **re-verified on installed pydantic 2.14.1** (`M().model_dump_json()` → `{"a":1}`, no null key); command layer `on_harness` returns `opts` unchanged when `q` falsy; SDK layer **re-verified on installed temporalio 1.31.0**: `_workflow_instance.py:3311-3313` sets `task_queue = input.task_queue or info.task_queue`.
- [x] CHK011 - Is the one deliberate routing-off change named as a contract exception, and is it real? [Consistency, worker-boot G-1; research R2] — verified: `check_test_drift` is defined (`vcs/git.py:180`), exported in `vcs.ACTIVITIES` (`vcs/__init__.py:55`), called (`code/step.py:711`), and **absent** from `worker.py:get_worker_activities()` (full list inspected) — a genuine latent defect, worker-side only (no command change), fixed in B2 and pinned by the classification test.
- [x] CHK012 - Are the untouched surfaces enumerated and respected — no `GraphWorkflow` node/handler change, no `<stage>.md`, no trust-layer file? [Consistency, P-FR-012; plan §Constraints + §Project Structure] — verified: the Project Structure lists no stage contract or containment files; the `graph_nodes/precode.py:58`/`postplan.py:124` edits are activity-call options, which P-FR-012 itself permits, and the AST test pins it.
- [x] CHK013 - Are R025's fleet runs and AP-2.5b/2.6/2.7 absent as work items? [Scope, plan §Summary, R12, J1] — verified: R12 is documentation only; J1 marks AP-2.5b open (AP-2.1 dependency).
- [x] CHK014 - Is the rollback story true as written? [Assumption, research R1; plan §Risks 5] — **FAILS for the maintenance family**: `maintenance/models.py` sets `extra="forbid"` throughout, so the "drops the unknown key" claim is false there. → **Gap 1 (blocking)**.

## The Split

- [x] CHK015 - Is 024-i shippable alone with routing hard-off? [Consistency, plan §Split decision, Phases B–F] — verified: B–F add no routing wiring; `require_harness_poller` exists from C3 but no start path calls it until H1; E2 carries the "routing not yet available" banner.
- [x] CHK016 - Does 024-ii depend only on 024-i (no 024-external prerequisite)? [Dependency, Phases G–J] — verified: G–J consume only `pools.py`, the boot plan and the registration from B–C.
- [x] CHK017 - Does the cut match spec A.4 as adjusted by advisor D7 (doctor + poller-check *function* in 024-i; start-path wiring and fleet proof in 024-ii)? [Consistency, spec §A.4; advisor D7; plan §Split decision] — verified; A.4's "fail-fast start" (the wiring) stays in 024-ii.
- [x] CHK018 - Does the plan state plainly that 024-i does not unblock R025? [Clarity, §Split decision, Risk 6] — yes, three times.

## Determinism & Replay

- [x] CHK019 - Can any new command be reached with routing off? [Consistency, W-1; R3; R1] — no: excluded-when-`None` payloads (verified), no `task_queue` key via `on_harness` (verified), child copies pass `None` (excluded), schedule bake-in is a no-op when unset, and `check_test_drift` registration is worker-side. The G-1 exception changes serving, not commands.
- [x] CHK020 - Does R7's no-`patched()` reasoning hold? [Consistency, R7; advisor D6; skeptic L1] — yes: L1's empirical replay proof (queue mismatch tolerated by temporalio 1.31.0 determinism matching), the queue is a pure function of recorded input, routing-on histories cannot predate 024 code, and the one command-adding proposal (D4.3 pre-flight) was rejected — so D6's "exclude that activity from projection equality" caveat is moot. H4(a) forced-queue replay + H4(b) in-test capture are the permanent guards.
- [x] CHK021 - Is the no-stored-fixture promise compliant with `tests/replay/AGENTS.md` rule 1 (capture tests behind env switches are the only writers)? [Constraint, R7; quickstart §3] — verified: H4(b) is in-test only; §3 asserts `git status --short tests/replay/` prints nothing. The scenario is real: `greenfield_happy.json` exists and contains `activity:run_coding_task`/`activity:create_worktree` (reaches the code stage), with its history in `histories/`.
- [x] CHK022 - Is the projection-equality expectation grounded (projection records activity type only, no queue)? [Assumption, `tests/replay/projection.py:24-40`] — verified by reading the projection source.

## Repo Constraints

- [x] CHK023 - Is the 1000-line ceiling handled with exact numbers? [Constraint, plan §Constraints + G1; `.file-size-baseline.json`] — verified: `stages/code/step.py` = **998**; G1 extracts first with a `wc -l` ≤ 975 assertion; `S/stages/code/acts.py` does not yet exist (no collision); the baseline file's only entry (`tests/test_assessment_workflow_e2e.py`) is untouched. R3's surrounding arithmetic has one error → Gap 2.
- [x] CHK024 - Is the cross-stage call ban respected? [Constraint, plan §Constitution] — `pools.py` is a horizontal leaf (imports stdlib + `temporalio.api` only); `acts.py` is stage-internal; stage steps import a helper, never another stage.
- [x] CHK025 - Do the seven new fast-tier test names avoid collisions with existing files? [Clarity, plan §Project Structure] — verified: no existing `tests/test_pools*.py`, `test_bench_ids.py`, `test_janitor_lock.py`, `test_doctor_pools.py`, `test_worker_boot_plan.py`, `test_axis_prune.py`.

## Claims Against the Code (independently re-verified)

- [x] CHK026 - `Field(exclude_if=)` exists and behaves as claimed on the installed pydantic (2.14.1)? — verified by probe.
- [x] CHK027 - `_workflow_instance.py:3311` implements `input.task_queue or info.task_queue` on the installed temporalio (1.31.0)? — verified by probe (lines 3310-3313).
- [x] CHK028 - The R1 root-input classes exist at the cited lines (8/8)? — verified.
- [x] CHK029 - The R6 start-path inventory is complete? — verified by whole-tree grep: the only client `.start_workflow(` sites are `graph/start.py:59` (covers cli.py:581 and operator/runtime via `start_graph`), `cli.py:784/828/879` (args at 793/839/889), `benchmarks/cli.py:335`, `maintenance/cli.py:248`, `schedules/apply.py` (`to_temporal` ~:58-66), and the allowlisted `demo/run.py` (own queue, verified at :117/:129); everything else is child starts inside workflows.
- [x] CHK030 - The R3 site table's 33 lines are harness-class activity calls (spot-check floor was 10)? — all 33 verified.
- [x] CHK031 - W-2's workflow enumeration matches what the worker registers? — **partial**: 10 workflows registered, W-2/H3 name 9; `ReflectWorkflow` omitted (core-only, no hole) → Gap 5.
- [x] CHK032 - Beyond the mandated claims, are further citations accurate (floor was 10)? — ~40 verified, incl. `task_queue.py:10`, `worker.py:292-307/:313`, `drift.py:80`, `code/step.py:93-104/:305`, `crew.py:98-105`, `crew/layouts/code.yaml:26` (`wall_clock_s: 5400`), `benchmarks/cli.py:338`, `benchmarks/workflow.py:340`, `projection.py:24-40`, `harness/base.py` (HOME allowlist + subprocess), `docker-compose.yml:18` + volume names (`worker-worktrees`/`worker-repos`/`worker-runs`), `docker-compose.override.example.yml:17`, `vcs/janitor.py:34` + `cleanup_run_dir`, `benchmarks/axis.py:222-236` (rmtree, no prune), stage `ACTIVITIES` lists (qa :692, merge :251, deploy :253), `context/activities.py:31/:91`, `git.py:97/:180/:253`, `validators/activities.py:18`, `maintenance/models.py:169/:350`, `docs/adr.md:91-95` (ADR-9 + five-pool amendment), `core/models.py:185-189` (`RoleConfig.kind`), `operator/runtime.py` (`start_graph` → `start_graph_run`). Failures: Gap 1 (extra="forbid") and Gap 6 (hash re-confirmation) only.

## Summary

- 32 checks; 29 pass clean, 3 feed the gap list (CHK014 → Gap 1 blocking; CHK031 → Gap 5; CHK032 → Gaps 1/2/6).
- One blocking gap: the maintenance `extra="forbid"` rollback claim (Gap 1). The design itself (field-on-inputs, `exclude_if`, `on_harness`, split, fail-fast, replay strategy) survives every check performed against the installed libraries and the tree.
