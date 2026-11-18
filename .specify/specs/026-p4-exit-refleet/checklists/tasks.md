# Tasks Quality Checklist: Round 026 — P4 exit fixes + smaller re-fleet (tasks domain, pass 1)

**Created**: 2026-11-18 · **Artifact**: [tasks.md](../tasks.md) judged against [plan.md](../plan.md) REVISION 2 (approved, plan pass 2, 6 non-blocking notes) + [spec.md](../spec.md) (A-1..A-8) + research.md R1–R9 + data-model.md + quickstart.md · **Domain**: tasks
**Pass**: 1 · **Depth**: standard · **Audience/timing**: SPEC & PLAN REVIEWER, before implementation
**Method note**: `/speckit-checklist` run with arguments fixed by `reviewer-brief-tasks-1.md`; clarifying questions skipped (scope pinned by the brief; non-interactive role). No `before_checklist`/`after_checklist` hooks registered. Plan-pass verdict (approve, 6 non-blocking) was input; its note 5 (source guard targets reads) is verified pinned in T001 below.

## Coverage & Traceability (both directions)

- [x] CHK001 — Does every plan step (A1–A6, B) map to ≥1 task? [Traceability, plan "Step list" ↔ tasks] — A1→T001–T008 (incl. T007 docs and T008 re-score, the step's two named bullets); A2→T009–T010; A3→T011–T018 (incl. T017 parity proof and T018 offline read, both step bullets); A4→T019–T024; A5→T025–T026; A6→T027; B→T040–T052 — 7/7
- [x] CHK002 — Does every FR (20) and SC (8) map to ≥1 task? [Traceability] — FR-001→T001/T002; FR-002→T003–T006; FR-003→T005; FR-004→T003; FR-005→T008; FR-006→T009/T010; FR-010→T014–T017; FR-011→T012/T013; FR-012→T011+T027 diff guard; FR-020→T024; FR-021→T019/T020; FR-022→T021/T022; FR-023→T024; FR-030→T025/T026; FR-040→T016+T027; FR-050→T040; FR-051→T042–T048; FR-052→T041/T050; FR-053→T050; FR-054→T050 · SC-A1→T008; SC-A2→T012/T014/T016; SC-A3→T024; SC-A4→T026/T027; SC-B1→T044–T050; SC-B2→T050; SC-B3→T042/T043/T044–T049; SC-B4→T050
- [x] CHK003 — Is there no orphan task? [Coverage] — T001–T027 and T040–T052 each carry a requirement, story or step citation (T007→step A1 docs bullet + FR-001's stated-roots duty; T017→US A2 AS3; T018→US A2 independent test's offline half, spec H3)
- [x] CHK004 — Do task IDs realize the plan's forward references 1:1? [Traceability, plan "Traceability"] — plan cites T001–T002, T003–T006, T008, T009–T010, T011–T018, T019–T024, T025–T026, T016/T027, T040–T052, T008/T027, T050–T051; tasks.md delivers exactly T001–T027 + T040–T052 (T028–T039 reserved, never referenced)

## RED/GREEN Discipline

- [x] CHK005 — Is every Part A implementation task preceded by (or structured around) a RED task? [Consistency, tasks:10] — pairs: T001←T002, T003←T004, T005←T006, T009←T010, T012←T013, T014←T015, T019←T020, T021←T022 (conditional), T025←T026. Exemptions stated with proof: T011 move-only (unchanged-green merge tests + identity assertions), T007/T024 docs (mkdocs --strict; table shape), T008/T018 evidence-only, T017 is itself a proof test, T027 close-out. **T016 and T023 fold RED and GREEN into one task** — see Finding 1 (non-blocking)
- [~] CHK006 — Does every RED task carry an explicit failing command? [Clarity] — yes: T001 (`uv run pytest -q tests/test_runs_paths.py`), T003 (`-k "no_summary or smoke"`), T005 (`-k "roots or no_summary"`), T009 (`-k sc1`), T012, T014, T019 (ImportError), T021 ("It must FAIL today"), T025. T016 and T023 do not spell their RED command — Finding 1 (non-blocking)
- [x] CHK007 — Are GREEN/verification commands explicit per task? [Clarity] — every GREEN names its suites; T016 carries the full replay battery + golden rebaseline + file-size; T027 the full close-out battery

## Command & Path Exactness

- [x] CHK008 — Are all commands exact and runnable from repo root? [Clarity] — literal `tests/`/`src/` paths throughout (no alias-in-command defect); `python -m sdlc.cli` entry verified (pass 1); `scripts/check_golden_rebaseline.py`, `scripts/check_file_size.py` exist; T002's selector `-k "calibration or export or artifact_store or graph_store"` is non-vacuous (`tests/calibration/`, `tests/test_artifact_store.py`, `tests/graph/test_graph_store*.py`, export-named tests all exist); `uv run --no-sync mkdocs build --strict` runs on this host (mkdocs 1.6.1 present in `.venv`, `mkdocs.yml` exists — note it is a `docs`-extra tool, so a bare `--extra dev` env would need it installed first; on this shared tree it is)
- [x] CHK009 — Do all file paths resolve or are clearly new? [Clarity] — existing verified: the 8 resolver sites, `src/sdlc/stages/code/step.py` (977), `src/sdlc/benchmarks/sc_rollup.py` (418), `src/sdlc/stages/qa/activities.py` (`QAInput` :45-48, `run_test_suite` :378), `src/sdlc/vcs/integration.py` (`prepare_base_worktree` :232), `src/sdlc/stages/research/toolset.py` (:41, :108-131, :133-145), `src/sdlc/stages/review/step.py` (:75,133,207,151-167), `docs/operations/fleet-runs.md`, `.specify/specs/024-two-worker-pools/baseline-failures.txt`, `.workspace/tasks/2026-11-18-env-pollutes-cli-tests.md`, `tests/{code,qa,merge,review,research,replay,calibration}` dirs; new files clearly marked: `src/sdlc/runs_paths.py`, `src/sdlc/toolchain/lint_scope.py`, `src/sdlc/stages/code/attempt_failure.py`, `src/sdlc/stages/code/attempt_record.py` (contingency), `tests/test_runs_paths.py`, `tests/test_benchmark_evidence_roots.py`, `tests/code/test_autofix_checkpoint.py`, `tests/qa/test_task_lint.py`, `tests/code/test_task_lint_loop.py`, `tests/test_attempt_failure.py`, `tests/test_architect_research_degrade.py`, `tests/test_dotenv_isolation.py`, `triage.md`
- [x] CHK010 — Is the nearest AGENTS.md named for every slice touched? [Clarity, tasks:18] — code (T013), qa (T015), merge (T011), review (T016), workflows (T004), research (T021, "(if present)" — it is present); all six files verified to exist; the header names them all

## Ordering & Gating

- [x] CHK011 — Is T008 ordered after T006, T010 and T023? [Consistency, tasks:83,286] — yes, stated twice, with the reason (strict row and SC-3 rows print in the re-score)
- [x] CHK012 — Are the shared-file serializations declared? [Consistency, tasks:289] — `sc_rollup.py`: T006→T010→T023; `stages/code/step.py`: T016→T020; T002 "run it alone" (8 files)
- [x] CHK013 — Is Part B gated on T027 + T008 + GATE 2? [Consistency] — header line 8, checkpoint line 222, dependency chain line 291
- [x] CHK014 — Does run sequencing match B.3 (sequential until two done, then ≤2 overlap)? [Consistency] — T045 "sequential until runs 1 and 2 have both completed"; T046∥T047 the only overlap, restated in the parallel-execution section

## Specific checks fixed by the brief

- [x] CHK015 — T001 source guard targets *reads*; the `demo/__main__.py:56` write is allowed to stay. [Clarity, plan pass-2 note 5] — T001 spells exactly that: AST scan for reads (`.get`, subscript, `getenv`), "Writes are allowed: `src/sdlc/demo/__main__.py:56` *sets* `SDLC_EXPORT_ROOT` … and that stays", with the `tests/test_judge_literal.py` precedent
- [x] CHK016 — T002's 8 call sites match research R1 exactly. [Traceability] — identical list (observability/activities:28, artifacts/store:48, observability/decisions:83, calibration/store:110, demo/run:100, benchmarks/evidence:53, benchmarks/recorder:24, graph/store:109-110 via `explicit_export_root()`), all verified against code at plan pass 2; test-seam arguments preserved
- [x] CHK017 — T016 carries the replay proof, the golden-rebaseline STOP rule and the line budget. [Consistency, FR-040, R4] — `tests/replay` + `-m temporal -k "replay or golden"` + `scripts/check_golden_rebaseline.py`; "regenerate only if the diff is defaulted keys only, and otherwise STOP"; `check_file_size.py` with ≤1000 and the move-only `attempt_record.py` overflow
- [x] CHK018 — T021/T022 are conditional, evidence-first, and the catch is narrow. [Consistency, R6] — T021 settles the evidence from run 1's records/transcripts *before* writing the test, records it in the commit body, and defines the contradiction path (classify the row, skip T022, backlog card); the FunctionModel fixture matches the verified mechanism (run_code ×4 → `UnexpectedModelBehavior`), with the Monty-unavailable stub fallback; T022 catches `UnexpectedModelBehavior` only, "Do not catch bare `Exception`", OUR text only, docstring residual updated, GATE 2 surfaced
- [x] CHK019 — T040 pre-flight covers the 025 host fixes, containment/adversary off, and the full attendant duty. [Coverage, A-3/A-5, FR-050] — `KROKER_HARNESS_QUEUE=default`, safe.directory ×5, read-only `auth.json` bind, `--build-arg KROKER_COMMIT`; `adversarial_review_enabled` False and `containment_enabled` False *from a dumped cell config* (research R4's unverified item made pre-flight, exactly as the plan promised); attendant: gates **and** clarification waits, approve-only with REVISE-disclosed-as-steering, 30-min idle watchdog, 60-second cost polling, ledger on
- [x] CHK020 — T049's run-6 rule is the conjunction. [Consistency, A-5/A-7] — "only if fewer than 5 scored runs are SC-2-measured (summarized) **and** the remaining judge headroom is ≥ $1.73", with the "not affordable" record branch and the never-exceed-6 cap
- [x] CHK021 — T050's report contains deltas vs the T008 baseline, the CI, the three SC-3 rows, and the MergeVerdict disclosure. [Coverage, FR-052/053/054] — all present, plus roots line, one-commit assertion read by the rollup, strict companion, evidence tier, lint conversion read (025 3/3), failures/infra tables split, per-class loop triage from `failure.checks`, spend vs ceiling, honest-miss section
- [x] CHK022 — Safety rules are pinned. [Consistency] — header: never write to the 025 runs root or scratch-repos, work on `mktemp -d` copies, never `rm -rf` a variable-derived path; T008 and T018 copy; T051 removes the dedicated checkout "by its literal path"; T024 read-only on the 025 root

## Ops discipline (Part B)

- [x] CHK023 — Does every `[OPS]` task announce and leave evidence? [Coverage, B.6] — T040 preflight.md; T041 freeze recorded+announced; T042 announced with expected spend, stamp + measured cost; T043 ceiling re-announce with the re-derive-and-STOP rule (> $13.95) and per-run stops; T044's announce/post-run template inherited by T045–T048 ("same procedure"), each reporting outcome, class, cost, escalation count, `lint_clean`; T050 fleet-report.md + saved outputs; T051 verification §026-B + ROADMAP; T052 four card closes (T034 closed-by-026 note, `.env` card done, the calibration-glob backlog card from advisor D1, close-out card)
- [x] CHK024 — Are all stop rules present? [Consistency, FR-051/054, B.1] — infra → STOP (T040, T044); two-stop limit and smoke-counts rule inherited via 025 B.4–B.6 binding (header line 228) + T042's "counts toward the two-stop limit"; commit freeze T042→last scored run (header); run cap 6 (T049); `timeout` on a planned gate = infra, pre-registered (T044); miss recorded as a miss (T050 honest-miss)

## Verification evidence — spot-checks against code

| Claim | Location | Verdict |
|---|---|---|
| `src/sdlc/gate.py` exists (T027's FR-040 diff-guard path is real) | `src/sdlc/gate.py` | ✅ |
| All six named AGENTS.md files exist (code, qa, merge, review, workflows, research) | `src/sdlc/stages/*/AGENTS.md`, `src/sdlc/workflows/AGENTS.md` | ✅ |
| `_workflow_id()` helper for T016's `lint_key` | `src/sdlc/stages/code/step.py:78` | ✅ |
| T002's `-k` selector non-vacuous | `tests/calibration/`, `tests/test_artifact_store.py`, `tests/graph/test_graph_store{,_root}.py`, export-named tests | ✅ |
| `tests/research/` for T022's command | `tests/research/test_research_agent_retries*.py` | ✅ |
| mkdocs command runnable on this host | `.venv/bin/mkdocs` 1.6.1; `mkdocs.yml` | ✅ (docs-extra note above) |
| 8 resolver sites, golden script, size script, baseline file, fleet doc | verified at plan passes 1–2 | ✅ |

## Findings

1. **T016 and T023 fold RED and GREEN into single tasks, and their RED steps lack the explicit failing command — non-blocking.** The header rule (tasks.md:10) says every implementation task is "preceded by a RED task"; T016 ("RED first, in `tests/code/test_task_lint_loop.py`") and T023 ("RED, in `tests/test_benchmark_sc_rollup.py`") keep the fail-first intent and full case lists inside one task, but neither spells its RED command (T016: `uv run pytest -q tests/code/test_task_lint_loop.py` is inferable; T023 has no selector, e.g. `-k "sc3"`). Same class as 025 tasks pass-1 Finding 2, which was folded as a one-line fix. All other nine RED tasks carry explicit commands.
2. **T008's enumerated expected list omits `SC-1-strict 0.00` — non-blocking (cosmetic).** T008 asserts "the quickstart's expected list" (which contains it, quickstart:44) and enumerates a subset; T008 is ordered after T010, so the strict row prints. An implementer working from the enumeration alone would not assert it.

## Metrics

- Checklist items: 24 — pass 22, partial 2 (CHK005, CHK006, both halves of Finding 1), fail 0
- Steps covered: 7/7 (A1–A6, B) · FRs: 20/20 · SCs: 8/8 · orphan tasks: 0 · forward refs 1:1
- RED→GREEN: 9 explicit pairs + 2 conditional/folded (Finding 1) · exemptions with stated proof: 7
- Code spot-checks: 7 claim groups — 7 ✅, 0 ❌ (plus 22 carried from the plan passes, unchanged)
- BLOCKING gaps: 0 · non-blocking: 2

VERDICT: approve
