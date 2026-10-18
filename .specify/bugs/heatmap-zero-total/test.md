# Bug Verification: heatmap oracle rendering crashes on 0/0 marks

- **Slug**: heatmap-zero-total
- **Tested**: 2026-10-18
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom no longer reproduces: a `LayeredHeatmap` carrying an
`OracleMark(passed=0, total=0)` renders through `render_heatmap_html` without
crashing, producing `<span class="hm-none">0/0</span>` with the `.hm-none`
grey rule and no step class. All six RED regression tests flipped green, the
named gate suites and the temporal replay tier are green, and the reviewer
seat approved the diff (one FYI, no required findings).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (pre-fix, RED) | probe + `pytest tests/test_benchmark_heatmap_render.py` on unfixed code | pass (RED confirmed) | `ZeroDivisionError: division by zero` at `heatmap_render.py:77`, 6 failed / 20 passed — symptom reproduced as failing tests, verified by the bug lead, not only by the qa seats |
| Reproduction (post-fix) | temp-file probe (assessment's steps) | pass | renders OK; `hm-none` span + CSS rule present; no `hm-s*` class on the mark; old rules `.hm-low{`/`.hm-s0{` intact |
| New / updated tests | `uv run pytest tests/test_benchmark_heatmap_render.py` | pass | 26/26 (7 new: 6 RED→green + 1 guard pin) |
| Brief's named gate set | `uv run pytest tests/test_benchmark_report.py tests/test_benchmark_score.py` | pass | 52/52 |
| Adjacent regression | `uv run pytest tests/test_benchmark_heatmap.py` | pass | 25/25 (layers builder untouched) |
| Lint / format / type | `ruff check`, `ruff format --check`, `mypy` on changed code files | pass | clean |
| Temporal replay (final gate) | `uv run pytest -m temporal tests/replay` | pass | `33 passed, 21 skipped, 187 deselected` in 58.99s — untouched-green |
| Reviewer gate | five-axis review of the working-tree diff | approve | 1 FYI only (see Residual Risks) |

## Output Excerpts

```
tests/...  26 passed          (renderer, post-fix)
tests/...  103 passed in 8.00s  (renderer + report + score + layers)
ruff check: All checks passed!   format: 2 files already formatted
mypy: Success: no issues found in 1 source file
33 passed, 21 skipped, 187 deselected in 58.99s   (temporal replay)
```

## Residual Risks

- Corrupt evidence (`passed > 0, total == 0`) renders `<span class="hm-none">3/0</span>`
  — grey, no crash, no step; honest display of the stored figures (reviewer
  FYI, no action). The §4.3 clause words the rule for the legitimate `0/0`
  shape; the implementation prints the actual figures.
- The env repair on this checkout (`.venv` was a stale WSL venv; rebuilt with
  `uv sync --frozen --extra dev --python 3.13`) is outside the diff but worth
  knowing when reproducing locally on Windows.
- The smoke run `bench-todo-api-greenfield-1792324584` itself was not re-run
  (token-spending tier); the reproduction is the in-process evidence-level
  probe plus the path-level test (`records → build_runs → build_layers →
  render`), which exercises the same code path the activity takes
  (`finalize_benchmark_report → write_score → write_heatmap →
  render_heatmap_html`).

## Recommendation

Close the bug — verified end-to-end at the evidence-render level, reviewer
approved, all gates green. Integrate `bug/heatmap-zero-total` into main.
