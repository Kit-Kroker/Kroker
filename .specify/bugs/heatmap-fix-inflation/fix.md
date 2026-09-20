# Bug Fix: heatmap fix-attempts inflate quadratically (n(n-1)/2 instead of n-1)

- **Slug**: heatmap-fix-inflation
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`build_heatmap` no longer sums the per-record `fix_attempts` running
counter. Each `(case_id, stage, run_id, task_id)` group now contributes its
MAX (the task's final-record count, n-1), group maxima sum into the cell,
and task_id-less records pass through per-record — the orchestrator-ruled
Direction A with the per-record passthrough sub-ruling. Producer and every
other consumer untouched.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/sdlc/benchmarks/heatmap.py` | modified | fix axis: group-max aggregation + rationale comment (run_id load-bearing; sc_rollup precedent) |
| `tests/test_benchmark_heatmap.py` | added test section (+7) | qa-happy; core ruled semantics; `_rec` helper gained optional `task_id`/`attempt` params, defaults preserve all existing call sites |
| `tests/test_benchmark_heatmap_fix_inflation.py` | new file (8 tests) | qa-chaos; adversarial edges + GREEN guards for the sub-rulings |

## Diff Highlights

```python
# before (heatmap.py:101)
acc[key]["fix"] += r.fix_attempts

# after
if r.task_id is not None:
    group = (r.case_id, stage, r.run_id, r.task_id)
    if r.fix_attempts > fix_group_max.get(group, 0):
        fix_group_max[group] = r.fix_attempts
elif r.fix_attempts:
    acc[key]["fix"] += r.fix_attempts
# ... then, once per group:
for (case, stage, _run_id, _task_id), group_max in fix_group_max.items():
    acc[(case, stage)]["fix"] += group_max
```

The in-code comment documents WHY run_id is in the key (task ids are
plan-scoped and repeat across runs of a case; a task-id-only key would
merge reruns' loops and undercount; `sc_rollup.py` groups identically) —
the ruling's binding condition against future "simplification".

## Tests Added or Updated

`tests/test_benchmark_heatmap.py` (qa-happy, RED-verified then green):
- `test_fix_axis_counts_n_minus_one_for_a_task_needing_four_attempts` — n=4 -> 3, not 6
- `test_fix_axis_counts_n_minus_one_for_a_task_needing_three_attempts` — n=3 -> 2, not 3
- `test_fix_axis_groups_by_run_id_because_task_ids_repeat_across_runs` — two runs of T01 -> 2+2=4, not 6
- `test_fix_axis_sums_group_maxima_across_tasks_in_one_run` — T01+T02 -> 2+1=3, not a cell-wide max
- `test_adjacent_zero_fix_qa_records_leave_the_code_cell_untouched` — qa rows never interfere
- `test_fix_axis_deflation_leaves_gate_runs_and_density_formula_unchanged` — only the fix axis moved; density recomputes
- `test_fail_reentry_pass_stays_additive_on_top_of_the_grouped_max` — FR-016/FR-017 interplay, no double-count

`tests/test_benchmark_heatmap_fix_inflation.py` (qa-chaos):
- `test_taskless_records_pass_through_per_record_not_grouped` — GREEN guard, sub-ruling
- `test_taskless_and_task_groups_in_one_run_stay_separate` — None-identity never merges
- `test_non_monotone_group_maxes_rather_than_sums` — max wins over garbage; idempotent on duplicates
- `test_missing_attempt_field_does_not_break_group_max` — grouping keys on task identity, not `attempt`
- `test_cell_values_are_order_independent` — GREEN guard, aggregation is multiset-functional
- `test_fail_reentry_adds_one_beside_the_group_max` — once-per-activation +1 on top of the grouped max
- `test_oracle_task_records_stay_excluded_with_task_identity` — GREEN guard, scope exclusion survives task grouping
- `test_density_reports_honest_fix_units_per_run` — density deflates with the fix axis

## Local Verification

- RED (pre-fix, independently re-verified by bug-lead):
  `.\.venv\Scripts\python.exe -m pytest tests\test_benchmark_heatmap.py tests\test_benchmark_heatmap_fix_inflation.py -q`
  -> 12 failed, ALL assertion value-mismatches (6≠3, 3≠2, 6≠4, 4≠3, 7≠6,
  8≠5, densities 7.0/9.0), 15 passed (12 pre-existing pins + 3 GREEN guards).
- GREEN (post-fix): same command + `tests\test_benchmark_heatmap_render.py`
  -> 32 passed. Pins `:258`/`:332` byte-identity and `:158` unknown-bucket
  survived untouched (ruling condition met).
- Full fast tier: `pytest -q` -> exit 0, all dots, no FAILED lines
  (pre-existing unrelated UnicodeDecodeError thread warning in
  tests/replay/test_feature_replay.py, present before this change).
- Static gates (`uv run --frozen`): `ruff check .` All checks passed;
  `ruff format --check .` 1428 files already formatted; `mypy` Success: no
  issues found in 375 source files; `scripts/check_file_size.py` exit 0.
- No uv.lock change.

## Deviations from Assessment

None. Implemented exactly the assessment's Preferred remediation
(Direction A + task_id-less per-record passthrough) as cleared at the
cause gate.

## Follow-ups

- Recorded heatmap baselines re-aggregate DOWNWARD on next report
  regeneration — expected, that is the point; generated artifacts are
  exempt from pinning.
- E77-OQ-1 card (`.specify/specs/001-canonical-stage-graph-sha/spec.md:273`)
  and research.md R-12's "Not changed" note now have their named follow-up
  delivered; the benchmark owner may want to tick them.
- `heatmap.py:19-22` header comment still says retry volume "belongs to
  code/qa" while qa records carry fix_attempts=0 — pre-existing wording,
  deliberately not touched (no drive-bys).
