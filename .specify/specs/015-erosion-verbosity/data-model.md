# Data model — round 015 erosion and verbosity

Names are binding: every identifier a task introduces is on this page
(§8). A name not here stops the task (plan rule 4).

## §1 New models

### `AxisBag` (`B/models.py`, rides `BenchmarkRecord.axis`)

One run's erosion-verbosity measurement, or its measured absence.

| Field | Type | Meaning |
|---|---|---|
| `erosion` | `float \| None` | mass(CC>10)/mass(all); None = no functions (reason `no functions`) or not measured |
| `verbosity` | `float \| None` | flagged/LLOC; None when erosion is None or not measured |
| `reason` | `str \| None` | why not measured: `no axis record` is the reader's, the writer's are below |
| `functions_total` | `int` | functions in the measured files |
| `functions_over` | `int` | functions with CC > 10 |
| `mass_total` | `float` | sum of mass over all functions |
| `mass_over` | `float` | sum of mass over CC > 10 |
| `flagged_lines` | `int` | union of rule-match spans, lines |
| `loc` | `int` | non-blank lines of the measured files |
| `files` | `int` | measured `*.py` files (changed vs base) |
| `head` | `str \| None` | the integration branch head measured |
| `ruleset_version` | `str` | `"1"`; the aggregation boundary (R-6) |
| `tools` | `dict[str, str]` | `{"radon": "...", "ast-grep": "..."}` |

Writer reasons (FR-006): `code stage did not finish`,
`integration branch absent`, `language not python` (covers
`language not recorded`), `no python files in diff`, `no functions`,
`measurement failed: <detail>`. Reader reason: `no axis record`
(every stored run; also a run whose axis record failed validation).

Invariant: `erosion is None` XOR (`reason is None`). Exactly one of the
two holds on a valid bag.

### `AxisInput` (`B/axis.py`, the activity's argument)

`case_id`, `repo_url`, `run_id`, `language`, `base_branch` (the oracle
input's five used fields) plus `code_finished: bool` (the cell progress
flag; a lost run is not measured without a checkout).

### Reader additions

- `Run.axis: AxisBag | None` (`B/runs.py`) — the run's last
  AXIS-scope record's payload; None = not measured.
- `Group.mean_erosion`, `mean_verbosity: float | None`;
  `axis_n: int`; `axis_versions: tuple[str, ...]` — means withheld
  (None) when more than one ruleset version is present, with the
  versions named in the header.
- `Totals.axis_measured`, `axis_not_measured: int`.

## §2 The record

One per cell that started, written by the workflow after the cell
record: `scope=AXIS`, `stage="axis"`, `role="axis"`,
`model="deterministic"`, `prompt_sha="none:deterministic"`, identity
and provenance fields identical to the cell record's, `quality` =
`QualityScore(score=None, judge="axis")`, `outcome=NOT_EVALUATED`,
`speed` spanning the measurement, the bag on `.axis`. It lands in the
cell's own `records.jsonl` (the recorder routes by cell_id; no new
file, no new directory).

## §3 The measurement (`B/axis.py`)

- `AXIS_EROSION_THRESHOLD = 10` (named constant, CC strictly above).
- `measure_files(paths) -> AxisBag` — pure: radon `cc_visit` per file
  for CC and per-function SLOC; ast-grep-py over the pinned rule set
  for flagged spans; sorted path order, sorted rule order.
- `measure_code_axis(AxisInput) -> AxisBag` — the fail-safe activity:
  reasons out `code stage did not finish` / `language not python` /
  `integration branch absent` (worktree add fails) / `no python files
  in diff` before any tool runs; wraps the measurement in
  try/except → `measurement failed: <detail>`; cleans its worktree in
  a finally.
- `axis_record(cell, bag, bench_run_id, run_id, started, ended, *, provenance, graph_sha) -> BenchmarkRecord` — the pure builder the
  workflow calls (the `cell_record` pattern).
- `AXIS_ACT` (`B/workflow.py`) — the activity config: start-to-close
  5 minutes, `maximum_attempts=1` (the activity never raises, so
  retries are dead code by construction).

## §4 The rule set

`src/sdlc/benchmarks/rules/verbosity/*.yml`, `RULESET_VERSION = "1"`
(constant beside the loader). v1 rules, ids binding:

`except-pass`, `bare-except`, `print-call`, `debugger-call`,
`nested-ternary`, `if-deep-4`.

A rule matches a node; the match flags the node's whole line span
(`lineno`..`end_lineno`). Flagged lines are the union over rules and
files. A rule that fails to compile fails the measurement (reason
`measurement failed: rule <id>`) — a broken rule set must never
silently flag nothing.

## §5 Writer/reader split

The writer (`measure_code_axis` + `axis_record`) needs git and the two
tools; the reader needs neither — `sdlc benchmark score` reads bags
from records only (research R-1, FR-013). `B/runs.py`, `B/grid.py`
stay free of `temporalio` and of both tools.

## §6 Display rules

Row: `0.42` for a figure; `n/m(<reason>)` short form for an absence —
`n/m(no record)` on stored runs. Group header:
`erosion 0.42 (3)`, `verbosity 0.18 (3)` after the all-pass figure,
grey under five measured runs. Totals line: the clause
`axis: <measured> measured, <not measured> not measured`. ASCII only.

## §7 Not changed

`CANONICAL_STAGES`, `CELL_STAGE_ORDER`, `TASK_LOOP_STAGES`,
`RUBRIC_JUDGES`, the heatmap layers and scales, the composite
decision, the gate-oracle view, the waste and agreement matrices, the
success-criteria rollup, the record file layout under `runs/`.

## §8 Name check (first task runs it)

New names this round: `AxisBag`, `AxisInput`, `BenchmarkScope.AXIS`,
`JudgeKind` literal `"axis"`, `measure_code_axis`, `measure_files`,
`axis_record`, `AXIS_EROSION_THRESHOLD`, `RULESET_VERSION`,
`rules/verbosity/` (six rule ids above), `Run.axis`,
`Group.mean_erosion` / `mean_verbosity` / `axis_n` / `axis_versions`,
`Totals.axis_measured` / `axis_not_measured`, the `015-quality-axis`
patch id, `AXIS_ACT`, writer reasons of §1. A task needing a name off
this page stops (plan rule 4).
