# Checklist: Plan Quality — 006 S-batch Inbox Fixes

**Purpose**: Unit tests for `plan.md` (with research.md, quickstart.md; tasks.md appeared during review and was cross-checked) — completeness against the approved spec (incl. GATE 1 rulings Q1–Q3 and post-GATE-1 amendments A1–A5), internal consistency, unambiguity, verifiably gated constraints. Not implementation tests.

**Created**: 2026-10-03 (reviewer seat; every load-bearing claim re-verified in code against main `817f819`)

**Updated**: 2026-10-03, round 2 — plan findings F1–F5 re-checked after the fixes; CHK004/CHK012/CHK024 flip to PASS, CHK017 re-fails on new evidence (see tasks round: `tests/doctor/test_doctor_checks_binaries.py:87`)

**Updated**: 2026-10-03, round 3 — tasks findings F1–F4 re-checked; CHK017 flips to PASS (D1 now re-pins the asserting test in the RED task; red-before/green-after verified in code)

## Plan Completeness

- [ ] CHK001 - Does the plan carry a design decision or explicit exclusion for every functional requirement FR-001..FR-015, with none silently dropped? — **PASS** [Completeness, Plan §Requirement coverage; coverage table plan.md:158-173 checked row by row]
- [ ] CHK002 - Is every spec edge case (7 bullets: B1 empty-output, B1 crew/empty-change-set, B2 empty-string, B2 both-tiers, B2 literal/`log`, B3 key-absence ×3, B3 wider drift) mapped to a plan element? — **PASS** [Completeness, Spec §Edge Cases, Plan §Design D1–D3 + plan.md:175]
- [ ] CHK003 - Are the GATE-1 rulings carried where they bind (Q1 doctor half rides → D2; Q2 taught rows + omission list, no sidecar → D3; Q3 drafts stay in inbox files, section names only → D5)? — **PASS** [Traceability, Spec §GATE 1 rulings, Plan §D2/D3/D5]
- [ ] CHK004 - Are amendments A1–A5 each carried into the plan at the point they bind (A1 → D3 drift table; A2 → D5 working-tree deliverables; A3 → D1 worker-log-only; A4 → D2 no de-dup; A5 → D4 stale-docstring bullet)? — **PASS** (round 2) [Traceability, Spec §A5 (spec.md:320-323), plan.md:149, research.md:89, tasks.md:97 — A5 now states each docstring's actual staleness and matches the code (`deps.py:8-12` "Task 8 concern"; `toolset.py:26` "(deferred)")]
- [ ] CHK005 - Does each success criterion SC-001..SC-007 have named evidence in the plan (test, command, or reviewer act)? — **PASS** [Traceability, Spec §Success Criteria, Plan §Requirement coverage, quickstart.md §1–5]
- [ ] CHK006 - Is the absence of `data-model.md` and `contracts/` both justified and acceptable (no new entity, no external interface; the one new public function fully specified)? — **PASS** [Completeness, plan.md:58, Plan §D2 — `unset_env_targets` signature, walk order, skip/no-log semantics are all stated]
- [ ] CHK007 - Is the task decomposition lean (14 tasks inside SC-007's 10–14; no ceremony inflation) with nothing load-bearing missing? — **PASS** [Measurability, tasks.md T001–T014, Plan §Scale/Scope; baseline+verification are the only overhead tasks and both produce required evidence — the one gap found is CHK017, not a missing task type]

## Plan Clarity

- [ ] CHK008 - Is D1's warning contract unambiguous (exactly one WARNING, worktree + stderr-or-stdout, no raise, sha unset) and is the stated test shape (monkeypatch `activities._git` passthrough failing `commit` only) workable in the named module? — **PASS** [Clarity, Plan §D1; `activities.py:24` imports `_git` as a module global, `:29` `_log`; `tests/code/test_coding_task_checkpoint.py` already monkeypatches that module and has the `git_repo`/`_StubHarness` scaffold; `tests/conftest.py:152` `git_repo`]
- [ ] CHK009 - Is D2's `unset_env_targets` semantics precise (path=None re-read via `_resolve_path`, walk `default` then `gates.*`, tiers `primary` then `fallback` — the loader's order, non-strings skipped, never logs) and is the doctor wiring (inside the existing `try`, after `load_routes()`, both except branches unchanged) fully specified? — **PASS** [Clarity, Plan §D2; loader order verified at `routes.py:93,116-121`; check shape at `checks.py:120-130`]
- [ ] CHK010 - Is D3's five-row drift table the COMPLETE closed set of first-regeneration differences (nothing added beyond it, nothing removed, no value change), with the guarded omission pop specified? — **PASS** [Completeness, Plan §D3, research.md §R3; independently re-enumerated against the models (`core/models.py:165,502,505,540,542,545`, `pending.py:42,54,68,81`, `dashboard/fleet.py:78,84,88`) and the committed fixture — rows 1–5 plus the omission row are exactly the delta]
- [ ] CHK011 - Is the taught-row content pinned so the executor cannot guess (18 stage names and `graph_sha` as commented literals, `total_open_runs=3`, the two `"kroker"` values, `closed_marks["graph-run-closed"]`)? — **PASS** [Clarity, Plan §D3; fixture lines 57-91, 158-202 carry exactly those facts; 18 stage names confirmed]
- [ ] CHK012 - Does the plan make SG-1 decidable when the regenerated file's root keys reorder to model field order (`closed_marks` moves to the end, after `open_errors`), i.e. is "nothing is removed and no existing value changes" explicitly a parsed-data judgement? — **PASS** (round 2) [Clarity, plan.md:137 ("judged on parsed data… that block move is expected and is not a difference"), tasks.md:19 (SG-1), tasks.md:85 (T010)]

## Plan Consistency

- [ ] CHK013 - Do plan↔spec↔fixture facts agree (14 tasks vs SC-007's 10–14; 8 commits; 4 source files; 7 runs; project_key set ×2 / null ×2 / absent ×3; `total_open_runs` 3 vs generator 2)? — **PASS** [Consistency, Plan §Scale/Scope, Spec FR-007/A1; every state re-counted in the committed fixture (lines 40,90,114,178 + three absent rows) and the omission list equals the absent set]
- [ ] CHK014 - Do quickstart steps map one-to-one onto the plan's evidence obligations, including the FR-015 empty-diff command and the second-regeneration no-op? — **PASS** [Traceability, quickstart.md §1–5, Plan §Constraints]
- [ ] CHK015 - Is D2's claim about doctor-test impact verified (only `test_notify_routes_ok_reports_pass` needs the isolation patch; the other two notify tests raise inside `load_routes` and never reach the helper; no other test in tests/doctor/ touches notify routes)? — **PASS** [Consistency, Plan §D2; `tests/doctor/test_doctor_checks_delegated.py:135-140,143-152,165-183`; grep of tests/doctor/ finds no other notify reference]
- [ ] CHK016 - Is B1's no-spurious-path analysis grounded in code (crew tasks never reach `run_coding_task`; `--allow-empty` makes an empty change set commit)? — **PASS** [Consistency, research.md §R1; crew branch at `code/step.py:308` else; `--allow-empty` at `activities.py:199`]
- [ ] CHK017 - Does the plan account for repo text that B1's change makes false — doctor `check_git_identity`'s FAIL detail "will fail SILENTLY — the failure is swallowed at stages/code/activities.py:197-202"? — **PASS** (round 3) [Consistency, `src/sdlc/doctor/checks.py:207-214`; plan.md:91 now names the one test that pins the old wording (`tests/doctor/test_doctor_checks_binaries.py:74-88`, assertion :87) and re-pins it in the RED task (T002: rename to `…_naming_the_logged_consequence`, `"silently" not in` + `"warning" in`, keep FAIL/`auto-detect`/`anchor`), while T003 keeps "warning"/"anchor" and drops "silently". Verified in code: both new assertions fail against the current detail (it contains "SILENTLY" and no "warning" substring) and pass under T003's mandated wording; repo-wide sweeps (case-insensitive "silent", "swallowed", `activities.py:197`, old test name) find no other asserting site]

## Acceptance & Verification Quality

- [ ] CHK018 - Is the FR-009/SC-3 frontend-passthrough claim grounded (the mapper reads none of the five added keys and treats absent and null alike)? — **PASS** [Measurability, Plan §D3, research.md §R3; verified at `http.ts:71,80,101` — `mapRun`/`mapClosed` read no `thaw_tests`/`parent_run_id`/`open_errors`/`graph_sha`]
- [ ] CHK019 - Does the freshness test pin the right failure mode (parsed comparison, CRLF-safe, message naming file + regenerate command), mirroring the sibling graph test? — **PASS** [Measurability, Plan §D3, `tests/test_graph_fixtures_fresh.py:37-43`]
- [ ] CHK020 - Is B4's verification loop closed (executor re-reads every candidate on the branch, keeps only what is true and not WHAT-level, reports kept/dropped/defect-candidates per SG-5)? — **PASS** [Traceability, Plan §D4, tasks.md T011 + SG-5; planner spot-checks confirmed in code (`step.py:254-271`, `stage.py:277-282`); further R5 citations sampled exact (`budget_store.py:87`, `verify.py:72,91`) except the CHK004 defect]
- [ ] CHK021 - Are B5/B6 verifiable without commits (git-ignored files, reviewer reads them, register-diff evidence command)? — **PASS** [Measurability, Plan §D5; `.gitignore:4` `.workspace/`; both inbox files and `docs/reports/external-ideas-2026-09.md` exist; quickstart.md §4]

## Dependencies & Assumptions

- [ ] CHK022 - Are environment claims scoped and true (kroker-dev only, host venv excluded; `addopts` already carries `-q` so no pyproject touch is needed)? — **PASS** [Assumption, Plan §Technical Context; `pyproject.toml:108`]
- [ ] CHK023 - Is FR-015 satisfiable as designed — no plan element needs an edit to `src/sdlc/stages/code/step.py`, `pyproject.toml` or `uv.lock` — and is the 991/1000 line fact accurate? — **PASS** [Measurability, Plan §Constraints; `step.py` counted at exactly 991 physical lines; B1's site is in `activities.py:198-204`, not step.py; no new dependency anywhere in D1–D5]

## Citation Accuracy

- [ ] CHK024 - Are research.md's file:line citations accurate against main `817f819`? — **PASS** (round 2) [Traceability, research.md:96 now cites `src/sdlc/benchmarks/agreement_matrix.py:148-153` (path verified, empty state at :148-153); research.md:89 reworded accurately. All other sampled citations remain exact — see round-1 evidence]
- [ ] CHK025 - Are spec↔plan↔research cross-references internally consistent (A1's five rows ↔ D3's table ↔ R3's table; ruling language; FR/SC numbering)? — **PASS** [Consistency, Spec §A1, Plan §D3, research.md §R3]
