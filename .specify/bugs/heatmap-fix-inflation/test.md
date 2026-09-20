# Bug Verification: heatmap fix-attempts inflate quadratically (n(n-1)/2 instead of n-1)

- **Slug**: heatmap-fix-inflation
- **Tested**: 2026-09-20
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The assessment's unit-level reproduction (n-attempt ladder records for one
(run_id, task_id)) now yields exactly n-1 fix attempts for every probed n;
the RED regression suite (12 tests) and GREEN guards (3) all pass, the full
fast tier is green, and all static gates pass. No regressions found.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | one-off `build_heatmap` script over producer-shaped ladders, n=3/4/5 | pass | n=3 -> 2, n=4 -> 3, n=5 -> 4 (previously 3/6/10); density deflates accordingly |
| Reproduction (pre-fix, RED) | `pytest tests\test_benchmark_heatmap.py tests\test_benchmark_heatmap_fix_inflation.py -q` on pre-fix tree | pass (12 assertion failures, independently re-verified by bug-lead) | symptom reproduced as failing tests, value mismatches only, no errors |
| New / updated tests | `.\.venv\Scripts\python.exe -m pytest tests\test_benchmark_heatmap.py tests\test_benchmark_heatmap_fix_inflation.py tests\test_benchmark_heatmap_render.py tests\test_benchmark_sc_rollup.py tests\test_benchmark_agreement_matrix.py tests\test_benchmark_cli.py -q` | pass | EXIT=0, 72 dots [100%] |
| Regression suite (full fast tier) | `.\.venv\Scripts\python.exe -m pytest -q` | pass | EXIT=0, [100%], 0 FAILED/ERROR lines; pre-existing unrelated UnicodeDecodeError thread warning in tests/replay/ unchanged |
| Pins byte-identical (ruling condition) | `test_current_records_render_byte_identical_to_the_pinned_literal` (:258), `test_fail_reentry_none_everywhere_is_byte_identical_to_no_graph` (:332), unknown-bucket (:158) | pass | all survived untouched — ruling condition met, no flow stop needed |
| Lint | `uv run --frozen ruff check .` | pass | All checks passed |
| Format | `uv run --frozen ruff format --check .` | pass | 1429 files already formatted |
| Type-check | `uv run --frozen mypy` | pass | Success: no issues found in 375 source files |
| File-size ceiling | `uv run --frozen python scripts/check_file_size.py` | pass | exit 0 |

## Output Excerpts

Post-fix reproduction (one-off script):

```
n=3: fix_attempts=2 (intended n-1=2; buggy n(n-1)/2=3) density=2.0
n=4: fix_attempts=3 (intended n-1=3; buggy n(n-1)/2=6) density=3.0
n=5: fix_attempts=4 (intended n-1=4; buggy n(n-1)/2=10) density=4.0
REPRODUCTION_POST_FIX: PASS
```

Pre-fix RED (representative, bug-lead-verified):

```
AssertionError: assert 6 == 3
 +  where 6 = HeatmapCell(case='c1', stage='code', gate_rejects=3,
    fix_attempts=6, oracle_fails=0, n_runs=1, density=9.0).fix_attempts
```

## Residual Risks

- Recorded heatmap baselines re-aggregate downward on the next report
  regeneration — intended (Direction A ruling), but any dashboard consumer
  diffing regenerated heatmaps against archived ones will see the deflation.
- The aggregation is honest only as long as the producer keeps the counter
  monotone per (run_id, task_id); the fix is defensive anyway (max, not
  last-record-wins), so non-monotone history degrades to the group max
  rather than an inflated sum.
- Live benchmark regeneration (finalize activity over real recorded
  history) was not exercised — out of scope by ruling (unit tests only, no
  e2e); the pure-aggregation seam makes the one-off script equivalent.

## Recommendation

Close the bug — verified end-to-end at the unit seam the assessment
defined. Tick E77-OQ-1 (spec.md:273) and research.md R-12's "Not changed"
note as delivered follow-ups.
