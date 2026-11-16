# Feature Specification: Round 025 — the SC-2 instrument and the fleet runs (P4 exit)

**Feature Branch**: none (spec-only phase; writes under `.specify/specs/025-sc2-instrument-fleet-runs/` only)

**Created**: 2026-11-16

**Status**: GATE 1 and GATE 2 cleared 2026-11-16 — ready for exec

**Input**: Orchestrator TASK BRIEF, 2026-11-16: "round 025, the last leg of P4: the SC-2 instrument, then the fleet runs that put SC-1..3 at target (P4's exit criterion). Part code, part operations; the operations half is paid." The 023 program table names this round (R025 a/b/c). 024 supplies the pool infrastructure it consumes.

---

## Part 0 — Hypotheses checked against the repo

| # | Brief's hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | SC-2 has no instrument | **Confirmed** | `src/sdlc/benchmarks/sc_rollup.py` builds SC-1, SC-3, SC-4, SC-6 (+advisory) only. `RunSummary` has no operator-time field. `ROADMAP.md:479` "SC-2 ≤15 min — not measurable". PRD wording: *"Median operator time per shipped feature ≤ 15 minutes of decisions"* (`PRD.md:668`) |
| H2 | The path in the brief, `benchmarks/sc_rollup.py` | **Stale path** | The file is `src/sdlc/benchmarks/sc_rollup.py`. (`benchmarks/` at repo root holds cases and config only) |
| H3 | A run already records who decided what | **Partly** | `GateOutcomeSummary` records `decided_by` (`human`/`policy`/`timeout`) and `decided_at`. `ClarificationOutcome.answered_by` records `human`/`suggested`/`unanswered`. **No record of when a gate or question was raised**, so no duration is derivable. `pending.py` carries `opened_at` for the live inbox only, and it is not retained into `RunSummary` |
| H4 | Fleet runs measure SC-1/2 as-is | **Contradicted by the defaults** | Benchmark runs force **every gate to `spec.gate_policy`, SOFT by default** (`benchmarks/workflow.py:158-164`). A SOFT gate auto-approves above its confidence bar. Left alone, SC-1 passes almost by construction and SC-2 reads ~0. See Q2 |
| H5 | Candidate cases are runnable locally | **Not on this host yet** | Every non-probe case points at `/srv/scratch-repos/<case>`; that directory **does not exist here**. Corpus cases also demand a clean tree and a passing smoke stamp for the exact commit (`benchmarks/cli.py` `_run_matrix`) |
| H6 | "z.ai subscription only" holds end to end | **Contradicted at the judge** | Authors are `zai-coding-plan/glm-5.3` / `glm-5.3-flash`. The **judge is `anthropic:claude-sonnet-5`** on every case, by ADR-6 (family-decorrelated from the author). It is an Anthropic API spend, not the z.ai subscription. See Q3 |
| H7 | 024 proved full pipeline runs | **Confirmed it did not** | 024 SC-003 used barrier fakes for `run_coding_task`. Pool *mechanics* are proven; no real multi-run pipeline execution has happened on pools |

---

## Part A — The SC-2 operator-time instrument (code, size L)

### A.1 What "operator time" means (the design boundary)

**Operator time of a run** = the sum, over every **human-decided interaction** in the run, of that interaction's **engaged time**.

*Human-decided interactions* — exactly the events the summary already classifies as human:

1. a gate whose `decided_by` is `human` (clarify, architecture, plan, merge, deploy, budget, and the per-task `task:<id>` fix-loop escalation);
2. a clarification question whose `answered_by` is `human`;
3. a merge override entered by a human (the inbox resolves these).

Not operator time: `policy` decisions, `timeout` decisions, `suggested` clarification answers, and any time a human merely *could* have acted. Wall-clock **wait** (raised → decided) is recorded but is **not** operator time: a gate that sat overnight must not read as eight hours of work.

*Engaged time* of one interaction is the interval from the moment it was **raised** to the moment it was **decided**, **capped** at a per-interaction engagement cap. Rationale: the system sees raise and decide; it cannot see when a person started reading. The cap bounds the error in the only direction that matters (overnight waits). The cap's value is Q1.

SC-2 aggregate: **median operator time per shipped run**, where *shipped* = the run reached `deployed:` or `merged-not-deployed:` (the PRD's "shipped feature"). Target ≤ 15 min. Below the existing `MIN_RUNS` floor the rate renders n/a, like every other criterion.

### A.2 User stories

#### User Story A1 — A run emits its own operator time (Priority: P1)

An operator finishes a run and finds, in that run's summary, how many human interactions it took and how long each engaged them, with the total.

**Independent test**: drive a run (fakes) with one human-answered gate, one human-answered clarification and one policy-decided gate; assert the summary lists exactly the two human interactions with raise/decide times and the total, and lists the policy gate as zero.

**Acceptance scenarios**:

1. **Given** a gate raised at T and decided by a human at T+4 min, **When** the run closes, **Then** the summary records that interaction with engaged time 4 min.
2. **Given** a gate raised at T and decided by a human at T+9 h, **When** the run closes, **Then** engaged time equals the cap, and the 9 h is recorded as wait.
3. **Given** a run with no human interaction, **When** it closes, **Then** operator time is a recorded **0**, distinct from "not measured".
4. **Given** a summary written before this round (no raise times), **When** it is aggregated, **Then** it is counted as **not measured** (excluded from SC-2's n and named in the output), never as 0.

#### User Story A2 — The rollup reports SC-2 beside the others (Priority: P1)

`sdlc benchmark score` renders SC-2 in the same table as SC-1/3/4/6, in markdown, HTML and JSON.

**Acceptance scenarios**:

1. **Given** ≥ `MIN_RUNS` shipped runs with operator time, **When** scored, **Then** SC-2 shows the median, n, target `<=15 min`, and its definition note.
2. **Given** fewer than the floor, **Then** SC-2 renders n/a.
3. **Given** a mix of measured and not-measured runs, **Then** the not-measured count is stated and excluded from n.
4. **Given** SC-2 is shown, **Then** the output also states how many of the shipped runs had **zero** human interactions, so an all-zero result cannot be mistaken for a measured effort (H4).

#### User Story A3 — SC-1 and SC-2 cannot be read independently of how gates ran (Priority: P2)

The rollup states the gate policy the runs executed under, because SC-1 and SC-2 are only interpretable with it (H4).

**Acceptance scenarios**: **Given** runs under SOFT, HARD or mixed policy, **Then** the rollup names the policy mix beside SC-1 and SC-2.

### A.3 Functional requirements

- **FR-001**: A run summary MUST record, for each human-decided interaction (A.1 list), its kind, identifier, raised time and decided time.
- **FR-002**: The raised time MUST be captured at the moment the gate or question is raised, in workflow-deterministic fashion (replay-safe, no wall-clock read inside workflow code outside the existing deterministic-time mechanism).
- **FR-003**: The summary MUST expose per-run operator time (capped engaged sum), uncapped wait (reported separately), and interaction count.
- **FR-004**: The engagement cap MUST be a single named, documented constant; the value is Q1. Changing it MUST NOT require re-running runs (recomputable from retained raise/decide times).
- **FR-005**: "Not measured" (legacy summary, or raise time missing) MUST be distinguishable from 0 everywhere it is stored or rendered.
- **FR-006**: `sc_rollup` MUST add an SC-2 rate as median operator time over shipped runs, with the n/a floor shared with the other criteria, and MUST render it in markdown, HTML and JSON.
- **FR-007**: The SC-2 note MUST state the definition, the cap, and the zero-interaction count (A2-AS4).
- **FR-008**: The rollup MUST report the gate-policy mix of the selected runs (A3).
- **FR-009**: The instrument MUST NOT change any gate's behavior, outcome, timing or policy, and MUST NOT change the replay of existing workflow histories (new data is additive and defaulted). The trust layer is untouched.
- **FR-010**: Pre-round summaries and records MUST continue to load and aggregate unchanged.
- **FR-011**: The stale `benchmarks/sc_rollup.py` path in the ROADMAP SC rows MUST be corrected as a rider. *(Found already correct in ROADMAP (research R9); the rider is realized as updating the SC rows and P4 line with the measured read, T033.)*

### A.4 Out of scope for Part A

- Measuring the human's actual reading or thinking time (no viewer telemetry); the cap is the honest substitute.
- Operator time for maintenance-loop (023) gates; only pipeline runs feed SC-2.
- Any change to SC-4/SC-6 definitions.

---

## Part B — The fleet-run protocol (operations, paid)

### B.1 Sequencing and gates

Part B starts only when Part A is merged, verified, and the tree is clean at one **fleet commit** (HEAD after the instrument lands). Part B has its **own gate** (GATE 2: protocol and ceiling confirmed) before the first run; thereafter the owner's standing delegation (2026-11-15) covers the recommended-path runs, each announced before it starts.

### B.2 Host prerequisites (each verified before run 1)

1. `/srv/scratch-repos/<case>` seeded for each selected case (absent on this host today, H5).
2. The pools overlay up (`docker compose -f docker-compose.yml -f docker-compose.pools.yml`; `docs/operations/worker-pools.md`), harness cap ≥ intended concurrency (Q3 sizing rule from 024), doctor green.
3. A passing smoke stamp for the fleet commit; clean tree.
4. `SDLC_RUNS_ROOT` set to a fresh, dedicated directory so the rollup's selection is exactly this fleet.
5. z.ai credentials present; judge credential present (Q3).

### B.3 Case selection

Selection rule: public or locally runnable, role `corpus` or `smoke`, **never** `parked` (hone, particle-swarm-optimization, stocktrends are parked for cause) and never `probe`.

| Case | Role / visibility | Use | Rationale |
|---|---|---|---|
| todo-api-greenfield | smoke / private | **unscored** corpus-gate smoke only (B.9) | `check_smoke` demands it; trivial, so it never pads a rate |
| deveval-readtime | corpus / public | runs 1 and 5 | small; judge-free in-run (`rubrics: {}`); the repeat is a same-case variance read |
| deveval-lice | corpus / public | runs 2 and 6 | second public case; judge-free in-run |
| deveval-geotext | corpus / public | run 3 (and top-up run 7) | third public case; judge-free in-run |
| cat-cafe-monitoring | corpus / private | run 4 | the one case with held-out grading, tasks, vetoes and rubrics; **conditional** on its scratch repo being seedable and on research-provider keys (a non-z.ai service); if either fails pre-flight it is replaced by a repeat of lice and the fleet report says so |

**Arm**: the strong arm (`zai-coding-plan/glm-5.3`) on every run. Corpus cases refuse a multi-arm run without `--arm`/`--all-arms`; the weak arm is a *separation* experiment, not a fleet measure, and mixing arms breaks comparability.

**Recommended count: 6** scored runs, all `corpus`. Cap 7. Run 7 is **pre-authorised only** if, after run 6, fewer than 5 runs are *shipped and measured* (SC-2's floor); if SC-2 is still n/a after 7, it is reported "not measurable at this n" and the delegation is not extended.

### B.4 Comparability rules

1. **One commit.** All runs at the fleet commit, clean tree, recorded provenance on every record.
2. One arm, one judge model, one gate policy (Q2), one pool configuration for the whole fleet.
3. **A commit change voids the fleet.** An infrastructure fix that edits the tree restarts the count at the new commit; earlier runs are retained as evidence but excluded from the rollup. A fix outside the tree (host, credentials, compose) does not.
4. Runs execute **one at a time until two have completed**; after that at most 2 may overlap (the pools cap). At an infrastructure stop, in-flight runs are allowed to finish and are classified on their own; no new run starts.
5. No re-running a run to "improve" it. A rerun happens only after an infrastructure stop (B.6), and the original is kept and labelled.

### B.5 Failure scoring

- **Case failure** (the pipeline ran and the case beat it: rejected outcome, red oracle, exhausted fix loop): the run **counts** in SC-1's denominator (not reaching merge *is* the miss) and in SC-3's loops, and is also **listed apart** in a failures table with its cause. It does not stop the sequence.
- **Infrastructure failure** (the pipeline could not run: worker down, provider outage, credential, routing, host, quota): the run is **not scored** in any rate, is listed apart as `infra`, and **stops the sequence** for diagnosis. The sequence resumes only after the owner has the diagnosis.
- **The case/infra rule is pre-registered, not judged post hoc.** A failure is `infra` only if (a) no stage produced a valid artifact or record, or (b) a verifiable host, process, HTTP 5xx, quota or auth error occurred outside harness task execution. Context exhaustion, harness task timeouts, bad code or tests, and oracle or rubric misses are **always case failures**. A contested call is scored as case failure and ALSO shown in a one-line sensitivity row (the rate with the run excluded). The classification and its evidence are recorded per run.

### B.6 Announcement and spend protocol

Before each run the operator posts: run number, case, arm, fleet commit, expected cost (from the case's prior records, or "no prior"), cumulative spend, remaining ceiling. After each run: outcome, class (success / case-failure / infra), actual cost, SC-2 interaction count, cumulative spend.

**Cost ceiling**: stated in dollars before run 1, as `1.5 ×` the sum of expected per-run costs, with the per-run expectation read from existing benchmark records of the same case (Part B's pre-flight reads them; where a case has none, the smoke run's measured cost stands in). The dollar ceiling has separate lines for the Anthropic judge and the research provider (Q3); the z.ai subscription is flat and has no dollar line. There is **no per-run budget switch for benchmark runs** (`run_budget_usd` defaults to 0 and `CaseSpec` carries none), and a budget gate would itself be an operator interaction; so the per-run stop is the operator cancelling the workflow when its running cost crosses the announced per-run limit. No code is added for this. The z.ai spend is a flat subscription: it is recorded (tokens, duration) but has no dollar ceiling; the ceiling lines are the Anthropic judge dollars and the third-party research provider. Crossing the ceiling, exceeding 7 scored runs, or a second infra stop (a failed **smoke** counts) **ends the delegation**: further runs need a fresh owner go. A fleet restart on a new commit (B.4 rule 3) also needs a fresh owner go for the remaining spend. *(No dollar figure is held here on purpose: this host has no benchmark records, and an invented number would be quoted. The ceiling is computed after the smoke run from its measured judge cost scaled by rubric count (todo-api 2 rubrics x 2 arms; cat-cafe 5), and announced before run 1.)*

### B.7 What to record and how the rollup consumes it

Per run: bench run id, run id, class, outcome, cost (author and judge), duration, interactions and operator time (from Part A), the operator's classification note. Per fleet: one `sdlc benchmark score` over the dedicated `SDLC_RUNS_ROOT`, with SC-1/2/3 (and 4/6 as by-products) rendered, saved beside a short **fleet report** that states the read against target and the honest-miss section if any.

### B.8 Operations functional requirements

- **FR-020**: The protocol (B.2–B.7) MUST be written as an operations document in the repo, with the pre-flight checklist and the announcement template.
- **FR-021**: Run 1 MUST NOT start until every B.2 prerequisite is evidenced.
- **FR-022**: Each run MUST be announced before it starts and reported after it ends (B.6).
- **FR-023**: An infrastructure-class failure MUST halt the sequence; no run starts until the owner clears it.
- **FR-024**: All scored runs MUST share one commit; the rollup MUST show the commit set and flag more than one.
- **FR-025**: The fleet report MUST state, for each of SC-1/2/3, measured value, n, target, and met/missed; a miss MUST be recorded as a miss with its evidence, never rounded or re-run away.

---

## Success Criteria *(mandatory)*

- **SC-A1**: A single scored run shows its operator time, interaction count and wait; a no-human run shows 0, a legacy run shows "not measured".
- **SC-A2**: `sdlc benchmark score` over a mixed selection renders SC-2 beside SC-1/3/4/6 in all three formats, n/a below the floor.
- **SC-A3**: Existing workflow histories replay unchanged and the pre-round fast tier is no worse than its documented baseline.
- **SC-B1**: At least 5 scored (non-infra) runs exist at one commit, all on the strong arm, aggregated by one rollup over a dedicated runs root.
- **SC-B2**: The fleet report states SC-1, SC-2 and SC-3 each as measured with n, **at target or an honest recorded miss**.
- **SC-B3**: Total spend never exceeded the announced ceiling without a fresh owner go; every run has an announcement and a post-run report.
- **SC-B4**: Every infrastructure failure halted the sequence before the next run started.

**Interpretation guard**: SC-1 ≥ 0.80, SC-2 ≤ 15 min median, SC-3 ≥ 0.70 (`PRD.md:666-669`, `sc_rollup.py`). With n≈6, SC-1 at 0.80 means 5 of 6; SC-3's denominator is fix *loops*, not runs, and may itself fall below the n/a floor if few loops occur — in which case SC-3 is reported **not measurable at this n**, not "met".

## Assumptions

- The owner's standing delegation (dated 2026-11-15 in the brief) covers the recommended count and path, announced per run, and nothing beyond.
- The 024 pool infrastructure works as verified; this round consumes it and does not change it.
- The rollup's existing floor (`MIN_RUNS`) is kept.
- Corpus cases need the smoke gate (`sdlc benchmark smoke`) at the fleet commit; that smoke run is itself a paid run and is counted in spend but is not one of the scored runs.

## GATE 1 record (2026-11-16)

Owner rulings, relayed by the orchestrator under the standing delegation (recommended answers taken):

- **Q1 → 10 minutes.** The engagement cap is 10 min per interaction (FR-004).
- **Q2 → SOFT, owner answers escalations.** SC-2 is always reported **with the zero-interaction count and the policy mix** so the weaker evidence is explicit (A2-AS4, A3, FR-007, FR-008).
- **Q3 → the plan checks first.** The plan MUST establish whether SC-1..3 runs can skip quality judging. If yes, z.ai-only holds. If no, the Anthropic judge stays, its cost is a **separate ceiling line**, and the orchestrator announces it before any such run proceeds (B.6).
- **Accepted riders/additions:** scratch-repo seeding and the corpus smoke stamp (paid, unscored, announced); the stale-path rider (FR-011); a `raised_at` field on `GateOutcomeSummary` (and the clarification equivalent) as the instrument's data source (FR-001/002).

No `[NEEDS CLARIFICATION]` markers remain.

Defaults chosen without asking (still reversible): 6 runs / cap 7; strong arm only; case list in B.3; per-run budget plus a fleet ceiling at 1.5x expected; tree-editing infra fixes restart the fleet.

## B.9 and amendments after the consults (2026-11-16; advisor + skeptic, dispositions in plan.md)

- **B.9 Smoke stamp.** Corpus runs refuse without a passing smoke stamp for the exact commit (`benchmarks/cli.py` `_run_matrix`; `check_smoke` needs rubric scores on `clarify` and `architecture`, so it needs the Anthropic judge and cannot be judge-free). `sdlc benchmark smoke` runs the smoke case across **all its arms** (two for todo-api) and needs the oracle to pass on every cell. It is announced, unscored, budgeted as two arms, and a smoke failure from case difficulty stops for the owner (never `--skip-smoke` without a fresh go). **Q3's answer:** z.ai-only holds for the three deveval runs; the smoke and cat-cafe need the Anthropic judge, each a separate announced ceiling line.
- **A.5 Companions that stop SC-2 being gamed (FR-012..015).** FR-012: SC-2 is reported in two rows: the PRD headline over *shipped* runs, and a companion over **all scored runs**; "SC-2 at target" requires both <= 15 min. FR-013: the rollup also shows the human-touched median and max, the uncapped wait, and the SC-4 human-answered fraction beside SC-2. FR-014: the rollup states the **commit set** by joining each summary to its benchmark records by run id, and flags more than one commit or a summary with no record. FR-015: SC-1 and SC-2 carry an **evidence tier** line: when every gate ran SOFT, they render "weak evidence (SOFT: no gate asked a human unless it escalated)". Whether P4 may close on SOFT-tier evidence is the owner's call at GATE 2, not the rollup's.
- **A.6 Counting rules (advisor D1-D3).** A batch of clarification questions raised and answered together is **one** interaction (capped once). "Human" means `decided_by` not in {`policy`, `timeout`} (the merge override can carry a reviewer name). Overlapping interactions are summed, so SC-2 is an upper bound and says so. A human interaction with no raise time makes the run "not measured". Raised time is read from the existing `GATE_AWAITED` / `CLARIFICATION_ASKED` event times; no new events or signals.
- **SC-3 and SC-2 floors.** Few fix loops are expected; SC-3 below the floor is reported "not measurable at this n" with the first-pass rate and per-case loop counts, and is a miss against P4's exit, never "met".
- **Host.** Corpus runs also demand a clean tree at the commit: the fleet runs from a dedicated checkout of the fleet commit, and **no commit may land between the smoke stamp and the last run**.
- **Rider outcome.** ROADMAP's SC rows already cite `src/sdlc/benchmarks/sc_rollup.py`; the stale path survives only in historical `docs/superpowers/` plans, which are left as written. The rider reduces to updating the SC-2 row and the P4 line with the measured read.

## GATE 2 record (2026-11-16)

Accepted under the owner's standing delegation (recommended answers taken independently). Binding on exec:

- **SOFT stands** (GATE 1 Q2). SC-1 and SC-2 are reported with the weak-evidence tier line, the policy mix and the zero-interaction count. The orchestrator discloses to the owner, before the fleet runs execute, that P4 would close on SOFT-tier evidence.
- **Spend lines accepted as briefed:** the smoke run (paid, unscored, Anthropic judge, two arms); cat-cafe with the Anthropic judge and the research key, **conditional**, with the lice-repeat fallback; fleet ceiling = 1.5x the measured judge cost scaled by rubric count, set after smoke and announced before run 1.
- **T020 stop-guard:** if the compose worker image runs its own baked copy of the code rather than the checkout's, the sequence **stops**.
- **Fleet host rules bind:** a dedicated clean checkout of the fleet commit; no commits between the smoke stamp and the last scored run; a tree-editing infrastructure fix restarts the fleet and needs a fresh owner go.
- **Unchanged:** plan.md and tasks.md are consumed by exec as written (plan reviewer approve; tasks reviewer approve at pass 2).
