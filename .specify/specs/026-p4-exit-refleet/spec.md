# Feature Specification: Round 026, turning round 025's measured misses into P4's exit (fixes plus a smaller re-fleet)

**Feature Branch**: none (spec-only phase; writes under `.specify/specs/026-p4-exit-refleet/` only)

**Created**: 2026-11-18

**Status**: GATE 1 and GATE 2 cleared 2026-11-18; ready for exec

**Input**: Orchestrator TASK BRIEF, 2026-11-18: "round 026: turn round 025's measured misses into P4's exit criterion... SC-3 0.385 (fix-loop), SC-1/SC-2 unmeasurable. Spec the round that targets exactly those." Part A covers the fixes (SC-2 plumbing, lint_clean diagnosis and fix, agent-failure triage). Part B is the re-fleet protocol. Success is P4's exit, or an honest second miss recorded with its deltas.

**Evidence base**: `.specify/specs/025-sc2-instrument-fleet-runs/{spec,tasks,verification,preflight}.md`, `../kroker-fleet-runs-025/` (runs root, `fleet-report.md`, per-run jsonl, `pipeline/<bench>/<cell>/{summary.json,events.jsonl}`), and the surviving integration branches in `../scratch-repos/<case>`. Every number below was re-measured from those files on 2026-11-18. None is copied from the brief.

---

## Part 0: The brief's hypotheses checked against the evidence

| # | Hypothesis (brief) | Verdict | Evidence |
|---|---|---|---|
| H1 | "Benchmark-mode runs produce no retro `summary.json`" (also T034's wording) | **Contradicted: they do produce it. The scorer reads the wrong root.** | Every run that terminated normally wrote `<runs-root>/pipeline/<bench_run_id>/<cell>/summary.json`, with `operator_instrumented: true` and `raised_at` on every gate. That covers 4 of the 6 scored runs plus the smoke, plus one orphan summary from the pre-smoke Nov-16 attempt that has no records (skeptic finding 1). The worker's export root is `/app/runs/pipeline`, bind-mounted to the fleet root (`docker-compose.override.yml`, `KROKER_RUNS_BIND`). The host scorer resolves summaries from `SDLC_EXPORT_ROOT` or the CWD-relative `./runs/pipeline` (`benchmarks/evidence.py:48-53`). It never derives that path from `SDLC_RUNS_ROOT`, so it found 0 of 7 (`sc-rollup.json`: `summary_runs: 0, selection_runs: 7`). Re-scoring the 025 root with `SDLC_EXPORT_ROOT=<root>/pipeline` (read-only, $0) finds 5 of 7 and renders SC-1, SC-2-all and the commit set. **The fix is root resolution, not a new export.** |
| H1b | (not in the brief) Runs that crash or are stopped leave no summary | **Confirmed. Those runs drop out of SC-1 and SC-2 silently.** | Run 1 (architecture crash) failed `GraphWorkflow` via `stored_failure`, and `graph.py:205-207` skips retro by design ("retro not run"). Run 6 was operator-terminated. Both have records but no summary. The rollup computes SC-1 from summaries only, so a crashed run disappears from SC-1's denominator instead of counting as a miss. |
| H1c | (not in the brief) The `_all` selection is the scored set | **Contradicted** | `selection_runs: 7` includes the smoke run (`todo-api-greenfield`, role `smoke`, unscored by 025 B.9) because it shares the runs root. |
| H2 | SC-1 needs genuinely unattended runs; the 025 attendant made SC-1 unreadable | **Partly. The deeper cause is SOFT on a cold calibration ledger.** | SOFT auto-approves only with confidence ≥ threshold **and a calibrated bucket** (`calibration/decision.py`). On this host the ledger was cold, so every SOFT gate fell through to a human: SC-6 = 1.00 (20/20 soft gates human-decided) at confidences 0.68–0.88. **Under SOFT on a fresh host, SC-1 is 0 by construction, whoever answers.** With the corrected root, the 025 SC-1 reads **0.00, n=5** under the rollup's current definition, which says "no human-decided gate before merge". The PRD defines it differently: *"reach the merge gate without human intervention **beyond configured gates** (no unplanned escalations)"* (`PRD.md` §8). The rollup's definition is stricter than the PRD's. See Q1. |
| H3 | Best run blocked by `lint_clean` alone. Is lint dirty, or does the check misfire? | **Lint is genuinely dirty. It is dirty against a rule set nobody chose, and the dev agent never sees it.** | (a) `lint_clean` blocked **all three** scored runs that reached merge and failed: cat-cafe (22 introduced), geotext (24), lice (73). It also blocked infra smoke 2. (b) The check is correct by its own contract: only *introduced* findings fail it (`merge/step.py:lint_check`). Policy-path and suppression counts are informational only. (c) **None of the three scratch repos has a ruff config.** The gate runs `ruff check` (`toolchain/adapters.py:252`), and with no config ruff ≥ 0.16 applies its broad built-in default set: **413 rules** enabled, verified on 0.16.9. Re-linting each run's surviving `integration` branch offline reproduces the gate exactly: 22, 24 and 74 findings (73 at the gate, a ±1 delta-vs-base). (d) **The per-task loop never runs lint.** `code/step.py` and `qa/step.py` build only the test command. Lint runs first at merge (`merge/step.py:383-398`), where it is absolute and has no fix loop. (e) **Autofix alone converts no run.** `ruff --fix` leaves 4 (cat-cafe), 15 (geotext) and 42 (lice). Cat-cafe's residual is 2 PERF102, 1 PLW1510 and 1 TRY004. Five of its findings are RUF100 (unused `noqa`), meaning the agent's own suppressions were themselves violations. |
| H4 | Case failures repeat in a few fixable modes (for example run 1's architect `run_code` TypeError) | **Partly verifiable now. The fix-loop causes are not in the records.** | Failure table, re-derived: run 1 died at architecture. The architect's CodeMode `run_code` raised a `TypeError` on the model's own code (`unsupported operand for +: 'Result' and 'Result'`), retried 3×, and failed the child. That is a tool error escalating to a stage death instead of returning to the model, which is plausibly a harness defect (to be confirmed in A.3). Runs 2, 3 and 4 were merge-blocked with `lint_clean` common to all three (H3); runs 2 and 3 also had `review_severity` and `traceability`, and run 2 also had `plan_drift`. Run 5 reached deploy with a merge verdict of `revise`, but the frozen oracle scored 0.25. Run 6 was a 3-task escalation cascade. **For the 13 fix loops, the task-attempt records carry no failure reason** (`error` empty, `quality.detail` null on every `code/qa/review` fail record), so SC-3's misses cannot be triaged from records. Their causes come from the session transcripts, which are retained on disk at `kroker-fleet-runs-025/pipeline/<uuid>/sessions/T*-a*.jsonl` (skeptic finding 6). |
| H5 | Re-fleet budget discipline from 025 binds | **Confirmed. 025 ended $0.015 under its ceiling.** | $8.7550 of $8.77. Measured judged cost per case for a full run: readtime $1.1531, lice $0.9326, geotext $1.2700, cat-cafe $2.0025, smoke $1.9381. Run 3 crossed its 1.5× per-run line but finished before a cancel point. |
| R1 | Rider: ambient `.env` pollutes CLI tests | **Confirmed. Card verified, size S.** | `.workspace/tasks/2026-11-18-env-pollutes-cli-tests.md`: 43 failures with the fleet `.env` present, and exactly the 2 baseline ids with it moved aside. The fleet host fixes (`KROKER_HARNESS_QUEUE`, `KROKER_RUNS_BIND`) leak into every child CLI process. |
| R2 | Rider: 025's T034 note | **Superseded by H1** | T034 says "wire a benchmark-compatible RunSummary source". The source exists, so the work becomes FR-001 to FR-004. T034 is closed by this round with a pointer, not done as written. |

**What 025 actually measured, re-read with the corrected root ($0, read-only):** the raw re-score (smoke still included, crashed runs still dropped) gives SC-1 0.00 (n=5) and SC-2-all 0.85 min (n=5). **The scored set (smoke excluded, crashed and terminated runs counted, per FR-002 to FR-004) gives:** SC-1 0.00 (n=6) · SC-2 shipped n/a (n=1 < floor) · SC-2-all **n/a** (4 measured runs, below the floor of 5; median 0.75 min; the "operator" was an automated attendant, so this is attendant latency, not human effort) · SC-3 0.385 (5/13) · commit set: one. Once the plumbing is fixed, 025's SC-2 is still below the floor. That is part of why the re-fleet needs 5 runs that each finish. These become the **025 baseline** that every delta in this round is measured against.

---

## Part A: The fixes (code, one L crew round, test-first)

### A.1 SC-2/SC-1 plumbing: the rollup reads what the fleet wrote

#### User Story A1: `benchmark score` over a fleet root renders SC-1, SC-2 and the commit set with no manual scan (Priority: P1)

An operator scores a dedicated fleet runs root and gets SC-1, both SC-2 rows and the commit set straight from the rollup. Every run of the scored selection is accounted for: either it has a summary, or it is named with the reason it has none.

**Why this priority**: 025's two "unmeasurable" criteria were measurable all along. Without this fix, the re-fleet would repeat the same blind spot.

**Independent test**: a copy of the 025 runs root, scored with only `SDLC_RUNS_ROOT` set, produces `summary_runs = 4` and `selection_runs = 6` (the smoke excluded from the 7 run ids on record), a commit set equal to `{ce3a36f8…}`, SC-2-all n/a (4 measured, below the floor), and named "no summary" entries for runs 1 (`crashed`) and 6 (`terminated`).

**Acceptance scenarios**:

1. **Given** a runs root whose worker export landed at `<root>/pipeline/<bench>/<cell>/summary.json`, **When** `benchmark score --all` runs with only the runs root configured, **Then** those summaries are read, and the output states which export root it used.
2. **Given** `SDLC_EXPORT_ROOT` is set explicitly, **When** scoring, **Then** the explicit root wins and that is stated.
3. **Given** a scored run whose workflow crashed or was terminated (records exist, summary does not), **When** scored, **Then** the run counts in SC-1's denominator as **not reaching merge unattended**, is listed as "not measured" for SC-2 with its terminal class, and is never silently dropped.
4. **Given** smoke-role case runs in the same root, **When** the scored selection is built, **Then** they are excluded from SC-1, SC-2 and SC-3, and the exclusion is stated.

### A.2 lint_clean: the dev agent sees the bar it will be judged by

#### User Story A2: a task that leaves lint dirty learns it inside its own fix loop, not at merge (Priority: P1)

A dev agent finishing a task gets the same lint verdict that the merge gate will apply, scoped to what the task introduced, while it can still fix it. Mechanically fixable findings never reach merge.

**Why this priority**: lint_clean blocked 3 of 3 merge-failing scored runs, and the closest run in the fleet (oracle 0.861, 11/11 QA) failed on nothing else. Converting that failure mode is the cheapest real gain available to SC-1.

**Independent test**: a fixture task whose diff introduces one autofixable and one non-autofixable finding under the scratch repo's effective rule set. The autofixable finding is removed before the task's check. The residual finding fails the task attempt with the finding in the feedback the dev receives, and a corrected attempt passes. Then the integration branch of 025's run 4, re-linted after the round's fix path is applied offline, shows the merge-gate finding count the fix path would have produced (recorded, not asserted).

**Acceptance scenarios**:

1. **Given** a task diff introducing lint findings under the worktree's effective configuration, **When** the task's check runs, **Then** the findings the task introduced (a delta against the task's base, the same way merge scopes it) are reported to the dev as part of the attempt's failure feedback.
2. **Given** findings that the linter can fix safely, **When** the task's check runs, **Then** they are fixed deterministically before the check, and the change is recorded in the task's record.
3. **Given** a repo with no lint configuration, **When** lint runs per task, **Then** it uses exactly the rule set the merge gate will use (same binary, same resolution), so the two can never disagree.
4. **Given** the merge gate, **When** it runs, **Then** `lint_clean` is unchanged: absolute, introduced-only, fail-closed.

### A.3 Agent-failure triage: a defect list, not a story

#### User Story A3: every 025 case failure and fix loop has a classified cause, and the small harness defects are fixed (Priority: P2)

The triage produces a table covering every 025 scored failure (5) and every fix loop (13). Each row carries a cause class (**harness defect**, **agent-tool defect**, **check/reviewer behavior**, **case difficulty**, or **cause not recoverable**) and an evidence pointer. Defects classed harness or agent-tool that have a small, test-first fix are fixed in this round. Everything else is recorded, not fixed.

**Why this priority**: SC-3 (0.385 against a 0.70 target) is the largest gap, and today its cause is unknown, because the records do not say why an attempt failed.

**Independent test**: the triage table exists, with 18 rows (5 runs plus 13 loops) and an evidence pointer on each. Every defect marked "fixed" has a red→green test. The run-1 failure mode (a model-code exception inside a sandboxed tool) is reproduced by a fixture and either returns to the model as a retryable observation within its retry bound, or is documented as correct behavior with the reason.

**Acceptance scenarios**:

1. **Given** a task attempt that fails code, QA or review, **When** its benchmark record is written, **Then** the record carries the failing check(s) and a bounded failure summary (an additive, defaulted field), so the re-fleet's loops can be triaged from records alone.
2. **Given** a sandboxed agent tool that raises on model-written code, **When** that happens inside a stage, **Then** the stage does not die on the first bounded retry exhaustion of a *tool* error unless that is the documented contract (decided by the A.3 investigation).
3. **Given** a loop whose 025 cause cannot be recovered (session transcripts or histories gone), **Then** it is classed "cause not recoverable" and is not guessed.

### A.4 Rider: test isolation against the ambient `.env`

#### User Story A4: local verification is immune to operator host configuration (Priority: P3)

**Independent test**: with the fleet `.env` present at the repo root, the full fast tier shows exactly the baseline failure ids (the card measured 43 extra failures today).

**Acceptance scenario**: **Given** a `.env` containing `KROKER_*`/`SDLC_*` host settings, **When** CLI-subprocess tests spawn the CLI, **Then** their children run with those variables scrubbed or pinned, and the suite result equals the result without the `.env`.

### Edge cases

- A summary exists but its `run_id` disagrees with the record's. The existing guard ignores it and says so; that guard stays.
- Two runs roots are mixed, or a summary has no record. The existing commit-set flags (025 FR-014) apply.
- A repo **has** a lint config. Per-task lint uses it, exactly as merge does. The fix never injects or alters lint configuration.
- Autofix changes behavior. Only fixes the linter classes as safe are applied, and the tests run after the autofix, so a behavior change shows up as a test failure inside the same attempt.
- Per-task lint makes loops **longer**: lint findings become fix-loop triggers. This can lower SC-3 and raise escalations. That risk is accepted and measured; see SC-B2's delta reporting.
- The run-1 fixture cannot reproduce the crash (the 025 history is gone). The row is classed "cause not recoverable", and only the general tool-error path is tested.

### Functional requirements (Part A)

- **FR-001**: When no explicit export root is configured and a runs root is, the scorer MUST resolve summaries from the runs root's export location (the layout the worker writes), and MUST state the export root it read in every output format.
- **FR-002**: The rollup MUST account for every run of the scored selection: summarized, or listed with a "no summary" reason and terminal class (crashed, timed out, terminated, summary missing; research R2).
- **FR-003**: SC-1's denominator MUST be the scored runs, derived from records. A run with no summary that did not reach merge counts as a miss. SC-2 lists it as not measured.
- **FR-004**: The scored selection MUST exclude smoke-role cases from SC-1, SC-2 and SC-3, and MUST state the exclusion.
- **FR-005**: Re-scoring 025's root with the fixed scorer MUST reproduce the 025 baseline stated in Part 0, written to this round's verification file as the delta base.
- **FR-006**: SC-1's definition in the rollup MUST follow the GATE 1 ruling on Q1, and the definition text MUST be rendered beside the rate.
- **FR-010**: The per-task check MUST run the same lint the merge gate will run (same tool resolution, same effective configuration), scoped to the task's introduced findings, and MUST feed those findings into the existing fix loop as attempt-failure feedback. The mechanism is fixed by GATE 1's ruling on Q2.
- **FR-011**: Linter-safe autofixes MUST be applied deterministically before the per-task lint check, and the applied fixes MUST be recorded on the task's attempt record.
- **FR-012**: The merge gate's `lint_clean` MUST NOT change (absolute, introduced-only, fail-closed). No lint configuration may be injected into, or edited in, a case repository by the system.
- **FR-020**: A triage table MUST classify each 025 scored failure and each of its 13 fix loops into one of the five A.3 classes, with an evidence pointer. It is written to this round's spec directory.
- **FR-021**: Task-attempt benchmark records MUST carry the failing checks and a bounded failure summary for failed code, QA and review attempts (additive, defaulted; legacy records load unchanged).
- **FR-022**: The run-1 mode (a sandboxed-tool exception on model code ending the stage) MUST be investigated and either fixed test-first, or documented as intended with the reason.
- **FR-023**: Only defects classed harness or agent-tool, each fixable test-first within one M-sized task, are fixed in this round. Larger defects go to the backlog with their evidence.
- **FR-030**: CLI-subprocess tests MUST run their children with operator host variables (`KROKER_*`, `SDLC_*`) scrubbed or pinned (rider R1).
- **FR-040 (standing constraints)**: No change to the trust layer: absolute checks, gate-policy semantics, the calibration rule, ADR-6 and containment. No `GraphWorkflow` or stage-contract change beyond what FR-010/011 strictly require, and any such change is ruled at GATE 1 (Q2). Every workflow-visible change carries a replay proof, or a declared incompatibility under the slice's existing rule. All new data is additive and defaulted.

---

## Part B: The re-fleet protocol (operations, paid)

### B.1 What is inherited unchanged from 025

`docs/operations/fleet-runs.md` and 025 spec B.2–B.7 bind as written: host pre-flight, a dedicated clean checkout at one fleet commit, no commit between the smoke stamp and the last scored run, strong arm only (`zai-coding-plan/glm-5.3`), the pre-registered case/infra rule, per-run announcements and post-run reports, any infra stop halting the sequence, a second infra stop (a failed smoke counts) ending the delegation, and a tree-editing fix restarting the fleet with a fresh owner go. The 025 host fixes (`KROKER_HARNESS_QUEUE=default`, the safe.directory entries, the read-only opencode `auth.json` bind, `KROKER_COMMIT` build arg) are pre-flight items, each evidenced before the smoke.

### B.2 What changes

1. **Sequencing.** Part B starts only after Part A merges and verifies, **and** an offline re-score of 025 with the fixed scorer reproduces the Part 0 baseline (FR-005). No paid run happens before the instrument is proven on old data for $0.
2. **Gate policy and the SC-1 instrument** follow Q1. The recommended design is in B.4.
3. **The attendant stays** (025 ruling), with its ledger. SC-2 is still reported with its evidence tier. Every interaction is still counted.
4. **The rollup is the authority.** The fleet report quotes the rollup's SC-1, SC-2, SC-3 and commit set. A manual record scan is allowed only as a cross-check, and any disagreement is a finding.

### B.3 Case selection (from the measured evidence)

| # | Case | Why (025 evidence) |
|---|---|---|
| 1 | cat-cafe-monitoring | The conversion test: 11/11 QA and oracle 0.861, blocked by lint_clean alone. If A.2 works, this is where it shows. Carries the judge and research lines |
| 2 | deveval-readtime | 025's only run to reach deploy (run 5), and also 025's architecture crash (run 1). It tests A.3's run-1 fix and same-case variance |
| 3 | deveval-geotext | Merge-blocked on lint plus review_severity and traceability, with 2 loops. A mixed-cause read |
| 4 | deveval-lice | The hardest case: 73 lint findings, cascades in both runs. Kept so the fleet is not cherry-picked to its easiest cases |
| 5 | cat-cafe-monitoring (repeat) | A second conversion read on the case closest to passing. A same-case variance read |
| (6) | deveval-readtime (repeat) | **Pre-authorized only** if, after run 5, fewer than 5 scored runs are SC-2-*measured* (summarized). A crash counts toward SC-1 but leaves SC-2 below its floor, which is what happened to 025 (4 measured) |

Smoke: `todo-api-greenfield` at the fleet commit (paid, unscored, mandatory per corpus rule). Order: runs 1 and 2 sequential, then at most 2 overlapping (025 rule 4).

**Count: 5 scored, cap 6.** Five is the rollup's `MIN_RUNS` floor, the smallest fleet that can produce an SC-1 rate at all. At n=5, SC-1 ≥ 0.80 means **4 of 5**.

### B.4 SC-1 measurement design (recommended answer to Q1)

The fleet runs `--gate-policy hard`. Stage gates (research, clarify, architecture, plan, merge, deploy) are then **configured human gates** that the attendant answers. Under the PRD's wording they do not count against SC-1. Task-level escalations (`task:<id>`, raised only when a fix loop exhausts) and any other gate the run did not configure are the **unplanned escalations**. SC-1 hit = the run reached the merge gate with zero unplanned escalations and no steering (A-2).

The reasons, each from evidence:

- (a) The PRD's own definition excludes configured gates (Part 0, H2).
- (b) SOFT on a cold ledger turns every stage gate into a fallthrough, so SC-1 reads 0 whatever the run's quality.
- (c) A mixed fleet with a gates-off subset cannot produce an SC-1 rate at this size. A subset below n=5 renders n/a, so a 2-run off subset would be a third unmeasurable read.
- (d) The SC-2 interactions stay real decisions on planned gates.

Retro-read of 025, for the delta table. Under the rule as coded (plan R3: a SOFT stage gate that fell through to a human is itself an unplanned escalation), 025 reads **0.00**, because every SOFT gate escalated. That is the SC-1 delta base. **0.33** (2 of 6: cat-cafe and readtime-5 reached merge with zero task escalations) is what 025 would have read had its stage gates been HARD. It is stated as a hypothetical, never as the baseline.

### B.5 Budget ceiling (derived; announced again after the smoke with its measured cost)

| Line | Basis (025 measured judged $ per full run) | Expected |
|---|---|---|
| Smoke (todo-api, unscored) | $1.9381 | $1.94 |
| cat-cafe × 2 | $2.0025 each | $4.01 |
| readtime | $1.1531 | $1.15 |
| geotext | $1.2700 | $1.27 |
| lice | $0.9326 | $0.93 |
| **Sum (5 scored + smoke)** | | **$9.30** |
| **Judge ceiling** = 1.5 × sum | | **$13.95** |
| Research (EXA) bound | as 025 | $1.00 |
| Optional run 6 (readtime) | $1.1531 | fits inside the ceiling |

**Per-run stop** = 1.5 × that case's 025 cost: cat-cafe $3.00, readtime $1.73, geotext $1.91, lice $1.40. The operator cancels at the crossing (025 run 3's "it finished before a cancel point" is not repeated: the attendant polls cost at each gate). z.ai is a flat subscription, recorded and not capped.

Tripwires, unchanged from 025: any infra stop means halt and report. A second infra stop, a crossed ceiling, or more than 6 scored runs each end the delegation. HARD policy has no judge-cost effect, so the ceiling does not depend on Q1. The Q2 fix may lengthen loops; judged cost per loop is small (flash QA and review at about $0.003–0.007 per attempt in 025), so the 1.5× headroom covers it.

### B.6 Operations functional requirements

- **FR-050**: Run 1 MUST NOT start before FR-005's $0 re-score passes and every 025 host pre-flight item is evidenced.
- **FR-051**: Every run is announced before it starts and reported after it ends (025 B.6 template), including unplanned-escalation count and cumulative spend against $13.95 + $1.00.
- **FR-052**: All scored runs share one commit. The rollup's commit set MUST show exactly one, read by the rollup itself.
- **FR-053**: The fleet report MUST state, for each of SC-1, SC-2 (both rows) and SC-3: value, n, target, met or missed, evidence tier, **and the delta against the 025 baseline** (Part 0). It also states the lint conversion read (how many merge-reaching runs `lint_clean` blocked: 025 had 3 of 3) and the per-class triage of the round's own loops from FR-021's records.
- **FR-054**: A miss MUST be recorded as a miss with its deltas, never re-run away (025 B.4 rule 5).

---

## Success criteria *(mandatory)*

### Part A (measurable without spend)

- **SC-A1**: Scoring a copy of the 025 root with only the runs root configured yields 4 of 6 scored runs summarized, 2 named no-summary runs with terminal class (crashed, terminated), the smoke excluded, a commit set of exactly one, SC-1 0.00 (n=6), SC-2-all n/a (4 measured), and SC-3 0.385 (n=13). This is the 025 baseline, produced by the rollup.
- **SC-A2**: A fixture task introducing a non-autofixable lint finding fails its attempt with that finding in the dev's feedback, and passes once corrected. An autofixable finding never reaches the check.
- **SC-A3**: The triage table covers 18 of 18 rows (5 failures and 13 loops), each with a class and an evidence pointer. Every "fixed" row has a red→green commit.
- **SC-A4**: The fast tier, with the fleet `.env` present, equals the documented baseline ids. Replay suites pass, or a declared incompatibility is recorded per the slice rule.

### Part B (P4's exit, or an honest second miss)

- **SC-B1**: At least 5 scored runs at one commit on the strong arm, aggregated by one rollup over a dedicated root, with no manual scan needed for the commit set or SC-2.
- **SC-B2**: **P4 exit**: SC-1 ≥ 0.80 (at n=5, 4 of 5), SC-2 ≤ 15 min on both the shipped and all-scored rows, and SC-3 ≥ 0.70 over a loop count at or above the floor. **Or** an honest second miss: each criterion's measured value, n and delta against the 025 baseline, plus the named cause of each remaining gap, taken from the triage classes.
- **SC-B3**: Spend stays within $13.95 judge + $1.00 research without a fresh owner go. Every run is announced and reported. Every infra failure halted the sequence.
- **SC-B4**: The lint conversion read is reported. Expected direction: fewer merge-reaching runs blocked by `lint_clean` than 025's 3 of 3.

**Expectation, stated in advance so the result cannot be re-read afterwards**: SC-1 and SC-2 become *measurable* with high confidence, because the plumbing is proven on old data first. **SC-1 at 0.80 and SC-3 at 0.70 are not likely** unless A.3 finds that the 13 loops fail through a small number of fixable defects. 025's lice and geotext loops ended in approve-to-proceed after 3 attempts, which points to case difficulty or reviewer behavior rather than harness faults, but the records cannot confirm this yet. The round is designed so that a second miss is still informative: measured, with deltas, and with a named cause for each remaining gap.

## Key entities

- **Scored selection**: the non-smoke runs in a dedicated runs root, each either summarized or listed with its terminal class.
- **Unplanned escalation**: a gate not decided by policy that is either outside the static `STAGE_GATES` allowlist (today `task:<id>`, `tool_approval`, `budget`) or ran SOFT. A planned gate decided with anything but `approve` is *steering* and disqualifies the run as well (A-2, A-8, research R3).
- **Task-attempt failure reason**: the failing check(s) and a bounded summary on a failed code, QA or review attempt record.
- **025 baseline**: the Part 0 re-read (SC-1 0.00 under both the current and the PRD-aligned rule, 0.33 only as a hypothetical had stage gates been HARD; SC-2 shipped n/a, SC-2-all n/a at n=4 (median 0.75 min); SC-3 0.385 over 13 loops; lint blocked 3 of 3 merge-reaching failures).

## Assumptions

- The owner's standing delegation covers recommended paths only. Q1–Q3 below are the points where the recommended path itself needs the owner's word: a measurement definition, a stage-behavior change, and the spend.
- 025's per-run session transcripts are on disk (`pipeline/<uuid>/sessions/`) and are A.3's primary source. Any cause they cannot settle is classed unrecoverable, never guessed.
- The 025 runs root and scratch-repo branches are kept read-only as evidence. Nothing in this round writes to them.
- `MIN_RUNS` stays 5. The engagement cap stays 10 min (025 Q1).
- One L crew round for Part A, plus Part B operations. If the plan sizes Part A beyond L, the cut is: A.1 + A.2 + A.4 stay, and A.3's fixes (not its triage table or FR-021's record field) defer, because SC-1 and SC-2 measurability and the lint conversion carry the most evidence per unit of work.

## GATE 1 questions

### Q1: SC-1 measurement design

**Context**: Part 0 H2 and B.4. The rollup's SC-1 ("no human-decided gate before merge") is stricter than the PRD's ("no unplanned escalations beyond configured gates"), and SOFT on a cold calibration ledger escalates every gate.

| Option | Answer | Implications |
|---|---|---|
| **A (recommended)** | Align the SC-1 rollup definition to the PRD (unplanned escalations only), and run the fleet `--gate-policy hard` with the attendant answering the configured gates | Measurable at n=5. SC-2 counts real planned-gate decisions. 025's indicative re-read is 0.33. Requires a measurement-definition change (rollup text and logic) |
| B | Mixed fleet: a gates-off (`off`) subset as the literal unattended instrument, with the rest SOFT and attended | The subset is below the n=5 floor unless the fleet grows to about 10 runs (about $25 judge ceiling). Otherwise SC-1 is n/a a third time |
| C | Whole fleet `off`, keeping the current SC-1 definition | SC-1 becomes "reaches merge at all". SC-2 reads 0 by construction (no interactions), which is met but empty |

### Q2: The lint fix path (a stage-behavior change)

**Context**: Part 0 H3. Lint runs first at merge (absolute, no fix loop), and autofix alone converts none of the three runs. FR-010/011 require per-task lint feedback, which changes what the code/QA task loop checks.

| Option | Answer | Implications |
|---|---|---|
| **A (recommended)** | Per-task: safe autofix, then a task-scoped lint delta under the merge gate's exact resolution, with findings entering the existing fix loop as attempt-failure feedback | Directly targets the measured blocker. Touches the task loop (replay proof or declared incompatibility needed). May lengthen loops and so pressure SC-3 |
| B | Prompt-only: the dev's instructions name the lint command and require a clean run before finishing. No check change | No stage change, nothing to replay. Weak: 025's agents already wrote their own `noqa`s that were themselves violations |
| C | Merge-time repair: autofix plus one dev repair pass when `lint_clean` is the only blocker | Keeps task loops unchanged, but adds a new loop to merge, a `GraphWorkflow`/stage-contract change the brief reserves for measured necessity |

### Q3: Re-fleet size and spend

**Context**: B.3 and B.5. 025 ended $0.015 under its ceiling.

| Option | Answer | Implications |
|---|---|---|
| **A (recommended)** | 5 scored runs plus smoke, cap 6; judge ceiling $13.95 + research $1.00 | The smallest fleet that yields SC-1/SC-2 rates. 4 of 5 needed for SC-1 |
| B | 6 scored plus smoke, cap 7; ceiling about $15.70 + $1.00 | One extra observation of slack. SC-1 then needs 5 of 6 |
| C | Part A only this round, re-fleet deferred | $0. P4 stays open with measurable instruments but no new reads |

## GATE 1 record (2026-11-18)

Owner rulings, relayed by the orchestrator under the standing delegation; all three recommendations accepted:

- **Q1 → A.** SC-1 follows the PRD rule: only unplanned escalations count against it; configured gates do not. The fleet runs `--gate-policy hard`, and the attendant answers the planned gates (FR-006, B.4).
- **Q2 → A.** Per task: apply safe autofixes, run the merge gate's own lint scoped to what the task introduced, and feed the remaining findings into the existing fix loop (FR-010/011). The merge gate is unchanged (FR-012).
- **Q3 → A.** Smoke plus 5 scored runs (cat-cafe ×2, readtime, geotext, lice), cap 6. Judge ceiling $13.95 plus $1.00 research. At n=5, SC-1 needs 4 of 5 (B.3, B.5).
- **Framing accepted.** The likelihood note under Success criteria is the round's framing: the targets are not likely to be met, and a second miss still yields deltas and named causes.
- **Rider accepted.** The `.env` test-isolation fix is part of the round (FR-030, A.4). T034 is closed by FR-001 to FR-004 (R2).

No open questions remain.

## Amendments after the consults (2026-11-18; dispositions in plan.md)

The skeptic answered first. The advisor's consult landed after the orchestrator's degradation ruling and after plan pass 1 was drafted. It was folded in before tasks were finalized (A-8). The record is in `consults/README.md`.

- **A-1 (skeptic 1, adopted).** The 025 baseline is the scored set: smoke excluded, crashes counted. That gives SC-1 0.00 (n=6), SC-2-all n/a (4 measured), and SC-3 0.385 (n=13). Part 0, SC-A1 and quickstart already carry these numbers.
- **A-2 (skeptic 2, adopted).** SC-1's planned gates are a fixed allowlist, `STAGE_GATES = {research, clarify, architecture, plan, merge, deploy}`. Any other gate is unplanned whatever its `policy`: `task:*`, `tool_approval`, `budget`, `deploy_failed`. A SOFT gate decided by a person is unplanned. **Steering guard:** a planned gate a person decided with any outcome other than `approve` (that is, `revise` or `reject`) disqualifies the run from SC-1. The attendant protocol is approve-only on planned gates; a REVISE is disclosed as operator steering. The `SC-1-strict` companion (025 rule) is rendered beside the headline.
- **A-3 (skeptic 3, adopted as disclosure plus protocol).**
  - Under HARD, a merge whose deterministic gate passes clean consults no MergeVerdict and opens no merge gate (`stages/merge/step.py:582-583`). HARD merge is also the production default (`core/models.py:383-390`). The fleet report states that 026's clean merges did not exercise MergeVerdict, as 025's SOFT runs did.
  - The benchmark override replaces merge's `on_timeout=HOLD` with REJECT (`benchmarks/workflow.py:163`). This is recorded and not changed (trust layer).
  - The attendant must service **both** pending gates **and** pending clarification waits (`stages/clarify/step.py:293-318`). It runs a watchdog that alerts after 30 minutes with nothing serviced while a run is active.
  - A planned gate decided by `timeout` is infra (research R8).
- **A-4 (skeptic 4, adopted).** The fleet report shows three SC-3 rows, pinned as the identifiers `SC-3` (overall), `SC-3-non-lint` (comparable to 025's 0.385) and `SC-3-lint` (lint-triggered loops), all from FR-021's `checks`. Autofix never touches fenced test paths on repair attempts, and runs before the checkpoint (research R4).
- **A-5 (skeptic 5, adopted).**
  - The attendant polls cumulative run cost on a 60-second wall-clock interval, not only at gates.
  - Optional run 6 is authorized only if the remaining judge headroom is at least $1.73 (1.5 × readtime).
  - n=5 is stated as the floor, not proof of reliability: 4 of 5 has a 95% exact CI of [0.28, 0.99]. The fleet report prints that interval beside SC-1.
- **A-6 (skeptic 6, adopted).** The transcripts are on disk, so A.3 reads them first. Part 0 H4 and Assumptions are amended.
- **A-7 (planner, from evidence).** Run 6's trigger is SC-2-measured runs (B.3), because a crash leaves SC-2 below its floor.
- **A-8 (advisor D1–D7, adopted; detail in research R1–R7).**
  - FR-001 is realized by a single shared resolver, `S/runs_paths.py`. It is used by every writer and reader of the records and export roots, and guarded by parity and source tests. One named behavior change: a host exporting `SDLC_RUNS_ROOT` sees its exports move together with their readers.
  - The no-summary classes are keyed on the cell record's `pipeline_finished`, and add `summary_missing` (a fail-closed miss). The child-failure string gains its cause type (a `BenchmarkWorkflow` string-only edit, surfaced at GATE 2) so that `timed_out` can be told apart.
  - The SC-1 rule uses `decided_by != "policy"`, so a timeout on a task gate is still an escalation. Unknown gate names count as unplanned.
  - Per-task lint uses merge's `ScopedLintReport` type, and its base is a sibling of the task worktree (ruff's config walk). Lint is kept out of the QA and review LLM prompts. NOT_COLLECTED never fails a task. Fenced findings are reported but do not fail. The autofix placement stays before the checkpoint (planner); the advisor's anchor-advance alternative is recorded in research R4.
  - The failure field carries the text the dev was actually shown.
  - The run-1 fix catches `UnexpectedModelBehavior` only, not bare `Exception`. The mechanism is verified in the installed pydantic-ai-harness.
  - The `.env` flag is set at conftest import, with two follow-ups (`dotenv_values` for the paid opt-in test, and a `child_env` helper).
  - **Backlog card:** the calibration ledger never sees benchmark summaries, because they sit one directory level deeper than its glob. FR-040 freezes the ledger, so this is not fixed here.

## GATE 2 record (2026-11-18)

Accepted under the owner's standing delegation. Reviewer verdicts: plan pass 1 fixes-needed (1 blocking, all four gaps folded), plan pass 2 **approve** (0 blocking, 6 non-blocking; the 3 cosmetic spec glosses applied, and note 5 pinned in T001), tasks pass 1 **approve** (0 blocking, 2 non-blocking, both folded). Binding on exec:

- **plan.md (revision 2) and tasks.md are consumed as written.** Part A is T001–T027. Part B is T040–T052, and it starts only after T027 is merged and **T008's $0 re-score reproduces the corrected 025 baseline**.
- **The surfaced items are accepted as disclosed** (plan "Surfaced for GATE 2", items 1–9):
  1. The run-1 fix narrows residual R1 to an `UnexpectedModelBehavior`-only catch. It is conditional on T021's evidence.
  2. Per-task lint may lower SC-3 and SC-1. The three SC-3 rows make that visible.
  3. HARD skips MergeVerdict on clean merges, and the benchmark override replaces merge's HOLD timeout with REJECT. Both are disclosed and unchanged.
  4. The attendant duty is wider: it services gates and clarification waits, approves only on planned gates, runs a 30-minute watchdog and 60-second cost polling, and a `timeout` decision means infra.
  5. n=5 is the floor. The CI prints beside SC-1.
  6. The corrected 025 baseline stands: SC-1 0.00 (n=6), SC-2-all n/a (4 measured), SC-3 0.385 (n=13).
  7. The named run-paths behavior change for hosts that export `SDLC_RUNS_ROOT`.
  8. The string-only cause-type edit in `BenchmarkWorkflow`.
  9. The calibration-glob gap is a backlog card, not a fix.
- **Spend, as GATE 1 Q3-A ruled:** smoke plus 5 scored runs, cap 6; judge ceiling $13.95 plus research $1.00; per-run stops cat-cafe $3.00, readtime $1.73, geotext $1.91, lice $1.40. Run 6 only if fewer than 5 scored runs are SC-2-measured **and** judge headroom is at least $1.73.
- **The 025 tripwires bind unchanged:** any infra stop halts the sequence; a second infra stop, a crossed ceiling, or more than 6 scored runs ends the delegation; a tree-editing fix restarts the fleet with a fresh owner go.
