# SKEPTIC Consult — Round 025 (`025-sc2-instrument-fleet-runs`)

**Role:** SKEPTIC (adversarial review, read-only on codebase; single consult output).  
**Target:** [spec.md](file:///home/maksim/work/Kroker/.specify/specs/025-sc2-instrument-fleet-runs/spec.md)  
**Verified against:** `src/sdlc/benchmarks/{sc_rollup.py,cli.py,smoke.py,workflow.py,runs.py}`, `src/sdlc/core/models.py`, `benchmarks/cases/todo-api-greenfield/case.yaml`.

---

## Executive Verdict

Part A's schema/replay design (`raised_at: datetime | None = None`, deterministic workflow time, `not measured` vs `0` distinction) is structurally sound and respects the 1000-line ceiling (`sc_rollup.py` is 275 lines) and cross-stage call ban.

**Part B and the SC-1/SC-2 evaluation protocol are not sound.** As written, the locked decisions allow SC-1 and SC-2 to pass **vacuously by construction** (SOFT gates + owner-paced clicks), risk **SC-2 and SC-3 collapsing to `n/a`** at `n=6`, **contradict the codebase on Q3/smoke** (`check_smoke` hard-requires the Anthropic judge and `dispatch_smoke` runs both arms), and leave **post-hoc failure classification** wide open to denominator gaming.

---

## (a) Operator Time = Capped `raised -> decided` (10 min cap, median over shipped runs)

### A1. Survivorship bias: excluding non-shipped runs games SC-2
- **Severity:** `CRITICAL`
- **Location:** `spec.md:43` ("median operator time per shipped run, where *shipped* = the run reached `deployed:` or `merged-not-deployed:`")
- **Concrete failure:** A run that burns 40 minutes of human clarifications, plan reviews, and `task:<id>` fix-loop escalations and then gets rejected at merge or fails QA is **excluded** from SC-2's denominator. Five trivial/auto-approved runs that ship with `0 min` plus one run that fails after `40 min` of human babysitting yields `SC-2 = 0 min (PASS)`.
- **Smallest fix:** Keep the PRD headline (`shipped` runs) if required for parity, **and** add a mandatory companion metric in `sc_rollup.py` / fleet report: **median and total operator time across ALL scored runs** (including case-failures). Fail SC-B2 if shipped-only SC-2 passes while all-scored SC-2 exceeds 15 min.

### A2. Per-interaction 10 min cap vs 15 min run target + owner-speed gaming
- **Severity:** `HIGH`
- **Location:** `spec.md:41, 93, 187`
- **Concrete failure:**
  1. **Owner speed *is* the metric:** Because the owner answers escalations live (`spec.md:188`) with no viewer telemetry (`spec.md:93`), reading a diff for 25 minutes *before* opening the inbox and clicking approve in 10 seconds records `0.17 min`. Conversely, leaving the inbox open for 15 minutes before clicking 3 batched gates records `30 min` (`3 × 10 min`).
  2. **Cap hides genuine human effort:** A single gnarly architecture or merge gate that legitimately takes 22 minutes of review is silently clipped to `10 min`, guaranteeing a single-gate run can never exceed the 15-min target regardless of actual effort.
- **Smallest fix:** Require the fleet report to publish **both** capped engaged time and **uncapped total human-gate wait** per run (FR-003 already captures wait; promote it to the SC-2 table row/note), and log a **self-reported review start/effort note** in the post-run operator report (`B.6`) whenever a human interaction occurs, flagging >2x discrepancy between self-reported reading time and `raised -> decided`.

---

## (b) SOFT Policy with Owner Answering Escalations

### B1. `SOFT` makes SC-1 vacuous and SC-2 artificially ~0
- **Severity:** `CRITICAL`
- **Location:** `spec.md:20 (H4), 69, 71-75, 170, 188`; `src/sdlc/benchmarks/workflow.py:163-164`; `src/sdlc/benchmarks/sc_rollup.py:92-101`
- **Concrete failure:** `workflow.py:163-164` forces every gate in a benchmark run to `spec.gate_policy` (`GatePolicy.SOFT` by default in `src/sdlc/benchmarks/models.py:400`). Under `SOFT`, gates auto-approve above their confidence threshold without human input. `_unattended_to_merge` (`sc_rollup.py:92-101`) only checks `decided_by == "human"` before `MERGE_GATE`. Thus, every `SOFT` run that reaches merge scores `SC-1 = hit` and `SC-2 = 0 min` **by construction**. Reporting the zero-interaction count (`FR-007`) and policy mix (`FR-008`) as a footnote does not stop `SC-B2` (`spec.md:170`) from declaring `SC-1: MET` and `SC-2: MET` on weak evidence.
- **Smallest fix:** Add an explicit **evidence-tier rule** to `SC-B2` (`spec.md:170`) and `sc_rollup.py`: a fleet run under `GatePolicy.SOFT` **cannot mark SC-1 or SC-2 as `MET` for P4 exit** — it must render/report as `PROVISIONAL (SOFT policy)` unless at least a `HARD`-gate or calibrated-escalation subset is run, or P4 explicitly accepts `SOFT` as an operational-shakedown-only proxy.

### B2. `suggested` clarifications bypass SC-2 without quality penalty
- **Severity:** `MEDIUM`
- **Location:** `spec.md:39`; `src/sdlc/core/models.py:520-527`
- **Concrete failure:** `ClarificationOutcome.answered_by == "suggested"` counts as `0` operator time (`spec.md:39`). Under unattended/SOFT runs, if clarifications auto-resolve via `suggested`, SC-2 reads `0 min` even when the clarifier's guess was wrong and caused downstream rework.
- **Smallest fix:** Require `sc_rollup` (and the fleet report) to display `SC-4` (`clarifications` human vs total/suggested) alongside `SC-2` so zero-human-clarification runs cannot be read without seeing how many questions were auto-filled.

---

## (c) 6 Runs, Strong Arm Only, Mixed Cases, One Commit, Tree-Editing Restart

### C1. `n=6` risks collapsing SC-2 below `MIN_RUNS = 5` (`n/a`)
- **Severity:** `CRITICAL`
- **Location:** `spec.md:127, 174`; `src/sdlc/benchmarks/runs.py:38`; `src/sdlc/benchmarks/sc_rollup.py:26, 65-68`
- **Concrete failure:** `MIN_RUNS` is `5`. `B.3` schedules `6` runs, explicitly noting this buys "one run of slack for a case-difficulty failure without dropping below the floor" (`spec.md:127`). SC-2 only counts **shipped** runs (`spec.md:43`). If **2 of 6** runs fail to ship (e.g., `cat-cafe-monitoring` + 1 `deveval` case-failure), `n_shipped = 4 < 5`, so `sc_rollup` renders **SC-2 = `n/a`** even though the fleet completed 6 valid scored runs! Furthermore, at `n=5` or `6`, a median has massive variance (one extra human escalation flips the median).
- **Smallest fix:** Raise the fleet cap/target slack or decouple SC-2's denominator (see **A1**: all scored runs = `6`, not just shipped = `4`), **and/or** bump the recommended count to `7` (cap `8`) when any high-difficulty case (`cat-cafe-monitoring`) is in the mix.

### C2. Mixed cases pad SC-1 with a `smoke` case and double-weight `deveval-readtime`
- **Severity:** `HIGH`
- **Location:** `spec.md:115, 117-123`; `benchmarks/cases/todo-api-greenfield/case.yaml:22`
- **Concrete failure:** `B.3` mixes `todo-api-greenfield` (`role: smoke`, trivial 1-file CRUD) as **run 1** of the scored fleet, repeats `deveval-readtime` twice (`runs 2 and 6`), and includes only 1 held-out/veto case (`cat-cafe-monitoring`). At `n=6` with `SC-1 >= 0.80` (needs `5/6`), counting the trivial `smoke` case as `1/6` of the fleet inflates SC-1 by `+16.7%` and weights `deveval-readtime` at `33%` of the fleet.
- **Smallest fix:** Keep `todo-api-greenfield` strictly as the **unscored** smoke prerequisite (`sdlc benchmark smoke`) and replace scored Run 1 with a distinct `corpus` case (or clearly separate `smoke` from `corpus` in the fleet report's SC-1/SC-2 breakdown).

### C3. Tree-editing infra fixes restart the fleet and collide with the 2-infra-stop ceiling
- **Severity:** `HIGH`
- **Location:** `spec.md:133, 147`
- **Concrete failure:** Any infra fix that edits `src/` or `benchmarks/` changes `HEAD`, voids all prior runs (`spec.md:133`), requires a new paid `sdlc benchmark smoke` pass, and restarts at Run 1—while `B.6` (`spec.md:147`) **ends the delegation on a second infra stop**. If Run 3 exposes a real bug in `024` pool routing or `Part A` instrumentation, fixing it + restarting burns half the budget and leaves only 1 infra stop for the entire new fleet.
- **Smallest fix:** Explicitly state in `B.6` that a **fleet restart on a new commit** resets the run counter *only* with a fresh owner go on the remaining budget (rather than silently counting against the old ceiling), and require a **dry-run / barrier integration check** on the pools overlay *before* Run 1 so pool/routing bugs are caught before paid runs start.

### C4. `FR-024` commit check cannot be enforced from `RunSummary` alone
- **Severity:** `HIGH`
- **Location:** `spec.md:159`; `src/sdlc/core/models.py:555-587`; `src/sdlc/benchmarks/sc_rollup.py:71-85`
- **Concrete failure:** `FR-024` requires `sc_rollup` to show the commit set and flag `> 1` commit. `RunSummary` (`src/sdlc/core/models.py:555-587`) **has no `kroker_commit` field**; only `BenchmarkRecord` carries `kroker_commit` (`src/sdlc/benchmarks/workflow.py:154`). If a `RunSummary` in `SDLC_RUNS_ROOT` lacks a matching `BenchmarkRecord` (or `sc_rollup` reads `summaries` without joining `records` by `run_id`), a stale-commit run is silently aggregated without triggering the multi-commit flag.
- **Smallest fix:** Add `kroker_commit: str | None = None` to `RunSummary` (additive, `None` on legacy) **or** require `build_sc_rollup` to cross-join `summaries` with `records` by `run_id` and flag any summary with missing or mismatched `kroker_commit`.

---

## (d) Case-Failure vs Infra-Failure Scoring, Concurrency, and SC-3 Denominators

### D1. Post-hoc operator classification invites denominator gaming
- **Severity:** `CRITICAL`
- **Location:** `spec.md:139-141`
- **Concrete failure:** `case-failure` stays in SC-1's denominator (where `2/6` misses `>= 0.80`), while `infra` is **excluded** from all denominators (`spec.md:140`). Because classification is made post hoc by the operator (`spec.md:141`), ambiguous mid-run failures—e.g., harness wall-clock timeout on a huge diff, model context overflow, worktree lock contention, or transient provider 429 during a 4th fix attempt—can be rationalized as `infra` to preserve `SC-1 >= 0.80`.
- **Smallest fix:** Define a **hard, pre-registered binary rule** in the `B.8` ops doc: a failure is `infra` **only if** (a) zero stages produced a valid artifact/record, OR (b) a verifiable host/process/HTTP-5xx/auth error occurred *outside* the harness's task execution. Context-window exhaustion, harness task timeouts, bad code/tests, and rubric/oracle failures are **always `case-failure`**. Any borderline call must be logged as **both** in a sensitivity line (`SC-1` with and without the contested run).

### D2. Concurrent runs (`B.4`) race with infra-stop halt (`FR-023` / `SC-B4`)
- **Severity:** `MEDIUM`
- **Location:** `spec.md:134, 140, 158, 172`
- **Concrete failure:** `B.4` allows runs to overlap up to the harness cap (`spec.md:134`). If Run 2 and Run 3 run concurrently and Run 2 hits an infra failure, Run 3 is already executing and spending z.ai + Anthropic tokens before the operator can diagnose or halt.
- **Smallest fix:** Run **sequentially** (concurrency = 1) for at least Run 1 (smoke) and Run 2, or explicitly define what happens to in-flight concurrent runs when an infra stop triggers (e.g., cancel in-flight Temporal workflows immediately, or let them finish and classify them independently).

### D3. SC-3's fix-loop denominator can fall below `MIN_RUNS = 5` (`n/a`) or be dominated by one run
- **Severity:** `HIGH`
- **Location:** `spec.md:174`; `src/sdlc/benchmarks/sc_rollup.py:117-144`
- **Concrete failure:** SC-3 counts `(run_id, task_id)` pairs with `fix_attempts > 0` (`sc_rollup.py:120-132`). On the strong arm (`glm-5.3`), 6 runs may trigger only `2–4` fix loops total, leaving `n < 5` (`MIN_RUNS`) so SC-3 renders **`n/a`**—failing P4's exit goal of measuring SC-3 at target (`spec.md:9`). Conversely, if `cat-cafe-monitoring` alone has 5 tasks that enter fix loops and fail, 100% of SC-3 comes from a single case.
- **Smallest fix:** Acknowledge in `SC-B2` that `SC-3 = n/a` (due to high first-pass success) is a **valid non-failure outcome** if first-pass code pass rate is reported alongside it, and report **per-case** loop counts in the fleet report so one case cannot silently dominate SC-3.

---

## (e) Judge Handling, Smoke Stamp, and Cost Ceiling

### E1. Q3 deferral contradicts `smoke.py`: smoke *requires* the Anthropic judge
- **Severity:** `CRITICAL`
- **Location:** `spec.md:181, 189`; `src/sdlc/benchmarks/smoke.py:78-88`; `src/sdlc/benchmarks/cli.py:301-313`
- **Concrete failure:** `Q3` (`spec.md:189`) asks the plan to check whether SC-1..3 runs can skip quality judging. Even if corpus runs skipped judging, `sdlc benchmark run` for any `CORPUS` case **refuses to start** without a passing smoke stamp (`cli.py:309-313`), and `check_smoke` (`smoke.py:78-88`) **hard-fails** if `clarify` and `architecture` lack `quality.score` from `RUBRIC_JUDGES` (`anthropic:claude-sonnet-5`). Thus, Anthropic API spend is **unavoidable** under current code.
- **Smallest fix:** Remove the "if yes, z.ai-only holds" branch from Q3/plan, or explicitly scope a code change in Part A/plan if judge-skipping is desired; otherwise lock Anthropic judge credentials and separate judge ceiling as **mandatory** in `B.2`.

### E2. `sdlc benchmark smoke` runs BOTH arms (including weak `glm-5.3-flash`) and can fail on case-difficulty or infra
- **Severity:** `HIGH`
- **Location:** `spec.md:181`; `src/sdlc/benchmarks/cli.py:619`; `benchmarks/cases/todo-api-greenfield/case.yaml:27-29`; `src/sdlc/benchmarks/smoke.py:109-115`
- **Concrete failure:**
  1. `dispatch_smoke` (`cli.py:619`) calls `_run_matrix(str(case_file), skip_smoke=True, gate_policy=gate_policy)` with **no `arm` filter**. `todo-api-greenfield/case.yaml:27-29` defines **two models** (`zai-coding-plan/glm-5.3` and `zai-coding-plan/glm-5.3-flash`). Running `smoke` therefore executes and pays for **two** full runs (including Anthropic judging on both).
  2. `check_smoke` (`smoke.py:109-115`) requires `oracle_all_pass` across all cells. If the weak arm (`glm-5.3-flash`) fails the oracle, `smoke` fails (`SystemExit`, `cli.py:655`), blocking all corpus runs—and `B.6` does not specify whether an infra-failed `smoke` counts toward the **2-infra-stop delegation limit**.
- **Smallest fix:** Either pass `--arm` / filter `smoke` to the strong arm only (if `smoke` is meant to validate the fleet's strong-arm stack), or budget `2 ×` smoke cost in `B.6` and explicitly state whether `smoke` infra failures count toward the 2-stop limit.

### E3. `1.5×` cost ceiling using `smoke` as fallback for "no prior" cases is broken
- **Severity:** `HIGH`
- **Location:** `spec.md:147`
- **Concrete failure:** `B.6` sets the ceiling at `1.5 ×` expected per-run costs, using "the smoke run's measured cost" when a case has no prior records (`spec.md:147`). `todo-api-greenfield` is a tiny 1-file CRUD smoke case; `cat-cafe-monitoring` is a multi-task private case with research, vetoes, and held-out grading. Using `todo-api-greenfield`'s cost as the proxy for `cat-cafe-monitoring` (or any multi-task `deveval` case without priors) will severely under-estimate the ceiling and trigger a premature delegation halt mid-fleet.
- **Smallest fix:** Require `B.6` pre-flight to compute the ceiling from **actual `budget_usd` caps** (`sum(budget_usd)` across the 6 runs + smoke) rather than `1.5 ×` a mismatched smoke proxy when prior records are absent.

---

## Mitigation Checklist (Required Before GATE 2)

1. [ ] **SC-2 survivorship & wait:** Report SC-2 over *all scored runs* alongside *shipped-only*, and surface uncapped wait beside capped engaged time.
2. [ ] **SOFT policy honesty:** Prevent `SOFT`-policy runs from claiming `SC-1`/`SC-2` as `MET` without an explicit `PROVISIONAL (SOFT)` qualifier.
3. [ ] **Floor safety (`n=6`):** Separate `smoke` from `corpus` scored runs, and ensure `n_shipped < 5` or `n_loops < 5` has a pre-declared reporting rule (plus first-pass code rate alongside SC-3).
4. [ ] **Commit provenance (`FR-024`):** Cross-join `RunSummary` with `BenchmarkRecord.kroker_commit` (or add `kroker_commit` to `RunSummary`) so multi-commit contamination cannot slip past `sc_rollup`.
5. [ ] **Pre-registered `infra` vs `case-failure` rule:** Ban post-hoc `infra` reclassification for timeouts, context limits, or oracle/rubric misses; include a sensitivity line for any contested run.
6. [ ] **Smoke & Judge reality:** Lock Anthropic judge as mandatory for `smoke` (`smoke.py:78-88`), account for `todo-api-greenfield` running **2 arms** in `dispatch_smoke` (`cli.py:619`), and replace the `smoke`-cost fallback in `B.6` with explicit `budget_usd` ceilings.
