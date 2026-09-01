# Task-history + error-class matrices (design)

| | |
|---|---|
| Status | Design — approved in brainstorming 2026-07-27 |
| Roadmap item | New scope — benchmarks tooling, not tied to a numbered `E-` tier |
| Design input | User-supplied reference images: a task×run pass/fail matrix and a error-class×model failure-density matrix |
| Anchors | FR-704 / NFR-4 (renders run/benchmark history to an export — same anchor as the E-36 heatmap) |
| Depends on | E-31 (oracle records), E-36 (heatmap precedent — pure aggregator + activity split), E-37 (arms/cell_id) |

---

## 1. What this delivers

Two new persistent, cross-run views over benchmark history, both scanned
on-demand from `runs/benchmarks/` (no new stateful store):

1. **Task-history matrix** — rows are individual numbered tasks (`t01`,
   `t02`, ...) declared per case; columns are every `(bench_run_id, cell)`
   that has produced task grades for that case, ordered chronologically.
   Cell = that task's score (0–1) on that run, colour-coded green
   (pass) → red (fail) → amber (partial). A `sum` row totals each column.
   Answers: *is this case getting better or worse over time, and which
   specific task keeps regressing.*

2. **Error-class matrix** — rows are a fixed, small taxonomy of failure
   classes; columns are `harness#model` arms; cell = average task failure
   mass per run for that class×arm. Answers: *which class of defect does
   this arm produce most, compared to other arms.*

Both read a **new** record scope (`ORACLE_TASK`) that does not exist yet.
Producing it requires extending oracle grading to score individual tasks,
not just the case as a whole — this is genuinely new scope, not a pure
reporting change like E-36 was.

### Design stance carried in

- **Opt-in, backward compatible.** A case with no `tasks.yaml` behaves
  exactly as today — no `ORACLE_TASK` records, no matrix, no change to the
  existing case-level oracle grade or heatmap.
- **No BenchmarkRecord schema change beyond a new scope.** `task_id`
  already exists on the record. `error_class` is *not* stored on the
  record — it is joined from `tasks.yaml` at aggregation time. This
  mirrors E-36's "no new record schema" discipline for the parts that
  don't strictly need one.
- **Pure core, I/O at the edges**, same shape as `heatmap.py` /
  `report.py`: aggregation and rendering are pure functions; the only I/O
  is (a) the existing `grade_oracle` activity, now also running task
  grading, and (b) a new CLI command that scans and writes the matrices.
- **Fail-safe.** A malformed `tasks.yaml`, a rubric task the judge fails
  to score, or an oracle-test id absent from the JUnit report never fails
  the case-level oracle grade — it degrades to a missing/`None` task
  score, visible in the matrix as an empty cell, never a fabricated 0/1.

---

## 2. Task definitions — `benchmarks/cases/<case_id>/tasks.yaml`

Optional per case.

```yaml
tasks:
  - id: t01
    error_class: functional
    oracle_tests: ["test_crud.py::test_create_todo"]
  - id: t02
    error_class: security
    rubric: "Rejects unauthenticated write requests with 401, not 500."
```

- `id` — unique within the case; free-form string (`t01`, `t02`, ... by
  convention, not enforced).
- `error_class` — must be one of the fixed taxonomy (§2.1). Unknown value
  is a load-time error.
- Exactly one of `oracle_tests` (list of JUnit node-ids, `file::test_name`)
  or `rubric` (free text judged by the cross-family LLM judge). Both set,
  or neither, is a load-time error.

### 2.1 Fixed error-class taxonomy

Oracle-outcome-shaped, mirroring what the existing oracle suites already
check (`test_activity` / `test_risk` / `test_monitoring` / `test_crud`):

```
functional, security, performance, data_integrity, error_handling, api_contract
```

A constant in `tasks.py`. Not user-extensible — a case author picks from
this list; a new class requires a code change, keeping the error-matrix
taxonomy stable and comparable across cases.

### 2.2 New pure module `src/sdlc/benchmarks/tasks.py`

```python
class TaskSpec(BaseModel):
    id: str
    error_class: str  # validated against ERROR_CLASSES
    oracle_tests: list[str] = []
    rubric: str | None = None


class TaskSuite(BaseModel):
    case_id: str
    tasks: list[TaskSpec]


class TaskGrade(BaseModel):
    task_id: str
    error_class: str
    score: float | None
    judge: Literal["oracle", "llm_judge", "error"]
    detail: str


ERROR_CLASSES: list[str] = [...]


def load_task_suite(case_id: str, cases_dir: Path | None = None) -> TaskSuite | None: ...
def grade_tasks(
    suite: TaskSuite, testcase_results: dict[str, bool], judge_scores: dict[str, float]
) -> list[TaskGrade]: ...
```

`load_task_suite` returns `None` when `tasks.yaml` is absent (opt-in);
raises `ValueError` with a specific message on a malformed file (unknown
`error_class`, both/neither grading mode, duplicate `id`) — loud at load
time, since this is a human-authored artifact, not runtime data.

`grade_tasks` is pure: for an oracle-mapped task, score is the pass
fraction over whichever of `oracle_tests` are present in
`testcase_results` (`score=None`, `judge="error"`, detail explains, if
*none* of the mapped node-ids were found — never silently 0). For a
rubric-mapped task, score comes straight from `judge_scores[task.id]`
(absent → `score=None`, `judge="error"`).

---

## 3. Grading pipeline — extends `grade_oracle`, no new activity

`oracle.py` gains:

```python
def grade_testcases_from_junit(xml_text: str) -> dict[str, bool]: ...
```

Parses individual `<testcase classname="..." name="...">` elements (today
`grade_from_junit` only reads suite-level totals) into
`{"classname::name": passed}`.

Inside the `grade_oracle` activity, after the existing JUnit read and diff
computation (worktree + diff text are already in scope), before the
`finally` cleanup:

```python
try:
    suite = load_task_suite(inp.case_id)
    if suite is not None:
        testcase_results = grade_testcases_from_junit(xml_text)
        judge_scores = {}
        for t in suite.tasks:
            if t.rubric:
                qs = _judge_sync(
                    JudgeInput(
                        artifact_json=diff_text,
                        rubric=t.rubric,
                        author_model=inp.author_model,
                        judge_model=inp.judge_model,
                    )
                )
                if qs.score is not None:
                    judge_scores[t.id] = qs.score
        task_grades = grade_tasks(suite, testcase_results, judge_scores)
except Exception:
    task_grades = []  # a broken suite/judge never fails the case grade
```

`_judge_sync` (from `judge.py`) is called **in-process**, not as a
separate Temporal activity — `grade_oracle` is already the activity
boundary doing blocking I/O (subprocess, git, file reads), so an
in-process synchronous judge call fits the same boundary without adding
workflow-level activity calls.

`OracleInput` gains two new optional fields, populated by the workflow
call site from the cell's resolved roles / the case spec:

```python
author_model: str = ""  # cell.role_models.get("dev", "") — judged code's author
judge_model: str | None = None  # spec.judge_model
```

Both are only read when a task has `rubric` set; oracle-only cases need
neither.

`OracleGrade` gains `task_grades: list[TaskGrade] = field(default_factory=list)`.

---

## 4. Recording — one new `BenchmarkScope`

`models.py`: `BenchmarkScope.ORACLE_TASK = "oracle_task"`.

`workflow.py` gains `_oracle_task_records(base_cell, grade, bench_run_id,
run_id, started, ended) -> list[BenchmarkRecord]`, one record per
`TaskGrade`:

```python
BenchmarkRecord(
    run_id=run_id,
    bench_run_id=bench_run_id,
    case_id=base_cell.case_id,
    scope=BenchmarkScope.ORACLE_TASK,
    stage="oracle",
    task_id=t.task_id,
    role="oracle",
    harness=base_cell.harness,
    model=base_cell.arm_name,
    quality=QualityScore(score=t.score, judge=t.judge),
    speed=SpeedBag(
        wall_clock_s=(ended - started).total_seconds(), started_at=started, ended_at=ended
    ),
    outcome=PASS if (t.score or 0.0) >= 1.0 else FAIL,
)
```

`error_class` is **not** on the record — joined from `tasks.yaml` by
`(case_id, task_id)` when the matrices are built (§5), keeping the write
path minimal.

In `BenchmarkWorkflow.run`, immediately after today's single
`record_benchmark` call for the case-level oracle record, loop over
`grade.task_grades` and call `record_benchmark` once per task grade. All
task records for a cell land in the same `records.jsonl` file as every
other record for that cell (existing `_cell_id_for` keys by
`case_id#harness#model`), so this adds no new file layout.

---

## 5. Cross-run aggregation — two new pure modules

Both scan **every** `bench_run_id` directory under `runs/benchmarks/`
(recomputed on demand — the "Scan-on-demand" choice), mirroring
`scripts/aggregate_benchmarks.py`'s existing walk, but purpose-built for
`ORACLE_TASK` records instead of stage rework density.

### 5.1 `src/sdlc/benchmarks/task_matrix.py`

```python
class TaskMatrixColumn(BaseModel):
    bench_run_id: str
    cell_id: str
    harness: str
    model: str
    started_at: datetime
    mean_score: float | None


class TaskMatrix(BaseModel):
    case_id: str
    task_ids: list[str]  # canonical order, from tasks.yaml
    columns: list[TaskMatrixColumn]  # chronological
    scores: dict[str, dict[str, float | None]]  # task_id -> {cell_key: score}


def build_task_matrix(
    case_id: str, records: list[BenchmarkRecord], suite: TaskSuite
) -> TaskMatrix: ...
def render_task_matrix_html(tm: TaskMatrix) -> str: ...
def render_task_matrix_json(tm: TaskMatrix) -> str: ...
```

- Filters `records` to `scope=ORACLE_TASK, case_id=case_id`.
- Groups into columns by `(bench_run_id, cell)`; column key =
  `f"{bench_run_id}#{cell_id}"`.
- Row order = `suite.tasks` order (not data-derived), so a run missing a
  task still renders an empty cell rather than shifting rows.
- `mean_score` = mean of that column's task scores (`None`-scores
  excluded from the mean, not treated as 0).
- HTML: one column header per run (`started_at` + `model` + `mean_score`),
  a `sum` row (Σ non-`None` scores per column), body cells colour-scaled
  green (score=1) → amber (0<score<1) → red (score=0) → grey (`None`),
  matching the reference screenshot.

### 5.2 `src/sdlc/benchmarks/error_matrix.py`

```python
class ErrorMatrixCell(BaseModel):
    error_class: str
    arm_key: str  # "harness#model"
    avg_failure_mass: float
    n_runs: int


class ErrorMatrix(BaseModel):
    case_id: str
    error_classes: list[str]  # ERROR_CLASSES order, only rows with data
    arms: list[str]  # arm_key, sorted
    cells: list[ErrorMatrixCell]
    max_value: float


def build_error_matrix(
    case_id: str, records: list[BenchmarkRecord], suite: TaskSuite
) -> ErrorMatrix: ...
def render_error_matrix_html(em: ErrorMatrix) -> str: ...
def render_error_matrix_json(em: ErrorMatrix) -> str: ...
```

- Scoped to **one case per invocation** (v1) — a case's task pool and
  taxonomy usage is case-specific; merging across differently-shaped
  cases is a later widening if needed, not required now.
- For each `(bench_run_id, cell)` column, failure mass per class =
  `Σ(1 - score)` over that column's tasks in that class (`None`-scores
  excluded). `avg_failure_mass` = mean of that quantity across every
  column sharing the same `arm_key` (`harness#model`, collapsed across
  `bench_run_id`).
- HTML: white → dark-red scale (reusing the hue-interpolation approach
  from `heatmap.py::_cell_color`, tuned to a monochrome red ramp instead
  of green→red, to match the reference SVG).

---

## 6. CLI

`cli.py` gains a `history` subcommand:

```
python -m sdlc.cli benchmark history --case <case_id> [--root DIR]
```

```python
def dispatch_history(case_id: str, root: str | None = None) -> tuple[Path, Path]:
    """Scan every bench_run_id under root for case_id's ORACLE_TASK records,
    write task-matrix.{html,json} and error-matrix.{html,json} under
    runs/benchmarks/_history/<case_id>/. Pure aggregate + write, no Temporal."""
```

Output location: `runs/benchmarks/_history/<case_id>/` — sibling to the
per-`bench_run_id` directories it reads, clearly separated as a derived,
regenerable artifact (already covered by the existing `runs/` gitignore).
A missing `tasks.yaml` for the case is a clear CLI error (nothing to
build the matrix's row/taxonomy structure from).

---

## 7. Error handling summary

| Failure | Behaviour |
|---|---|
| No `tasks.yaml` for a case | No `ORACLE_TASK` records produced; existing oracle/heatmap behaviour unchanged |
| Malformed `tasks.yaml` | `load_task_suite` raises at load time (case authoring error, not a run-time failure) |
| `grade_oracle`'s task-grading step raises for any reason | Caught; `task_grades=[]`; case-level oracle grade unaffected |
| Oracle-mapped task's test id(s) absent from JUnit output | `score=None, judge="error"`; matrix renders an empty/grey cell |
| Rubric-mapped task's judge call fails or returns unparseable JSON | `_judge_sync`'s existing behaviour (`score=None, judge="error"`) flows through unchanged |
| `dispatch_history` called for a case with no `tasks.yaml` | CLI error, nothing written |

---

## 8. Testing

Unit tests (pure functions, no Temporal environment):

- `grade_testcases_from_junit` — multi-suite JUnit XML, per-testcase pass/fail extraction, malformed XML.
- `load_task_suite` — valid file, missing file (`None`), unknown `error_class`, both/neither grading mode, duplicate id.
- `grade_tasks` — oracle-mapped (all present / some missing / none found), rubric-mapped (present / absent from `judge_scores`).
- `build_task_matrix` — column ordering, missing-task empty cells, `mean_score` excluding `None`.
- `render_task_matrix_html` — colour-threshold boundaries (1.0 / 0.0 / partial / `None`).
- `build_error_matrix` — failure-mass aggregation across columns sharing an arm, `None`-score exclusion.
- `render_error_matrix_html` — colour-scale boundaries.
- One CLI-level test: `dispatch_history` against a temp `runs/benchmarks/` tree with 2+ synthetic `bench_run_id` dirs and a `tasks.yaml`, asserting both output files exist and parse.
