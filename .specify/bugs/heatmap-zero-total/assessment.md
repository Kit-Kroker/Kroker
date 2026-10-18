# Bug Assessment: ZeroDivisionError in heatmap oracle rendering kills report finalization

- **Slug**: heatmap-zero-total
- **Created**: 2026-10-18
- **Source**: pasted text (orchestrator TASK BRIEF; probe-proven stack for bench run `bench-todo-api-greenfield-1792324584`, main `4bcfe74a`)
- **Verdict**: valid (reproduced in-process on main `4bcfe74a`)
- **Severity**: high

## Report (verbatim, condensed)

> `finalize_benchmark_report` dies with `ZeroDivisionError` on a completed smoke run
> (`bench-todo-api-greenfield-1792324584`, main `4bcfe74a`). Probe-proven stack:
> `src/sdlc/benchmarks/heatmap_render.py` line 76-77, `_marks_td` computes
> `m.passed / m.total` and the run's evidence contains an oracle mark with
> `total == 0` (0 tests collected for that cell) — division by zero, the whole
> report finalization activity fails and the outer `BenchmarkWorkflow` fails
> after the pipeline itself completed.

## Symptom

A benchmark run whose evidence contains a graded run with an oracle grade of
`0/0` (oracle suite collected no tests) crashes report finalization with
`ZeroDivisionError`; the whole `BenchmarkWorkflow` fails after all pipeline
cells already completed, and no report artifacts are written for the run.
Expected: the renderer treats `0/0` as a valueless mark (grey, no colour step,
`0/0` text kept) and finalization completes.

## Reproduction

Verified in code and reproduced in-process (no files modified):

1. A graded run's oracle components come from `_oracle_components`
   (`src/sdlc/benchmarks/runs.py:223-236`): the last oracle-scope record's
   `quality.components` `passed`/`total`. Components `{"passed": 0, "total": 0}`
   yield `(0, 0)` — both non-`None`, so `Run.oracle_passed=0, oracle_total=0`.
2. `Run.partial_credit` (`runs.py:95-96`) and `all_pass` (`runs.py:104`)
   already treat `oracle_total <= 0` as a legitimate, guarded shape
   (no ratio, not all-pass). The model layer is not surprised by `0/0`.
3. `build_layers` (`src/sdlc/benchmarks/heatmap.py:313-322`) emits an
   `OracleMark(passed=0, total=0)` for every graded member with both fields
   non-`None` — including `0/0`.
4. `_marks_td` (`src/sdlc/benchmarks/heatmap_render.py:76-77`) computes
   `m.passed / m.total` unconditionally → `ZeroDivisionError`.
5. Propagation: `render_heatmap_html` ← `write_heatmap`
   (`src/sdlc/benchmarks/report.py:317-331`, invoked at
   `src/sdlc/benchmarks/score.py:130`) ← `write_score` ←
   `finalize_benchmark_report` (`report.py:335-345`) ← `BenchmarkWorkflow`
   (`src/sdlc/benchmarks/workflow.py:506-508`). The activity exception fails
   the workflow after the pipeline completed.

Probe (CPython 3.13, repo venv): constructing `LayeredHeatmap` with one
`OracleMark(passed=0, total=0)` and calling `_marks_td` /
`render_heatmap_html` raises `ZeroDivisionError: division by zero` at both
levels.

The only dividing site is `_marks_td` line 77: `render_heatmap_json`
(`heatmap.py:431-434`) is pure serialization and the grid printer
(`src/sdlc/benchmarks/grid.py:353-354`) formats `passed/total` without
dividing. Earlier smokes never hit it only because every prior graded run had
`total > 0`.

## Suspected Code Paths

- `src/sdlc/benchmarks/heatmap_render.py:73-80` — `_marks_td`, the
  unconditional `m.passed / m.total`; the defect.
- `src/sdlc/benchmarks/heatmap.py:313-322` — mark emission (correct; `0/0` is
  a legitimate evidence shape, see `runs.py:95-96`).
- `src/sdlc/benchmarks/runs.py:223-236` — where `(0, 0)` enters from evidence
  (correct per contract §1.4; components carried, no invention).

## Root Cause Hypothesis

`_marks_td` assumes every `OracleMark` has `total > 0` when computing the
colour step, but `build_layers` legitimately emits `0/0` marks for graded runs
whose oracle suite collected zero tests — a shape the model layer already
guards for (`Run.partial_credit` returns `None` for `total <= 0`). The renderer
is the only consumer that divides unguarded, so one `0/0` mark in the evidence
crashes the entire report finalization activity and, with it, the otherwise
completed `BenchmarkWorkflow`. Confidence: **high** (probe-reproduced; every
link in the chain read in code).

## Proposed Remediation

**Preferred**: make `_marks_td` total-aware. When `m.total == 0`, emit
`<span class="hm-none">0/0</span>` — a grey, no-step class styled like the
existing `hm-low` grey (`background:hsl(0,0%,87%);color:#555`), keeping the
`0/0` text. When `total > 0`, behaviour is byte-identical to today
(`step_for("oracle", passed/total)`). Add the `.hm-none` CSS rule next to
`.hm-low` in `render_heatmap_html`'s stylesheet. Reason on record (doc comment
on `_marks_td` and in the fix report): `0/0` means *no oracle tests collected*
— no ratio exists (`Run.partial_credit` is `None`), so it takes no colour step
(SC-007: steps classify values; `0/0` is valueless) and renders grey like
other unstep-able cells. No change to evidence loading, `build_layers`,
scoring figures, or `render_heatmap_json`.

**Alternatives** (rejected):
- Treat `0/0` as 0% → `hm-s4`. Rejected: zero tests collected is not a 0%
  pass rate; it would visually equate a collection failure with a fully
  failing suite and violate the valueless-mark semantics the model layer
  already encodes.
- Drop `0/0` marks in `build_layers`. Rejected: hides legitimate evidence
  (a graded run with an empty oracle collection) from the report and changes
  the data model rather than the rendering defect.

**Files likely to change**:
- `src/sdlc/benchmarks/heatmap_render.py` (`_marks_td` + one CSS rule)
- `tests/test_benchmark_heatmap_render.py` (RED regression tests)

**Tests to add or update** (RED contract first — symptom must reproduce as a
failing test before the fix):
- Renderer-level: feed a mark with `total=0` through `_marks_td` /
  `render_heatmap_html`; assert no crash and the chosen rendering
  (`<span class="hm-none">0/0</span>` present, no `hm-s*` class on it).
- Path-level: build from records — a graded run whose oracle record carries
  `components={"passed": 0, "total": 0}` flows through `build_runs` /
  `build_layers` / `render_heatmap_html` without crashing and shows the grey
  mark. Note: the `_oracle` test helper (`tests/test_benchmark_heatmap_render.py:82-95`)
  itself computes `passed / total` for `score`, so the `0/0` record must be
  built via `_record(...)` with an explicit `QualityScore` (or the helper
  guarded); mind this in the RED phase.
- Neighbour pins: a `total > 0` mark still renders its step class (already
  pinned by `test_html_oracle_mark_prints_passed_total`) and `heatmap.json`
  output is unchanged for the same input.

## Risks & Considerations

- Severity rationale (high): any bench run containing one `0/0` oracle mark
  loses *all* report artifacts (`report.md`, grid, heatmap, gate-oracle,
  sc-rollup, matrices) and the workflow ends failed after the pipeline
  succeeded; evidence itself is intact (re-running the score writer after the
  fix recovers the report), so no data loss — reporting-layer regression only.
- Styling addition must not disturb existing class names (`hm-s0..4`, `hm-low`,
  `hm-empty`); `hm-none` is new and additive.
- SC-007 stays intact: `0/0` deterministically renders `hm-none` in any
  report; valued marks are untouched.
- File ceiling: `heatmap_render.py` is 147 lines; the fix adds ~4. No ceiling
  risk.
- Test-env note: `.venv` in this checkout was a stale WSL-created venv that
  blocked `uv run` on Windows; rebuilt with `uv sync --frozen --extra dev
  --python 3.13` (3.14 has no Windows wheel for `pydantic-monty-client`, per
  AGENTS.md). Recorded here so the reviewer isn't surprised by the new venv.

## Open Questions

- None blocking. The class name `hm-none` is the preferred choice within the
  brief's "grey/no-step class" envelope; orchestrator may veto at the cause
  gate before the fix lands.
