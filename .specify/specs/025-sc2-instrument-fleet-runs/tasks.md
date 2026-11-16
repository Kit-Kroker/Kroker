# Tasks: SC-2 instrument and fleet runs — round 025

**Input**: `.specify/specs/025-sc2-instrument-fleet-runs/`: spec.md (US A1–A3, FR-001..015, FR-020..025, SC-A1..B4), plan.md (steps A–K), research.md R1–R9, data-model.md, quickstart.md.

**Two halves, one file.**
- **Part A = T001–T014**: code, one L crew round. Test-first.
- **Part B = T020–T033**: operations, **paid**. Starts only when Part A is merged and verified (T014) **and** GATE 2 is cleared. Tasks marked `[OPS]` are performed by the operator/orchestrator, not a coding crew, and each run task is **announced before it starts** (spec B.6).

**Tests**: REQUIRED. Every Part A implementation task is preceded by a RED task that must fail first; the commit body of the GREEN task shows the red→green. Part B tasks are guarded by evidence (files, command output) recorded in `verification.md` §025.

**Sizes**: **S** ≈ ≤30 min; **M** ≈ one focused sitting. No task is L.

**Executor rules (Part A)**: one commit per task with the task id in the subject; never `git add -A`, never stash, never revert files you did not create; shared tree. Read `src/sdlc/workflows/AGENTS.md` before any file under `src/sdlc/workflows/` (this round edits none). Paths are written out in full; commands run from the repo root with `uv run`.

**Standing constraints**: no workflow, gate, containment, `pre_tool`, env-allowlist or ADR-6 change; no new event kinds or signals; defaulted additive fields only; Part B changes no code and no tracked file except docs/verification written at the end.

---

## Part A — the instrument

- [x] **T001 [S] RED — gate raised_at.** In `tests/test_run_summary_build.py` add tests: a trace with `GATE_AWAITED` (seq a) then `GATE_DECIDED` human → `summary.gates[0].raised_at == awaited.at`; a bare+enriched merge double `GATE_DECIDED` after one `GATE_AWAITED` keeps `raised_at`; a policy-decided gate with no `GATE_AWAITED` → `raised_at is None`. Run `uv run pytest -q tests/test_run_summary_build.py -k raised_at` → FAIL. *(FR-001/002, US-A1 AS1)*
- [x] **T002 [S] RED — clarification times and marker.** In the same file: `CLARIFICATION_ASKED`/`ANSWERED` events give `ClarificationOutcome.raised_at/answered_at`; an unanswered question has `answered_at None`; every built summary has `operator_instrumented is True`. In `tests/test_run_summary_model.py`: a pre-025 JSON (no new keys) loads with `operator_instrumented False` and `raised_at None`. Run `uv run pytest -q tests/test_run_summary_build.py tests/test_run_summary_model.py -k "operator_instrumented or answered_at or legacy"` → FAIL. *(FR-001/005/010, AS4)*
- [ ] **T003 [S] Models.** Add the four defaulted fields per data-model.md to `src/sdlc/core/models.py` (`GateOutcomeSummary`, `ClarificationOutcome`, `RunSummary`). T002's legacy-load test goes GREEN; the others stay RED. `uv run pytest -q tests/test_run_summary_model.py`.
- [ ] **T004 [M] Builder.** `src/sdlc/observability/summary.py`: after the gate dedup loop build `{(gate, round): at}` from `GATE_AWAITED` and set `raised_at` on each gate (do NOT add to `_ENRICH_OPTIONALS`); set `raised_at/answered_at` on clarifications from the events; pass `operator_instrumented=True`. T001+T002 GREEN: `uv run pytest -q tests/test_run_summary_build.py tests/test_run_summary_model.py`. *(FR-001/002)*
- [ ] **T005 [M] RED — operator_time.** Create `tests/test_operator_time.py` (module `sdlc.benchmarks.operator_time` does not exist yet → import fails = RED). Run `uv run pytest -q tests/test_operator_time.py` → FAIL (ImportError). Cases: not_measured (marker false); zero (marker true, none human); measured: 4 min gate → engaged 240 s; 9 h gate → engaged 600 s, wait 32400 s; merge override with `decided_by="reviewer-name"` counts human; `timeout`/`policy` do not; a batch of 3 human-answered questions sharing raise/answer times is ONE interaction capped once; a human gate with `raised_at None` → not_measured; two overlapping gates sum (documented upper bound). *(FR-003/004/005, A.6)*
- [ ] **T006 [M] GREEN — operator_time.** Create `src/sdlc/benchmarks/operator_time.py` per data-model.md (`ENGAGEMENT_CAP_S = 600`, `Interaction`, `RunOperatorTime`, `operator_time(summary)`). Pure, no I/O. `uv run pytest -q tests/test_operator_time.py`.
- [ ] **T007 [M] RED — SC-2 rollup rows.** In `tests/test_benchmark_sc_rollup.py` add: SC-2 (shipped = `deployed:`/`merged-not-deployed:`) is the median in minutes with target `<=15 min`; SC-2-all over all scored runs; n/a below `MIN_RUNS` for each; not-measured runs excluded from n and counted in the note; the SC-2 note states definition, cap and the zero-interaction count; supplementary lines (human-touched median and max, uncapped wait median, SC-4 fraction beside, policy mix, evidence tier text when all gates are soft); all of it present in markdown, HTML and JSON. Run `uv run pytest -q tests/test_benchmark_sc_rollup.py -k "sc2 or evidence or policy_mix"` → FAIL. *(FR-006/007/008/012/013/015, A2, A3)*
- [ ] **T008 [M] GREEN — rollup.** `src/sdlc/benchmarks/sc_rollup.py`: add `_sc2`, `_sc2_all`, supplementary fields on `SCRollup`, renders. Keep the file < 450 lines. T007 GREEN; existing rollup tests unchanged-green. `uv run pytest -q tests/test_benchmark_sc_rollup.py tests/test_benchmark_score.py`.
- [ ] **T009 [S] RED — commit set.** In `tests/test_benchmark_sc_rollup.py`: records for runs `r1,r2` carry commit `aaa`, `r3` carries `bbb` → `commits == {aaa,bbb}` and `commit_flag` set; a summary with no matching record → flagged "commit unknown"; one commit → no flag. Run `uv run pytest -q tests/test_benchmark_sc_rollup.py -k commit` → FAIL. *(FR-014, FR-024)*
- [ ] **T010 [S] GREEN — commit set.** `build_sc_rollup` joins summaries to `records` on `run_id`, fills `commits/commit_flag` (BOTH flags: more than one commit, and a summary with no record), renders them. T009 GREEN.
- [ ] **T011 [S] Legacy and fixtures.** (a) `uv run pytest -q tests/test_fleet_fixture_fresh.py tests/test_dashboard_fleet_summary.py tests/test_run_summary_model.py tests/test_run_summary_build.py`: the drift guard is `tests/test_fleet_fixture_fresh.py::test_committed_fleet_snapshot_equals_a_fresh_build` over the committed fixtures in `interfaces/dashboard/frontend/src/api/__fixtures__/`. If it only gains defaulted keys, regenerate with `uv run python scripts/dump_dashboard_fixtures.py` and note which files changed. (b) Settle research R8: `grep -n "extra=" src/sdlc/core/models.py` for `RunSummary`/`GateOutcomeSummary`/`ClarificationOutcome`. *(FR-010)*
- [ ] **T012 [S] Replay proof.** `uv run pytest -q tests/replay` and `uv run pytest -q -m temporal -k "replay or golden"` (existing tests): green, no history change. If a replay test fails, STOP and report (a workflow-visible change slipped in).
- [ ] **T013 [M] Docs.** Create `docs/operations/fleet-runs.md`: definition of operator time and the 10-min cap; how a run emits it; the full B.2 pre-flight checklist; the pre-registered case/infra rule and sensitivity row; announcement and post-run templates; the stop rules; how `sdlc benchmark score` consumes a dedicated `SDLC_RUNS_ROOT`; the commit-freeze and dedicated-checkout rule. Add a link from `docs/operations/worker-pools.md`. Run the repo's docs checks if any (`grep -rn "docs-site\|mkdocs" pyproject.toml mkdocs.yml 2>/dev/null` and the documented link check). *(FR-020)*
- [ ] **T014 [M] Battery and A close-out.** `uv run pytest -q` (compare to `.specify/specs/024-two-worker-pools/baseline-failures.txt`; record the numeric baseline and result in verification.md; no new failures), `uv run ruff check . && uv run ruff format --check . && uv run mypy`. Write `.specify/specs/025-sc2-instrument-fleet-runs/verification.md` §025-A with each command and its result against quickstart "Part A". Name the fleet commit candidate (HEAD after merge). *(SC-A1..A3)*

**Checkpoint — Part A done.** Reviewer tasks checklist passed; Part A merged. Do not start T020 without GATE 2.

---

## Part B — the fleet runs `[OPS]`

All of Part B uses the **fleet commit** (HEAD after Part A merges and the docs land) in a dedicated clean checkout. **No commit lands between T022 and the last scored run.**

- [ ] **T020 [OPS][S] Pre-flight evidence.** Write `.specify/specs/025-sc2-instrument-fleet-runs/preflight.md` evidencing, with command output: re-read `src/sdlc/benchmarks/cli.py` verbs/flags (arm names, `--gate-policy`, `--arm`); doctor green; pools overlay up with harness cap ≥ 2 (`docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q` and `ps`); z.ai credentials; judge credential; research-provider key (cat-cafe, todo-api); `adversarial_review_enabled` resolves False; whether the worker image runs the checkout's code (research R7) — if it does not, STOP; `SDLC_RUNS_ROOT` fresh and dedicated. *(FR-021)*
- [ ] **T021 [OPS][M] Seed cases.** Create `/srv/scratch-repos/<case>` for todo-api-greenfield, deveval-readtime, deveval-lice, deveval-geotext, and (conditional) cat-cafe-monitoring, using the repo's seeding path; run `sdlc benchmark verify-case --case <id>` for each. cat-cafe unseedable or no research key → mark it replaced by a lice repeat in `preflight.md`. *(B.2.1, B.3)*
- [ ] **T022 [OPS][S] Freeze.** Create the dedicated checkout at the fleet commit; assert `git status --short` is empty; record the commit. Announce the freeze.
- [ ] **T023 [OPS][M] Smoke (paid, unscored, announced).** Announce: expected spend (two arms, 2 rubrics each, Anthropic judge), no prior. Run `sdlc benchmark smoke --gate-policy soft` with `SDLC_RUNS_ROOT` set. PASS writes the stamp. A case-difficulty failure STOPS for the owner (never `--skip-smoke` without a fresh go); an infra failure counts toward the two-stop limit. Record measured judge cost. *(B.9, FR-022)*
- [ ] **T024 [OPS][S] Ceiling.** From T023's measured judge cost, scale by rubric count (todo-api 2 rubrics × 2 arms; cat-cafe 5) and set the fleet ceiling at 1.5× the sum; state the per-run stop limit; state z.ai usage is recorded not capped. Announce the number; record it in `preflight.md`. If the judge line is non-trivial, the orchestrator announces it before run 1 as Q3 requires. *(B.6)*
- [ ] **T025 [OPS][M] Run 1: deveval-readtime, strong arm.** Announce (run no., case, arm, commit, expected cost, spend so far, ceiling left) → `benchmark run --case benchmarks/cases/deveval-readtime/case.yaml --arm zai-coding-plan-glm-5.3 --gate-policy soft` → the owner answers escalations → post-run report (outcome, class by the pre-registered rule, cost, interaction count). Infra class → STOP. *(FR-022/023)*
- [ ] **T026 [OPS][M] Run 2: deveval-lice** (same procedure; sequential until runs 1 and 2 have both completed).
- [ ] **T027 [OPS][M] Run 3: deveval-geotext** (same procedure; at most 2 concurrent from here).
- [ ] **T028 [OPS][M] Run 4: cat-cafe-monitoring**, or a lice repeat if T021 replaced it (same procedure; this run carries the Anthropic judge line).
- [ ] **T029 [OPS][M] Run 5: deveval-readtime repeat.**
- [ ] **T030 [OPS][M] Run 6: deveval-lice repeat.**
- [ ] **T031 [OPS][S] Run 7 decision (conditional).** If fewer than 5 runs are shipped and measured after run 6, run deveval-geotext once more (same procedure). Otherwise record "run 7 not needed". Do not exceed 7; do not extend the delegation.
- [ ] **T032 [OPS][M] Fleet score and report.** `SDLC_RUNS_ROOT=<dir> sdlc benchmark score --all`; save the outputs beside `fleet-report.md`: SC-1/2/3 each with value, n, target, met/missed, evidence tier; SC-2 shipped and all-scored; commit set (must be one); failures table (case) and `infra` table apart; the sensitivity row for any contested classification; per-case loop counts and first-pass rate for SC-3; total spend vs ceiling; an honest-miss section. *(FR-024/025, SC-B1..B4)*
- [ ] **T033 [OPS][S] Close P4.** Update `ROADMAP.md` SC-2 row (and SC-1/SC-3 rows, P4 line) with the measured read, citing the fleet report; if any SC is below target or not measurable, say so and propose the conditional round 026 (owner decides). Append §025-B to `.specify/specs/025-sc2-instrument-fleet-runs/verification.md`. Remove the dedicated checkout. *(FR-011: ROADMAP's SC rows already cite `src/sdlc/benchmarks/sc_rollup.py` (research R9), so no path rewrite is needed.)*

---

## Dependencies

T001→T003→T004; T002→T003→T004; T004→T005→T006→T007→T008→T009→T010→T011→T012→T013→T014. Part B: T014 → GATE 2 → T020→T021→T022→T023→T024→T025→T026→(T027–T030)→T031→T032→T033. T001/T002 may be written in parallel; Part B tasks T025–T030 are otherwise strictly announced and ordered as above.
