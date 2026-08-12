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
and it is the precondition for P3's exit and everything in P4.

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
  context_window, compacted`; TemporalAgent usage records carry the proposer
  side. The numbers are collected; they are not yet aggregated into run-level
  counters.
- **CLI surface** — `sdlc ... benchmark` verb already exists (FR-603).
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

### Tier B — Rubric judging (subjective, already built)

The E-27 mechanism: a rubric per stage, scored by the cross-family judge. This
is the *only* way to grade non-code stages (clarify quality, architecture
soundness, research grounding) where no oracle suite can exist. It is already
wired for `clarifier/architect/planner` and, since E-27, `qa/research`.

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
| **Model × role** | which model drives each of 11 roles | `STAGE_MODELS` + `agents.yaml` per-role `model` | landed (E-37): per-cell arms + `--role-model`, ADR-6 per run |
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
because `PipelineConfig()` is constructed *inside* the workflow (E-26). A
per-cell model sweep needs the override to resolve at the boundary
(`benchmarks/workflow.py`) and satisfy ADR-6 *per run*. **E-37 landed this:**
each cell now carries a named `Arm` (role→model mix); `_cell_config` builds
`cfg.roles` from the arm and enforces ADR-6 per run via `validate_run_roles`,
and the CLI exposes the same override via `--role-model`. The full model×role
sweep is now expressible; the pre-E-37 harness-only `models=[...]` form still
works (desugared to one arm per model).

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
  primary number. Requires §6 priority 1.
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
- **Tokens per role**, with the planner/worker split Cursor highlight (workers
  carried ≥69%, often >90%, of tokens but a minority of cost).
- **Context-ceiling events** — `input_tokens > fraction × context_window` and
  `compacted=true` counts, from `HarnessRunResult` (SDLC-spec §4, ADR-13). A
  harness that keeps hitting its ceiling is a signal to decompose smaller.

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

### 4.4 The error heatmap (Abdullin's prioritisation instrument)

Aggregate the above — including the session-derived waste (§4.3) and the
anti-cheat findings (below) — into a **case × stage** grid: rows are benchmark cases,
columns are the 15 stages, cell colour is failure/rework density (gate
rejections, fix-loop iterations, oracle failures attributable to that stage).
This is Abdullin's `error heatmap` and it answers the only question that matters
between iterations: *which stage, on which class of case, is costing the most —
and therefore what do I fix next.* It is strictly more useful than a scalar and
it is the natural home for every §4.1–4.3 metric.

*Status (2026-08-03):* the case x stage heatmap is one of five grids written
by `sdlc benchmark score` (`heatmap`, `task-matrix`, `error-matrix`,
`waste-matrix`, `sc-rollup`), each emitted as `{.html,.json}` into the score
directory. The session-derived waste that feeds it landed in the same pass
(see §4.3).

---

## 5. Cases — authoring the corpus

Cases are the dataset. Three sources, matching the greenfield reality (there is
no history to mine):

- **Spec-authored katas (primary).** A case is a feature spec + a held-out
  oracle suite, authored together. The bar E-27 set is the right one: *"large
  enough to require decomposition and small enough to specify completely."* The
  cat-café case meets the "specifiable" half but not the "decomposition" half —
  **the top corpus gap is one case that forces genuine planner decomposition**
  (multiple vertical slices, real inter-task contracts), because that is the
  load-bearing variable Cursor's entire result turns on and the one the current
  suite cannot see.
- **Public anchors (external validity).** A handful of SWE-bench-Verified-style
  tasks (issue → PR with hidden tests) give an external, task-independent
  reference point that doesn't move when you change your own prompts. Use them
  to tell "my change regressed *my* cases" from "my change regressed
  *everything*". These grade purely on Tier A.
- **Distilled production incidents (the second loop).** Abdullin's loop B and
  Cursor's Field Guide are the same idea: every time the factory fails in real
  use, that failure becomes a case. This is *the* mechanism that grows the
  corpus past the cold start — and it is exactly what the retro stage (14) +
  `RunSummary` are for. Closing that stage (§6 priority 2) turns production runs
  into eval intake automatically. Until then, cases are hand-authored only.

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
   | Full matrix | `sdlc benchmark run` | hours | what does this architecture change do end-to-end |

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
  what real model behavior does to degraded prompts. The veto→`FAIL_ABSOLUTE`
  path works end-to-end; the `clarify` role is largely invariant under prompt
  degradation (the frozen fixture and schema carry the domain) — the honest
  OQ-P5 answer. See the spec's §9 for the recorded outcome.

---

*This document adds no scope to `PRD.md`. Every `(new scope)` marker above is a
measurement capability — held-out oracles, anti-cheat assertions, rubric
calibration tracking, the Field-Guide memory condition — that needs a PRD line
before it becomes a real requirement. Everything else is an `E-`-style plan for
measuring requirements already open in the tracker.*
