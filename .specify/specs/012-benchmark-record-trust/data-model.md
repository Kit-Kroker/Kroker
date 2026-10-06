# Data Model: Benchmark Record Trustworthiness (012)

Every name the round adds or changes. A name not listed here is not
introduced without a report to the orchestrator. Decisions are in
[research.md](research.md); behaviour is in
[contracts/records-and-harness.md](contracts/records-and-harness.md).

`B/` = `src/sdlc/benchmarks/`.

## 1. Changed models

### 1.1 `BenchmarkRecord` (`B/models.py`)

All additions are optional with defaults: every stored line still loads.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `kroker_commit` | `str \| None` | `None` | Commit of the Kroker tree that ran the pipeline. `None` = the record predates 012. A 012 writer writes a commit id or the literal `unknown`. |
| `tree_dirty` | `bool \| None` | `None` | Uncommitted changes at run start. `None` = not determinable (or pre-012). |
| `arm` | `str \| None` | `None` | The cell label: the arm name (ruling R1). `None` = pre-012. |
| `cell_id` | `str \| None` | `None` | `case#harness[:lead]#arm`, equal to `BenchmarkCell.cell_id`. `None` = pre-012. |
| `cell` | `CellStatus \| None` | `None` | Set only on the cell record (scope `cell`). |

Unchanged in type, changed in what is written:

| Field | Before | After |
|---|---|---|
| `prompt_sha` | always `""` | sha256 hex of the role's `instructions.md`, or `none:<reason>`; never `""` from a 012 writer |
| `model` | arm name on oracle records, model id elsewhere | always the model that did the work; `deterministic` on oracle, oracle-task and cell records |

### 1.2 `CellStatus` (new, `B/models.py`)

Frozen, `extra="forbid"`.

| Field | Type | Meaning |
|---|---|---|
| `pipeline_finished` | `bool` | The child pipeline returned without raising. |
| `code_finished` | `bool` | A post-code stage wrote a record. |
| `completed` | `bool` | `pipeline_finished and code_finished`. Stored, not derived at read. |
| `last_stage` | `str \| None` | Latest stage (by `CELL_STAGE_ORDER`) that wrote a record; `None` if none did. |
| `grading` | `Literal["graded", "not_graded", "grading_failed", "no_oracle"]` | See contract §3. |
| `child_result` | `str \| None` | The child's return text, or its failure text, truncated to 500 characters. |

### 1.3 `BenchmarkScope`, `BenchmarkOutcome` (`B/models.py`)

| Enum | New value | Used by |
|---|---|---|
| `BenchmarkScope` | `CELL = "cell"` | the one cell record per cell; stage `"cell"`, role `"cell"` |
| `BenchmarkOutcome` | `NOT_EVALUATED = "not_evaluated"` | a gate not evaluated in benchmark mode; an oracle grade that could not run |

### 1.4 `BenchmarkSummary` (`B/models.py`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `cell_id` | `str \| None` | `None` | The cell the row belongs to (012 rows). |
| `arm` | `str \| None` | `None` | The cell label (012 rows). |
| `pre012` | `bool` | `False` | The row aggregates pre-012 records only. A row never mixes kinds. |

`model` on a 012 row is the sorted, comma-joined distinct models of the
row's records.

### 1.5 `BenchmarkConfig` (`core/models.py`)

Optional, defaulted; old payloads validate unchanged.

| Field | Type | Default |
|---|---|---|
| `arm` | `str \| None` | `None` |
| `cell_id` | `str \| None` | `None` |
| `kroker_commit` | `str \| None` | `None` |
| `tree_dirty` | `bool \| None` | `None` |

`core/` holds only configuration and envelopes; these are configuration
of a benchmark run, the same kind as the fields already there.

### 1.6 `OracleGrade` (`B/oracle.py`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `changed_files` | `int` | `0` | Files changed against the base branch. `0` with a zero score = the empty-diff guard fired. |

## 2. New module-level names

### 2.1 `B/paths.py` (new, leaf: imports nothing from `B/`)

| Name | Signature | Notes |
|---|---|---|
| `cases_dir` | `() -> Path` | Reads `SDLC_CASES_ROOT` at call time. |
| `calibration_dir` | `() -> Path` | `cases_dir().parent / "calibration"`. |
| `check_case_assets` | `(rubrics: dict[str, str], vetoes: dict[str, str], case_dir: Path) -> list[str]` | Reads the file system, nothing else. One message per missing or empty registered file. |
| `MISSING_CASE_ASSET` | `"MissingCaseAsset"` | The `type` of the `ApplicationError(non_retryable=True)` that `load_case_assets` raises. No exception class is added. |

### 2.2 `B/provenance.py` (new)

| Name | Signature | Notes |
|---|---|---|
| `Provenance` | dataclass: `kroker_commit: str`, `tree_dirty: bool \| None` | `kroker_commit` is a commit id or `UNKNOWN_COMMIT`. |
| `UNKNOWN_COMMIT` | `"unknown"` | |
| `resolve_provenance` | activity, `() -> Provenance` | git, then environment, then unknown. Never raises. |
| `prompt_sha_for` | `(role: str, model: str) -> str` | Pure, import-time data. Registry hash, or `none:deterministic`, or `none:no-registry-prompt`. |
| `PROMPTED_ROLES` | `frozenset[str]` | Roles that have a registry prompt. Built from the registry at import. |

Environment variables read: `KROKER_COMMIT`, `KROKER_TREE_DIRTY`
(`1`/`true` or `0`/`false`).

### 2.3 `B/models.py`

| Name | Signature | Notes |
|---|---|---|
| `cell_key` | `(r: BenchmarkRecord) -> str` | `r.cell_id`, else the pre-012 derivation (`case#harness[:lead]#model`, `proposer` when no harness). |
| `arm_label` | `(r: BenchmarkRecord) -> str` | `r.arm`, else `r.model`. |
| `is_pre012` | `(r: BenchmarkRecord) -> bool` | `r.kroker_commit is None and r.case_id != "_production"`. Drift records are never pre-012. |
| `CELL_STAGE_ORDER` | `tuple[str, ...]` | Record stage names in pipeline order. |
| `POST_CODE_STAGES` | `frozenset[str]` | `analyze`, `merge`, `deploy`. |

`CELL_STAGE_ORDER` is filled from the stage names record writers use
(at base: `research`, `clarify`, `architecture`, `plan`, `code`,
`tool_approval`, `qa`, `review`, `adversary`, `deep_review`, `handoff`,
`analyze`, `merge`, `deploy`). Intake and retro emit trace events only
and write no record, so they are not in it. A test fails when a writer
uses a stage name that is not in it.

### 2.4 `B/cell.py` (new)

| Name | Signature | Notes |
|---|---|---|
| `CellProgress` | dataclass: `last_stage: str \| None`, `code_finished: bool` | Activity result. |
| `summarize_cell` | activity, `(bench_run_id: str, cell_id: str) -> CellProgress` | Reads the cell's record file. |
| `cell_record` | `(cell, status: CellStatus, bench_run_id, run_id, started, ended, provenance, graph_sha) -> BenchmarkRecord` | Pure builder. |
| `grading_status` | `(has_oracle: bool, code_finished: bool, grade: OracleGrade \| None) -> str` | Pure; the table in contract §3. |

### 2.5 Other

| Name | Where | Notes |
|---|---|---|
| `_provision_oracle_env` | `B/oracle.py` | `async (worktree, oracle_dir, timeout_s) -> tuple[dict[str, str] \| None, str \| None]`. The seam fast tests replace. |
| `_ORACLE_ENV_ALLOW` | `B/oracle.py` | Names copied from the worker environment into the oracle's. |
| `"012-cell-record"` | `B/workflow.py` | `workflow.patched` id guarding the new activity calls. |
| `KROKER_COMMIT` | `Dockerfile` | Build argument and environment variable. |

## 3. Removed names

| Name | Where | Replaced by |
|---|---|---|
| `_CASES_DIR` | `B/judge.py` (imported by `B/report.py`) | `paths.cases_dir()` |
| `_cases_dir` | `B/oracle.py`, `B/tasks.py` | `paths.cases_dir()` |
| `_CALIB_DIR` | `B/calibration.py` | `paths.calibration_dir()` |

Tests that monkeypatch a removed name switch to `SDLC_CASES_ROOT`.

## 4. Case corpus files

| File | Change |
|---|---|
| `benchmarks/cases/cat-cafe-monitoring/oracle/requirements.txt` | new: the oracle's own test dependencies |
| `benchmarks/cases/todo-api-greenfield/oracle/requirements.txt` | new |
| the six `deveval-*` cases | new only if their oracle imports something beyond `pytest` and the produced project; decided by reading each `oracle/` |

A `requirements.txt` inside `oracle/` is not collected by the test
runner and is copied with the rest of the directory at grade time.

## 5. Name check (first task)

Before any edit, confirm none of these already exists with another
meaning: `rg -n "kroker_commit|tree_dirty|CellStatus|cell_key|arm_label|is_pre012|NOT_EVALUATED|check_case_assets|MISSING_CASE_ASSET|resolve_provenance|summarize_cell|prompt_sha_for" src tests interfaces scripts`.
Expected: no hits outside this spec directory. A hit is reported before
work continues.
