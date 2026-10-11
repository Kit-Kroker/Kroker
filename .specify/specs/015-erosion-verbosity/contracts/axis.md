# Contract — the erosion-verbosity axis (round 015)

Behavioural clauses. Each numbered clause is testable and carries its
proof. `B/` = `src/sdlc/benchmarks/`. The spec is
[spec.md](../spec.md); names live in [data-model.md](../data-model.md).

## §1 Definitions

1. **Erosion** of a run = Σ mass(f) over functions with CC(f) > 10,
   divided by Σ mass(f) over all functions of the run's measured files,
   where mass(f) = CC(f) × sqrt(SLOC(f)), CC is radon's cyclomatic
   complexity and SLOC(f) = end_lineno − lineno + 1. No functions →
   n/a (reason `no functions`), never 0.
2. **Verbosity** of a run = flagged lines / LOC over the measured
   files. Flagged lines = the union of the line spans of nodes matched
   by the pinned rule set (data-model §4). LOC = non-blank lines.
   Cloned lines are not united in (GATE 1 R1); the difference from the
   source benchmark's definition is stated in `BENCHMARK.md`.
3. **Measured files** = `*.py` paths in
   `git diff --name-only <base_branch>...HEAD` at the integration
   branch head, final state (research R-2). Nothing else is measured;
   the whole tree is never reported.

## §2 The writer (run end)

1. For every cell that started, the workflow calls the measurement
   activity after the cell record, under the `015-quality-axis` patch;
   a cell rejected before it starts writes no axis record, as at base.
2. The activity is fail-safe: it never raises; every failure path
   returns a bag with a §-data-model writer reason. A measurement
   failure does not fail the run, the grade, or any other record
   (FR-006).
3. Preconditions, in order, each short-circuiting with its reason:
   code stage not finished → no checkout; language ≠ `python` → no
   checkout (covers language not recorded); worktree add fails →
   `integration branch absent`; diff has no `*.py` →
   `no python files in diff`.
4. The record is written through the existing recorder into the cell's
   `records.jsonl`; no new file or directory appears in the bench dir.
5. The bag carries the branch head, the rule-set version, the tool
   versions, and the audit counts (data-model §1). Two measurements of
   one tree under one tool set produce identical figures (FR-005).
6. The measurement needs no network; the worktree is removed in a
   `finally`.

## §3 The reader

1. A run's axis is its last AXIS-scope record's bag; no such record →
   not measured, reason `no axis record`. A run never has its axis
   recomputed (FR-013).
2. Absence renders as `n/m(<reason>)` on the row and enters no mean,
   rate, colour or count except the not-measured count (FR-009).
3. Group means are over measured runs of one rule-set version; mixed
   versions withhold the means and name the versions (FR-010). Means
   over fewer than five measured runs render grey with their count
   (FR-014).
4. The totals line gains exactly one clause:
   `axis: <measured> measured, <not measured> not measured`. No other
   line of the totals changes.
5. The two figures appear in the grid row (after the code-score
   columns), the group header, and `grid.json`; nowhere else. In
   particular: no `## Stages` row, no heatmap layer, no composite
   weight, no gate-oracle count, no quality column, no
   partial-credit figure, in text, HTML or JSON (FR-011).
6. `sdlc benchmark score` needs no worker, server, network, git, radon
   or ast-grep (FR-013, FR-046 carry-over).

## §4 Stored corpus

1. Every stored run reads not measured (`no axis record`); the
   not-measured count equals runs started for every stored case
   (SC-003).
2. Every figure recorded in round 013's verification.md §2 reproduces
   unchanged, the totals clause added (FR-015).
3. The stored records fingerprint (013 baseline tool) is byte-identical
   before and after every command this round runs against the corpus.
   The smoke run writes only its own new bench directory.

## §5 Dependencies

1. `radon==6.0.1` and `ast-grep-py==0.50.0` are pinned runtime
   dependencies; `uv.lock` is regenerated once, in the round's first
   source task, never touched after (GATE 2 item).
2. Both import on the container's Python 3.13 — proven in the baseline
   before any code depends on them (research R-8).

## §6 The smoke run (live proof)

1. One todo-api-greenfield run per the launch runbook: dedicated
   temporal server, clean worktree, dedicated scratch repo, never
   parallel with live pipeline runs; launched only on the
   orchestrator's go (SG-4).
2. Acceptance: the bench dir has one axis record per cell with figures
   (erosion and verbosity not None); the score shows them on the rows
   and in the group header with tool identifications on the record;
   oracle and code figures match the case's known envelope; the run's
   opencode waste counters are non-zero (013's parser follow-up
   closed live).
3. The run's verification lands in `verification.md` as an addendum
   with the bench run id.

## §7 Clause-to-proof map

| Clause | Proof |
|---|---|
| §1.1-1.3 | `tests/test_benchmark_axis.py` on fixture trees with hand-computed mass/lines |
| §2.1-2.3 | `tests/test_benchmark_workflow_sequence.py` (stubbed activity; lost run, non-python, absent branch) |
| §2.4 | sequence test asserts the record lands in the cell's jsonl |
| §2.5 | measure the same fixture twice, compare figures (SC-002) |
| §2.6 | the axis test runs with no network stub and passes |
| §3.1-3.4 | `tests/test_benchmark_runs.py`, `test_benchmark_grid.py`, `test_benchmark_report.py` |
| §3.5 | `tests/test_benchmark_score.py` asserts grid.json carries the axis and no other output mentions it |
| §4.1-4.3 | `tests/test_benchmark_stored_scores.py` new rows + the fingerprint check |
| §5.2 | baseline.md |
| §6 | verification.md addendum with the bench run id |
