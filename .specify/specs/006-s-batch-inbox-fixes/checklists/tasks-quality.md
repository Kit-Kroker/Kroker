# Checklist: Tasks Quality — 006 S-batch Inbox Fixes

**Purpose**: Unit tests for `tasks.md` — coverage of every FR/SC/edge case/amendment/plan decision, TDD ordering with reds verified against the code as it will be, commit-pairing vs revertability, per-task executability, stop-guard decidability, constraint enforcement, format and arithmetic. Not implementation tests.

**Created**: 2026-10-03 (reviewer seat; verified against main `817f819`)

**Updated**: 2026-10-03, round 2 — tasks findings F1–F4 re-checked after the fixes; CHK004 and CHK009 flip to PASS (the re-pinned doctor test verified red-before/green-after in code, no other asserting site exists)

## Task Completeness

- [ ] CHK001 - Does every functional requirement FR-001..FR-015 map to at least one task, and is each Requirement→task map row accurate against the task texts (no task claimed as evidence that does not actually evidence it)? — **PASS** [Completeness, tasks.md:131-146; each row checked against T001–T014 text]
- [ ] CHK002 - Is every amendment A1–A5 carried into a task (A1 → T009/T010 + SG-1; A2 → Phase 6 preamble + T012/T013; A3 → T003's message scoped to the worker log; A4 → T004's both-tiers case and T005's no-dedup; A5 → T011's stale-docstring bullet)? — **PASS** [Traceability, spec §Post-GATE-1 amendments, tasks.md per phase]
- [ ] CHK003 - Is every spec edge case either covered by a task or explicitly dispositioned as design behavior (B1 both-empty → T002 case 2; B1 crew/empty-change-set → dispositioned in research R1, verified: `code/step.py:308` crew branch, `activities.py:199` `--allow-empty`; B2 empty-string/both-tiers/literal-`log` → T004; B3 key-absence → T009 test 2; B3 wider drift → T010 + SG-1)? — **PASS** [Consistency, spec §Edge Cases, tasks.md T002/T004/T009/T010]
- [ ] CHK004 - Does every plan design decision D1–D5 have implementing tasks with nothing dropped — including D1's doctor-text correction? — **PASS** (round 2) [Completeness, plan.md:91, tasks.md:55-56 — T002 now renames and re-pins `test_identity_unresolvable_reports_fail_naming_the_silent_consequence` as part of the RED set (`"silently" not in` + `"warning" in`, FAIL/`auto-detect`/`anchor` kept, module docstring reworded); T003 keeps "warning"/"anchor" and drops "silently". Verified in code: both new assertions fail against the current detail (checks.py:207-214 contains "SILENTLY" and no "warning" substring) and pass under T003's wording]
- [ ] CHK005 - Is a baseline task present so later evidence has a comparison point (base sha, fast-tier pass count, mypy count)? — **PASS** [Measurability, tasks.md:43 (T001) → baseline.md]

## Ordering & Dependencies

- [ ] CHK006 - Is every behaviour task (T003, T005, T007, T010) preceded by its RED task, and is each RED red for the right reason against the code as it will be at that point? — **PASS** (verified in code) [Traceability, tasks.md §Standing rules; T002 cases 1–2 red: `activities.py:198-204` has no else branch, no warning exists (the module's only `_log.warning` is :163, unreachable via `_StubHarness`); T002 case 3 green pre-fix (control; `capture.py:54`'s warning is a different logger); T004 red: `routes.py` has no logger today; T006 red: `unset_env_targets` name missing; T009 both red against the T008 generator: the models emit `project_key: null` on every run/closed row (`core/models.py:505,545`) so "exactly three lack the key" fails, the graph rows do not exist yet, and test 1 fails on 2-runs-vs-7 among the five drift axes]
- [ ] CHK007 - Does the commit-pairing rule (RED tests ride the green-turning commit) leave no red commit and keep every item independently revertible (B1 ×1, B2 ×2, B3 ×2, B4 ×1; T008's refactor commit lands no test and breaks nothing — nothing imports the fleet script yet)? — **PASS** [Consistency, tasks.md:11, §Phase order, spec FR-014]
- [ ] CHK008 - Is the dependency list complete and non-contradictory (T001 first / T014 last; T002→T003; T004→T005→T006→T007 with T007 needing T005's `_env_ref`; T008→T009→T010; T011–T013 only need T001), including the same-file question: T003 edits `check_git_identity` (checks.py:169-215) and T007 edits `check_notify_routes` (checks.py:120-130) — disjoint hunks in strictly serial phases, no ordering or revert hazard? — **PASS** [Consistency, tasks.md:124-129; regions verified disjoint in `src/sdlc/doctor/checks.py`]
- [ ] CHK009 - Are stop-guards SG-1..SG-5 attached to the exact task where the failure appears and decidable as written? — **PASS** (round 2) [Completeness, tasks.md:17-23 — SG-1/2/3/5 decidable (SG-1 parsed-data with the reorder note); SG-4 now names the four edited test modules in place (`tests/code/test_coding_task_checkpoint.py`, `tests/test_notify_routes.py`, `tests/doctor/test_doctor_checks_delegated.py`, `tests/doctor/test_doctor_checks_binaries.py`), matching T002/T003's widened scope]

## Executability

- [ ] CHK010 - Does each task name the files it touches, and do all named paths exist on main `817f819` (source, tests, script, fixture, both `.workspace/tasks/` inbox files, `docs/reports/external-ideas-2026-09.md`)? — **PASS** [Clarity, tasks.md all tasks; every path checked on disk]
- [ ] CHK011 - Is each task executable by an agent with no other context — exact symbols, the RED failure reason, the expected outcome, no unstated steps? — **PASS** [Clarity, tasks.md T002–T013; each RED names why it fails, each fix names the exact edit, T010 names run/compare/regenerate-again/check_ui, T011 names keep-rules and the report contents, T012/T013 name section, layout source and content]
- [ ] CHK012 - Do test tasks name the module they extend or create and the tier they run in? — **PASS** [Clarity, tasks.md T002/T004/T006/T009 + §Standing rules (fast tier)]

## Parallelism

- [ ] CHK013 - Is the one [P] pair (T012, T013) free of file overlap and hidden ordering (different inbox files, both working-tree, independent evidence)? — **PASS** [Consistency, tasks.md:129, Phase 6]
- [ ] CHK014 - Are tasks that share a file (T002/T003 same test module; T005/T007 same source module; T003/T007 both `checks.py`) correctly NOT marked [P] and ordered? — **PASS** [Consistency, tasks.md §Dependencies; all in strictly serial phases]

## Constraint Enforcement

- [ ] CHK015 - Is each binding constraint (no `step.py`/`pyproject.toml`/`uv.lock`/historical-docs/`external-ideas-*` edit; no retry/budget/timeout change; kroker-dev only; no attribution trailers) enforced by a standing rule, stop-guard, or diff gate rather than only stated? — **PASS** [Measurability, tasks.md:9-14 standing rules, SG-3, T014's FR-015 diff]
- [ ] CHK016 - Does the final verification task (T014) run every gate the quickstart names and record the comparison evidence (pass-count delta vs baseline, SG-5 list, commit shas)? — **PASS** [Completeness, tasks.md:120, quickstart.md §5]

## Format & Traceability

- [ ] CHK017 - Are all tasks checkbox items with sequential IDs T001–T014, no gaps or duplicates? — **PASS** [Clarity]
- [ ] CHK018 - Are [US] labels used only in story phases, with every story-phase task carrying one (T001/T014 correctly unlabeled)? — **PASS** [Consistency]
- [ ] CHK019 - Do phase checkpoints state a verifiable boundary state? — **PASS** [Measurability, tasks.md per-phase Checkpoint lines]
- [ ] CHK020 - Are the claimed counts arithmetically right — 14 tasks = 1+2+4+3+1+2+1 (setup/US1/US2/US3/US4/US5/verification), 8 commits = 1+1+2+2+1+0+1 matching the phase table and the pairing rules? — **PASS** [Consistency, tasks.md:29-37, :152]
- [ ] CHK021 - Are B5/B6 (T012, T013) stated as working-tree deliverables in git-ignored files with no commit, and is that verifiable (Phase 6 preamble; `git status --short docs/reports/` evidence; `.gitignore:4`)? — **PASS** [Measurability, tasks.md:103-114, spec A2]
- [ ] CHK022 - Is the list lean — nothing inflated (baseline and verification are the only overhead tasks, both evidence-producing) and nothing missing (other than the CHK004 gap)? — **PASS** [Completeness]
