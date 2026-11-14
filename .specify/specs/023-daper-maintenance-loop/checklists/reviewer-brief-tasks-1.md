# Reviewer brief — round 023a tasks, pass 1

RESET: still feature 023 (DAPER, round 023a). Your plan pass-1 verdict was approve. The three minor notes were folded in: a catch-all disposition row, the configured-off quickstart bullet, and the cite fixes.

Role: SPEC & PLAN REVIEWER. Review advice only. Edit nothing except `checklists/tasks.md`. Make no git writes and run no test suite or temporal CLI.

Artifacts: `.specify/specs/023-daper-maintenance-loop/tasks.md`, judged against `spec.md`, `plan.md` (phases A–H, §Traceability), `research.md`, `data-model.md`, `contracts/*.md` and `quickstart.md`.

Do:
1. Run `/speckit-checklist` for the **tasks** domain. Write it to `checklists/tasks.md`.
2. Check, analyze-style:
   - **Format.** Every task follows `- [ ] T0NN [P?] [USn?] description with exact file path (size)`. Story labels appear only in story phases. IDs are sequential.
   - **Coverage.** Every plan step A1..H2, every FR-001..018 and every SC-001..007 is covered by at least one task. List any orphan.
   - **Test-first.** Every implementation task is preceded by a RED test task in the same story. The RED tasks assert the spec's acceptance scenarios, not implementation details.
   - **Sizing.** No task is L. No M task hides two unrelated deliverables (flag any that should split). The size summary matches the task lines.
   - **Dependencies.** The dependency section is consistent with the file overlaps, and the [P] markers are honest (no [P] pair writes the same file).
   - **Scope.** No 023b scope leaked in: no execute, PR, verification branch, memory retain, or deploy/rollback.
   - **Riders.** T029–T032 carry the riders exactly: the Option B override record with the intent doc addendum-only, the `ROADMAP.md:475` path, the AP-1.0 box, the ARCHITECTURE §7 note, and no PRD edit.
   - **Repo rules.** The 1000-line ceiling (`cli.py` 908), `tests/replay/AGENTS.md` (no new fixture writer, goldens untouched), and executor commit rules.
   - **Citations.** Spot-check at least 8 cited `file:line` refs.
3. Put the verdict on **line 1**: exactly `VERDICT: approve` or `VERDICT: fixes-needed`. Number the gaps below it, each with its task id.

Reply in the pane with only the verdict word.

## Pass 2 (2026-11-14)

All five pass-1 gaps are folded in. Tasks are renumbered T001–T037 (37 tasks: 24 S, 13 M).
1. T032–T034 (old T029–T031) lost [P]. They are sequenced T032→T033→T034 because all three write `ROADMAP.md`, and the riders line was removed from §Parallel.
2. The RED tests were split into their own tasks: T015 (render) before T016, T022 (inbox + R11 check) before T023, T030 (CLI nudge/disable) before T031. The header now names the only test-less tasks: T008 (pure move) and polish.
3. `MaintenanceKickInput` now lives in `S/maintenance/models.py` (T027 text, data-model.md), so T026→T027 depends on Phase 2 only.
4. T032 depends on T031 (US3 landed).
5. T013 parametrizes the per-kind SC-001 matrix (build_probe, dependencies advisory, secrets). T003 adds an advisory-finding seed helper at the pure tier.

Also new since pass 1: `main` merged FR-202 (`80692c1b`). T010/T018 now forward the maintainer's per-role validation retries via the VR-3a pattern (`S/workflows/assessment.py:685-695`). The role-wiring cites moved to `roles.py:132-133,226,310,338-339`. T034 fixes all four stale `sc_rollup` copies (`ROADMAP.md:475,479,482,486`).

Re-check those items, plus a fresh format, ID-sequence and placeholder sweep and a check that every cross-reference id points at the intended task after renumbering. Overwrite line 1 of `checklists/tasks.md` with the pass-2 verdict and append a "## Pass 2" section marking each gap resolved or open.
