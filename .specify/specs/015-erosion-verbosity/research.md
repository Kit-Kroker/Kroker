# Research — round 015 erosion and verbosity

Branch decision input for `plan.md`. Every claim was checked in the tree
at main `c3f6319c` (2026-10-11) unless a source is named. Decisions are
R-1 to R-10; the consult log is at the end.

## Verified in the tree

- **The run's end sequence** (`B/workflow.py`): for each cell — child
  pipeline, then (patched `012-cell-record`) `summarize_cell`, then
  `grade_oracle` when `spec.language is not None and progress.code_finished`,
  then oracle records, then the one cell record; after all cells,
  `finalize_benchmark_report(bench_run_id)`.
- **The integration branch is reachable the way the oracle reaches it**
  (`B/oracle.py:252-277`): `git worktree add --detach <tmp> sdlc/<run_id>/integration`
  from `inp.repo_url`; failure means "no produced code". The branch is
  never deleted by `BenchmarkWorkflow` — it survives until the scratch
  repo is cleaned, so a measurement activity after the cell record can
  use the identical checkout pattern.
- **`grade_oracle` runs only for code-finished cells of oracle cases**
  (`B/workflow.py:359`). Lost runs and language-less cases never reach
  it, so the axis cannot ride inside `grade_oracle` — it would silently
  skip exactly the runs that must read "not measured with reason".
- **`BenchmarkRecord` extension points** (`B/models.py`): scope is a
  `StrEnum` (`CELL` was added by 012 the same way); payload fields ride as
  optional (`cell: CellStatus | None`, `waste: WasteBag | None`) so old
  records still validate; `JudgeKind` is a `Literal` pinned by
  `tests/test_judge_literal.py` (additive edits are that test's to make).
- **A new scope is inert to every existing derivation** (`B/runs.py`):
  `cell_progress` counts only `CELL_STAGE_ORDER` stages; `_task_outcomes`
  filters `stage == "code"`; `_tokens` sums only records that carry
  tokens; `_wall_clock` reads the cell record or stage/attempt scopes;
  the heatmap layers read `Run` fields, not raw records. A record with
  `scope=AXIS, stage="axis"` changes no existing figure.
- **The summary rows exclude new scopes by construction**
  (`B/scoring.py:27`): `_ROW_SCOPES = (STAGE, TASK_ATTEMPT)`; the
  `## Stages` table gains no axis row.
- **`write_score` output set** (`B/score.py:93-151`): report.md, grid.*,
  heatmap.*, gate-oracle.*, sc-rollup.*, per-case matrices. The axis
  rides the grid (row + group header + totals clause) and grid.json —
  no new output file (FR-045).
- **Replay coverage**: no BenchmarkWorkflow history exists under
  `tests/replay/histories/` (feature/graph only). The replay constraint
  on this round is in-flight benchmark runs, and the repository's answer
  to that is the `workflow.patched` seam (`012-cell-record`,
  `B/workflow.py:305,349`) — old runs replay the unpatched branch. The
  workflow is otherwise covered by `tests/test_benchmark_workflow_sequence.py`
  (temporal tier, stubbed activities).
- **Activity registration** (`src/sdlc/worker.py:177-182`): benchmark
  activities are imported and listed explicitly; a new activity is added
  in both places.
- **Tools are absent** from `pyproject.toml`/`uv.lock` (grep for
  radon/ast-grep: no hits).

## Verified externally (2026-10-11)

- **radon** 6.0.1 — MIT, pure Python (`py2.py3-none-any` wheel, sole
  dependency `mando`), programmatic API for cyclomatic complexity
  (PyPI). Classifiers stop at 3.9 (last release 2023-03); it is pure
  Python and widely used on newer interpreters — step 0 must import it
  on the container's 3.13 before anything depends on it (residual, R-8).
- **ast-grep-py** 0.50.0 — MIT, the official ast-grep binding (repo
  `ast-grep/ast-grep`), version-specific wheels cp310–cp314 for Windows
  x86-64 and Linux x86-64/ARM64 (PyPI). Development status "3 - Alpha"
  on PyPI — disclosed at GATE 2; the binding surface this round uses
  (compile a language, apply YAML rules, read match spans) is the
  binding's core.

## Decisions

**R-1 — a separate fail-safe activity, not a ride-along.** New activity
`measure_code_axis(AxisInput) -> AxisBag` in a new `B/axis.py`, called
from `BenchmarkWorkflow` under `workflow.patched("015-quality-axis")`
after the cell record, for every cell that started (rejected cells write
nothing, as at base). It does its own
`git worktree add --detach ... sdlc/<run_id>/integration` (the oracle's
pattern) and never raises: every failure returns a bag with
`reason` set. Rejected alternatives: measuring inside `grade_oracle`
(skips lost runs and language-less cases — the not-measured paths
disappear); measuring in `finalize_benchmark_report` (no repo_url/run_id
on its input, and the branch may already be gone).

**R-2 — the unit is the produced diff, not the whole tree.** Measured
files: `*.py` in `git diff --name-only <base_branch>...HEAD` at the
integration head, final state. Rationale: a run owns its diff; a
whole-tree share would attribute the base repository's complexity to
every run and make greenfield and brownfield cases incomparable. The
record carries the changed-file count. (The spec's "final state of the
integration branch" is honoured: the measured files are the final state
of what the run produced.)

**R-3 — erosion exactly as the source defines it, via radon.**
Per function: CC from `radon.complexity`, SLOC = `end_lineno − lineno + 1`
(radon blocks carry both), `mass = CC × sqrt(SLOC)`;
erosion = mass of functions with CC > 10 over mass of all functions;
`None` (n/a, reason `no functions`) when the measured files contain no
function. The record carries functions_total, functions_over,
mass_total, mass_over so the figure is auditable. Threshold 10 is a
named constant.

**R-4 — verbosity: own rule set, ast-grep-py engine, cloned lines out.**
Ruling R1. Rules are YAML files under
`src/sdlc/benchmarks/rules/verbosity/`, applied by ast-grep-py; a match
flags its whole node span; flagged lines are the union of spans;
verbosity = flagged / LOC where LOC = non-blank lines of the measured
files. `RULESET_VERSION = "1"` is written on every bag; rules are
sorted by id before application so the union is order-independent.
The initial set (pinned in the contract): `except-pass`, `bare-except`,
`print-call`, `debugger-call` (breakpoint/pdb), `nested-ternary`,
`if-deep-4` (four nested ifs). Each is a small unambiguous slop marker;
the set grows in later rounds under a new version.

**R-5 — the record shape.** `BenchmarkScope.AXIS = "axis"`; the record
has `stage="axis"`, `role="axis"`, `model="deterministic"`,
`prompt_sha="none:deterministic"`, the cell identity + provenance fields
identical to the oracle records, `quality=QualityScore(score=None,
judge="axis")` — `JudgeKind` gains the literal `"axis"`
(`test_judge_literal.py` pins the set and is edited additively) — and
the figures in a new optional payload `BenchmarkRecord.axis: AxisBag |
None`, the pattern `cell`/`waste` already use. Figures never enter
`quality` (FR-011): `score=None` guarantees the axis record can never
render in a quality figure.

**R-6 — reading side.** `Run.axis: AxisBag | None` (the run's last
AXIS-scope record; absent = not measured, reason `no axis record` —
every stored run). `Group` gains mean erosion/verbosity over measured
runs **of one ruleset version**; a group whose measured runs mix
versions withholds the means and names the versions. `Totals` gains
`axis_measured` / `axis_not_measured`; the totals line gains one clause
(`axis: 2 measured, 16 not measured`). The grid row gains two columns
after the code-score columns (erosion, verbosity: value or short
reason); `grid.json`/`grid.html` carry them; the under-five grey rule
applies to the group means. The heatmap is untouched — the axis is not
per-stage and is not a layer.

**R-7 — determinism is tested, not assumed.** Files visited in sorted
path order; rules applied in sorted id order; no timestamps or paths in
the bag beyond the branch head. One fixture tree measured twice must
produce identical figures (SC-002). The bag carries tool
identifications (radon and ast-grep versions) so a figure is
interpretable against the tools of its time.

**R-8 — dependencies.** `radon==6.0.1` and `ast-grep-py==0.50.0` pinned
in `[project.dependencies]` (the worker measures at run end — runtime
deps, not dev extras), `uv.lock` regenerated, container venv re-synced.
Step 0 verifies both import on the container's Python 3.13 before any
code depends on them.

**R-9 — the live proof is one todo-api smoke run.** Ruling R2. Per the
benchmark launch runbook: dedicated temporal server (7234), clean
worktree, `D:\srv` scratch repo, never parallel with live pipeline
runs. Its acceptance: the bench dir contains one axis record per cell
with figures, the score shows them on the row and in the group header,
and the run's oracle figures are unaffected. The same run closes 013's
"live confirmation of the opencode parser" follow-up (its opencode
attempts' waste counters must be non-zero under the 014 parser).

**R-10 — the stored corpus is the negative proof.** No stored run has
an axis record, so after the round every stored run reads not measured
with reason `no axis record`, zero axis means, and the not-measured
count equals runs started. Every figure of 013's verification.md must
reproduce unchanged except the totals line's new clause. The records
fingerprint of the stored corpus is taken at baseline and compared
before every commit (the smoke run writes only its own new bench dir).

## Alternatives considered

- **Whole-tree measurement** (R-2): matches the source benchmark's
  greenfield setting; rejected because Kroker's corpus is brownfield and
  the base code would dominate every share.
- **Clone detection in v1**: ruled out at GATE 1 (licence-unchecked
  candidates, second engine); the version stamp keeps it honest to add.
- **A heatmap layer per figure**: rejected — the axis is per-run, not
  per-stage; forcing it into stage columns would invent a stage.
- **Storing figures in `QualityScore.components`**: rejected — the
  quality column must hold rubric scores only (013 FR-027, this round
  FR-011); a payload field keeps the axis out of every quality path.
- **Stdlib-`ast` rules instead of ast-grep-py**: no new engine, but
  rules become code instead of data and every later rule change is a
  code change; the versioned YAML set is the honest artefact (ruling R2
  sanctions the engine).

## Consult log

No advisor or skeptic seats were run for this round (solo session,
2026-10-11). The plan's reviewer gate stays per-task and blocking; the
GATE 2 list carries the disclosures a skeptic would flag (dependencies
change, the smoke run, the Alpha-status binding, radon's 2023 release).
