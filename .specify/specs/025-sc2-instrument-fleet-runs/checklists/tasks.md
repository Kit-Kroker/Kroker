# Tasks Quality Checklist: Round 025 — SC-2 instrument + fleet runs (tasks domain, pass 1)

**Created**: 2026-11-16 · **Artifact**: [tasks.md](../tasks.md) judged against [plan.md](../plan.md) + [spec.md](../spec.md) · **Domain**: tasks
**Pass**: 1 · **Depth**: standard · **Audience/timing**: SPEC & PLAN REVIEWER, before implementation
**Method note**: `/speckit-checklist` run with arguments fixed by `reviewer-brief-tasks-1.md`; clarifying questions skipped (scope pinned by the brief; non-interactive role). No `before_checklist`/`after_checklist` hooks registered. Plan-pass verdict (approve, 4 non-blocking) was input; fold-in of those gaps verified below.

## Coverage & Traceability (both directions)

- [x] CHK001 — Does every plan step A–K map to at least one task? [Traceability, plan "Step list" ↔ tasks] — A→T001–T003, B→T004, C→T005/T006, D→T007–T010, E→T011–T014, F→T014, G→T020–T022, H→T023/T024, I→T025–T031, J→T032, K→T033 — 11/11
- [x] CHK002 — Does every FR (21) and SC (7) map to at least one task? [Traceability, plan "Traceability" ↔ tasks] — FR-001/002→T001/T002/T004; FR-003..005→T005/T006; FR-006..008→T007/T008; FR-009/010→T011/T012/T014; FR-011→T033; FR-012..015→T007–T010; FR-020→T013; FR-021→T020–T022; FR-022→T023/T025–T031; FR-023→stop rules; FR-024→T009/T010/T032; FR-025→T032; SC-A1..A3→T014 (+ their Part A tasks); SC-B1..B4→T025–T032
- [x] CHK003 — Is there no orphan task (every task traces to a step/FR/SC)? [Coverage] — T001–T033 each carry a requirement or protocol citation; none orphaned
- [x] CHK004 — Do task IDs realize the plan's forward references 1:1? [Traceability] — plan cites T001–T014, T020–T033; tasks.md delivers exactly those (T015–T019 intentionally never referenced)

## RED/GREEN Discipline

- [x] CHK005 — Is every Part A implementation task preceded by a RED task? [Traceability, tasks "Tests" rule] — T003/T004 ← T001/T002; T006 ← T005; T008 ← T007; T010 ← T009
- [~] CHK006 — Does every RED task carry an explicit failing command? [Clarity] — T001 yes (`uv run pytest -q T/test_run_summary_build.py -k raised_at`); T002/T005/T007/T009 state the target file(s) and expected FAIL but not the command — see Finding 2 (non-blocking)
- [x] CHK007 — Are the GREEN/verification commands explicit per task? [Clarity] — T003, T004, T006, T008 name them; T011–T014 name suites/commands

## Command & Path Exactness

- [~] CHK008 — Are all test commands exact and runnable from the repo root? [Clarity] — two defects: the `T/`/`S/` aliases appear *inside* command strings (declared at tasks.md:13 but not literally runnable — Finding 3, non-blocking) and T011's fixture selector is wrong (Finding 1, BLOCKING)
- [x] CHK009 — Are file paths exact for every code/doc artifact? [Clarity] — all Part A paths resolve (`src/sdlc/core/models.py`, `src/sdlc/observability/summary.py`, `src/sdlc/benchmarks/sc_rollup.py`, new `operator_time.py`, `docs/operations/worker-pools.md` exists; new `docs/operations/fleet-runs.md`); case paths `benchmarks/cases/{deveval-readtime,deveval-lice,deveval-geotext,cat-cafe-monitoring}/case.yaml` all exist; `docker-compose.pools.yml` exists; `.specify/specs/024-two-worker-pools/baseline-failures.txt` exists (T014 anchor valid)
- [~] CHK010 — Is `verification.md`'s location unambiguous? [Clarity] — repo convention is the per-round spec dir (024 has `.specify/specs/024-two-worker-pools/verification.md`); T014/T033 should name `.specify/specs/025-sc2-instrument-fleet-runs/verification.md` — Finding 4 (non-blocking)

## Dependencies, Ordering & Gating

- [x] CHK011 — Is RED ordered before GREEN, including T003's partial-green (T002 legacy test) correctly stated? [Consistency, tasks "Dependencies"]
- [x] CHK012 — Is Part B gated behind T014 AND GATE 2? [Consistency, plan "Shape"] — explicit checkpoint (tasks.md:36) + dependency chain `T014 → GATE 2 → T020`
- [x] CHK013 — Does run sequencing match B.4 rule 4 (sequential until two done, then ≤2; in-flight finish on stop)? [Consistency, T026/T027 notes]
- [x] CHK014 — Are task sizes plausible with none L? [Completeness] — all S/M; T008 additionally guards `sc_rollup.py < 450` lines

## Part B Ops Discipline

- [x] CHK015 — Does every `[OPS]` task have an announce step and an evidence artifact? [Coverage, spec B.6] — preflight.md (T020/T021/T024), stamp+cost (T023), per-run announce/report template (T025, inherited by T026–T031), fleet-report.md (T032), verification §025-B (T033)
- [x] CHK016 — Are all stop rules present: infra stop halts, two-stop limit, run cap 7, commit freeze T022→last run, smoke failure stops for owner (never `--skip-smoke` without fresh go)? [Consistency, FR-022/023, B.4/B.6/B.9] — T023 (both limits), T025 ("Infra class → STOP"), T031 ("Do not exceed 7; do not extend"), Part B header freeze
- [x] CHK017 — Are all B.2 prerequisites covered before run 1? [Coverage, spec B.2] — 1 seed→T021; 2 overlay/doctor/cap→T020; 3 stamp+clean tree→T022/T023 (before T025); 4 fresh `SDLC_RUNS_ROOT`→T020; 5 credentials (z.ai, judge, research)→T020

## Scope Safety

- [x] CHK018 — Does no task change workflow/trust-layer code or add events/signals? [Consistency, FR-009, tasks standing constraints] — Part A file set: core/models.py (defaulted fields), observability/summary.py, new pure benchmarks/operator_time.py, benchmarks/sc_rollup.py, tests, docs; T012 guards replay; executor rule flags `S/workflows/` as untouched

## Verification evidence — spot-checks against code

| Claim | Location | Verdict |
|---|---|---|
| CLI verb `run` with `--gate-policy`/`--arm`; `score` with `--all` | `src/sdlc/benchmarks/cli.py:74-86, 112-117` | ✅ |
| CLI verb `smoke` with `--gate-policy` | `src/sdlc/benchmarks/cli.py:420-424` | ✅ |
| CLI verb `verify-case` (registered in the *top-level* CLI, not benchmarks/cli.py) | `src/sdlc/cli.py:327, 652-655` | ✅ (note: T020's re-read names only `S/benchmarks/cli.py`; the fleet's own verbs all live there, but verify-case/import-deveval live in `S/cli.py`) |
| `--arm` name `zai-coding-plan-glm-5.3` matches arm derivation | `src/sdlc/benchmarks/matrix.py:23-39` (family + "-" + model) | ✅ |
| T011 fixture claim: summary fixtures under `T/fixtures`, selector catches drift | `tests/fixtures/` (no RunSummary JSONs); committed dashboard fixtures at `interfaces/dashboard/frontend/src/api/__fixtures__/` (`scripts/dump_dashboard_fixtures.py:28`); drift guard is `tests/test_fleet_fixture_fresh.py::test_committed_fleet_snapshot_equals_a_fresh_build` | ❌ — see Finding 1 |
| `-k` selector reality: T001 `raised_at` (new tests, fine); T012 `-m temporal -k "replay or golden"` non-vacuous; T011 selector misses | `tests/replay/` exists, 9 files carry `pytest.mark.temporal` (incl. `test_graph_golden.py`, `test_pools_replay.py`); no test/module name anywhere contains `dashboard_fixture` | T012 ✅; T011 ❌ |
| Baseline anchor exists | `.specify/specs/024-two-worker-pools/baseline-failures.txt` | ✅ (folds plan-checklist Gap 4 into a repo-resolvable file) |

Fold-in of the plan checklist's four non-blocking gaps: Gap 2 → T024 ("z.ai usage is recorded not capped") ✅; Gap 3 → T009/T010 ("BOTH flags", RED test for no-record case) ✅; Gap 4 → T014's named baseline file ✅; Gap 1 (FR-011 annotation) → T033 implements the amended intent but carries no explicit "path already correct (R9/B.9)" note — cosmetic, Finding 5.

## Findings

1. **T011 fixture-drift step mis-targets the real fixture surface — BLOCKING.** (a) The selector `-k "dashboard_fixture or fleet_summary or run_summary"`: the `dashboard_fixture` disjunct matches no test or module name in the repo, and the actual drift guard — `tests/test_fleet_fixture_fresh.py::test_committed_fleet_snapshot_equals_a_fresh_build` — is matched by none of the three disjuncts, so the stated purpose ("run the fast tier for fixture-dump drift") executes nothing that checks drift. (b) "Load every existing summary fixture under `T/fixtures`": `tests/fixtures/` contains benchmark records/opencode jsonl/reference repos — no `RunSummary` JSONs; the committed dashboard fleet-snapshot fixtures live at `interfaces/dashboard/frontend/src/api/__fixtures__/` (`scripts/dump_dashboard_fixtures.py:28`). As written, R8's fixture-pin risk (a named research risk with a backlog item) is not exercised at T011 and would instead surface as a red full battery at T014, after the intended regeneration point. Fix is one line: name `tests/test_fleet_fixture_fresh.py` + the interfaces fixture dir (or change the selector to `-k "fleet_fixture or fleet_summary or run_summary"`).
2. **RED tasks T002, T005, T007, T009 lack the explicit failing command — non-blocking.** Only T001 spells one. Target files and expected FAIL are named; GREEN commands exist. Add the command lines for uniformity.
3. **`T/`/`S/` aliases inside command strings — non-blocking.** e.g. `uv run pytest -q T/test_run_summary_build.py -k raised_at` is not literally runnable until `T/` → `tests/` is substituted (alias declared at tasks.md:13). Spell real paths inside backticked commands.
4. **`verification.md` location unspecified — non-blocking.** 024 precedent puts it in the round's spec dir; T014/T033 should name `.specify/specs/025-sc2-instrument-fleet-runs/verification.md` so it is not created at the repo root.
5. **FR-011 note not carried into T033 — non-blocking (cosmetic).** T033 performs B.9's amended rider correctly (update SC-2/SC-1/SC-3 rows + P4 line; no stale-path rewrite), but the one-line "path already correct (R9/B.9)" note suggested at plan pass was not added.

## Metrics

- Checklist items: 18 — pass 15, partial 3 (CHK006, CHK008, CHK010), fail 0 (CHK008's failure half recorded as Finding 1)
- Steps covered: 11/11 · FRs: 21/21 · SCs: 7/7 · orphan tasks: 0
- RED→GREEN pairs: 4/4 (command explicit in 1 + 3 partials)
- Code spot-checks: 7 claim groups — 5 ✅, 2 ❌ (both halves of Finding 1)
- BLOCKING gaps: 1 · non-blocking: 4

VERDICT: fixes-needed

# Pass 2

**Date**: 2026-11-16 · **Input**: tasks.md amended per pass-1 findings 1–5 (per `reviewer-brief-tasks-1.md` PASS 2). Re-verification of the folds only, plus a regression scan of the rest of the file.

- [x] CHK019 — Was Finding 1 (T011 fixture mis-targeting) fixed? [Traceability, tasks.md T011] — yes: T011 now names the real drift guard (`tests/test_fleet_fixture_fresh.py::test_committed_fleet_snapshot_equals_a_fresh_build`), the real fixture dir (`interfaces/dashboard/frontend/src/api/__fixtures__/` — matches `scripts/dump_dashboard_fixtures.py:28`), the documented regeneration command (`uv run python scripts/dump_dashboard_fixtures.py`), and R8 is settled by a direct `grep -n "extra=" src/sdlc/core/models.py`. The dead `-k` selector and the `T/fixtures` summary-fixture claim are gone. All four named test files exist.
- [x] CHK020 — Was Finding 2 (missing RED commands) fixed? [Clarity] — yes: T002 (`-k "operator_instrumented or answered_at or legacy"`), T005 (`→ FAIL (ImportError)`), T007 (`-k "sc2 or evidence or policy_mix"`), T009 (`-k commit`) all carry explicit failing commands now.
- [x] CHK021 — Was Finding 3 (aliases inside commands) fixed? [Clarity] — yes: header rule changed to "Paths are written out in full"; every command now uses literal `tests/`/`src/` paths; no `S/`/`T/` tokens remain anywhere in the file.
- [x] CHK022 — Was Finding 4 (`verification.md` path) fixed? [Clarity] — yes: T014 writes and T033 appends to `.specify/specs/025-sc2-instrument-fleet-runs/verification.md` (matches the 024 convention).
- [x] CHK023 — Was Finding 5 (FR-011 note) fixed? [Traceability, tasks.md T033] — yes: T033 carries the note "(FR-011: ROADMAP's SC rows already cite `src/sdlc/benchmarks/sc_rollup.py` (research R9), so no path rewrite is needed.)"
- [x] CHK024 — Regression scan: did anything else change or break? [Consistency] — dependencies chain, T014→GATE 2 gate, checkpoint, standing constraints, task sizes (none L), coverage mapping, stop rules, T012's verified `-m temporal -k "replay or golden"`, and all pass-1-verified commands are unchanged and intact.
- [~] CHK025 — Is the amended text clean? [Clarity] — one new cosmetic defect introduced by the fold-in: T005 duplicates the RED command sentence ("Run `uv run pytest -q tests/test_operator_time.py` → FAIL (ImportError)." appears twice back-to-back). Harmless — same command, no semantic effect.

## Pass 2 findings

1. **T005 duplicated command sentence — non-blocking (cosmetic).** Introduced by the fold-in; delete one instance. No other changes needed.

## Pass 2 metrics

- Pass-1 findings fixed: 5/5 · regression: none · new findings: 1 (non-blocking, cosmetic)
- BLOCKING gaps: 0 · non-blocking: 1

VERDICT: approve
