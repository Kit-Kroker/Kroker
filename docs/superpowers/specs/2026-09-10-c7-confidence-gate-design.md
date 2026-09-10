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
happens. This logic is defined twice, byte-for-byte identical except for the
docstring:

- `role_host.py:55-75` (`_auto_decision_for`), consumed at `role_host.py:224`
  inside `_revisable_stage` (`:212-239`), which serves the architecture gate
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
(`architecture/step.py:190-195`, `plan/step.py:110-114`). But it is a
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
  `plan_drift` ADVISORY check (`merge/step.py:87-116`, `:397`) — "any task
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

The **merge** gate has no realized-outcome signal at all today — nothing
in the codebase observes what happens to a build after it merges (no revert
detection, no post-merge hotfix linkage). This is a real hole in the design
space, not an oversight in this spec; see Open Question 2.

## 4. Design

### 4.1 Shape

A **gate calibration ledger**: a durable, cross-run table of
`(gate, bucket_key, confidence, realized_outcome)` tuples, built from data
already flowing through retro, plus a `calibration_verdict_for(gate,
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
   `GateOutcomeSummary` in `RunSummary.gates` where `decided_by == "policy"`
   (i.e., every auto-approve — HARD-decided and human-decided rows are not
   calibration inputs, since there is no "would a human have caught this"
   counterfactual for them), compute a realized-outcome label from
   already-available run data:
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
   This labeling is pure computation over data the run already produced —
   no new activity, no new I/O, added to the retro step that already runs
   best-effort and non-blocking (`stages/retro/step.py`'s existing
   try/except envelope covers it, so a labeling bug degrades to "this run's
   samples are skipped," never a run-outcome change).

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
   event and `GateOutcomeSummary`. This is a small, additive schema change
   (new optional field, old records read back with `bucket_key=None` →
   treated as "insufficient data," never a crash). See Open Question 4 for
   the alternative (bucket by `gate` alone).

4. **`calibration_verdict_for(gate, bucket_key)` lookup.** A new activity,
   read once per `_revisable_stage`/merge-gate call, before
   `_auto_decision_for` runs — analogous to how `_cached_stage` reads
   `cache_get` before invoking `run_fn` (`role_host.py:124-126`). Computes
   `compute_agreement` over the ledger rows for that bucket (most recent N,
   or a time window — Open Question 5) and returns a small
   `CalibrationVerdict(verdict: "calibrated"|"uncalibrated"|"insufficient_data",
   n, agreement_rate)`. `_auto_decision_for` becomes: `confidence >=
   threshold and calibration.verdict == "calibrated"` (both are pure once
   the verdict is fetched — the function itself stays synchronous and
   testable; only its caller becomes async-dependent on one more activity
   result, same shape as the existing memoization read).

5. **De-duplicating the two `_auto_decision_for` copies.** `merge/step.py`'s
   copy (`:161-177`) is byte-identical logic to `role_host.py`'s
   (`:55-75`) apart from the docstring. C7 is the natural forcing function
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

For each, a recommendation is given; none is self-ruled.

1. **Production realized-outcome proxies are noisier than a judge score.**
   Fix-attempt rate and plan-drift rate are real, already-computed signals,
   but they are indirect — a low-fix-attempt run doesn't prove the
   architecture was *right*, only that it was *cheap to build against*.
   **Recommendation:** accept the proxies for v1, tag every sample's
   `source` (`benchmark` vs. `production-proxy`), and keep the two
   populations in separate calibration buckets (never pooled — see Q6) so
   a future, better production signal can replace the proxy without
   silently changing what "calibrated" has meant historically.

2. **The merge gate has no realized-outcome signal, so under this design its
   SOFT auto-approve stops firing entirely (§4.2.1) until one exists.** Is
   that acceptable as a shipped side effect, or does merge need its own
   scoped fix first (e.g., a minimal post-merge revert/hotfix linkage) as a
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
   N=20 samples per bucket, matching `calibration.py`'s existing default
   `threshold=0.75` / `epsilon=0.15` for the agreement math itself. Every
   bucket starts "insufficient data" → fails through to human, so a new
   proposer model or gate has to earn auto-approve rather than default to
   it.

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
