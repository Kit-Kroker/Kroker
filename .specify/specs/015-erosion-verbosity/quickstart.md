# Quickstart — round 015 erosion and verbosity

Validation guide. One command per shell call; Python in the
`kroker-dev` container (host repo venv only where the exec brief
sanctions it); git on worktrees runs on the host.

## §1 Automated gates

| Row | Command (container, `uv run ...`) |
|---|---|
| 1 | `pytest tests/test_benchmark_axis.py tests/test_benchmark_stored_scores.py` |
| 2 | `pytest tests/test_benchmark_runs.py tests/test_benchmark_grid.py tests/test_benchmark_report.py tests/test_benchmark_score.py tests/test_benchmark_models.py` |
| 3 | `pytest tests/test_benchmark_workflow_sequence.py` (temporal tier: `pytest -m temporal tests/test_benchmark_workflow_sequence.py`) |
| 4 | `pytest tests/test_judge_literal.py tests/test_benchmark_scoring.py tests/test_benchmark_heatmap.py tests/test_benchmark_heatmap_render.py` |
| 5 | full fast tier: `pytest` |
| 6 | `pytest -m temporal tests/replay` then `pytest -m temporal tests/test_benchmark_workflow_sequence.py` |
| 7 | `ruff check .` ; `ruff format --check .` ; `mypy` |
| 8 | host: `python scripts/check_file_size.py` ; `python scripts/check_clauses.py` (always exits 0 — read it) |

Expectations: rows 1-4 green; row 5 differs from the baseline only by
this round's tests; row 6 identical to baseline (no BenchmarkWorkflow
history exists in the replay suite — the sequence test is the
workflow's cover); row 7 clean; row 8 no new clause-without-test line.

## §2 The score on the stored corpus (read-only)

Scores are written with `--out` to a directory outside `runs/`.

1. `sdlc benchmark score --case cat-cafe-monitoring --out <dir>`
   - totals line: the 013 figures unchanged, plus the clause
     `axis: 0 measured, 18 not measured`.
   - every run row: `n/m(no record)` in both axis columns; no group
     axis mean anywhere.
2. `sdlc benchmark score --case todo-api-greenfield --out <dir>` —
   same, with that case's 013 figures unchanged.
3. `sdlc benchmark score --out <dir>` (all): the clause holds per
   selection; wall time under one minute still (013 SC-012).
4. Host, after §2: the records fingerprint equals the baseline's;
   `git ls-files runs/` prints nothing.

## §3 Determinism and fixture proofs

1. `pytest tests/test_benchmark_axis.py -k determinism` — one fixture
   tree measured twice, figures identical (SC-002).
2. The mass-split fixture (half the complexity mass above threshold)
   reads erosion exactly 0.50; the slop fixture's verbosity equals its
   hand-counted flagged/non-blank ratio (SC-001).
3. The measurement of a case-sized fixture tree completes in under
   30 s (SC-005).

## §4 The smoke run (live proof; SG-4 — orchestrator's go first)

Per the benchmark launch runbook; never parallel with live pipeline
runs.

1. Dedicated temporal server (port 7234), clean worktree of the
   branch, dedicated scratch repo.
2. Launch `todo-api-greenfield` (one cell is enough; the case's usual
   arm).
3. After the run: the bench dir's cell `records.jsonl` contains one
   axis record with figures; `sdlc benchmark score --bench <id>` shows
   them on the row and in the group header; the record's `tools` and
   `ruleset_version` are populated.
4. The same run's opencode waste counters are non-zero (013 follow-up
   closed live).
5. Record the bench run id and the figures in `verification.md`'s
   addendum (SC-006).
