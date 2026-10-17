# Verification: Corpus Acceptance (Round 015, Phase 3 — Code Half Close-Out)

**Date**: 2026-10-11
**Branch**: `015-corpus-acceptance`
**Worktree**: `D:\own\Kroker-wt015`
**Base Commit**: `77c89885` (on top of main `c3f6319c`)
**Commit Under Verification**: T017 (`fc72ecc7`) / T018 close-out

---

## 1. Full Gates Against T001 Baseline

### Container Test Runs (`docker exec -w /app kroker-dev ...`)

| Check | Baseline (T001) | T018 Seen | Status / Delta |
|---|---|---|---|
| `uv run pytest` (fast unit tier) | 6038 passed, 3 failed, 9 errors, 12 skipped, 263 deselected (757.61s) | Shared root (moment ~18:00): 6154 passed, 5 failed, 9 errors<br>Shared root (moment ~23:55): 6136 passed, 24 failed, 9 errors<br>Clean 111-file snapshot: 6154 passed, 4 failed (0 stored pin failures) | **BLOCKED ON SHARED ROOT**<br>(Branch clean in isolation; 16/16 stored pins pass against 111-file snapshot. Shared root contaminated by external live run.) |
| `uv run pytest -m slow tests/test_benchmark_offline_checks.py tests/test_cat_cafe_case.py tests/test_deveval_verify.py` | N/A (new suites in round 015) | 5 passed, 14 deselected in 155.61s (clean snapshot) | **PASS** |
| `uv run pytest -m temporal tests/replay` | 32 passed, 21 skipped, 171 deselected, 138 warnings (118.80s) | 32 passed, 21 skipped, 171 deselected, 138 warnings in 193.24s (clean snapshot) | **PASS** (reproduces golden traces exactly; warnings match baseline 138) |
| `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | 5 passed in 26.75s | 5 passed in 48.22s (clean snapshot) | **PASS** |
| `uv run ruff check .` | All checks passed! (0 issues) | All checks passed! (0 issues) | **PASS** |
| `uv run ruff format --check .` | 1726 files already formatted | 1743 files already formatted | **PASS** (clean) |
| `uv run mypy` | Success: no issues found in 394 source files | Success: no issues found in 400 source files | **PASS** (0 errors) |

#### Fast Tier Breakdown: Moment-in-Time Runs vs Isolated Snapshot

1. **Moment-in-Time Executor Run (~18:00)**:
   - 6154 passed, 5 failed, 9 errors, 12 skipped, 265 deselected (1402.69s).
   - 3 baseline worktree path failures (`test_superpowers_scratch_is_still_ignored`, `test_unchanged_prompt_passes_without_calling_a_model`, `test_resolve_instructions_git_ref_reads_from_git`).
   - 9 baseline mount permission errors in `/app/runs` (`test_eval_mutation_seam.py`, `test_promptfoo_config.py`).
   - 1 runner load import timing failure (`test_provider_imports_fast_enough_for_the_promptfoo_worker`).
   - 1 stored-score pin failure (`tests/test_benchmark_stored_scores.py::test_stored_todo_api_three_groups`: saw 4 groups instead of 3 due to external live run).

2. **Moment-in-Time Reviewer Run (~23:55) — Contamination Growth**:
   - 6136 passed, 24 failed, 9 errors, 12 skipped, 265 deselected.
   - External run in host directory `runs/benchmarks/bench-todo-api-greenfield-1791746672` continued executing, writing 48 lines with last write at 23:53.
   - Appended records contain `scope: 'axis'` and `judge: 'axis'` which `BenchmarkRecord` does not recognize in round 015.
   - Because `test_benchmark_stored_scores.py` parses all `runs/benchmarks/**/*.jsonl`, 15 of 16 stored PIN tests failed against the contaminated shared mount.

3. **Isolated Snapshot Verification (`SDLC_BENCHMARKS_ROOT=/tmp/clean-records`)**:
   - When tested against an isolated directory containing strictly the 111 baseline manifest files:
     * `tests/test_benchmark_stored_scores.py`: **16 of 16 PASSED** (branch code fully exonerated; round 013 pins intact).
     * `tests/doctor/test_doctor_cli.py`: **10 of 10 PASSED** (deferred CLI imports fix verified).
     * Slow tier: **5 passed, 14 deselected in 155.61s**.
     * Temporal replay: **32 passed, 21 skipped, 171 deselected, 138 warnings in 193.24s** (warnings match baseline 138 exactly; 147 warnings seen earlier was caused by the external run).
     * Temporal sequence: **5 passed in 48.22s**.
     * Ruff check / format / mypy: All clean.

4. **Handoff Condition**:
   - The branch code is proven clean and free of regressions against the 111-file baseline.
   - However, the shared records root remains contaminated by an active external run.
   - Merge to `main` and Batch R0 clearance are **BLOCKED** pending an orchestrator ruling to quarantine the external run file (or wait out the run) and re-verify the full gate on the restored root.

---

### Host Checks

| Check | Baseline (T001) | T018 Seen | Status |
|---|---|---|---|
| `python scripts/check_file_size.py` | Exit 0 | Exit 0 | **PASS** (hard 1000-line ceiling preserved across all authored code) |
| `python scripts/check_clauses.py` | 202 clauses declared, 10 untested, 0 dangling | 202 clauses declared, 10 untested, 0 dangling | **PASS** (clean; no untracked clauses or dangling references) |
| Records Fingerprint | `111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831` | `111 2a32da9727fb...` on baseline manifest; 112 on disk (`112 1b335cac...`) | **PASS** (reconciled per reviewer and orchestrator ruling; baseline manifest matches 111/111 baseline records exactly) |
| `git ls-files runs/` | Empty | Empty | **PASS** (no files under `runs/` tracked in git) |

---

## 2. Stored Cat-Cafe Scoring and Root-Cause Analysis

Command executed:
`python -m sdlc.cli benchmark score --case cat-cafe-monitoring --out /tmp/cat-cafe-score`

All 19 score artifacts written to destination, including `root-cause.html` and `root-cause.json`.

### Root-Cause Metrics Observed
- **Runs Started**: 18
- **Lost Runs**: 8 (all 8 classified under `planning`, matching FR-021: stage before code)
- **Finished Graded Runs**: 10
- **Unmapped Requirement Test Failures**: `no_requirement_results: 10` (the 10 historical runs were graded against the legacy 12-test oracle prior to requirement mapping; tracked separately without false attribution, matching §4.4)
- **Labelled by person**: 0
- **Unlabelled**: 0
- **Root-Cause Table**:
  * `zai-coding-plan-glm-5.2 (pre012)`: planning `8/18`, execution `0/18`, verification `0/0 (low_n)`, unattributed `0/0 (low_n)`
- **Round 013 Scorecard / Heatmap Invariants**: Verified intact; exact figures preserved without drift.

---

## 3. Success Criteria Evaluation (SC-001 to SC-012)

| Criterion | Description | Evidence / Verification | Status |
|---|---|---|---|
| **SC-001** | Offline acceptance green (ref passes all, floor passes fewer) for cat-cafe and DevEval cases with no worker, server, or model call. | Cat-cafe (ref 36/36, floor 0/36); geotext (ref 9/9, floor 0/2); hone (ref 12/12, floor 0/3); pso (ref 6/6, floor 0/3); readtime (ref 12/12, floor 0/4); stocktrends (ref 9/9, floor 0/4).<br>**Note on `deveval-lice` (SG-10)**: rejected with `reason: reference` (30/31 passed; `test_package_template` upstream defect, reproduced by `verify-case`, not repaired per GATE 2 item 4). Per orchestrator ruling: committed as-is, keeps role `corpus`, excluded from R1 screening. | **PASS** |
| **SC-002** | Saturated fixture yields `rejected / saturated`; todo-api itself yields `rejected / reference`. | Proven in tests: `tests/test_benchmark_acceptance.py::test_separation_strong_all_1_gives_rejected_saturated` verifies `rejected / saturated`; `tests/test_benchmark_cli.py::test_dispatch_accept_smoke_case_with_oracle_and_no_reference_gives_rejected_reference` verifies todo-api reads `rejected / reference`. | **PASS** |
| **SC-003** | Cat-cafe oracle has 30–40 tests, each in exactly one requirement; reference passes all; empty tree passes none. | Oracle has 36 tests across all 15 requirements (FR-026/027); reference passes 36/36; floor passes 0/36. Verified in `tests/test_cat_cafe_case.py`. | **PASS** |
| **SC-004** | With no stamp, starting corpus case refused in <5s; with valid stamp, starts. | Proven in `tests/test_benchmark_cli.py`: missing stamp raises `SystemExit` in <5s without network; valid stamp allows run to proceed. | **PASS** |
| **SC-005** | Scoring cat-cafe on stored records shows 8 lost runs under planning in root-cause view; round 013 figures unchanged. | `sdlc benchmark score --case cat-cafe-monitoring` output verified: 8 lost runs under planning; 10 finished runs tracked under `no_requirement_results`; round 013 figures unchanged. | **PASS** |
| **SC-006** | All 111 baseline record files byte-identical at end of round. | `baseline-records.sha256` manifest verifies 111/111 files matching base sha256 `111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831`. | **PASS** |
| **SC-007** | Every case on disk has role and visibility; every corpus case has committed acceptance record matching oracle identity. | All 10 cases have `role` and `visibility` in `case.yaml`. All 7 corpus cases have committed `acceptance.yaml` matching `oracle_identity`. Verified by `test_committed_records_match_their_cases`. | **PASS** |
| **SC-008** | Round closing report states "N of 8 accepted or provisional, M of 2 private" from committed records; lists parked cases. | `sdlc benchmark corpus` outputs `0 of 8 accepted or provisional, 0 of 2 private`, honestly reflecting offline acceptance state; lists `deveval-lice` rejected (reference); 0 parked. Documented in `BENCHMARK.md` §5.1 and `ROADMAP.md`. | **PASS** |
| **SC-009** | Zero files from NL2Repo-Bench in repo; licence note records inspection. | Zero files imported from NL2Repo-Bench. Dated licence note committed at `.specify/specs/015-corpus-acceptance/licence-nl2repo.md` with same-day re-checks. | **PASS** |
| **SC-010** | No verdict of `accepted` recorded on fewer than three graded runs per arm. | Proven in `tests/test_benchmark_acceptance.py`: one run per arm gives `provisional`; three runs on one arm and two on other gives `provisional`; only 3+ per arm with margin >= 0.15 gives `accepted`. | **PASS** |
| **SC-011** | (If R1 runs) each of the six DevEval cases has a screening result or `no result`, and a role that follows. | **Awaits runs** (blocked on explicit orchestrator clearance for Batch R1). | **Awaits runs** |
| **SC-012** | (If R2 runs) cat-cafe has one graded run per arm on the grown oracle and a separation verdict. | **Awaits runs** (blocked on explicit orchestrator clearance for Batch R2). | **Awaits runs** |

---

## 4. Upstream Defect Finding: `deveval-lice` (SG-10)

During T016 offline acceptance checks, `deveval-lice`'s reference solution failed `tests/test_package_template.py::test_package_template_without_year` (1 of 31 tests failed; 30/31 passed).
- **Root Cause**: Upstream defect in DevEval's imported test fixture/reference code, reproduced independently by `sdlc benchmark verify-case --case deveval-lice`.
- **Ruling applied**:
  1. Per GATE 2 item 4 ("do not repair upstream defects in imported cases"), the reference was not modified.
  2. The acceptance record was committed as-is: `verdict: rejected`, `reason: reference`, naming `test_package_template` in the note.
  3. `deveval-lice` retains `role: corpus` in `benchmarks/cases/deveval-lice/case.yaml` (not parked).
  4. Per orchestrator ruling, `deveval-lice` is excluded from the upcoming Batch R1 screening run.

---

## 5. Records Fingerprint Reconciliation

- **Baseline Manifest**: `.specify/specs/015-corpus-acceptance/baseline-records.sha256` covers exactly 111 record files matching the baseline fingerprint:
  `111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831`
- **External Run Artifact**: During round 015 execution, an external live-run process wrote a single record file `bench-todo-api-greenfield-1791746672/todo-api-greenfield#opencode#zai-coding-plan-glm-5.2.jsonl` to the primary checkout directory (`D:\own\Kroker\runs\benchmarks`). This file appended an unmapped record (`scope: axis`, `judge: axis`) not defined in the baseline schema.
- **Clean Snapshot Verification**: When tested against an isolated snapshot containing strictly the 111 manifest files (`SDLC_BENCHMARKS_ROOT=/tmp/clean-records`), 16 of 16 stored-score pin tests in `tests/test_benchmark_stored_scores.py` pass completely.
- **Invariants**: No baseline file was modified, overwritten, or deleted. All 111 baseline files remain byte-identical. No files under `runs/` are tracked by git.

---

## 6. Conclusion & Handoff to Orchestrator

The code half of Round 015 (Tasks T001 through T018) is **fully implemented, tested, and documented**:
- All round 015 logic, CLI commands, test suites, and docs are complete.
- Branch code is fully exonerated against the isolated 111-file baseline snapshot (16/16 stored score pins pass).
- Success criteria SC-001 through SC-010 are satisfied with verifiable evidence; SC-011 and SC-012 await run batches R1 and R2.

### Gate Status & Handoff Condition (SG-1 / SG-5)
- **External Run Contamination**: An external pipeline run (`bench-todo-api-greenfield-1791746672`) from another process is actively executing against the primary checkout's `runs/benchmarks/` root, appending unmapped `scope: 'axis'` records that fail stored-score parsing.
- **Merge & Run Clearance Blocked**:
  * Merge to `main` is **BLOCKED** pending an orchestrator ruling to quarantine the external file out of the records root (or wait out the run) and re-verify the full fast tier on the restored root.
  * Phase 12 (Run Batches R0–R3, Tasks T019–T023) remains strictly blocked per SG-5 until the orchestrator issues explicit batch clearance.

---

## 7. Addendum (2026-10-13): R0 attempts, defect bundle D-A..D-D, and the repeat

**Merge note first**: the block in §6 was resolved (the external run finished;
root re-verified), the code half merged, and Phase 12 cleared for R0.

### 7.1 Attempt timeline

| # | Run | Pin | Verdict | Failed condition |
|---|---|---|---|---|
| 1 | `bench-todo-api-greenfield-1791808170` | `91cff98f` | FAIL | `oracle_all_pass` |
| 2 | `bench-todo-api-greenfield-1791839267` | `91cff98f` | FAIL | `oracle_all_pass` |
| 3 | `bench-todo-api-greenfield-1791883560` | `80e787dc` | FAIL | `rubric_scores` (external — §7.4) |
| 4 | `bench-todo-api-greenfield-1791897241` | `80e787dc` | FAIL | `rubric_scores` (external — §7.4) |
| 5 | `bench-todo-api-greenfield-1791922358` | `ccfe0a64` | FAIL | `rubric_scores` (external, reason on record — §7.4) |
| 6 | `bench-todo-api-greenfield-1791960889` | `736dd591` | **PASS** | — |

Attempts 1–2 surfaced four defects (D-A..D-D). Per T019/D-12 the fixes are
code changes on `main` (`f2739c15`, `24896c1f`, `aafb3139`, `f772ca52`,
`80e787dc`), and attempt 3 reran R0 from a detached worktree of the new pin
with the rebuilt worker image. Attempt 4 re-ran the same pin after a
pre-dispatch probe of the judge endpoint returned HTTP 200. After two
consecutive rubric-503 losses the orchestrator chose judge hardening over a
blind re-roll: attempts 3–5 lost **5 of 5 real rubric calls** to the same
`gemini-3.5-flash` UNAVAILABLE 503 at hours spread across the day. The
hardening landed as `e9b732d1` (transient-HTTP + read-timeout retry with
5/30/120 s backoff, dedicated `JUDGE_ACT` activity budget, `QualityScore.
detail` persisted as the record's `error` on the four stage sites) plus
`ccfe0a64` (timeout coverage; attempt 5's pin). Attempt 5's records then
carried the reason inline (§7.4). With saturation confirmed as the model's
chronic state, the orchestrator moved the case judge to
`google:gemini-3.8-flash` (`736dd591`), and attempt 6 passed all four
smoke conditions.

### 7.2 Defects and root causes

| # | Defect | Root cause | Fix |
|---|---|---|---|
| D-A | `check_smoke` condition 4 swept every record with `stage=='oracle'`, so six task-level error grades failed the smoke while the case-level oracle graded 6/6 | checker overreach | condition reads `scope=ORACLE` only (`f2739c15`) |
| D-B | live grades wrote all six `oracle_task` records as `judge='error', score=None, error=null`; identical code+branch graded perfectly on demand | **stale host-compiled bytecode rode into the grade environment**: `.dockerignore`'s `__pycache__/` is root-anchored (unlike `.gitignore`), so `COPY benchmarks` baked Windows-compiled pycs into the worker image; `grade_oracle`'s plain `copytree` carried them into the grade worktree; matching py313+pytest-9.1.1 tags and preserved mtime/size meant no recompile, so every code object kept its Windows `co_filename`; pytest's legacy junit `file` attribute follows `co_filename` (`Function.reportinfo` → `getfslinno`), so every oracle node id came out as the compiling host's absolute path and every `tasks.yaml` mapping missed. The reason existed in `TaskGrade.detail` but was dropped at record write, and the junit died with the temp worktree — hence "invisible without instrumented recording" | `copy_case_tree` (no `__pycache__`/`*.pyc`) at all three oracle copy sites; nested `**/__pycache__///**/*.pyc` dockerignore patterns; error-grade reason + observed report keys persisted on the record (`24896c1f`). Proven by a single-variable worker replay: with the cache, `file="D:\own\..."` and six error grades; without it, `file="oracle/test_crud.py"` and six `1.0 oracle` |
| D-C | axis measured with an empty rule set in the worker | two halves: `rules/`+`rules/verbosity/` had no `__init__.py` (package find missed them) **and** package-data listed only `**/*.yaml` while the rule files are `.yml` (axis.py's own comment warned). The second half was caught inspecting the rebuilt image of `f772ca52`, whose wheel shipped the package with `__init__.py` and zero rule files | package markers (`aafb3139`) + `**/*.yml` in package-data with a pattern-coverage test (`80e787dc`) |
| D-D | smoke had no gate override; R0 #1–2 needed five hand-babysitted gates | missing passthrough | `benchmark smoke --gate-policy` reaches `_run_matrix` (`f772ca52`); attempt 3 ran unattended end-to-end |

### 7.3 Attempt 3 record evidence (all on pin `80e787dc`)

- 42 records, one file per cell, commit `80e787dc` on every record
  (`commit_on_records` green).
- Case-level oracle `1.0`, 6/6, pass; **all six `oracle_task` records
  `judge=oracle score=1.0 outcome=pass error=null`** — D-B closed in live
  records.
- **Axis measured** in-workflow (`axis: 1 measured, 0 not measured` in the
  report totals; erosion 0.27, verbosity 0.00, 60 functions / 1 over CC 10)
  — D-C closed live.
- Cell: graded, merge last, oracle 6/6, first attempt 3/5, after repair 4/5,
  1.81M tokens, wall 6687 s.

- Cell: graded, merge last, oracle 6/6, first attempt 3/5, after repair 4/5,
  1.81M tokens, wall 6687 s.

### 7.3a Attempt 4 record evidence (all on pin `80e787dc`)

- 48 records, commit `80e787dc` on every record.
- Case-level oracle `1.0`, 6/6; **all six `oracle_task` records
  `judge=oracle score=1.0 outcome=pass error=null`** — D-B stays closed
  live. Axis measured (erosion 0.0495, verbosity 0.0082, 84 functions) —
  D-C stays closed. Unattended end-to-end on `--gate-policy off` (D-D).
- Cell: graded, merge last; research/clarify/architecture/plan first-pass;
  code 2/5 first attempt, 4/5 after repair; `analyze` failed (17 untraced
  criteria) and merge blocked on `build_integration_green` (3 introduced
  failing tests) — proposer-quality findings, not harness defects; the
  smoke conditions do not score the cell. 2.40M tokens, wall 10199.8 s.

### 7.3b Attempts 5–6 record evidence

Attempt 5 (pin `ccfe0a64`, 48 records): D-B/D-C/D-D hold live (oracle 6/6
with six `oracle_task` 1.0 `error=null`; axis measured erosion 0.0 /
verbosity 0.0; unattended). The two rubic-stage records carried the judge
failure **inline** — the hardening's first live proof:
`ModelHTTPError: status_code: 503, model_name: gemini-3.5-flash, body:
{'error': {'code': 503, 'message': 'This model is currently experiencing
high demand…', 'status': 'UNAVAILABLE'}}` on both clarify and
architecture. The retry chain (5/30/120 s) exhausted against the wave —
it is longer than the backoff, not a blip.

Attempt 6 (pin `736dd591`, 35 records) — **all four smoke conditions
pass**, stamp `passed=true []`:

- **Rubric judge scored live for the first time since the fix bundle**:
  clarify `staged_rubric 1.0`, architecture `staged_rubric 0.91` on
  `google:gemini-3.8-flash`.
- Oracle 6/6 with all six `oracle_task` records `1.0/oracle error=null`;
  axis measured erosion 0.00 / verbosity 0.00 (43 functions, 0 over CC).
- Cell graded, last stage `deploy` (deepest run of the round: analyze
  failed on 21 untraced criteria — proposer quality — everything else
  first-pass, merge scored 1.0). 1.31M tokens, wall 5175.2 s.

### 7.4 The remaining failure is external

`rubric_scores` failed because the judge model endpoint
(`generativelanguage.googleapis.com`, `gemini-3.5-flash`) returned
**503 Service Unavailable** twice during the run window — 09:43:09Z
(clarify) and 09:55:58Z (architecture), exactly the two records with
`judge=error score=None`. The judge fail-safe behaved as designed (score
None, run continued to the oracle). A direct probe after the run returned
HTTP 200 — the outage was transient. No code defect remains behind this
condition.

**Attempt 4 confirmed the same external signature, this time from the
worker log directly** (attempt 3's causes were inferred from timing): two
`POST …/gemini-3.5-flash:generateContent → 503` lines in
`kroker-worker-1` at 14:35:15Z (clarify) and 14:46:47Z (architecture) —
again exactly the two `judge=error` records, again after a pre-dispatch
probe (12:07Z) had returned 200. Across attempts 3–4 that is 4/4 real
rubric calls 503'd while both one-off toy probes (tiny prompt) succeeded;
cannot distinguish `gemini-3.5-flash` overload waves from a
request-shape factor (the judge prompt carries the full stage artifact;
the architecture author stage pulled 218K input tokens).

Two structural facts make this fragile and invisible:

- **Zero retries.** `_judge_sync` swallows every exception into
  `QualityScore(score=None, judge="error")` (judge.py:197), and the
  activity then completes successfully — so Temporal's activity retry
  never engages and one 503 costs the stage's rubric score for the run.
- **The reason is dropped for stage records.** The D-B fix persisted the
  error reason on task/oracle grades only; stage records carry
  `error=null` (confirmed on attempts 3–4), which is why both outages
  needed log forensics.

**Resolution.** Attempt 5 (pin `ccfe0a64`) confirmed both facts fixed
live: the retry chain fired and the reason landed on the records
(§7.3b) — but also settled the question §7.4 opened: the failure is
**the model, not the waves**. Five real rubric calls across hours of
three separate days all drew the same "high demand / UNAVAILABLE" 503,
while toy probes intermittently returned 200. The orchestrator moved the
R0 case judge to `google:gemini-3.8-flash` (`736dd591`); attempt 6
scored both rubric stages and passed. `benchmarks/config.yaml`'s
`default_judge_model` and the other cases still name `gemini-3.5-flash`
— extend the move once 3.8-flash has more healthy-hours evidence.

### 7.5 Standing state

- **R0 is closed.** Passing stamp on the round's pin:
  `runs/ops/smoke/736dd591….json` → `passed=true, failed_conditions=[]`
  (attempt 6, written 2026-10-14T08:21:11Z). The FR-036 gate for R1–R3 is
  satisfied on `736dd591`.
- Decision trail (orchestrator, 2026-10-13/14): two 503 losses on
  `80e787dc` → judge hardening chosen over a blind re-roll (re-pin
  `ccfe0a64`); attempt 5 proved the cause is the model's chronic
  saturation → judge moved to `gemini-3.8-flash` (re-pin `736dd591`);
  attempt 6 passed.
- Judge hardening that outlives the round: transient-HTTP/timeout retry
  with backoff at the judge seam, a real activity budget for
  `judge_artifact`, and judge-failure reasons persisted on stage records
  (`e9b732d1`, `ccfe0a64`).

## 8. Addendum (2026-10-16): R0 on the final pin and the R1 screen

### 8.1 The judge lottery, attempts 7–11 (pins `e4fe5962` → `f1603fcb`)

After §7.5 the pin moved twice by orchestrator decision — every case
judge to `gemini-3.8-flash` (`e4fe5962`), then the `--arm` spec
validation fix (`f1603fcb`) — and each move re-opened R0 per D-12.
Four attempts lost to **four different external causes**:

- **Attempt 8** (`f1603fcb`): `gemini-3.8-flash` itself 503'd on both
  rubric stages in an evening window (17:35–19:45 local); retries
  exhausted. Independently, research failed grounding by citing
  Kroker's own repo files.
- **Attempt 9**: died entering architecture — hindsight recall
  read-timeouts under a 90-memory consolidation backlog started right
  after the stack was recreated; four recalls degraded to empty, the
  fifth exceeded its budget and the child workflow died. Drained
  within 3 minutes of the failure; a pure window collision.
- **Attempt 10**: `429 "You exceeded your current quota"` — the free
  tier's **daily** quota, not a wave. Minute-scale backoff cannot
  cross a quota reset; the pipeline otherwise ran nearly complete
  (oracle 1.0).
- **Attempt 11** (morning): 503s again on both rubric windows while a
  ~94 KB probe and a toy probe both returned 200 — small requests
  answer while real rubric calls shed. That closed the "run at a
  quiet hour" theory: **the free-tier lottery is unwinnable at run
  scale, at any hour** (5 of 6 attempts lost across two gemini
  models).

### 8.2 The judge that worked, and two more causes (attempts 12–14)

- Judge moved to **`anthropic:claude-sonnet-5`** everywhere
  (`64cd9f54`; paid, stable; ADR-6 holds vs the zai producers;
  `ANTHROPIC_API_KEY` and the SDK were already in the worker image).
- **Attempt 12**: died *before* any judge call — the **proposer** hit
  zai `429 code 1302` at clarify with three retries in five seconds
  (no backoff in the proposer retry layer). Recovered in minutes;
  re-roll passed the stage. Hardening candidate, not exercised
  further this round.
- **Attempt 13**: first run where both rubric stages scored — clarify
  0.97, architecture 0.94 under sonnet-5 (`rubric_scores` green for
  the first time on the pin) — then died at
  `plan-validation: task 'T4' depends on unknown task id(s) ['T3']`
  (glm-5.3 emitted a dangling dependency). Also surfaced a provenance
  trap: **records carry the worker image's baked `KROKER_COMMIT`
  while smoke stamps key on the harness env** — the worker image was
  rebuilt with `--build-arg KROKER_COMMIT=64cd9f54…` before the next
  dispatch (rule: rebuild on every re-pin, even when only yaml
  changed).
- **Attempt 14**: `smoke: PASS 64cd9f54` — **R0 closed on the round's
  final pin** (`runs/ops/smoke/64cd9f54….json`, 2026-10-15T12:19Z).

### 8.3 R1 screen results (T020, arm `zai-coding-plan-glm-5.2`, pin `64cd9f54`)

Prep defect found by the first wave: deveval cases need a per-case
scratch repo at `D:/own/sdlc-scratch-repos/<case_id>` (bind-mounted to
`/srv/scratch-repos`, an empty init commit); geotext and hone burned
their first runs as `lost` in ~20 s for its absence, and **a lost run
exits rc=0**, so chain retries must grep the report (`lost: 1`), not
trust the exit code.

| case | mean oracle | verdict |
|---|---|---|
| deveval-geotext | **0.778** (7/9) | graded — corpus candidate |
| deveval-readtime | **0.167** (2/12) | graded — corpus candidate |
| deveval-hone | 1.000 (12/12) | rejected / saturated |
| deveval-stocktrends | 0.000 (0/4) | rejected / degenerate |
| deveval-particle-swarm-optimization | — | lost ×2 at plan-validation |
| deveval-lice | — | rejected / reference (unchanged) |

- **pso lost twice, same class**: `failed:plan-validation: task 'T7'
  depends on unknown task id(s) ['T6']` — glm-5.3 systematically
  violates the plan contract on this case (todo attempt 13's `T4→T3`
  is the same defect on a different case). The T020 single lost-run
  repeat is spent; the case is unassessed and the plan-validation
  failure mode is a registered proposer-quality concern.
- Accept verdicts read `not_assessed` mid-screen by design: the
  separation check needs a strong/weak pair and the screen ran one
  arm.

### 8.4 Standing state

- **R0 closed on `64cd9f54`** (passing stamp on disk); **R1 screen
  complete** — all five cases have runs, scores and accept records;
  role moves per T020 (geotext + readtime stay corpus; hone /
  stocktrends out; pso unassessed) land with the records on the
  follow-up branch.
- Infrastructure rules the round proved: rebuild the worker image
  with the new `KROKER_COMMIT` on every re-pin; recreate the stack
  (or at least drain hindsight) before a dispatch after prior runs;
  scratch repos per case must exist before dispatch; zai and the
  proposer seam have no 429 backoff (judge seam does).
- Residuals for the register: proposer 429 hardening, the
  plan-validation dangling-dependency failure class, and research
  grounding flakiness on the smoke case (failed 2 of the last 4
  attempts, non-gating but ~$1 each).

## 9. Addendum (2026-10-17): R2 acceptance runs and the R4 erratum

### 9.1 R2 results (T021, one run per arm, pin `64cd9f54`, judge
`anthropic:claude-sonnet-5`)

The grown oracles (012) got one strong-arm run (`zai-coding-plan-glm-5.2`)
and one weak-arm run (`zai-coding-plan-glm-5.3-flash`) each:

| case | strong glm-5.2 | weak glm-5.3-flash | margin | verdict |
|---|---|---|---|---|
| cat-cafe-monitoring | 0.472 (17/36) | 0.833 (30/36) | −0.361 | rejected / no_separation (d768d571) |
| deveval-geotext | 0.778 (7/9) | 0.222 (2/9) | 0.556 | provisional (fe18e07d) |
| deveval-readtime | 0.167 (2/12) | 0.250 (3/12) | −0.083 | rejected / no_separation (fe18e07d) |

The weak arm outscored the strong arm on 2 of 3 grown oracles.

### 9.2 R4 erratum: the tier assumption is contradicted by public
benchmarks

R4 chose `glm-5.3-flash` as the weak arm on the assumption that "the
flash tier of the current generation [is] clearly below the strong arm
(glm-5.2, variant max)". A public-benchmark check (2026-10-17) shows the
opposite ordering: Z.ai reports GLM-5.3-Flash beating GLM-5.2 across six
coding/agentic benchmarks, often by a wide margin (DeepSWE 63.4 vs
46.2), and full GLM-5.3 at 34.5% vs GLM-5.2's 23.4% on SWE-bench-style
agentic coding. The harness results agree with the public ordering on
cat-cafe and readtime; geotext (the only case where glm-5.2 won) is the
outlier, not the rule. The R2 inversions were therefore predictable from
open data at GATE 1 time: no public evidence ever supported "clearly
below", and the harness-side calibration set (todo-api) was run on the
strong arm only.

Consequences, without rewriting R4's record (it stands as the decision
that was made):

- The arm pair MUST be re-decided before R3. Relabeling in place is not
  enough: with glm-5.3-flash as the strong arm, the R1/R2 glm-5.2 runs
  become weak-arm data and a fresh strong arm is still needed.
- The only untested weaker candidate from the R4 list is
  `glm-5-turbo` (no public coding scores found); glm-4.7 stays a
  capability cliff per R4. A FR-034 probe plus one screen run decide it.
- Open benchmarks are adopted as a pre-run baseline check for arm
  choice: they predicted 2 of 3 harness outcomes at zero cost. They do
  not replace runs — geotext shows the harness (opencode + gates +
  partial-credit oracle) can invert the public ordering at n=1.
- The geotext provisional verdict and both no_separation rejections
  stand as recorded; separation matching was verified correct
  (name-based, `acceptance.py`), and each run's code stage ran its
  declared arm's model.

### 9.3 Ruling R4-r1 (2026-10-17): the arm pair is relabeled

On the §9.2 evidence the user ruled (variant 1): the pair is relabeled
in place across all seven corpus manifests — `zai-coding-plan-glm-5.3-flash`
becomes the strong arm, `zai-coding-plan-glm-5.2` the weak one. The
`models:` base list is untouched, so base cell ids do not change; the
base cell now belongs to the weak arm. Public data supports the pair as
strong/weak (DeepSWE 63.4 vs 46.2, a 17-point gap), and the weak arm's
observed 0.167–0.778 range keeps it clear of guaranteed zeros. No new
model is probed; `glm-5-turbo` stays a fallback if a second, independent
pair is ever needed. The R2 acceptance records are NOT re-derived under
the new labels — they stand as the R4-era assessment; R3's fresh runs
are assessed with the relabeled manifests.

### 9.4 Ruling R4-r2 (2026-10-17): R3 assessed offline from the stored cells

Preparation for R3 on the new pin (58678268) surfaced the records
`runs/ops/r3-*.log` (2026-10-16 19:30–22:21, pin `64cd9f54`): the
flash-arm runs on both screened-in cases already existed —
`bench-deveval-geotext-1792161325` and
`bench-deveval-readtime-1792171942` had run as R3 under the OLD labels
(with flash as the weak arm) and were folded into the R2-era acceptance
records. Cell data is label-agnostic (the arm lives in the cell id), so
the strong/weak pair exists in storage for every corpus case and R3
needs no new model calls — only `accept` re-run against the relabeled
manifests.

This supersedes the non-re-derivation clause of R4-r1 for the three
corpus cases: the user ruled (variant 1) that the acceptance records
are regenerated offline from the stored cells. The old R2-era records
stand in git history (`git log -- benchmarks/cases/*/acceptance.yaml`);
they are not rewritten, only replaced by re-derivation. Accept was run
once per case in a throwaway container on detached pin worktree
58678268 (log: `runs/ops/r4r2-accept.log`); results, exactly as
predicted from the cell arithmetic:

| case | strong (glm-5.3-flash) | weak (glm-5.2) | margin (≥0.15) | verdict |
|---|---|---|---|---|
| cat-cafe-monitoring | 0.8333 | 0.4722 | +0.3611 | **provisional** (n=1/arm) |
| deveval-geotext | 0.2222 | 0.7778 | −0.5556 | rejected no_separation |
| deveval-readtime | 0.2500 | 0.1667 | +0.0833 | rejected no_separation |

Reading: under the honest labels the harness agrees with the public
ordering only on cat-cafe — the sole case where separation now holds,
and the only one where the R2-era weak score (0.472) leaves room below
the strong arm. Geotext's R2 provisional status was an artifact of the
inverted labels: with flash as strong the margin is deeply negative,
the harness inverting the public ordering at n=1 the same way §9.2
described. Readtime stays a near-tie (margin 0.083 < 0.15) under
either labeling, now with the sign flipped. Fresh runs on the new pin
remain optional top-up (accept averages whole cells; n=1/arm verdicts
stay provisional at best) and are NOT scheduled by this ruling.

Corpus state after R4-r2: 1 of 8 accepted or provisional
(cat-cafe-monitoring, provisional), 1 of 2 private; geotext and
readtime rejected no_separation; hone/stocktrends parked
(saturated/degenerate), pso unassessed (plan-validation), lice
rejected/reference. T023's tally and documents update from this state.
