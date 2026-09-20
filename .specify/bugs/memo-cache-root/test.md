# Bug Verification: machine-global memo cache root breaks run hermeticity

- **Slug**: memo-cache-root
- **Tested**: 2026-09-20
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The assessment's live reproduction no longer reproduces on the fixed tree (checkout B cannot read checkout A's judged entry; B's own rerun still hits), all 11 adopted contract tests pass, the full fast tier passes with no regressions, and the DD10 binding constraint is green. No deviations from the ruled scope.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (pre-fix, baseline) | probe script (two non-repo CWDs, default root, identical `risk_key`) | reproduced | `B sees A's entry: True`, root `...\Temp\sdlc\memo_cache` (machine-global) |
| Reproduction (post-fix) | same probe, unchanged | **pass** | `B sees A's entry: False`; `B sees own entry on rerun: True`; root `...\memo_cache\23a3d066ba5db288` (namespaced) — verdict `NOT_REPRODUCED` |
| Adopted contract tests | `.venv\Scripts\python.exe -m pytest tests/test_memoization_cache_root.py tests/test_memoization_cache_root_chaos.py -q --no-header` | pass | 11 passed (RED-verified pre-fix by qa-happy, qa-chaos, and lead: 8 failed / 3 green-by-design) |
| Regression suite (fast tier) | `pytest` | pass | 5186 passed, 13 skipped, 221 deselected (0:05:09) |
| DD10 (binding constraint) | single test, temporal tier, per-file, 600 s bounded wrapper, temporal-test-server killed before/after | pass | `tests/test_assessment_workflow_e2e.py::test_a_second_assessment_of_the_same_tree_hits_the_memo` → `.[100%]` |
| Lint | `ruff check` + `ruff format --check` (touched files) | pass | clean |
| Type-check | `mypy` | pass | Success: no issues found in 375 source files |

## Output Excerpts

Post-fix probe (the assessment's reproduction, verbatim):

```text
default_root: C:\Users\start\AppData\Local\Temp\sdlc\memo_cache\23a3d066ba5db288
A sees own entry: True
B sees A's entry (DEFECT if True): False
B sees own entry on rerun (DD10 core): True
PROBE_VERDICT: NOT_REPRODUCED
```

Adopted tests post-fix: `...........  [100%]` (11 passed).

## Residual Risks

- Old machine-global entries at `%TEMP%\sdlc\memo_cache\*.json` are now unreachable (stale but inert); optional one-off cleanup, not part of this fix.
- Namespace digests accumulate per checkout path under `%TEMP%`; %TEMP% cleaners already treat this space as ephemeral.
- Cross-checkout memo reuse (uncontracted) is gone by design; anyone who implicitly relied on it gets cold caches per checkout — that is the hermeticity working.

## Recommendation

Close the bug — verified end-to-end: symptom does not reproduce, contract tests pin both directions, regression suite and the DD10 constraint are green, and the change stayed exactly inside the cause-gate ruling.
