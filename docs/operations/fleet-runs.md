# Fleet runs — operations

The round-025 protocol for running the benchmark **fleet**: a set of paid
corpus runs at one commit that puts SC-1/2/3 on the record together. This
page is the operator's manual; the normative sources are the
[round 025 spec](../../.specify/specs/025-sc2-instrument-fleet-runs/spec.md)
(GATE 1/GATE 2 records included) and
[its tasks](../../.specify/specs/025-sc2-instrument-fleet-runs/tasks.md).

## What operator time means (SC-2)

**Operator time of a run** is the sum, over every human-decided
interaction, of that interaction's **engaged time**. A human-decided
interaction is exactly:

1. a gate whose `decided_by` is `human` — or a **merge override carrying a
   reviewer name** (anything not `policy`/`timeout` engaged a person);
2. one **clarification batch**: questions raised together (they share a
   raise time) count as ONE interaction when at least one was answered by
   a human, deciding on the batch's latest answer.

*Engaged time* runs from raised to decided, **capped at 10 minutes per
interaction** (`ENGAGEMENT_CAP_S = 600`, owner ruling Q1): the system sees
raise and decide, not when reading started, and the cap bounds that error
in the only direction that matters — overnight waits. Uncapped **wait**
(raised → decided) is recorded beside it, never summed into operator time.

Three honest states, never conflated: **measured** (n ≥ 1 human
interaction), **zero** (instrumented, no human interaction), and **not
measured** (a pre-025 summary, or a human interaction missing its raise
time). Overlapping interactions are summed, not merged — per-run totals
are an **upper bound** and are reported as such.

## How a run emits it

No new events, signals or workflow code (FR-009):

- `GATE_AWAITED` already carries the moment a gate opened for a human; the
  retro-stage summary builder keys it `(gate, round)` onto
  `GateOutcomeSummary.raised_at`. `CLARIFICATION_ASKED`/`ANSWERED` give
  `ClarificationOutcome.raised_at`/`answered_at` (unanswered stays `None`).
- `RunSummary.operator_instrumented` marks summaries written by the 025
  builder — the pre/post boundary for "not measured".
- `sdlc.benchmarks.operator_time` derives the per-run numbers from those
  raw times (pure; changing the cap re-derives, never re-runs).
- `sdlc.benchmarks.sc_rollup` renders SC-2 (shipped runs: `deployed:` /
  `merged-not-deployed:`) and SC-2-all (all scored runs), each flooring on
  its own n, with the companions that stop SC-2 being gamed: zero-count,
  human-touched median/max, uncapped wait median, SC-4 beside, the gate
  policy mix, and the evidence tier. The **commit set** joins summaries to
  benchmark records by run id and flags a mixed set or any summary no
  record vouches for.

## Pre-flight checklist (B.2)

Run 1 does not start until every line is evidenced (round 025 records it
in `preflight.md`):

1. `/srv/scratch-repos/<case>` seeded for every selected case, each
   passing `sdlc benchmark verify-case --case <id>` (cat-cafe is
   conditional on its scratch repo and the research provider key; if
   either fails it is replaced by a lice repeat, and the fleet report
   says so).
2. The pools overlay up (`docker compose -f docker-compose.yml -f
   docker-compose.pools.yml`), harness cap ≥ intended concurrency
   ([worker pools](worker-pools.md)), `doctor` green.
3. A passing **smoke stamp** for the exact fleet commit — paid, unscored,
   announced, both arms, Anthropic-judged (the stamp cannot be judge-free).
4. `SDLC_RUNS_ROOT` set to a fresh, dedicated directory: the rollup's
   selection is then exactly this fleet.
5. z.ai credentials present; judge credential present; research-provider
   key when cat-cafe runs.
6. `adversarial_review_enabled` resolves **False** (it defaults off).
7. The compose worker image runs **the checkout's code**, not its own
   baked copy — if it does not, **STOP** (T020 stop-guard; provenance is
   stamped from the CLI's tree).

The spend ceiling is set **after** the smoke run — 1.5× the measured judge
cost scaled by rubric count — and announced before run 1.

## Fleet host rules

- **Dedicated clean checkout** of the fleet commit for the whole fleet;
  `git status --short` must be empty.
- **Commit freeze**: no commit lands between the smoke stamp and the last
  scored run. All scored runs share one commit, one arm, one judge model,
  one gate policy, one pool configuration.
- A commit change **voids the fleet**: runs at the old commit stay as
  evidence but leave the rollup. An infrastructure fix that **edits the
  tree** restarts the fleet on a new commit and needs a fresh owner go; a
  fix outside the tree (host, credentials, compose) does not.
- Runs execute **one at a time until two have completed**; after that at
  most 2 overlap (the pools cap). At a stop, in-flight runs finish and are
  classified on their own; no new run starts.
- **No re-running a run to improve it.** A rerun follows only an
  infrastructure stop, and the original is kept and labelled.

## Failure classes (pre-registered)

The rule is fixed before the runs, not judged after:

- **Case failure** — the pipeline ran and the case beat it (rejected
  outcome, red oracle, exhausted fix loop; context exhaustion, harness
  timeouts, bad code/tests, oracle or rubric misses are ALWAYS this). It
  counts in SC-1's denominator and SC-3's loops, is listed apart with its
  cause, and does not stop the sequence.
- **Infrastructure failure** — the pipeline could not run: no stage
  produced a valid artifact, or a verifiable host/process/HTTP-5xx/quota/
  auth error occurred outside harness task execution. Not scored, listed
  apart as `infra`, and **halts the sequence** for owner diagnosis.
- A **contested** call is scored as a case failure AND shown in a
  sensitivity row (the rate with the run excluded).

## Announce and report (B.6)

Before each run:

```
RUN <n>/<cap>: case <case>, arm <arm>, commit <fleet-commit sha>
expected cost: <from prior records | no prior>; spend so far $<x>; ceiling left $<y>
```

After each run:

```
RUN <n> done: outcome <outcome>, class <success | case-failure | infra>,
cost $<actual> (author/judge split), SC-2 interactions <k>, cumulative $<x>
```

The smoke run is announced the same way (two arms, expected judge spend,
no prior). Escalations during a run are answered by the owner.

## Stop rules

- An **infra-class** failure halts the sequence; nothing starts until the
  owner clears it. A smoke failure from case difficulty stops for the
  owner — never `--skip-smoke` without a fresh go. A failed smoke counts
  toward the two-stop limit.
- **Crossing the announced ceiling**, exceeding **7 scored runs**, or a
  **second infra stop** ends the standing delegation: further runs need a
  fresh owner go. A fleet restart on a new commit also needs one for the
  remaining spend.
- The per-run stop is manual: the operator cancels the workflow when its
  running cost crosses the announced per-run limit (no budget switch
  exists, and a budget gate would itself be an operator interaction).

## Scoring the fleet

```bash
SDLC_RUNS_ROOT=<the dedicated dir> uv run python -m sdlc.cli benchmark score --all
```

One rollup over the dedicated runs root; the outputs are saved beside the
fleet report, which states for each of SC-1/2/3: value, n, target,
met/missed and the evidence tier; SC-2 shipped and all-scored; the commit
set (it must be exactly one); the failures and `infra` tables apart; the
sensitivity row for any contested classification; per-case loop counts and
first-pass rate for SC-3; total spend against the ceiling; and an
honest-miss section — a miss is recorded as a miss, never rounded or
re-run away.
