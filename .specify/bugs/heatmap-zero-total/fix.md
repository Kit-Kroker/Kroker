# Bug Fix: heatmap oracle rendering crashes on 0/0 marks

- **Slug**: heatmap-zero-total
- **Fixed**: 2026-10-18
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`_marks_td` divided `m.passed / m.total` unconditionally, so one legitimate
`0/0` oracle mark (a graded run whose oracle suite collected no tests) crashed
`render_heatmap_html` and with it the whole `finalize_benchmark_report`
activity. A `total == 0` mark now renders `<span class="hm-none">0/0</span>` —
a grey no-step class, the `0/0` figure kept — exactly as cleared at the cause
gate.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/sdlc/benchmarks/heatmap_render.py` | modified | `_marks_td` now renders via `_mark_span`; `total == 0` → grey `hm-none` span, no division; `total > 0` path byte-identical to before. `.hm-none` CSS rule (same grey as `.hm-low`) added to the stylesheet. Reason on record in the `_mark_span` comment. |
| `.specify/specs/013-benchmark-scoring-output/contracts/scoring-output.md` | modified | §4.3 clause extended: a `total == 0` mark keeps the `0/0` figure and takes the grey `hm-none` class, no step (artifact-boundary rule: clause updated in the same diff). |
| `tests/test_benchmark_heatmap_render.py` | added tests | 7 tests by the qa seats (see below); no pre-existing test edited or weakened. |

## Diff Highlights

```python
def _mark_span(m: OracleMark) -> str:
    # total == 0: the oracle suite collected no tests, so no ratio exists
    # (`Run.partial_credit` is None for total <= 0) — the mark takes no
    # colour step (steps classify values; 0/0 is valueless) and renders
    # grey like the other unstep-able cells, the figure kept.
    if m.total == 0:
        return f'<span class="hm-none">{m.passed}/{m.total}</span>'
    return f'<span class="hm-s{step_for("oracle", m.passed / m.total)}">{m.passed}/{m.total}</span>'
```

```css
.hm-low{background:hsl(0,0%,87%);color:#555}
.hm-none{background:hsl(0,0%,87%);color:#555}
```

## Tests Added or Updated

Written RED-first by the qa seats (verified RED at `heatmap_render.py:77`
ZeroDivisionError before the fix, by the seats and independently by the bug
lead):

- `test_html_oracle_mark_zero_total_takes_the_grey_no_step_class` — renderer
  level (`_marks_td` + `render_heatmap_html`): 0/0 mark does not crash,
  renders the exact `hm-none` span.
- `test_html_zero_total_oracle_mark_from_records_renders_grey_without_crashing`
  — path level: records with oracle components `{"passed": 0, "total": 0}` →
  `build_runs` → `build_layers` → render, grey span, no crash.
- `test_html_valued_mark_keeps_its_step_class_beside_a_zero_total_mark` —
  neighbour pin: `3/4` keeps `hm-s2` beside a `0/0`.
- `test_html_row_of_only_zero_marks_renders_every_mark` — a row whose every
  mark is 0/0 renders both `hm-none` spans.
- `test_stylesheet_gains_hm_none_and_keeps_the_old_rules` — `.hm-none{`
  exists; `.hm-low{` / `.hm-s0{` survive.
- `test_render_heatmap_json_keeps_the_zero_total_mark` — guard pin (`# PIN:`):
  the JSON data layer keeps the 0/0 mark untouched.
- `test_html_zero_total_mark_render_keeps_empty_cells` — `hm-empty` cells
  unaffected by the fix.

## Local Verification

- Commands run:
  - `uv run pytest tests/test_benchmark_heatmap_render.py` → RED before fix
    (6 failed, 20 passed, failures at `heatmap_render.py:77`
    ZeroDivisionError / missing `.hm-none{` rule); **26 passed** after.
  - `uv run pytest tests/test_benchmark_report.py tests/test_benchmark_score.py`
    → 52 passed.
  - `uv run pytest tests/test_benchmark_heatmap.py` → 25 passed.
  - `ruff check` / `ruff format --check` on both changed code files → clean.
  - `mypy src/sdlc/benchmarks/heatmap_render.py` → no issues.
- Manual checks: valued-mark output path is unchanged (`step_for("oracle",
  m.passed / m.total)` only reached when `total > 0`); `render_heatmap_json`
  and the grid printer were never dividing and are untouched.

## Deviations from Assessment

None. The preferred remediation was applied as written (class name `hm-none`
as approved at the cause gate). One addition beyond the assessment's file
list: the 013 contract clause §4.3 (`scoring-output.md`) — the AGENTS.md
artifact-boundary rule ("code without a clause is a defect") requires the
clause to travel with the behaviour change.

## Follow-ups

- None required. (Env note, not a code follow-up: the checkout's `.venv` was
  a stale WSL venv that blocked `uv run` on Windows; rebuilt with
  `uv sync --frozen --extra dev --python 3.13`.)
