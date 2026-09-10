# C7 — Calibrating the self-reported confidence that skips the human gate

| | |
|---|---|
| Date | 2026-09-10 |
| Register row | C7, `docs/reports/external-ideas-2026-09.md` |
| Source finding | `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md`, census row 8 ("Row 8 is the headline") |
| Status | Design only — brainstorming + spec phase. No implementation in this change. |

## 1. The gap, restated precisely

Under `GatePolicy.SOFT`, a proposer's own self-reported `confidence` field,
if `>= GateConfig.threshold`, synthesizes a `GateDecision(outcome=APPROVE,
decided_by="policy")` that the gate short-circuits on — the human wait never
happens. This logic is defined twice, logically identical with identical
output, differing only in the docstring and cosmetic formatting (one builds
its `comments` string via line-continuation, the other via a parenthesized
expression):

- `role_host.py:55-75` (`_auto_decision_for`), consumed at `role_host.py:224`
  inside `_revisable_stage` (`:212-244`), which serves the architecture gate
  (`architecture/step.py:188`) and the plan gate (`plan/step.py:109`).
- `merge/step.py:161-177` (`_auto_decision_for`, an independent copy — not
  imported from `role_host.py`), consulted at `merge/step.py:484` inside
  `step()`, gated behind `cfg.gates.get("merge", ...).policy == SOFT` at
  `:468`. (The audit's `merge/step.py:84-100` / `:399` line numbers predate
  the 2026-09-10 C8 merge; current lines verified above.)

Two guards already exist and are real:

- `role_host.py:64-65`: `confidence is None` never auto-approves — falls
  through to the human wait. (Same guard duplicated at `merge/step.py:165`.)
- `role_host.py:236-239`: once `_revisable_stage` exhausts
  `cfg.max_gate_rounds`, the final gate call passes no `auto_decision` at
  all, so even SOFT waits.

What neither guard nor anything else in the codebase does: check whether the
confidence number itself has ever been *right*. A proposer that is
confidently wrong every time clears `threshold` exactly as reliably as one
that is calibrated, and nothing downstream of `_auto_decision_for` notices
the difference before the human gate is skipped — the skip already
happened.

## 2. What "confidence calibration is already retained and fed back" (C5) actually refers to

Register row C5 says the reviewer-tuning idea "extends" an existing loop:
"confidence calibration is already retained and fed back." Verified against
the tree: this describes a **different mechanism** than the one C7 needs,
and the two must not be conflated in the fix.

- `src/sdlc/benchmarks/calibration.py` is rubric-judge calibration (E-36 /
  FR-110): a human hand-scores a sample of `CalibrationFixture`s, the
  cross-family LLM judge scores the same fixtures, `compute_agreement`
  reports agreement rate / MAE / Spearman against a fixed `epsilon`/
  `threshold`, written to `calibration.json` and rendered as a trust table
  (`render_calibration_markdown`). It calibrates **the judge's `QualityScore`
  against a human rater**. It is offline, requires manual `human_score`
  entry, and — per its own docstring — "Advisory only — never modifies a
  composite score or a gate outcome." It has no connection to
  `_auto_decision_for` and does not read `GateOutcomeSummary.confidence`.
- `src/sdlc/capability/store.py:68`'s "calibration signal the contracts
  claim to retain" is about capability-identity correction reasons (`BC-NNN`
  re-matching), not gate confidence at all — a third, unrelated meaning of
  "calibration" in this codebase.
- The thing that *is* retained today, and *is* the right substrate: every
  gate decision's confidence is captured in `GateOutcomeSummary`
  (`core/models.py:441-451`, built by `_gate_outcome`,
  `observability/summary.py:33-45`, from the `GATE_DECIDED` trace event) and
  rolled into `RunSummary.gates` (`core/models.py:469`), which retro writes
  to episodic memory on **every** run — not just benchmark runs
  (`stages/retro/step.py`, docstring: "fires on every terminal path,
  populates run_summary() ... updates episodic memory"). `sc_rollup.py`'s
  `_sc6` (`:159-183`) already reads this list, but only computes a
  **frequency** — "soft gates a human decided" / "soft gates with waved
  advisory checks" — never an **accuracy** comparison against what actually
  happened next. That gap between "retained" and "scored against outcome"
  is exactly what C7 names.

So C5's premise is half right: the *confidence value* is retained
(`GateOutcomeSummary.confidence`) and *is* fed into a rollup (SC-6). What is
not retained or fed back is any realized-outcome label to score that
confidence against, and nothing consumes such a score at decision time. C7
is not "extend C5" so much as "build the missing half of what C5 assumed
already existed," which is exactly the register row's own framing ("C5's
calibration loop pointed at gates rather than at findings") — this spec
makes that framing literal rather than aspirational.

## 3. Ground-truth availability — the constraint that shapes the whole design

`ctx.judge` (`core/context.py:52`, implemented at
`workflows/benchmark_host.py:107-139`) is the strongest available quality
signal — a cross-family LLM judge score against a pinned rubric — and it is
already called unconditionally after both the architecture and plan gates
(`architecture/step.py:190-195`, `plan/step.py:111-116`). But it is a
**no-op outside benchmark mode**: `_judge` returns
`QualityScore(score=None, judge="llm_judge")` immediately when
`not self._benchmarking(cfg)` (`benchmark_host.py:126-128`). Most real runs
are not benchmark runs. A calibration design that only scores confidence
against `ctx.judge` output would silently cover almost none of the traffic
that actually exercises the auto-approve short-circuit — the exact failure
shape C5's premise had.

Production runs (non-benchmark) do already compute two downstream signals,
unconditionally, that can stand in as realized-outcome proxies:

- **Plan drift** (E4): `compute_plan_drift` (`plan/models.py:51`) runs per
  task at code-stage (`code/step.py:750`), is attached to every
  `BenchmarkRecord`-shaped task result, and is aggregated at merge into the
  `plan_drift` ADVISORY check (`merge/step.py:87-118`, consulted `:397`) — "any task
  exceeded the per-task threshold." This is a plan-quality signal computed
  today and, per the audit's out-of-scope table, "read by nothing" for any
  calibration purpose. It is the natural realized-outcome proxy for the
  **plan** gate: a plan whose tasks drifted heavily was a plan the gate
  should not have trusted.
- **Fix-loop cost**: `StageOutcome.fix_attempts` (`core/models.py:428`,
  populated from `RunEvent` data at `observability/summary.py:20-30`) is
  recorded for every stage on every run. A high fix-attempt rate for tasks
  downstream of an auto-approved architecture/plan is a second, coarser
  realized-outcome proxy, usable for the **architecture** gate (which has no
  drift-style signal of its own — the audit's out-of-scope table notes "the
  plan stage has nothing analogous" to the architect's brownfield delta
  check).

The **merge** gate has no *attributable* realized-outcome signal today. The
deploy stage (E-67, `src/sdlc/deploy/`: apply → smoke → rollback, with its
own `deploy_failed` gate) does observe post-merge build behavior, but it is
off by default (`DeployConfig.enabled = False`, `core/models.py:301-305`,
D-9), is not always configured even when reached (`merged-not-deployed:`
outcomes exist as their own class, `sc_rollup.py:32`), and nothing links a
deploy outcome back to the merge gate's `confidence` or `GateOutcomeSummary`
row that produced the build being deployed. So it is a candidate signal, not
a usable one as-is — a real hole in the design space, not an oversight in
this spec; see Open Question 2.

## 4. Design

### 4.1 Shape

A **gate calibration ledger**: a durable, cross-run table of
`(gate, bucket_key, confidence, realized_outcome)` tuples, built at retro
from the run's own data — today that reaches retro only for the fix-attempt
label; the plan-drift and judge-score labels need the plumbing Open
Question 8 decides — plus a `calibration_verdict_for(gate,
bucket_key)` lookup that `_auto_decision_for`'s caller consults before
honoring a self-reported confidence. An auto-approve now requires **two**
conditions instead of one: `confidence >= threshold` **and** the ledger's
calibration verdict for that gate/bucket says the confidence signal has
historically been trustworthy. Below the sample floor, or when the verdict
is "uncalibrated," the gate falls through to the human wait — the same
fail-safe shape as the existing `None`-confidence guard (`role_host.py:
64-65`), extended from "no data" to "not enough good data."

This reuses `calibration.py`'s existing agreement math
(`compute_agreement`, `AgreementStats`, the `epsilon`/`threshold`/`verdict`
shape) rather than inventing a second statistic — but as a **second
instantiation of that function**, over a different pair population
(self-reported `confidence` vs. a realized-outcome label, not judge-score
vs. human-score), with its own storage. It does not touch or reuse
`calibration.py`'s `CalibrationFixture` file-based storage, which is
purpose-built for hand-scored offline fixtures and has no cross-run
retention story.

### 4.2 Pieces

1. **Realized-outcome labeling (retro-stage addition).** At retro, for each
   `GateOutcomeSummary` in `RunSummary.gates` where `policy == "soft" and
   decided_by == "policy" and confidence is not None` — this is deliberately
   narrower than "every `decided_by == 'policy'` row": `GatePolicy.OFF` also
   synthesizes `decided_by="policy"` (`gates.py:195-198`), but with no
   confidence to score, so it must be excluded explicitly rather than by
   accident of having nothing to compute — compute a realized-outcome label
   from already-available run data:
   - `architecture`: label = 1.0 minus a normalized downstream fix-attempt
     rate for tasks in the run (proxy from §3); if benchmark mode and
     `ctx.judge` produced a score for this stage, prefer the judge score
     (stronger signal) and tag the sample `source=benchmark`.
   - `plan`: label = 1.0 minus the plan-drift rate from `plan_drift` checks
     across the run's tasks (proxy from §3); same benchmark preference and
     tagging.
   - `merge`: no label computed in this design (§3) — the merge gate's
     entries are retained (so the ledger is ready the day a signal exists)
     but never scored, and `calibration_verdict_for("merge", ...)` always
     returns "insufficient data," which — per §4.1 — means merge's SOFT
     auto-approve never fires under this design until Open Question 2 is
     resolved. This is a behavior change worth flagging on its own: it is a
     strictly more conservative posture than today's merge gate, adopted
     as a consequence of the ground-truth gap rather than chosen directly.

   **Correction: this labeling is *not* pure computation inside retro as it
   stands today, for two of the three inputs.** Retro's step signature is
   `(ctx, cfg, summary, session_refs, trace)` (`stages/retro/step.py:34-40`).
   `RunSummary` (`core/models.py:454-476`) carries no plan-drift or
   quality-score field, and the `STAGE_ENDED` trace emit
   (`benchmark_host.py:93-102`) carries only `stage`, `role`, `outcome`,
   `duration_s`, `fix_attempts`, and `cost_usd` — no `plan_drift`, no
   `task_id`, no judge `QualityScore`. Per-task `PlanDrift` is attached to
   `BenchmarkRecord`s (`code/step.py:750, 769`) and reaches durable storage
   only in benchmark mode (`benchmark_host.py:103-105`); in a production run
   it lives only in workflow-local memory during the code stage and in
   merge's in-flight `CheckResult`, which `GATE_DECIDED` never carries
   (`feature.py:241-250`; merge's own gate-decided emit at
   `merge/step.py:453-462` doesn't either). The judge score has the same
   problem: `_quality.score` (`architecture/step.py:190-195`,
   `plan/step.py:111-116`) never reaches `summary` or `trace`. Only the
   fix-attempt label is actually computable inside retro today, from
   `summary.stages[].fix_attempts`.

   This is a plumbing decision the spec must make, not leave for the
   implementation plan to discover — see **Open Question 8**. Once that
   plumbing exists, labeling itself stays pure computation over data the run
   already produced, added to the retro step that already runs best-effort
   and non-blocking (`stages/retro/step.py`'s existing try/except envelope
   covers it, so a labeling bug degrades to "this run's samples are
   skipped," never a run-outcome change).

2. **Ledger storage.** One row per labeled sample:
   `(gate, bucket_key, confidence, outcome_label, source, run_id,
   recorded_at)`. Recommended: a new table in the board's existing SQLite
   substrate (`board/schema.py`, the pattern `capability/store.py` already
   follows per ADR-19 — "adapters, not substrate," reusing the board's
   optimistic-concurrency discipline rather than a third storage scheme).
   Appended once per labeled sample at retro, via a new activity (parallel
   to `record_benchmark`, but unconditional rather than benchmark-gated).

3. **`bucket_key`.** The `GATE_DECIDED` trace event
   (`workflows/gates.py:234`, `_on_gate_decided`) and `GateOutcomeSummary`
   carry `gate`, `round`, `policy`, `decided_by`, `approved`, `confidence`,
   `overrides` — **no proposer model**. Bucketing by `(gate, author_model)`
   — recommended, since different proposer models calibrate differently —
   requires threading `resolve_role_model(cfg, stage)` (already computed at
   the `_cached_stage` call site, `role_host.py:121`) into the gate-decided
   event and `GateOutcomeSummary`. This is a small, additive schema change:
   the field being added is `author_model` (`bucket_key` is derived from it,
   e.g. `f"{gate}:{author_model}"` — not itself a stored field). Old
   records read back with `author_model=None` → their derived bucket_key is
   excluded from lookups (or falls into a `(gate, None)` bucket that never
   clears the sample floor) → treated as "insufficient data," never a crash.
   See Open Question 4 for the alternative (bucket by `gate` alone).

4. **`calibration_verdict_for(gate, bucket_key)` lookup.** A new activity,
   read once per `_revisable_stage`/merge-gate call **only when the gate's
   configured policy is SOFT and the artifact's `confidence` is not
   `None`** — every other path (`HARD`, `OFF`, SOFT-with-no-confidence,
   the exhausted-rounds final gate) skips the read entirely, so §4.3's
   "untouched" claim holds as a property of the call site, not just of
   `_auto_decision_for`'s internals, and no activity call or new dependency
   is added to those paths. Read before `_auto_decision_for` runs —
   analogous to how `_cached_stage` reads
   `cache_get` before invoking `run_fn` (`role_host.py:124-126`). **Lookup
   failure (storage outage, activity exhausts its retry policy) is treated
   as `insufficient_data`** — the same in-band fail-safe value as "not
   enough samples yet," not a stage failure — so the auto-approve path
   degrades to the human wait exactly like the existing `None`-confidence
   guard, rather than raising. Computes
   `compute_agreement` over the ledger rows for that bucket (most recent N,
   or a time window — Open Question 5) and returns a small
   `CalibrationVerdict(verdict: "calibrated"|"uncalibrated"|"insufficient_data",
   n, agreement_rate)`. `_auto_decision_for` becomes: `confidence >=
   threshold and calibration.verdict == "calibrated"` (both are pure once
   the verdict is fetched — the function itself stays synchronous and
   testable; only its caller becomes async-dependent on one more activity
   result, same shape as the existing memoization read).

5. **De-duplicating the two `_auto_decision_for` copies.** `merge/step.py`'s
   copy (`:161-177`) is logically identical to `role_host.py`'s
   (`:55-75`), with identical output, differing only in the docstring and
   in how the `comments` string is formatted (§1). C7 is the natural forcing function
   to collapse them into one shared function (`role_host.py`'s, imported by
   `merge/step.py`) rather than plumbing the calibration-verdict parameter
   through two independent copies that will drift again. This is a
   refactor riding along with the feature, not a separate goal — flagged
   here so the reviewer doesn't read it as scope creep.

### 4.3 What this does not change

- `GateConfig.threshold` and `GatePolicy` are untouched — the calibration
  check is a second, independent gate on the auto-approve path, not a
  replacement for the existing confidence-vs-threshold comparison.
- HARD and OFF gates are untouched — calibration only ever *removes* an
  auto-approve that would otherwise have fired under SOFT; it cannot cause
  a gate that would have waited for a human to skip that wait.
- The exhausted-rounds final gate (`role_host.py:236-239`) is untouched —
  it already never passes `auto_decision`.

## 5. Open questions

For each, a recommendation is given; none is self-ruled. **All nine were
ruled at the user gate on 2026-09-10 — see §6.**

1. **Production realized-outcome proxies are noisier than a judge score.**
   Fix-attempt rate and plan-drift rate are real, already-computed signals,
   but they are indirect — a low-fix-attempt run doesn't prove the
   architecture was *right*, only that it was *cheap to build against*.
   **Recommendation:** accept the proxies for v1, tag every sample's
   `source` (`benchmark` vs. `production-proxy`), and keep the two
   populations in separate calibration buckets (never pooled — see Q6) so
   a future, better production signal can replace the proxy without
   silently changing what "calibrated" has meant historically.

2. **The merge gate has no *attributable* realized-outcome signal (§3 — the
   deploy stage is the one weak candidate, off by default and never linked
   back to the gate decision), so under this design its
   SOFT auto-approve stops firing entirely (§4.2.1) until one exists.** Is
   that acceptable as a shipped side effect, or does merge need its own
   scoped fix first (a minimal post-merge revert/hotfix linkage, or
   attributing the existing deploy outcome back to the merge gate's
   `GateOutcomeSummary` row) as a
   prerequisite rather than a follow-up? **Recommendation:** ship the
   architecture/plan calibration now (proxies exist, addresses the audit's
   headline row for two of the three sites), and file the merge-gate
   realized-outcome signal as its own register row rather than blocking
   this spec on it — but flag explicitly that this changes merge's runtime
   behavior (more human gates fire) the day C7 ships, so it is a decision,
   not an incidental detail.

3. **Cold-start sample floor.** How many labeled samples before a
   `(gate, bucket_key)` is allowed to auto-approve at all?
   **Recommendation:** reuse the existing `MIN_RUNS = 5` floor pattern from
   `sc_rollup.py:24` conceptually, but at the *sample* (not *run*) level —
   N=20 samples per bucket. Every
   bucket starts "insufficient data" → fails through to human, so a new
   proposer model or gate has to earn auto-approve rather than default to
   it. The agreement math's own constants (`threshold` / `epsilon`) are a
   separate, sequenced decision — see Open Question 9(3), which governs
   them; this question fixes only the sample floor.

4. **Bucket granularity.** Per `(gate, author_model)` (recommended, §4.2.3)
   or per `gate` alone (simpler, no schema change to `GateOutcomeSummary`/
   `GATE_DECIDED`, but blends a well-calibrated model's confidence with a
   poorly-calibrated one behind one number, and a model swap silently
   resets nothing since the blended bucket never resets). **Recommendation:**
   per-model, accepting the schema addition, because the failure mode of
   coarse bucketing (a good model's calibration masking a bad one's) is
   exactly the kind of thing this spec exists to prevent.

5. **Window vs. all-time.** Should `calibration_verdict_for` compute over
   *all* retained samples for a bucket, or a rolling window (last N, or last
   K days)? All-time is simpler and matches `calibration.py`'s existing
   fixture-set model; a rolling window adapts faster if a proposer's
   calibration genuinely improves (e.g., after a prompt change) but needs a
   decision on window size and how to treat a just-reset bucket (same
   cold-start floor, presumably). **Recommendation:** rolling window, last
   200 samples per bucket, specifically because a prompt or model change
   should be able to earn back trust rather than being permanently
   penalized by stale samples — but this is a product call about how fast
   trust should be regained, not a technical one.

6. **Pooling `benchmark` and `production-proxy` samples.** Already
   recommended against in Q1, restated as its own decision because it is
   the one most likely to be "helpfully" merged later for sample-count
   reasons: pooling would let a judge-backed calibration verdict silently
   authorize auto-approves on proxy-only evidence. **Recommendation:** keep
   permanently separate, or at minimum require both sub-populations to
   independently clear the calibration bar before a pooled verdict can be
   "calibrated."

7. **Downgrade shape.** An uncalibrated verdict fully disables auto-approve
   for that bucket (this design, §4.1) — binary. An alternative is a
   *sliding* threshold (e.g., effective threshold = configured threshold +
   a calibration penalty proportional to miscalibration), which degrades
   more gracefully but adds a second tunable number nobody has calibrated
   either. **Recommendation:** binary for v1 — it's the same fail-safe
   shape as the existing `None`-confidence guard, easy to reason about, and
   avoids inventing a second uncalibrated parameter on day one.

8. **Plumbing the plan-drift and judge-score labels into retro.** §4.2.1's
   labeling step needs two inputs retro cannot see today: per-task
   `PlanDrift` (production runs only compute it transiently at code-stage
   and merge, never durable outside benchmark mode) and `ctx.judge`'s
   `QualityScore` for the architecture/plan artifact (computed, but never
   written to `summary` or `trace`). Two ways to close this:
   - **(a) Extend the `STAGE_ENDED` emit / `RunSummary`.** Add `plan_drift`
     (the chosen scalar — see Open Question 9) and `quality_score` to the
     `STAGE_ENDED` emit (`benchmark_host.py:93-102`) alongside the existing
     `fix_attempts`, so `_stage_outcome` (`observability/summary.py:20-30`)
     carries both into `RunSummary.stages` the same way it already carries
     `fix_attempts`. Small, additive (new optional trace fields, old traces
     replay as `None`), and keeps retro's
     `(cfg, summary, session_refs, trace)` signature the sole input to
     labeling — the property §4.2.1 originally (incorrectly) assumed.
     **The judge score must ride `STAGE_ENDED`, not `GATE_DECIDED`**: the
     gate-decided event fires from `_on_gate_decided` at the end of `_gate()`
     (`gates.py:234`), which returns *before* `ctx.judge` is called
     (`architecture/step.py:190-195`, `plan/step.py:111-116` — both after
     `revisable_stage` has already returned), so the score does not exist
     yet at that point. The named alternative, if the score must be
     correlated to a specific gate round rather than to the stage, is a
     merge-style enriched re-emit: a second, stage-authored `GATE_DECIDED`
     carrying the extra field after the score exists, the way
     `merge/step.py:453-462` already re-emits its own gate-decided event
     with an `overrides` field the host's `_on_gate_decided` never emits.
   - **(b) Thread task results into retro.** Change retro's step signature
     to also receive the run's task results / `BenchmarkRecord`-shaped data
     directly (as merge already does, `merge/step.py`'s `task_results`
     parameter), bypassing the trace/summary round-trip entirely.
   **Recommendation: (a).** It is strictly additive to an already-established
   pattern (`fix_attempts` and `confidence` already make this exact
   round-trip through `STAGE_ENDED`/`GATE_DECIDED` → `RunSummary`), keeps
   retro's signature and its "derived purely from `RunSummary`/`trace`"
   contract intact, and doesn't hand retro a second, wider surface (raw task
   results) it would otherwise have to defensively read past. (b) is more
   direct but couples retro to the task-result shape the way merge is
   coupled to it, which is exactly the kind of surface-widening this
   codebase's `StageContext` seam (`core/context.py`'s docstring: "is this a
   capability the orchestrator provides, or a value it holds?") argues
   against for a best-effort, non-blocking stage.

9. **Label definition and normalization.** §4.2.1's labels — "1.0 minus a
   normalized downstream fix-attempt rate" and "1.0 minus the plan-drift
   rate" — leave the exact quantity undefined, and the calibration verdict
   is entirely a function of it: `compute_agreement`'s verdict is
   `|confidence − label| <= epsilon` for `>= threshold` of samples
   (`calibration.py:125-157`). If labels cluster near 1.0 — e.g., most tasks
   take zero fix attempts, or most plans don't drift — then any
   consistently-high self-reported confidence clears the agreement bar
   trivially, reconstructing row 8's hole under a calibration-shaped name:
   the check would say "calibrated" without ever having been tested against
   a case where the proposer should have been less confident. Concretely
   undefined:
   - **Plan-drift label**: the codebase already computes two different
     quantities that could serve — the binary per-task
     `_plan_drift_flags` threshold check (`merge/step.py:87-95`, "did this
     task exceed the per-task ratio") or the continuous
     `touched_unhinted / files_touched` ratio itself
     (`plan/models.py:40-43`). A binary label produces a near-degenerate
     [0, 1] outcome distribution (mostly 0 or 1 drift-exceeded, aggregated
     across a run's tasks into some run-level fraction); the continuous
     ratio is smoother but needs its own clamping/aggregation decision
     (mean across tasks? worst task? weighted by task size?).
   - **Fix-attempt label**: needs an explicit denominator (attempts capped
     at `cfg.max_fix_attempts`? normalized against a run-wide or
     project-wide baseline rate rather than an absolute count, so a
     naturally-harder codebase doesn't permanently read as "low
     confidence-worthiness"?) and an aggregation level (per-task, then
     averaged into one run-level label per gate decision, or one label per
     task attributed to the same architecture/plan decision?).
   - **The agreement constants** `epsilon=0.15` / `threshold=0.75`
     (`calibration.py:125-127`) were chosen for judge-score-vs-human-score
     agreement, a different population from confidence-vs-outcome-label.
     Inheriting them is only defensible while the ledger has no real samples
     to derive better ones from — which makes this a sequenced decision, not
     a standing one, and this question (not Q3) governs it.
   **Recommendation:** before the implementation plan, pin: (1) plan-drift
   label = the continuous `touched_unhinted/files_touched` ratio,
   mean-aggregated across the run's tasks, inverted (`1 - ratio`) and
   clamped to `[0, 1]` — continuous over binary, so the label has room to
   discriminate rather than degenerating to two clusters; (2) fix-attempt
   label = `1 - min(attempts, cfg.max_fix_attempts) / cfg.max_fix_attempts`,
   mean-aggregated per run, deferring any project-relative baselining to a
   later iteration rather than adding a second undefined normalization now;
   (3) the agreement constants in two explicitly sequenced steps — **inherit
   `calibration.py`'s `threshold=0.75` / `epsilon=0.15` at cold start**, when
   there is no ledger data to do better with, **then re-derive both
   empirically from the first batch of real collected samples** once the
   ledger has them, treating the inherited pair as a starting position rather
   than a settled default. Treat all three as the
   user's call, not something this design should settle unilaterally, since
   a wrong choice here is precisely how the check goes vacuous.

## 6. Rulings — user gate, 2026-09-10

All nine open questions were decided at the gate, taking both reviewer passes
(`.workspace/tmp/reviewer-1.md`, verdict *fixes-needed*, folded at `a960411`;
`.workspace/tmp/reviewer-2.md`, verdict *approve*, waived minors folded at
`31fe9a2`) into account. **Every ruling took this spec's own recommendation
unchanged** — so §4's design as written above is the design as ruled, and no
section needed re-editing to match a ruling. Each question is restated below
so the reasoning survives the decision, and the implementation plan
(`docs/superpowers/plans/2026-09-10-c7-confidence-gate.md`) implements the
spec as ruled here, not the spec's open-ended form.

**OQ1 — production proxies: ACCEPT for v1, with `source` tagging.**
Fix-attempt and plan-drift rates are indirect evidence of whether an
auto-approved artifact was good, but they are the only signals that exist
outside benchmark mode, which is where nearly all auto-approvals actually
happen. Every sample carries `source` (`benchmark` | `production-proxy`) so a
later, better production signal can replace the proxy without silently
redefining what "calibrated" has meant historically. *Folded into §3, §4.2.1,
§4.2.2.*

**OQ2 — the merge gate: SHIP WITHOUT IT; merge's SOFT auto-approve stops
firing.** Merge has no *attributable* realized-outcome signal (§3: the deploy
stage is the one weak candidate — off by default, often absent, never linked
back to the gate decision). Consequence, accepted deliberately rather than
incidentally: merge-gate rows are still written to the ledger, but are never
labeled, so `calibration_verdict_for("merge", ...)` never clears
insufficient-data and the human merge gate always fires under SOFT. The
post-merge signal that would lift this is filed as its own register-row
proposal rather than blocking C7. Per protocol the register row itself is
added by the user. *Folded into §3, §4.2.1.*

**OQ3 — cold-start floor: N=20 SAMPLES per bucket.** Sample-level, not
run-level — the `MIN_RUNS = 5` floor at `sc_rollup.py:24` is the precedent for
having a floor at all, not for its value. Every bucket starts
insufficient-data and therefore fails through to the human, so a new proposer
model or gate earns auto-approve rather than defaulting to it. This question
governs the floor only; the agreement constants are OQ9(3). *Folded into
§4.2.4, §5 Q3.*

**OQ4 — bucketing: PER `(gate, author_model)`, with the additive schema
change.** `author_model` is added to the `GATE_DECIDED` emit and
`GateOutcomeSummary`; `bucket_key` is derived from it, not stored. Coarser
`(gate)`-only bucketing would let a well-calibrated model's history mask a
poorly-calibrated one's — the exact substitution this spec exists to prevent.
Old records read back with `author_model=None` and never clear the floor.
*Folded into §4.2.3.*

**OQ5 — window: ROLLING, last 200 samples per bucket.** A prompt or model
change should be able to earn trust back rather than being permanently
weighted down by stale samples. The cold-start floor (OQ3) applies to the
window's contents, so a freshly-reset bucket fails through to the human until
it refills. *Folded into §4.2.4.*

**OQ6 — populations: NEVER POOLED.** Benchmark (judge-backed) and
production-proxy samples stay in separate buckets permanently. Pooling would
let judge-backed evidence silently authorize auto-approves that only
proxy-backed evidence actually supports — and the pressure to pool "just for
sample count" is exactly why this is a standing ruling rather than an
implementation detail. *Folded into §4.2.1, §4.2.2.*

**OQ7 — downgrade shape: BINARY.** An `uncalibrated` or `insufficient_data`
verdict disables auto-approve for that bucket outright; no sliding threshold
penalty. Same fail-safe shape as the existing `None`-confidence guard
(`role_host.py:64-65`), and it avoids introducing a second uncalibrated tuning
constant on day one. *Folded into §4.1, §4.2.4.*

**OQ8 — label plumbing: OPTION (a), extend the `STAGE_ENDED` emit and
`RunSummary`.** Both `plan_drift` (the OQ9 scalar) and `quality_score` ride
`STAGE_ENDED` (`benchmark_host.py:93-102`) alongside the existing
`fix_attempts`, and `_stage_outcome` (`observability/summary.py:20-30`)
carries them into `RunSummary.stages`. The judge score cannot ride
`GATE_DECIDED`: that event fires from `_on_gate_decided` at the end of
`_gate()` (`gates.py:234`), before `ctx.judge` runs. Retro's
`(cfg, summary, session_refs, trace)` signature is unchanged — it is not
handed raw task results. *Folded into §4.2.1, §5 Q8.*

**OQ9 — label definitions: ALL THREE PINNED as recommended.**
(1) plan-drift label = the continuous `touched_unhinted / files_touched` ratio
(`plan/models.py:40-43`), mean-aggregated across the run's tasks, inverted
(`1 - ratio`), clamped to `[0, 1]` — continuous over the binary per-task flag
(`merge/step.py:87-95`) so the label can discriminate instead of collapsing
into two clusters. (2) fix-attempt label =
`1 - min(attempts, cfg.max_fix_attempts) / cfg.max_fix_attempts`,
mean-aggregated per run; project-relative baselining is deferred rather than
adding a second undefined normalization now. (3) agreement constants in two
sequenced steps: inherit `calibration.py`'s `threshold=0.75` / `epsilon=0.15`
at cold start, then re-derive both empirically from the first batch of real
collected samples. The vacuity risk this settles — labels clustering near 1.0
letting any high self-reported confidence clear the bar — is the failure mode
that would have recreated audit row 8's hole under a calibration-shaped name.
*Folded into §4.2.1, §5 Q9.*
