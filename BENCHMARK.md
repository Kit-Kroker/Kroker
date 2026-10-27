# Benchmark & Evaluation Foundation — Agentic SDLC Factory

| | |
|---|---|
| Status | Design input — not yet reconciled into ROADMAP.md |
| Companion to | `ROADMAP.md`, `SDLC-spec-v2.md`, `ARCHITECTURE.md`, `PRD.md` |
| Source of truth for scope | `PRD.md` / `ARCHITECTURE.md` / `SDLC-spec-v2.md` (this doc adds none) |
| Anchoring rule | Like every `E-` item: this doc is *how we measure* requirements already open in the tracker, not new requirements. Genuinely new scope is marked **(new scope)** and needs a PRD change before it is real. |

> **What this document is.** The factory already has a benchmark harness
> (`benchmarks/workflow.py`, landed with **E-27**) and a prompt eval loop
> (`sdlc eval`, **E-4**). What it does not yet have is a *measurement design*:
> a stated ground-truth strategy, the metrics each success criterion needs,
> and the wiring that turns SC-1..SC-6 from "not measurable" into numbers.
> This document is that design. It exists because three of the four phase
> exits in `ROADMAP.md §0` are gated on measurement that does not run yet:
> P3's exit is literally "SC-4 and SC-6 measurable", and SC-1/SC-2/SC-3 are
> all marked `—` (not falsifiable from code alone).

> **COST-HISTORY BREAK MARKER — 2026-10-02 (005 native zai provider).** The
> 11 glm proposer roles changed route and served model:
> `anthropic:glm-5.2` over the Anthropic-compatible endpoint →
> `zai:glm-5.3` on z.ai's native **coding** endpoint; the served model went
> glm-5.2 → glm-5.3. Per-1M rates (USD, genai-prices): old row (zhipuai
> fallback) 1.103 input / 3.862 output; new row (native zai) 1.400 input /
> 4.400 output. **Every record before this marker was priced on the old row
> and answered by the old model** — do not compare token-USD or quality
> across the marker without re-basing. Research-stage dollar budgets are
> reached 14–27% sooner on the same tokens (same rows, higher rates); they
> were **not retuned** — the tightening is accepted and recorded here. **No
> benchmark was re-run** for this change; the harness and case suites are
> untouched.

> **RESEARCH-SPEND BREAK MARKER — 2026-10-04 (008 research cap handling).** A
> research sub-question that hits a bound — its request limit or a tool
> budget cap — now reports and prices the model spend it incurred before
> stopping, instead of recording zero. Research rows for capped runs
> therefore show more `calls`, more tokens and more `cost_usd` than
> before, and the run budget gate reads the higher total — a run that
> used to pass that gate can now stop there. **Every record before this
> marker under-reports research spend for capped runs and is not
> rewritten**; runs that hit no cap are unchanged. **No benchmark was
> re-run** for this change.

---

## 0. Why a benchmark is the load-bearing artifact here

Three independent sources converge on the same claim, and the factory's own
roadmap is the fourth.

The **quality-is-a-trajectory** view (Abdullin): you start a project from the
feedback loop, not the architecture, because the eval environment is the
instrument that lets you compare *any* architecture on *your* task in minutes.
Half the work is building that environment and labelling the hard cases; the
clean harness that results is a by-product of the eval, not the goal.

The **harness-is-the-variable** view (Cursor's SQLite swarm): they held the
task, the models, and the time budget fixed and varied only the harness, then
graded against a held-out suite the swarm was never told existed. The
behavioural differences (thrash, contention, duplicated work) were far larger
than the score differences — so a single pass/fail number hides the thing you
actually want to improve.

The **model-economics** view (also Cursor): every model mix reached similar
quality at wildly different cost ($1,339 → $10,565 on the same task), because
few moments in a task need frontier intelligence. Cost per role, not per token,
is the number that moves.

And the **factory's own state**: `ROADMAP.md` marks SC-1 through SC-6 as
either not-measurable or mechanism-exists-no-metric. The pipeline can ship a
feature end-to-end (P1 done), but it cannot yet tell you *how well* or *how
cheaply* it does so across a fleet. The benchmark is the missing instrument,
and it is the precondition for P3's exit and everything in P4. Since round
013 the SC figures `sdlc benchmark score` prints are computed from the
scored runs' own summaries — the rollup opens with `N of M runs left a run
summary` and takes only those — never from every summary on disk.

**Design stance carried from the architecture.** ADR-11 already commits the
factory to a deterministic DAG *contra* the Bitter Lesson. The benchmark
inherits that stance: it is a fixed, versioned instrument, not a self-modifying
one. The two feedback loops below improve the *system under test*; the
instrument itself changes only through reviewed diffs, exactly as ADR-11 treats
the DAG.

---

## 1. What already exists (the honest baseline)

Measurement pieces already in the tree, per `ROADMAP.md` and `SDLC-spec-v2.md`:

- **Benchmark harness** — `benchmarks/workflow.py` (E-27). Runs golden cases
  through the real `FeatureWorkflow`, judges per-stage artifacts against
  rubrics via the cross-family `judge_artifact`. Two cases today
  (cat-café monitoring + one more), both *"sized for a single short factory
  run"*.
- **Cross-family judge** — `judge_artifact` with the ADR-6 family-inequality
  invariant, so the judge never shares an authoring model family with the
  producer. This is the "decorrelated review lens" idea, already load-bearing.
- **Prompt eval loop** — `sdlc eval <role>` (E-4): A/B-scores a working-tree
  `instructions.md` against a committed one on a captured fixture, using the
  same judge + case rubric. `sdlc eval capture` harvests fixtures from a run's
  history. On-demand, stage-isolated.
- **Cost attribution** — exists *in benchmarks only* today (ROADMAP §9.5,
  E-19). `HarnessRunResult` carries `input_tokens, output_tokens,
  context_window, compacted`; TemporalDurability usage records carry the proposer
  side. The numbers are collected; they are not yet aggregated into run-level
  counters.
- **CLI surface** — `sdlc ... benchmark` verb already exists (FR-603).
- **The record (round 012).** Every record a benchmark run writes carries
  its provenance and cell identity: `kroker_commit` (a commit id or the
  literal `unknown` — resolved once per run, never empty), `tree_dirty`,
  `arm` (the cell label; a cell is a case under an arm), `cell_id`, and a
  real `prompt_sha` (sha256 of the role's `instructions.md`, or an explicit
  `none:<reason>` — never empty). One **cell record** (scope `cell`,
  stage/role `cell`) is written per cell after it ends and after any
  grading: whether the pipeline completed, the last stage reached, and the
  grading state — `graded`, `not_graded` (code stage did not finish; the
  oracle never runs for it), `grading_failed` (the oracle could not run),
  `no_oracle`. A 012 run writes **one record file per cell**
  (`<run>/<cell_id>.jsonl`); pre-012 records (no `kroker_commit`) load
  unchanged but are marked **pre-012 (untrusted)** by every report and are
  never averaged together with 012 rows.
- **Record extensions (round 017).** Stage records and cell outputs carry
  extended observability fields:
  - `trace` (`TraceBag` on analyze records): captures evidence counts
    (`traced_by_test`, `traced_by_file`, `traced_by_command`, `untraced`),
    `criteria_trace` (`list[CriterionAudit]` entries with criteria keys, buckets,
    and evidence), and `truncated` (if trace exceeded the size cap). Note: criteria
    that no available evidence form can express remain untraced by contract; this
    reflects a plan-authoring outcome, not an analyze execution defect.
  - `tasks_total` (`int` on plan records): total tasks planned. `StageReach`
    carries `tasks_not_finished = tasks_total - finished`.
  - `blocking_checks` (`list[str]` on merge records): names of gating checks
    that failed and blocked merge completion.
  - `stage_reach` (`StageReach` on cell and oracle records): deterministic record
    of pipeline progression: `last_stage`, `last_stage_outcome`, `final_stage`,
    `tasks_total`, `tasks_qa_passed`, `tasks_not_finished`, `merge_outcome`, and
    `merge_blocking_checks`.
  - Oracle collection/import error signals: oracle records capture `exit_code`
    and `errors` (JUnit error count) in `quality.components`. When pytest exits
    with code 2 or 4, or JUnit errors constitute at least half the total tests
    (2E >= N > 0), `quality.detail` records `"collection/import errors: E of N"`,
    distinguishing environment/collection failure from test assertions without
    altering partial credit.
- **Memoization that is eval-aware** — `content_key` keys on
  `prompt_sha + model_id + recall_snapshot` (FR-103, NFR-6), so a benchmark
  cell that changes a prompt or a role's model invalidates exactly the affected
  stages and nothing else. This is what makes A/B cells cheap.
- **Golden-artifact regression suite** — named as the prompt-lifecycle
  mechanism in ARCHITECTURE §10 (edit → offline eval → deploy), with an
  external platform (e.g. Braintrust) as an optional later owner. The seam is
  the prompt loader.

**Three limits the roadmap already admits, which this design must fix:**

1. **No held-out grade wired end-to-end.** The coverage seam
   (`measure_coverage`) reads `coverage.xml` from the *integration* worktree,
   but `run_test_suite` runs per-task in *task* worktrees, so the artifact
   never lands where the gate looks (ROADMAP §1 stage 12, FR-106). Until this
   is closed there is no objective, test-based grade — only rubric judgments.
2. **Decomposition is unexercised.** Both benchmark cases are single-run-sized,
   so *"planner decomposition — the load-bearing variable in real work — is
   unexercised"* (E-27). Cursor's whole result is about decomposition quality;
   the factory cannot see it yet.
3. **The learning loop is open.** `reflect()` is registered but the retro
   *stage* (14) never runs (`RunSummary` unbuilt); nothing writes to `org_bank`
   (E-25). So SC-4/SC-6 have no signal to measure, and Abdullin's second loop
   (distil production into eval cases) has no intake.

---

## 2. Ground truth without a project history

The factory builds greenfield features, so there is no back-catalogue of
closed tickets to mine. Ground truth has to be authored, and it comes in three
tiers, ordered cheapest-to-most-objective. Every benchmark case declares which
tier(s) grade it.

### Tier A — Held-out acceptance tests (objective, ungameable)

The Cursor pattern: a test suite the factory is **never told exists**, run
against the produced code, graded as fraction passing. For greenfield this is
authored *with* the case (Abdullin's "label the hard cases up front"), which is
natural under the factory's own criterion→test discipline (FR-106): the case
author writes acceptance criteria and a hidden oracle suite; the factory's
Analyst proposes its own criterion→test mapping; the gate enforces traceability
against the *plan's* criteria, and the benchmark grades against the *hidden*
oracle. The gap between the two is itself a signal (did the factory test what
mattered, or only what it chose to?).

- **Ground-truth artifact:** `benchmarks/cases/<case>/oracle/` — a test suite
  + fixtures, held out of the workflow's context, run in a clean checkout of
  the produced code **through the case's `ToolchainAdapter`** (ADR-15).
  Generated projects can be Python / TS / Go / Rust, so the oracle is run by
  a language-resolved adapter, not a hardcoded `pytest`. The case manifest
  declares `language:`; the adapter is picked by **marker file in the
  produced repo** (`pyproject.toml`/`package.json`/`go.mod`/`Cargo.toml`),
  and manifest-vs-detected mismatch is itself a signal. Coverage normalises
  to Cobertura XML and the absolute security floor to semgrep/SARIF so the
  deterministic gate stays language-agnostic and unchanged (ADR-15, E-30).
- **Anti-cheat (Cursor's manual review, made routine):** two layers. (i) The
  oracle must be *held out* — never in the worktree, never in a prompt,
  never recalled; the case runner asserts this, and a post-run diff-coverage
  check confirms the code was built out evenly, not just where the oracle
  looks. (ii) **Session inspection** (the `HarnessSession`, E-38) automates
  the *"read the run, not just the code"* half of Cursor's manual review —
  did the agent peek at a hidden test, hardcode expected answers, or fit to a
  discovered oracle? The `deep_review` lens (E-39) and the offline benchmark
  both read the scrubbed session for exactly this. **(new scope relative to
  E-27, which judges rubrics only.)**
- **Unblocks on:** the coverage/test-execution seam (§1 limit 1). This is the
  single highest-leverage fix in the whole document — see §6.

**Tier A grading, per round 012.** A cell is graded only when its code
stage finished (a post-code stage record exists — never the mere
existence of an integration branch); a cell that stopped early is
`not_graded`, excluded from every quality mean and counted separately.
Each grade runs in its **own clean environment**: a venv created inside
that grade's temporary worktree (the produced project's declared
dependencies, then the case's `oracle/requirements.txt` if it ships one,
else pytest) and an allowlisted test environment with no `PYTHONPATH`/
`PYTHONHOME` — nothing from one grade can influence another, and the
worker's own site-packages are never the test environment (the round's
F3 finding; measured cost ≈25 s per provision). An integration result
with **no change against the base scores zero without running a test**
(the empty-diff rule). A grade that could not run is `grading_failed`
with the reason, distinct from both `not_graded` and a graded zero. For
all of these reasons, **oracle scores from round 012 on are not
comparable with pre-012 scores** (isolated environments; aborted cells
no longer count as zero).

### Tier B — Rubric judging (subjective, already built)

The E-27 mechanism: a rubric per stage, scored by the cross-family judge. This
is the *only* way to grade non-code stages (clarify quality, architecture
soundness, research grounding) where no oracle suite can exist. It is already
wired for `clarifier/architect/planner` and, since E-27, `qa/research`.

- **A registered rubric or veto file must exist (round 012).** A case
  manifest that names a rubric or veto file it does not ship is a broken
  manifest: `sdlc benchmark run` stops before contacting Temporal, and
  the loader activity raises non-retryably — at zero model spend. Every
  reader of case files (judge, report, calibration, task loader, oracle,
  DevEval import, verify) resolves the cases location through one
  function honouring `SDLC_CASES_ROOT`, so an override moves everything
  together — including the judge, which before 012 ignored it and could
  not find the rubrics the worker image had.

- **Calibration requirement (non-negotiable, from the eval literature and
  Cursor's "decorrelated lenses"):** a rubric judge measures the judge unless
  it is calibrated. Before a rubric's score is trusted in a phase-exit
  decision, hand-score 20–30 fixtures and confirm judge agreement (report the
  agreement rate; treat low agreement as a rubric defect, not a model defect).
  Track this per rubric. **(new scope.)**
- **Known open defect:** research grounding is unreachable for a mid-tier
  author model — `verify_brief` fails closed on byte-exact quote matching and
  glm-5.2 plateaus at 3 violations (E-29). Until E-29 lands, research rubric
  scores are unit-tested but unproven end-to-end (E-27 note). A benchmark that
  reports a research score today is reporting a number the pipeline can't yet
  earn live.

### Tier C — Golden-artifact regression (differential, partially specified)

ARCHITECTURE §10's named mechanism: a committed baseline artifact per stage;
a new run diffs against it; drift is a reviewed event, not a silent change.
This does not say "how good" — it says "changed vs the known-good baseline",
which is exactly what you want for regression protection during prompt/model
iteration. `sdlc eval` (E-4) is the on-demand half; the *committed baseline + CI
check* half is explicitly a named future increment (OQ-E2 in E-4's note).

- **Use for:** every prompt edit and model swap, as the fast inner loop.
- **Relationship to Tier A/B:** C catches "you made it *different*"; A/B catch
  "you made it *worse*". C is cheap and runs on every change; A is expensive and
  runs on the matrix.

---

## 3. The four axes of the benchmark matrix

The factory's registry (`agents.yaml`, FR-201) already makes three of these
axes *configuration*, not code changes. That is the single biggest reason the
benchmark is tractable: an axis is a config sweep, not a fork.

| Axis | What varies | Where it lives today | Roadmap dependency |
|---|---|---|---|
| **Harness** | `claude -p` vs `opencode run` vs **cursor (to add)** | `harness/adapters.py`, `HARNESSES` (FR-203) | new adapter must normalise into `HarnessRunResult` (§4) |
| **Model × role** | which model drives each of 11 roles | `STAGE_MODELS` + `agents.yaml` per-role `model` | landed (E-37): per-cell arms + `--role-model`, ADR-6 per run; **proposer arms real since 004** (override is forwarded and validated; pre-004 caveat in §3.2) |
| **Memory** | Hindsight on/off/watermark, `project` vs `+org` banks | `MemoryConfig` (`memory.enabled` default `False`) | org bank has no writers — **E-25**; retro closes the loop — stage 14 |
| **Case** | greenfield feature specs of graded complexity | `benchmarks/cases/` | only single-run-sized cases exist — need a decomposition-forcing case (§5) |

### 3.0 Language is a case property, not a fifth axis

Generated projects can be any language, but language should **not** be a
sweep dimension crossed with the others (that multiplies the matrix for
little insight). Instead each case *declares* its language and carries an
oracle in it (§2 Tier A, E-31); the corpus spans several languages; and the
**error heatmap is sliceable by language** (§4.4). This catches the real
risk cheaply: if every prompt and rubric was tuned on Python cases, the
factory may quietly do worse on Go, and a Python-only benchmark never sees
it. Running *the same spec* in Python vs Go as a deliberate probe is
possible but expensive — hold it as an optional later experiment, not the
default. The machinery that makes any of this work is the `ToolchainAdapter`
(ADR-15) under E-30.

### 3.1 Harness axis — and where `cursor` fits

Adding cursor is worthwhile, but **as a third point on this axis, not as a
replacement.** The value is not "cursor vs claude in the abstract" — that's a
blog post about someone else's task. The value is measuring
`claude -p` vs `opencode` vs `cursor` **on your SDLC, through your
DeterministicQualityGate, on your held-out oracles.** That comparison cannot be
bought or borrowed.

The one hard requirement (from FR-203 + the `HarnessRunResult` contract): a new
harness adapter must normalise its output — tokens, cost, `context_window`,
`compacted`, session-resume handle — into `HarnessRunResult`. If cursor reports
cost/usage in a different shape, that translation is the adapter's job (E-24
also wants its version pinned and asserted at boot, exactly as eve's
dependency-drift failure mode warns). Until the adapter fills those fields, the
**economics axis is blind for that harness** — you'll have quality without cost,
which defeats half the point.

### 3.2 Model × role axis — the economics result to reproduce

Cursor's finding, restated for this factory: the expensive roles are the
*proposers that decide* (architect on `opus-4-8` per `agents.yaml`), and the
volume is in the *harness roles that execute*. The benchmark should attribute
**dollars per role**, not tokens, because planner-family tokens cost multiples
of worker-family tokens. The registry already lets you pair a frontier architect
with a cheaper developer harness and measure whether quality holds — which is
precisely Cursor's $1,339-vs-$10,565 experiment, expressed in your config.

*E-33 landed this: `RunSummary.roles` carries per-role dollars on every run; proposer `BenchmarkRecord.cost` is now populated, so `mean_cost_usd` is real for proposer cells.*

Blocker to be honest about: `cfg.roles` was a hardcoded mirror of `agents.yaml`
because `PipelineConfig()` is constructed *inside the workflow* (E-26). A
per-cell model sweep needs the override to resolve at the boundary
(`benchmarks/workflow.py`) and satisfy ADR-6 *per run*. **E-37 landed this:**
each cell now carries a named `Arm` (role→model mix); `_cell_config` builds
`cfg.roles` from the arm and enforces ADR-6 per run via `validate_run_roles`,
and the CLI exposes the same override via `--role-model`. The full model×role
sweep is now expressible; the pre-E-37 harness-only `models=[...]` form still
works (desugared to one arm per model).

**004 closes the loop on proposer arms:** until 004, a proposer override was
resolved, priced and keyed but never *forwarded* — the registry model answered
while the record named the override. From 004, proposer arms and `--role-model`
overrides are real: the override reaches the call, and the label, the priced
model, the usage record and the memo key all describe the model that actually
answered; invalid arm strings (`default` or proposer `role_models` entries that
are not `provider:model` ids of an installed provider) are refused at matrix
expansion before any cell runs. Records made before 004: the inventory in
`.specify/specs/004-model-forwarding-single-retry/inventory.md` establishes
that **no benchmark record predating the fix carries a mislabelled proposer
model** — no proposer override was ever used in a committed arm on this
machine, so nothing needs re-running or re-labelling.

### 3.3 Memory axis — the measurement the whole stack was built for

This is the axis that justifies Hindsight's presence, and it is the one the
roadmap is furthest from being able to run. The experiment is simple: the same
case, same models, same harness, run with `memory.enabled=false` and
`memory.enabled=true`. The delta in quality (and in fix-loop cost — recalled
gotchas should make attempt N+1 cheaper, SDLC-spec §6) is the value of memory.

Why it can't run yet, precisely: SC-4 ("repeat-clarification <10% by run 10")
and SC-6 ("soft-gate override <5%") both need *reflect wiring + real runs*
(ROADMAP SC-4/SC-6). The nightly project reflect ships (E-12/E-13) but only
accrues signal on runs with `memory.enabled=true` (default false), the retro
stage that writes `RunSummary` is unbuilt (stage 14), and nothing writes to
`org_bank` (E-25). So the memory axis is gated on closing the learning loop —
which is §6's second priority.

---

## 4. Metrics — beyond a single pass rate

Cursor's central lesson: the behavioural differences dwarfed the score
differences. A benchmark that emits one number per run cannot see thrash,
duplicated work, or a harness that silently compacted mid-task. The factory
should emit a **row per run** with these fields, aggregated across the matrix.

### 4.1 Quality (the grade)

- **Oracle pass rate** — fraction of the held-out Tier-A suite passing. The
  primary number. Requires §6 priority 1. **Round 013:** the code stage
  carries two task scores — *first attempt* and *after repair*, each `k/n`
  over the tasks with a record at the stage — and no quality mean. The
  oracle row shows the mean partial credit of graded runs beside the
  all-pass rate `k/n`. A verdict stage prints a pass rate over its own
  gate decisions, never a quality score. The composite is shown only when
  the case has two arms with a graded run each.
- **Grade-over-time** — Cursor grade the suite as a *rising curve*, because
  agents choose their own strategy (broad-foundation-then-spike vs
  deep-then-plateau) and *"trends matter more than exact scores at exact
  moments"*. The factory's stages are discrete, so the natural analogue is
  **grade at each gate** (post-clarify, post-architecture, post-plan, post-QA,
  post-merge) — a step curve, not a smooth one, but it shows *where* quality is
  won or lost.
- **Rubric scores per stage** (Tier B) — for the non-code stages, with the
  calibration agreement rate attached so a score is never read without its
  trust level.
- **Traceability gap** — criteria the factory tested (its own mapping) vs
  criteria the oracle covers. A proxy for "did it build evenly or to the test"
  (the Cursor anti-cheat, quantified).

### 4.2 Economics (the cost)

- **$ per run**, decomposed **per role** (not per token — §3.2).
  **Round 012 limit:** dollars on harness records are not measured — a
  subscription-billed harness run reports $0.00 by construction; tokens
  are the usable volume figure on those records.
- **Tokens per role**, with the planner/worker split Cursor highlight (workers
  carried ≥69%, often >90%, of tokens but a minority of cost).
- **Context-ceiling events** — `input_tokens > fraction × context_window` and
  `compacted=true` counts, from `HarnessRunResult` (SDLC-spec §4, ADR-13). A
  harness that keeps hitting its ceiling is a signal to decompose smaller.
- **Research spend split (round 017, FR-034 / A-1).** Trace-derived surfaces
  include all research spend (planner, sub-question execution, synthesis, and
  dead-attempt ledger folds): the run summary (`RunSummary.roles`), the live
  `run_state` role view and total (`cost_usd_total`), the Cost tab, and
  benchmark records (`BenchmarkRecord.cost`). In contrast, `_role_usage`-derived
  surfaces exclude research spend: `_check_budget` (the pipeline budget gate),
  `budget_counted_usd`, and per-activation `graph_view` spend. The E-75 §4.3
  invariant `attributed + unattributed == sum(_role_usage)` continues to hold.

### 4.3 Coordination & waste (the factory's analogue of swarm thrash)

The factory runs a serial DAG, not a 1,000-commit/sec swarm, so Cursor's
merge-conflict and megafile metrics don't port directly. The *principle* does:
measure work that didn't advance the goal.

- **Fix-loop attempts** per run — QA loop (`MAX_REPAIR_ATTEMPTS`, spec says 3)
  and review-fix loop (`MAX_REVIEW_FIX_ATTEMPTS = 2`). Note the numeric drift
  the roadmap flags (FR-105: default 2 vs spec 3) — the benchmark should record
  the *actual* cap in force, not assume.
- **Gate rounds** per gate — REVISE re-entries (`MAX_GATE_ROUNDS`, default 2,
  FR-301). Repeated revisions at one stage localise where the pipeline
  struggles.
- **Escalations** — how often fix loops exhausted into a hard human gate.
- **Wall-clock per stage** — from Temporal history, free.
- **Session-derived waste** (from the `HarnessSession`, E-38) — the richest
  signal the diff hides: tool-call count, file re-reads, failed commands
  (non-zero exits), and rewrite/backtrack churn *within* a run. The diff
  never shows "rewrote the auth module three times before settling"; the
  transcript does. This is the factory's analogue of Cursor's commit-churn
  metric — activity that did not advance the goal — read from the session
  rather than VCS. Also surfaces `compacted` mid-run context loss (ADR-13)
  as *what* was dropped, not just that it happened. These aggregates are
  computed **pre-truncation** (E-38 retention policy), so they are kept on
  clean-green runs too — where only a `SessionDigest`, not the full
  transcript, is retained — and the heatmap never goes blind on green.
- *Landed 2026-08-03:* `WasteBag` on `BenchmarkRecord` +
  `benchmarks/waste_matrix.py`. Six gridded metrics; volume metrics and
  `compacted` ride on the record without a grid. Coding tasks only --
  proposer stages have no transcript by construction.
- *Round 013:* the stored opencode counters are **not measured** — their
  streams were captured before tool events were parsed, so a bag with no
  capture mark and zero tool calls cannot be told apart from an unparsed
  stream and reads as not measured (counted as such, never scored as a
  zero); claude and cursor counts were always measured. New digests carry
  the capture mark (`capture_rev`), so a marked bag's zero is a measured
  zero. Tool events are parsed from opencode streams pending a captured
  stream — round 013's parser task waits on one.
- *Round 016 / FR-041:* the round-013 residual is closed. Opencode waste
  counters have filled end to end since rounds 013/014: the capture feeds the
  digest, and the digest feeds the `WasteBag`. A real stream now pins this:
  `tests/fixtures/opencode/bench-todo-api-greenfield-1792335476-T-001-a1.jsonl`
  is the scrubbed round-016 R0 capture of todo-api T-001 attempt 1 (opencode
  1.18.35, `--format json`). Unit tests in `tests/test_opencode_normalise.py`
  and `tests/test_opencode_captured_stream.py` run it through
  `normalise_session`, `digest_of`, `WasteBag.from_digest` and
  `waste_measured`.

### 4.4 The error heatmap (Abdullin's prioritisation instrument)

Aggregate the above — including the session-derived waste (§4.3) and the
anti-cheat findings (below) — into a **case × stage** grid. This is
Abdullin's `error heatmap` and it answers the only question that matters
between iterations: *which stage, on which class of case, is costing the most —
and therefore what do I fix next.* It is strictly more useful than a scalar and
it is the natural home for every §4.1–4.3 metric.

*Status (2026-10-10, round 013):* the heatmap is **four layers on identical
stage columns** — rows are `(case, harness, arm, generation)` groups, columns
the pipeline stages in order plus `oracle`:

| Layer | Unit / denominator | Colour steps (0→4) |
|---|---|---|
| attrition | lost runs positioned at a stage / runs that reached it | 0, ≤.05, ≤.10, ≤.25, above |
| first attempt | units whose first verdict failed / units with a verdict | 0, ≤.10, ≤.25, ≤.50, above |
| wasted tokens | tokens on superseded or lost work / all tokens at the stage | 0, ≤.10, ≤.25, ≤.50, above |
| oracle | one `passed/total` mark per graded run | 1, ≥.90, ≥.75, ≥.50, below |

Colour steps are fixed per layer, one hue at five lightness levels, so the
same value always gets the same class in any report; a cell under five
observations is grey, and every cell prints its own `num/den`. Known limit:
a stage record is written when the stage ends, so a run that stopped inside
a stage shows the stage before it as its last. The **run grid** — one row
per run, grouped by arm and commit, with mean and spread per group — is the
main view and opens `report.md`; `gate-oracle` puts each gate against the
oracle (agreement, escape rate, false-reject rate, mean partial credit per
side). A score writes `report.md`, `grid.*`, `heatmap.*`, `gate-oracle.*`,
`sc-rollup.*` and, per case, the waste, reviewer-versus-adversary, task,
root-cause (`root-cause.html`, `root-cause.json`), and error matrix files.
The E-77 `fail_reentry` axis and the per-task maximum of `fix_attempts` are
superseded by the first-attempt layer's per-`(run, task)` units. The run
grid's rows carry two quality-axis columns (§4.5) after the code-score
columns, and the `## Runs` totals line ends with one axis clause
(`axis: N measured, M not measured`).

**Root cause (round 015, report 3.5).** Aggregates failure modes into four
standard buckets: `planning`, `execution`, `verification`, and `unattributed`.
Lost runs are classified deterministically by their last recorded stage:
before `code` counts under `planning`; `code` or any task-loop stage (including
analyze, merge, deploy) counts under `execution`. Graded runs count failed
requirements (score below 1.0) under `unattributed` unless a person applies a
label file under `benchmarks/labels/<case>/<bench_run_id>.yaml` attributing it.
No cause is assigned automatically to a graded run. Graded runs without
requirement results (no requirement mapping) are tracked separately under
`no_requirement_results` and never falsely attributed.

### 4.5 Erosion and verbosity (the second, objective quality axis)

*Status (2026-10-11, round 015):* the oracle says whether the produced code
works; nothing else said what the run **did to the code**. At the end of
every run the worker measures two deterministic properties of the produced
diff at the integration branch head and stores them as one record beside
the run's others — no judge, no network.

- **Erosion** — the share of complexity mass in functions whose cyclomatic
  complexity is above 10, where a function's mass is its complexity times
  the square root of its lines (`mass = CC × sqrt(SLOC)`, radon's CC and
  line spans). A run can pass every held-out test and still double the
  complexity mass of what it touched; this is the figure that shows it.
  The record carries the mass split, so the share is auditable.
- **Verbosity** — the lines the project's own pinned rule set flags, over
  the non-blank lines of the measured files. The rule set lives in this
  repository (`src/sdlc/benchmarks/rules/verbosity/`, versioned; v1:
  `except-pass`, `bare-except`, `print-call`, `debugger-call`,
  `nested-ternary`, `if-deep-4`), applied by ast-grep; a match flags its
  whole node span and the flagged lines are the union. Cloned lines are
  NOT united in v1 — the source benchmark's definition unites them, but
  no licence-checked clone detector is a dependency yet; a later rule-set
  version adds them without lying about the old figures.

**Measured = the produced diff.** The measured files are the `*.py` paths
of `git diff --name-only <base>...HEAD` at the integration head, final
state — a run owns its diff, never the whole base repository. The record
carries the branch head, the rule-set version and the tool versions, so a
figure stays interpretable months later; measuring the same tree twice
gives the same figures.

**Absence is a state, never a zero.** A run that cannot be measured reads
`n/m(<reason>)`: `code stage did not finish`, `integration branch absent`,
`language not python` (v1 measures Python only), `no python files in diff`,
`no functions`, `measurement failed: <detail>` — and for every run recorded
before round 015, `no axis record` forever (no integration branch
survives). The totals line counts both sides; a group mean never crosses a
rule-set version and is grey under five measured runs.

**The axis never blends with the oracle.** The figures appear in the run
grid's two columns and in the group header, and nowhere else — never in a
quality column, a partial-credit or all-pass figure, a composite weight,
or a gate-versus-oracle count, in text, HTML or JSON. They ride their own
record payload, never `QualityScore`.

---

## 5. Cases — authoring the corpus

Cases are the dataset. Three sources, matching the greenfield reality (there is
no history to mine):

- **Spec-authored katas (primary).** A case is a feature spec + a held-out
  oracle suite, authored together. The bar E-27 set is the right one: *"large
  enough to require decomposition and small enough to specify completely."* The
  cat-café case meets the "specifiable" half and now features a grown 36-test
  oracle across 15 requirements, plus a verified reference solution.
- **Public anchors (external validity).** A handful of SWE-bench-Verified-style
  tasks (issue → PR with hidden tests) give an external, task-independent
  reference point that doesn't move when you change your own prompts. Use them
  to tell "my change regressed *my* cases" from "my change regressed
  *everything*". These grade purely on Tier A. Six DevEval cases (`deveval-*`)
  anchor Python kata validity.
- **Distilled production incidents (the second loop).** Abdullin's loop B and
  Cursor's Field Guide are the same idea: every time the factory fails in real
  use, that failure becomes a case. This is *the* mechanism that grows the
  corpus past the cold start — and it is exactly what the retro stage (14) +
  `RunSummary` are for. Closing that stage (§6 priority 2) turns production runs
  into eval intake automatically. Until then, cases are hand-authored only.

### 5.1 Acceptance rule and corpus status (round 015)

Every case on disk declares `role` (`corpus`, `smoke`, `probe`, `parked`),
`visibility` (`private`, `public`), and held-out `exposure` (`repo_public`, `isolated`).
Corpus cases specify a `strong_arm` and `weak_arm`.

Acceptance into the corpus is determined by `sdlc benchmark accept --case <id>`:
1. **Reference check**: the reference solution in `reference/` must pass 100% of oracle tests.
2. **Floor check**: an empty tree must pass strictly fewer tests than the reference.
3. **Separation check**: on graded runs sharing the current oracle identity, the strong
   arm must beat the weak arm by at least `SEPARATION_MARGIN = 0.15` (with 1e-9 tolerance).
   Verdicts:
   - `accepted`: all checks pass with ≥3 graded runs per arm.
   - `provisional`: all checks pass with <3 runs per arm.
   - `rejected`: with reason `reference`, `floor`, `saturated` (strong arm 1.0 on all runs),
     `degenerate` (strong arm 0.0 on all runs), or `no_separation`.
   - `not_assessed`: separation has no runs yet, case has no oracle, or `stalled`
     (both arms stalled at the same unfinished stage with partial credit <= 0.05;
     note: `"not separable: stalled at <stage>"`). The stalled rule fires only when
     every run has `stage_reach`, credit <= 0.05, all share one `last_stage`, and
     that stage was completed by no run in either arm. `ArmEvidence.stall_points`
     records each run's `last_stage` (empty for pre-017 runs).

**Corpus table:**
Run `sdlc benchmark corpus` to display status across all cases (state after the
round 016 run batch closed, 2026-10-18 — tally: **1 of 8 accepted or
provisional, 1 of 2 private**). A row prints `Stale: yes` for either of two
causes: **oracle drift** (the record's `oracle_id` no longer matches the
current hash of `oracle/`) and, since R019 (FR-009), **arm drift** (the
record's separation arms differ from the case's `strong_arm`/`weak_arm`);
stale rows stay out of the tally. Known limits of the arm rule: it compares
arm **names** only (a renamed `role_models` payload under the same name does
not trip it), and records with `separation: null` are exempt.
- `cat-cafe-monitoring`: `corpus`, `private`, **`provisional`** (strong
  `glm-5.3-flash` 0.833 vs weak `glm-5.2` 0.472, margin +0.361, n=1 per arm —
  the only case where the harness agrees with the public model ordering)
- `deveval-geotext`: `corpus`, `public`, **`rejected` (`no_separation`)** (flash
  0.222 vs glm-5.2 0.778, margin −0.556 — the harness inverts the public
  ordering here; its R2-era `provisional` was an artifact of the inverted arm
  labels, see R4-r2)
- `deveval-hone`: `parked`, `public` — saturated at screening (oracle 1.000 =
  strong arm 1.0 on all runs; nothing left to separate)
- `deveval-lice`: `corpus`, `public`, `rejected` (`reference`, 30/31 passed, failed `test_package_template` due to upstream template mismatch; excluded from R1 screen)
- `deveval-particle-swarm-optimization`: `parked`, `public` — unassessed (lost
  twice at plan-validation: glm-5.3 emits dangling task deps, `T7→T6`; the
  single repeat was spent)
- `deveval-readtime`: `corpus`, `public`, **`rejected` (`no_separation`)** (flash
  0.250 vs glm-5.2 0.167, margin +0.083 < 0.15 — a near-tie under either
  labeling)
- `deveval-stocktrends`: `parked`, `public` — degenerate at screening (oracle
  0.000 on all runs)
- `theatre-box-office`: `corpus`, `private`, `isolated`, **`rejected`
  (`no_separation`)** on round 016 pre-017 records (pin `1e697522`, oracle `a66c0c4e`: strong
  flash 0.0179 vs weak glm-5.2 0.0179, margin 0, n=1 per arm — both arms
  graded but failed at `merge`, so the oracle scored broken integration trees;
  plan shapes differed — flash 9 tasks/chain 7, glm-5.2 12 tasks/chain 10, no
  dangling deps — while per-tier credit was ~0 everywhere; under round 017's
  stalled verdict rule, runs carrying `stage_reach` that stall together at merge
  evaluate to `not_assessed` (`stalled`) rather than `no_separation`)
- `todo-api-greenfield`: `smoke`, `private`
- `add-login-greenfield`: `probe`, `private`
- `crew-probe`: `probe`, `private`

Cases parked by screening runs keep role `parked` and their reason; they enter neither
the active corpus count nor the exit tally. Rounds 016 and 017 will expand the corpus
with private multi-step decomposition katas and brownfield anchors.

### 5.2 The private store (round 016)

Round 016 adds a second cases root read alongside the in-repo corpus: the
**private store**, a directory outside this repository (written `<store>` here;
its real path lives only in the git-ignored `docker-compose.override.yml` and
the host `.env`). What lives there: private cases in the same shape as in-repo
ones — `case.yaml`, `tasks.yaml`, `rubrics`, a held-out `oracle/`, a
`reference/`, plus authoring-time material the repo never carries
(`review/`, `verification/`). Nothing of a store case may reach this repo:
a pre-commit hook (`check-private-leak`, always on, skipping with a note when
no store is configured) scans every commit's added lines against the store's
tokens — oracle test names, requirement ids and features, reference symbols,
and 8-word runs of the case text and rubrics.

- **Resolution and exposure.** `SDLC_PRIVATE_CASES_ROOT` names the store's
  `cases/` root; every reader (oracle, task suite, judge assets, report,
  corpus, `accept`/`verify-case`/`corpus` at the CLI) resolves a case id in
  either root, refusing duplicates. A case found in the store reports exposure
  `isolated`; in-repo cases stay `repo_public`. The corpus tally still counts
  by `visibility`, so a private store case counts in both numbers exactly as
  an in-repo private case does. With no store configured, every behaviour is
  exactly as before.
- **Running a private case.** Mount the store (see
  `docker-compose.override.example.yml`: the worker read-only at
  `/srv/private-cases` plus `SDLC_PRIVATE_CASES_ROOT`, `kroker-dev`
  read-write because `sdlc benchmark accept --case <id>` writes
  `acceptance.yaml` into the case dir in the store) and put
  `SDLC_PRIVATE_CASES_ROOT=<store>\cases` in the host `.env`. A run takes the
  store case's `case.yaml` path directly (`--case /srv/private-cases/<id>/case.yaml`);
  the by-id CLI subcommands resolve across both roots. Labelling private cases
  is unsupported this round (labels stay on the primary root).
- **Research is off for private cases.** An invented kata has nothing public to
  research; the research stage would send the case text to external search
  providers (a publication path) and costs about a third of a run's stage
  dollars for nothing. Private corpus cases are authored with
  `research_enabled: false` and no research rubric.
- **New environment variables (round 016).** `SDLC_PRIVATE_CASES_ROOT` (the
  store, above; unset = no store), `SDLC_RAW_STREAM_DIR` (opt-in raw opencode
  stream capture to `<dir>/<safe run_id>/<task>-a<attempt>.jsonl`, default
  off, R0-only tooling), and `SDLC_JUDGE_MAX_TOKENS` (the rubric judge's
  output budget; default 16000, proven on the stored cat-cafe plans — without
  a budget the judge hits the provider default and records
  `judge=error` instead of a score).

- **Decomposition report.** `scripts/decomposition_report.py` reads the
  stored plan artifacts and per-requirement oracle grades of a case's runs
  and writes an aggregates-only report — plan shape (tasks, dependency
  edges, longest chain), optionally beside a baseline plan, and partial
  credit per requirement tier (`basic`/`rule`/`cross`) per arm, each with
  its denominator. It names no test and quotes no requirement text; its
  numbers are copied by hand into this document and the round's
  `verification.md`.

No corpus row or tally change yet: the round's own case lands in the closing
commit (T023) with its verdict, as the run batches (R0/R1) are cleared
separately and nothing has been run at document-writing time.

**Case layout note (round 012).** A case's `oracle/` directory may ship a
`requirements.txt` — the oracle's own test dependencies (e.g. `httpx`,
`pytest-asyncio`), installed into the per-grade environment after the
produced project's own. A file that the case does not need (oracle imports
only pytest and the produced project) should not be added; every oracle in
the corpus was audited and the two oracle cases ship one.

**Field Guide vs Hindsight — a note, not a task.** Cursor's Field Guide (a
line-budgeted, agent-curated `index.md` injected at every agent start) is a
lightweight, in-repo cousin of Hindsight's cross-run memory. It is worth
holding as a *fourth memory-axis condition* eventually (none / Field-Guide /
Hindsight-project / Hindsight+org), because it isolates "shared scratchpad
within a run" from "consolidated memory across runs" — but it is speculative and
should be filed, not scheduled, in the spirit of E-5.

---

## 6. Sequencing — ranked by what each unblocks (not by effort)

Following `ROADMAP.md §8`'s discipline: rank by which measurement invariant is
undercut, not by size.

1. **Wire the held-out grade (a pipeline capability, not a benchmark fix).**
   The stage-11/12 quality activities are *production* code the benchmark
   merely exercises, and generated projects are multi-language, so the grade
   cannot be language-agnostic unless those stages are. Deliver a
   `ToolchainAdapter` abstraction (ADR-15, E-30): a `TOOLCHAINS` registry
   resolving by repo marker file, normalising `build/test/lint/coverage` into
   `TestReport`, with canonical Cobertura coverage and a semgrep/SARIF
   security floor so the gate reader is untouched. Ship **one reference
   adapter (Python) end-to-end** — including the diff-scoped test artifact
   crossing the merge into the integration worktree where `measure_coverage`
   reads (the original FR-106 gap) — then add the Tier-A held-out oracle on
   that one language (E-31). *Without this there is no objective grade and
   every other metric sits on rubric-only judging.* This is the sqllogictest
   moment: `DeterministicQualityGate` is most of the way there — it already
   has `build_integration_green`, `lint_clean`, `security_no_critical`; the
   gaps are the artifact crossing the merge and the language abstraction
   under it. **Deliberately Python-first:** proving one language end-to-end
   unblocks the first SC signal without waiting on N adapters; further
   languages (E-30a/b/c) follow the corpus, ranked below.

2. **Close the learning loop** — build the retro stage (14): emit `RunSummary`,
   call the already-registered `reflect()`, and give `org_bank` a writer
   (**E-25**). *This unblocks SC-4 and SC-6 (P3's exit criterion), turns on the
   memory axis (§3.3), and opens Abdullin's loop-B case intake (§5).* Three
   payoffs from one stage.

3. **Full cost attribution + a decomposition case** — promote cost bookkeeping
   from benchmarks-only to run-level counters (**E-19**), attribute per role
   (§4.2), and author the decomposition-forcing kata (§5). *Now the
   economics graph in Cursor's style is reproducible on your data, and the
   axis that matters most (decomposition) is finally exercised.*

4. **Add the cursor adapter** — third point on the harness axis (§3.1),
   normalised into `HarnessRunResult`, version-pinned at boot (**E-24**). *Do
   this after §6.3 so the economics fields exist to receive it; otherwise
   cursor's cells are quality-only.*

5. **Error heatmap + calibration harness** — the `case × stage` aggregation
   (§4.4) and the rubric-calibration agreement tracking (§2 Tier B). *The
   prioritisation instrument and the trust layer under every rubric number.*
   **Landed 2026-08-03:** the heatmap is one of five grids written by
   `sdlc benchmark score`; calibration reports via `sdlc calibrate <rubric>`
   (E-36, landed earlier). The instrument now has three loops:

   | Loop | Command | Cost | Answers |
   |---|---|---|---|
   | Prompt A/B, one stage | `sdlc eval <role>` | seconds | did this prompt edit help on a captured fixture |
   | Re-score stored evidence | `sdlc benchmark score` | seconds | what do the runs I already have say, under these weights |
   | Smoke test | `sdlc benchmark smoke` | minutes | verify four smoke conditions and write commit stamp (`--gate-policy off` matches the 012/015 unattended-run precedent; the four conditions include the case-level oracle all-pass) |
   | Full matrix / arm run | `sdlc benchmark run --arm <arm>` | hours | what does this architecture change do end-to-end |

   **Run gate (round 015).** Starting a `corpus` case with `sdlc benchmark run`
   is gated on a passing smoke stamp (`<ops root>/smoke/<commit>.json`) for the
   current Kroker commit and a clean working tree. Running with `--skip-smoke`
   explicitly overrides the gate and is logged. `parked` cases refuse to run
   unless overridden with `--allow-parked`. For multi-cell cases, `--arm <name>`
   selects a specific named arm (e.g. `zai-coding-plan-glm-5.2` or
   `zai-coding-plan-glm-5.3-flash`), or `--all-arms` runs the entire matrix.

6. **Per-role model sweep** — resolve `cfg.roles` at the benchmark boundary
   (**E-37**, folds E-26) so each cell overrides role→model and satisfies
   ADR-6 per run. *The full model×role matrix. Landed: per-cell `Arm`s +
   `--role-model`, judge family validated at expansion (answers OQ-B2).*

Items already banked that this design builds on: E-4 (prompt eval loop),
E-12/E-13 (nightly project reflect), E-27 (benchmark harness + rubric judging),
FR-103/NFR-6 (eval-aware memoization), FR-201/FR-203 (registry + harness
adapters).

---

## 7. Open questions

- **OQ-B1 — Oracle authorship cost.** Tier-A oracles are hand-written per case.
  What's the minimum corpus (how many cases, what complexity spread) before the
  matrix produces a trustworthy signal rather than noise? Cursor ran one task
  across four mixes; Abdullin spent half a project on the environment. Likely
  10–30 cases, but this needs its own calibration.
- **OQ-B2 — Judge independence under model sweep. ANSWERED 2026-07-24 (E-37).**
  ADR-6 forbids the judge sharing a family with the *producer*. When the
  model×role axis sweeps producer families, the judge family must move to stay
  independent per cell. Resolution: the judge is **fixed per case** (one
  `judge_model` on `CaseSpec`), and `expand_matrix` validates at expansion that
  its family differs from **every producer model in every arm** of the matrix.
  It does not re-resolve per cell — the guard is up front, so a case whose
  judge collides with any arm's producer family is rejected before any cell
  runs. (Ties to OQ-E2.)
- **OQ-B3 — Research grounding gate for benchmark cells (E-29). ANSWERED
  2026-07-23.** Benchmark cells run with the hard grounding verifier
  unchanged; a violation is a recorded research-stage `FAIL` in the cell's
  record — retain and digest are skipped and the run continues on the idea
  alone (the 2026-07-20 fail-and-continue decision, `feature.py:987`).
  Research rubric judging happens only on grounded briefs, so a cell's
  research grade is earnable but not guaranteed — never an unearnable
  number silently reported. The demote-to-inferred + still-judge variant
  was considered and deliberately not built
  (`2026-07-23-cat-cafe-tier-a-oracle-design.md` §2).
- **OQ-B4 — Regression-gate half of E-4 (OQ-E2).** `sdlc eval` is on-demand;
  the committed-baseline-plus-CI-check half is unbuilt. Is the golden-artifact
  regression suite (Tier C) a CI gate on every prompt/model change, or an
  advisory report? ADR-11's stance (deterministic, reviewed change) argues for
  a gate.
- **OQ-B5 — External platform seam.** ARCHITECTURE §10 names Braintrust as an
  optional later owner of the eval loop, seam = prompt loader. At what corpus
  size does an external eval platform earn its keep over the in-repo harness?

- **OQ-B6 — Multi-language corpus balance (ADR-15).** With language a case
  property (§3.0), how is the corpus balanced across Python / TS / Go / Rust
  so per-language signal is trustworthy, and which languages get a
  `ToolchainAdapter` first (E-30a/b/c order) — driven by the cases that exist,
  or by the languages the factory is expected to target? Also: is a language
  with no adapter yet a hard case-skip or a rubric-only (Tier-B) grade?

- **OQ-B7 — Session retention under capture-always (ADR-16, E-38) — DECIDED,
  one sub-point open.** Policy: **full transcript** on fail / benchmark / any
  run with >0 fix-loop attempts (the diagnostic and measurement cases —
  "green after a retry" counts as full, since *how the agent recovered* is
  the point); a structured **`SessionDigest`** on clean-green (first-pass)
  runs. The digest is not a byte-truncation — it is the §4.3 waste aggregates
  + a decision-skeleton (tools/files/decisions, no full payloads), computed
  **pre-truncation** in the same scrub activity and always kept, so the
  heatmap sees waste on green runs and P5 harvesting keeps successful-
  trajectory shape. Ordering is strict: capture → scrub (fail-closed) → then
  branch full-vs-digest; a scrub failure stores nothing, either way. **Still
  open: the TTL on full transcripts** — keep failed/benchmark sessions
  indefinitely, or purge N days after the run is triaged? That is the only
  remaining sub-decision; the scrub is non-negotiable and fail-closed
  regardless. **Implemented (E-38):** capture → fail-closed scrub → full
  transcript (`harness_session`) + `SessionDigest` stored by
  `run_coding_task`; retro downgrades clean-green non-benchmark runs to
  digest-only (`keep_full_transcripts` / `apply_session_retention`). The
  §4.3 digest is always kept. **TTL on kept full transcripts is the one
  remaining open sub-point.**

- **OQ-B8 — Usable corpus size from DevEval. ANSWERED 2026-08-09 (E-79).**
  **Six of ten** Python repositories are committed. Two (`ArXiv_digest`,
  `chakin`) genuinely need live egress and are quarantined behind
  `network_required` until E-21; two (`Hybrid_Images`, `TextCNN`) need `cv2`
  and `torch` to reach a green verify and are re-importable on a machine that
  has them. The corpus is now 9 cases, which is the first real data point for
  OQ-B1's "10–30 cases" estimate.

- **OQ-B9 — Cost of confirming a generated `tasks.yaml`. ANSWERED 2026-08-09
  (E-79).** It is a **rewrite, not a light edit** — budget 15–30 minutes per
  case. Test-file granularity is too coarse to be requirement-weighted
  (`lice` arrived as one task holding 31 tests), so all six suites were
  regrouped into 31 PRD-level requirements over 79 tests. The draft still
  earns its keep by supplying exact node-id strings, but its grouping is a
  starting point only.

- **OQ-B10 — Contract-frozen vs pinned as the default for imported cases.**
  Imported cases ship contract-frozen (reference architecture inlined in the
  description). Once E-80 lands, should they keep that, run pinned, or run
  both as separate arms? Running both measures how much the architect stage
  contributes when handed the answer in prose rather than skipped outright.

## 7. Judge sensitivity (E-83)

E-83 sharpened the quality instrument and added the one plan-execution signal
the pipeline did not measure. Quality scores from before and after E-83 sit on
**different scales**; the `judge` field makes the boundary queryable and
`report.md` names it (averaging across it is now visible, not implicit).

- **Typed rubric vetoes** (`src/sdlc/benchmarks/vetoes.py`). A rubric
  criterion that states an absolute override ("scores 0 regardless") is a
  closed three-kind vocabulary (`mentions_all` / `not_both` / `nonempty`),
  evaluated **deterministically over the parsed artifact — zero model calls**
  — at both layers: an ABSOLUTE failure in the prompt gate, and a forced `0.0`
  override at Layer 3. Authored per case as `benchmarks/cases/<case>/vetoes-*.yaml`.
- **Staged judge.** The single-shot rubric prompt became two calls: rubric →
  ordered evaluation steps (cached per `sha256(rubric)`), then artifact →
  per-component scores. Vetoes override the LLM's output rather than being
  argued into it. Records carry `judge="staged_rubric"`; pre-E-83 records keep
  `"llm_judge"`.
- **Plan adherence, split by provenance.** A deterministic `PlanDrift` on each
  code-stage `BenchmarkRecord` (`files_hinted` vs `files_touched`, with
  `hinted_untouched`/`touched_unhinted`); and advisory `plan_deviations` folded
  into the existing `deep_review` lens (not a fifth lens), each with verbatim
  transcript evidence or dropped.
- **Sensitivity is proven, not asserted.** The mutation suite
  (`SDLC_PROMPT_EVAL=1 python -m pytest -m prompt_eval -k mutations`) records
  what real model behavior does to degraded prompts. The `scope_dropped`
  mutation fails absolutely via the `scope_preserved` veto — the gate's teeth
  are real and end-to-end. (`truncated`, which has no veto and relies on the
  advisory judge, remains the open case.) See spec §9 for the recorded outcome
  and the substring-matching correction.

---

*This document adds no scope to `PRD.md`. Every `(new scope)` marker above is a
measurement capability — held-out oracles, anti-cheat assertions, rubric
calibration tracking, the Field-Guide memory condition — that needs a PRD line
before it becomes a real requirement. Everything else is an `E-`-style plan for
measuring requirements already open in the tracker.*
