# Bug Assessment: heatmap fix-attempts inflate quadratically (n(n-1)/2 instead of n-1)

- **Slug**: heatmap-fix-inflation
- **Created**: 2026-09-20
- **Source**: pasted text (orchestrator TASK BRIEF, worktree `D:/own/Kroker-bug` @ e096eb9)
- **Verdict**: valid
- **Severity**: medium (benchmark reporting integrity; headline density metric overstated quadratically; no pipeline/runtime behavior affected)

## Report (verbatim or summarized)

A code task needing n attempts reports n(n-1)/2 fix attempts in the benchmark
rework heatmap instead of the intended n-1 (3 attempts -> 3 shown; 4 -> 6
shown). Recorded benchmark baselines re-aggregate inflated. Evidence card:
E77-OQ-1 (`.specify/specs/001-canonical-stage-graph-sha/spec.md:273`),
explicitly deferred by E-77's research.md R-12 ("Not changed: the
pre-existing `attempt - 1` handler convention (E77-OQ-1)").

## Symptom

The `fix_attempts` value of a heatmap cell `(case_id, stage="code")` is the
SUM of a per-record running counter rather than the task's final count, so a
task loop of n attempts contributes 0+1+...+(n-1) = n(n-1)/2 instead of n-1.
Because `density = (gate + fix + oracle) / n_runs`, the inflated fix axis
inflates the heatmap's headline rework-density metric.

## Reproduction

Deterministic, unit-level (pure aggregation; no I/O, no Temporal):

1. Construct n=4 `BenchmarkRecord`s with the same `run_id` and `task_id`,
   `stage="code"`, `attempt=0..3`, `fix_attempts=0..3` (exactly what
   `code/step.py` stamps for a 4-attempt task).
2. `build_heatmap(records)` -> cell `fix_attempts == 6` (observed) instead of
   `3` (intended n-1).
3. n=3 -> 3 shown (intended 2); n=4 -> 6 shown (intended 3). Matches the
   reported symptom exactly.

On recorded data: any bench run whose records contain a (run_id, task_id)
group with >=3 code attempts; `heatmap.json` overstates that task's
contribution by n(n-1)/2 - (n-1).

## Suspected Code Paths

- `src/sdlc/stages/code/step.py:784` — producer: the attempt loop (`while
  True`, `attempt += 1` at :559) stamps `fix_attempts=attempt-1` on EVERY
  code-stage record (:786 also stamps `attempt=attempt-1`), so a task's
  records carry the running counter 0..n-1, one record per attempt.
- `src/sdlc/benchmarks/heatmap.py:101` — aggregator: `acc[key]["fix"] +=
  r.fix_attempts` sums the running counter across all records in the
  (case_id, stage) cell -> arithmetic inflation.
- `src/sdlc/benchmarks/heatmap.py:103-119` — E-77 fail_reentry pass
  (once per distinct (run_id, activation_id) with fail_reentry==1) adds to
  the SAME accumulator; orthogonal axis, not a co-cause (see Interplay).
- `src/sdlc/benchmarks/report.py:130-154` — `write_heatmap` / finalize call
  site (file writes live here; unchanged by either direction).

## Root Cause Hypothesis

**Confidence: high (verified by inspection; arithmetic identity).** The
per-record `fix_attempts` field is a *within-loop running counter* ("fixes
made before this attempt"), but the heatmap consumes it as if each record
carried an *increment* ("fixes made by this attempt"). Only the final record
of a (run_id, task_id) group carries the task's true total n-1. Summing a
monotone 0..n-1 counter yields n(n-1)/2. Verified:

- **Only `code` records carry nonzero fix_attempts.** `review/step.py:158,226`
  stamps 0 (pinned by `tests/review/test_adversary_workflow.py:140`), the qa
  record of the same loop (`code/step.py:793-808`) omits it (default 0,
  `benchmarks/models.py:183`), handoff records stamp 0 (`code/step.py:458`,
  `feature.py:256`), all other stages omit it. `heatmap.py:19-22` documents
  the lens convention.
- **Record identity / monotonicity (binding constraint, verified).** The
  group that owns a counter is `(run_id, task_id)` — task_ids are plan-scoped
  and REPEAT across runs of a case, so run_id must be in the key; this is
  already the repo's convention in `sc_rollup.py:105` (`attempts[(r.run_id,
  r.task_id)]`). Within that group the counter is strictly monotone
  0,1,...,n-1 by construction: every loop path increments `attempt` exactly
  once per record (the :914 one-more-attempt REVISE rule sets
  `budget = attempt + 1` and continues the same loop; the thaw path and the
  drift-forced `budget = attempt` termination do not reset or re-stamp
  anything). Therefore `max()` per group == the final record's value == n-1,
  exactly, for all recorded history.
- **Honest precedent in-repo:** `scripts/aggregate_benchmarks.py:206`
  (`fix_attempts_max = max(...)` per run) and `sc_rollup.py:110`
  (`any(r.fix_attempts > 0)` boolean) already consume the counter without
  summing it.

## Consumer map (binding constraint: ALL consumers of fix_attempts)

Record path (`BenchmarkRecord.fix_attempts`, running counter):

| Consumer | Reads | Inflated? | Effect of fix directions |
|---|---|---|---|
| `benchmarks/heatmap.py:101` | SUM per (case, stage) cell | **YES — this bug** | A fixes; B fixes future only |
| `scripts/aggregate_benchmarks.py:206` | MAX per run over task records | no | A: unchanged. **B: breaks** (max reads 0/1, not n-1) |
| `scripts/aggregate_benchmarks.py:260,532` | raw per-record detail rows | no (shows the counter per row) | A: unchanged. B: rows lose the counter |
| `benchmarks/sc_rollup.py:99-126` | `any(>0)` per (run_id, task_id) | no (boolean) | A: unchanged. B: unchanged |
| `observability/summary.py:31,89` | per-event `StageOutcome` rows (no summation) | no (rows, not a total) | A: unchanged. **B: row semantics change** |
| `calibration/labels.py:107-109` | mean over code rows of capped counter — RULED reading OQ9(2), docstring :57-67 + pinned tests | no (documented mean-over-attempts) | A: unchanged. **B: silently changes the ruled label semantics** |
| `workflows/benchmark_host.py:102` | trace event per record | no | A: unchanged. B: event payload changes |
| `observability/export.py:35,85` | per-record render | no | A: unchanged. B: rows lose the counter |
| `retro/step.py:103-113` | boolean `any(FIX_ATTEMPT, attempt != 1)` | no | unchanged either way |
| `benchmarks/agreement_matrix.py` | comment only (adversary rows carry 0) | no | n/a |

Board path (separate data; honest, NOT affected by this bug):
`workflows/build.py:62` writes `fix_attempts=r.attempts` (TaskResult.attempts
== true n, once per task) -> `board/store.py:480-492` SUMs per-task values ->
`operator/tools.py:163,196` displays. No inflation; out of scope.

Findings (not drive-bys, per constraints): `summary.py` rows and the
calibration label consume the same counter with ruled/pinned semantics that
are NOT summation — no defect there. No other consumer sums the counter.

## Proposed Remediation

**Preferred — Direction A (aggregate-side; benchmark-owner ruling requested
at the CAUSE GATE):** in `heatmap.py`, stop summing the running counter
record-by-record. Group code records by `(run_id, task_id)` (plus the cell
key `(case_id, stage)`), take `max(fix_attempts)` per group (== final-record
value == n-1, monotonicity verified above), and sum the group maxima into
the cell. Records WITHOUT `task_id` pass through per-record as today:
the running-counter identity is the task loop, and the only nonzero
producer always stamps `task_id` (`code/step.py:785`), so a task_id-less
record cannot be part of a loop — this also keeps every existing synthetic
fixture (which never sets task_id) byte-stable.

- **Baseline effect:** recomputes ALL recorded history honestly, downward,
  to n-1 per (run, task). No producer change; recorded JSONL untouched.
- **Blast radius:** `heatmap.py` + tests only. Calibration (OQ9(2)),
  sc_rollup, aggregate_benchmarks, export, trace events, board — all
  unchanged.
- **E-77 interplay / FR-016:** the fail_reentry pass (:103-119) is a
  separate additive axis (once per (run_id, activation_id)) and cannot
  double-count the handler axis (the fix loop runs WITHIN one activation;
  re-entry is a router-level event). Handler counting convention unchanged.
  FR-016 holds.
- **Tooltip wording** (`heatmap.py:170-174` "fix-attempts"): stays honest —
  the cell then reads "total fix attempts across task loops", which is what
  a reader expects.

**Alternative — Direction B (stamp-side):** change the producer so only the
final record (or a 0/1-per-repair flag) carries the count. REJECTED as
recommendation: recorded baselines stay inflated (the symptom explicitly
complains history re-aggregates wrong); it breaks
`aggregate_benchmarks.py:206`'s max convention (reads 1, not n-1); and it
silently changes the ruled calibration label population
(`labels.py:65-67`: "Each ATTEMPT emits its own row, so the mean is over
attempts"). Blast radius far exceeds the heatmap — contrary to the card's
scope.

**Other (rejected):** stamping the true total n-1 on every intermediate
record is impossible at stamp time (n is unknown until the loop ends) and
would require mutating recorded artifacts.

**Files likely to change (Direction A):**
- `src/sdlc/benchmarks/heatmap.py` (aggregation loop only)
- `tests/test_benchmark_heatmap.py` (new tests; pin updates if any)

**Tests to add or update:**
- RED regression: n=4 same-(run,task) monotone counter -> cell == 3 (not 6);
  n=3 -> 2.
- Cross-run isolation: same task_id in two run_ids groups contributes
  max(group1) + max(group2), never merged.
- task_id-less records pass through per-record (pin-keeper).
- Existing pins re-checked: with the pass-through rule, `:258`
  (byte-identity) and `:332` survive untouched (fixtures carry no task_id);
  `:158-184` unknown-bucket pin survives (no task_id); `:283`/`:318` are
  relational and survive. If the ruling instead merges task_id-less records
  into one group, `:158`'s `fix_attempts == 5  # 2 + 3` moves to 3 with a
  rationale note — direction ruling decides.
- fail_reentry pass still adds exactly +1 per re-entered activation on top
  of the repaired handler axis (no double-count).

## Risks & Considerations

- Recorded heatmap baselines move DOWNWARD for all history — that is the
  point, but any consumer comparing old generated heatmap.json against
  regenerated ones sees diffs (generated artifacts are exempt from review
  pinning; noted for the benchmark owner).
- `density` values shrink accordingly; `max_density` and cell colors shift.
- The group rule must document WHY run_id is in the key (task ids repeat
  across runs; sc_rollup precedent) or a future edit will "simplify" it into
  a task-id-only key and merge reruns.
- Unit tests only; pure aggregation; no e2e, no Temporal, no graph/, no
  store.py (per constraints).

## Open Questions

- [CAUSE GATE — needs orchestrator ruling] Direction A (aggregate-side max
  per (run_id, task_id), recommended) vs Direction B (stamp-side) vs other.
  This changes how recorded baselines re-aggregate and is the benchmark
  owner's call per E77-OQ-1.
- [CAUSE GATE — sub-ruling within A] treatment of records with
  `fix_attempts > 0` but no `task_id`: per-record pass-through (recommended;
  no real producer emits them; keeps all pins byte-stable) vs folding them
  into a `(run, None)` group (moves the `:158` pin 5 -> 3).
