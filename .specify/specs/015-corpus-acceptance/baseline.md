# Baseline: Corpus Acceptance (Round 015, Phase 3)

**Date**: 2026-10-11
**Base Commit**: `77c89885` (spec set committed on `015-corpus-acceptance`, on top of main `c3f6319c`)

## 1. Clean Tree and Diff Against Base

- `git diff --stat c3f6319c HEAD -- src/sdlc/benchmarks src/sdlc/cli.py benchmarks BENCHMARK.md`: Empty (0 files changed, 0 insertions, 0 deletions).
- No source or benchmark files differ from `c3f6319c`.

## 2. Command Results and Counts

### Container Test Runs (`docker exec -w /app kroker-dev ...`)

1. `uv run pytest` (default fast unit tier):
   - Result: 3 failed, 6038 passed, 12 skipped, 263 deselected, 249 warnings, 9 errors in 757.61s.
   - Failures (3):
     - `tests/test_plans_are_tracked.py::test_superpowers_scratch_is_still_ignored`: `git check-ignore` failed due to container `.git` worktree link resolving Windows host path (`fatal: not a git repository: /app/D:/own/Kroker/.git/worktrees/Kroker-wt015`).
     - `tests/test_prompt_gate.py::test_unchanged_prompt_passes_without_calling_a_model`: `git show` failed with the same `.git` worktree link error.
     - `tests/test_promptfoo_provider.py::test_resolve_instructions_git_ref_reads_from_git`: `git show` failed with the same `.git` worktree link error.
   - Errors (9):
     - `tests/test_eval_mutation_seam.py` (2 errors): fixture attempts `tempfile.mkdtemp(dir="/app/runs")` on read-only mount (`OSError: [Errno 30] Read-only file system`).
     - `tests/test_promptfoo_config.py` (7 errors): fixture attempts `tempfile.mkdtemp(dir="/app/runs/.prompt_gate_tests")` on read-only mount (`OSError: [Errno 30] Read-only file system`).
2. `uv run pytest -m temporal tests/replay`:
   - Result: 32 passed, 21 skipped, 171 deselected, 138 warnings in 118.80s (PASS).
3. `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`:
   - Result: 5 passed in 26.75s (PASS).
4. `uv run ruff check .`:
   - Result: All checks passed! (0 issues).
5. `uv run ruff format --check .`:
   - Result: 1726 files already formatted (0 unformatted).
6. `uv run mypy`:
   - Result: Success: no issues found in 394 source files (0 errors).

### Host Checks

1. `python scripts/check_file_size.py`:
   - Result: Exit 0 (all authored code within 1000-line ceiling).
2. `python scripts/check_clauses.py`:
   - Result: 202 clauses declared, 10 untested, 0 dangling (baseline unchanged).
3. Records Fingerprint:
   - Command: `python -c "import hashlib,pathlib;fs=sorted(pathlib.Path('runs/benchmarks').rglob('*.jsonl'));h=hashlib.sha256();[h.update(str(f.relative_to('runs/benchmarks')).replace(chr(92),'/').encode()+hashlib.sha256(f.read_bytes()).digest()) for f in fs];print(len(fs),h.hexdigest())"`
   - Output: `111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831` (matches base value exactly).
4. Manifest:
   - `.specify/specs/015-corpus-acceptance/baseline-records.sha256` written with 111 sorted entries matching `runs/benchmarks/*.jsonl`.

## 3. Verify Items (a) to (l)

### (a) D-1: CellProgress Dataclass and DataConverter Decoding
- **Location**: `src/sdlc/benchmarks/cell.py:42-47`
- **Evidence**: `CellProgress` is declared as `@dataclass(frozen=True)` with fields `last_stage: str | None` and `code_finished: bool`. It is the return type of activity `summarize_cell` (`src/sdlc/benchmarks/cell.py:50-51`).
- **DataConverter**: Temporal's `JSONPlainPayloadConverter` deserializes dataclasses field-by-field. When a field defines a default (such as `oracle_id: str | None = None`), incoming payloads omitting that key successfully decode to the default value (`None`). Verified directly with Temporal's `DataConverter.default`.
- **Test proving it in T003**: `tests/test_benchmark_cell.py` will verify that `CellProgress(last_stage=..., code_finished=...)` constructs and validates with `oracle_id=None` when omitted, and replay suite `tests/replay` passes without deserialization failure.

### (b) D-1: Cell ID Prefix Structure
- **Location**: `src/sdlc/benchmarks/models.py:304-306`, `src/sdlc/benchmarks/matrix.py:106-114`
- **Evidence**: `BenchmarkCell.cell_id` property is defined as:
  ```python
  lead = f":{self.lead_harness.value}" if self.lead_harness else ""
  return f"{self.case_id}#{self.harness.value}{lead}#{self.arm_name}"
  ```
  Every cell constructed by `expand_matrix` produces a `cell_id` starting strictly with `self.case_id` followed by `#`. For crew cells, `self.harness` is `HarnessKind.CREW` (`"crew"`), and `lead` is `":<lead_harness>"`, producing `{case_id}#crew:{lead_harness}#{arm_name}`.

### (c) Names: Arm Name and Extra Args Lookup
- **Location**: `src/sdlc/benchmarks/matrix.py:34-40`, `src/sdlc/benchmarks/workflow.py:95-98`, `benchmarks/cases/*/case.yaml`
- **Evidence**:
  - For all seven corpus cases (`cat-cafe-monitoring`, `deveval-geotext`, `deveval-hone`, `deveval-lice`, `deveval-particle-swarm-optimization`, `deveval-readtime`, `deveval-stocktrends`), `case.yaml` specifies `models: ["zai-coding-plan/glm-5.2"]`.
  - In `_arms_for`, the default arm name is computed as `_family(m) + "-" + m.rsplit("/", 1)[-1].rsplit(":", 1)[-1]`. For `"zai-coding-plan/glm-5.2"`, `_family` is `"zai-coding-plan"`, yielding `"zai-coding-plan-glm-5.2"`.
  - In `_cell_config` (`src/sdlc/benchmarks/workflow.py:97`), extra arguments are resolved via `spec.extra_args_by_model.get(model, [])` where `model` is the role model string (`"zai-coding-plan/glm-5.2"`). Therefore, an explicit arm specifying that model preserves `--variant max`.

### (d) D-3: Python Environment Provisioning on Packaging Metadata Absence
- **Location**: `src/sdlc/stages/qa/activities.py:158-198`
- **Evidence**: `_ensure_python_env` creates `.sdlc-venv`. If no packaging file exists (`uv.lock`, `pyproject.toml`, `setup.py`), the `-e` editable pip installs fail non-fatally. The loop over `_REQUIREMENTS_FILES` (`requirements.txt`, `requirements-dev.txt`, `requirements/base.txt`, `requirements/dev.txt`) executes `pip install -q -r <file>`. Finally, `pytest pytest-cov ruff` are installed unconditionally.
- **On an empty tree**: No requirements file exists; `-e` installs fail tolerated; only `uv` and `pytest pytest-cov ruff` are installed. The function returns a clean environment dictionary with `.sdlc-venv/bin` prepended to `PATH`.

### (e) D-3: DevEval Case Requirements Files
- **Location**: `benchmarks/cases/deveval-*/`
- **Evidence**:
  - `reference/requirements.txt`: Absent across all 6 DevEval cases (`deveval-geotext`, `deveval-hone`, `deveval-lice`, `deveval-particle-swarm-optimization`, `deveval-readtime`, `deveval-stocktrends`).
  - `reference_env/requirements.txt`: Present in 5 cases (`deveval-geotext`, `deveval-lice`, `deveval-particle-swarm-optimization`, `deveval-readtime`, `deveval-stocktrends`). Absent in `deveval-hone`.

### (f) D-4: grade_from_junit on Import/Collection Failure
- **Location**: `src/sdlc/benchmarks/oracle.py:31-70`
- **Evidence**: Running `pytest` against an empty directory on `benchmarks/cases/deveval-readtime/oracle` generates 4 collection errors (`ModuleNotFoundError: No module named 'readtime'`). Pytest outputs JUnit XML reporting `<testsuite errors="4" tests="4">`.
- **Function return**: `grade_from_junit(xml)` returns `(0.0, 0, 4, "0/4 oracle tests passed")`. `score` is `0.0` and `passed` is `0`.

### (g) D-8: resolve_provenance Git Calls in Detached Worktrees
- **Location**: `src/sdlc/benchmarks/provenance.py:90-108`
- **Evidence**: `resolve_provenance` runs `git -c safe.directory=* rev-parse HEAD` and `git -c safe.directory=* status --porcelain`.
- **Detached worktree**: `git rev-parse HEAD` outputs the exact commit SHA of HEAD whether attached to a branch or detached. `git status --porcelain` evaluates uncommitted working tree modifications. In a detached worktree, both commands succeed identically, producing `Provenance(kroker_commit=<sha>, tree_dirty=False)`.

### (h) D-9: Stored 012 todo-api Runs Against Smoke Conditions
- **Location**: `runs/benchmarks/bench-todo-api-greenfield-17914*`
- **Four Smoke Conditions**: `rubric_scores`, `commit_on_records`, `one_file_per_cell`, `oracle_all_pass`.
- **Results on stored runs**:
  1. `bench-todo-api-greenfield-1791472617`:
     - `one_file_per_cell`: PASS (1 record file)
     - `oracle_all_pass`: PASS (score 1.0, 6/6 passed)
     - `commit_on_records`: FAIL (`kroker_commit` is `"unknown"`)
     - `rubric_scores`: FAIL (clarify and architecture records have `judge: "error"`, `score: None`)
  2. `bench-todo-api-greenfield-1791479569`:
     - `one_file_per_cell`: PASS (1 record file)
     - `oracle_all_pass`: PASS (score 1.0, 6/6 passed)
     - `commit_on_records`: PASS (`kroker_commit` is `"b3344416"`)
     - `rubric_scores`: FAIL (clarify and architecture records have `judge: "error"`, `score: None`)
  3. `bench-todo-api-greenfield-1791488612`:
     - `one_file_per_cell`: PASS (1 record file)
     - `commit_on_records`: PASS (`kroker_commit` is `"b3344416"`)
     - `rubric_scores`: FAIL (clarify passed rubric with 1.0, but architecture record is missing due to lost run)
     - `oracle_all_pass`: FAIL (no oracle record emitted; run lost before oracle)

### (i) Rule 4: Scratch Repository Seeding and Held-out Material Isolation
- **Location**: `src/sdlc/vcs/worktree.py`, `src/sdlc/stages/code/activities.py`, `src/sdlc/benchmarks/oracle.py:270-375`
- **Evidence**: Scratch repositories are seeded as standard git repositories at `repo_url` (e.g. `/srv/scratch-repos/<case>`). A task worktree is created via `git worktree add -b <branch>` branching off the base branch.
- **Isolation**: No file under `benchmarks/cases/<case>/` is copied into the scratch repository or worktree during execution. Only `oracle/` is copied in uncommitted at grade time (`src/sdlc/benchmarks/oracle.py:276`) by activity `grade_oracle` and immediately destroyed upon grade completion (`src/sdlc/benchmarks/oracle.py:373`). `reference/`, `tasks.yaml`, and `acceptance.yaml` never enter worktrees or prompts.

### (j) Tests Asserting on Benchmark Matrix and Group/Row Keys
- **`B/error_matrix.py`**: `tests/test_error_matrix.py`, `tests/test_error_matrix_render.py`
- **`B/task_matrix.py`**: `tests/test_task_matrix.py`, `tests/test_task_matrix_render.py`
- **`group_runs` group key**: `tests/test_benchmark_runs.py`, `tests/test_benchmark_stored_scores.py`
- **`compute_summaries` row keys**: `tests/test_benchmark_composite.py`, `tests/test_benchmark_scoring.py`
- **Heatmap row key**: `tests/test_benchmark_heatmap.py`, `tests/test_benchmark_heatmap_render.py`, `tests/test_benchmark_score.py`, `tests/test_benchmark_stored_scores.py`, `tests/test_benchmark_report.py`, `tests/test_benchmark_gate_oracle.py`, `tests/test_benchmark_cli.py`
- **Gate-oracle row key**: `tests/test_benchmark_gate_oracle.py`
- **File list returned by `write_score`**: `tests/test_benchmark_score.py`, `tests/test_benchmark_report.py`

### (k) CLI Benchmark Subparsers Registration and Line Count
- **Location**: `src/sdlc/cli.py`
- **Registration**: `_build_parser` lines 282–353 (`bp = sub.add_parser("benchmark")`, `bs = bp.add_subparsers(...)`).
- **Dispatch**: `_dispatch` lines 520–575 (`if args.cmd == "benchmark": ...`).
- **Line count**: 841 physical lines.

### (l) CaseSpec Extra Field Handling
- **Location**: `src/sdlc/benchmarks/models.py:238-289`
- **Evidence**: `CaseSpec` inherits from `pydantic.BaseModel` without `extra="forbid"`. Extra fields are ignored by default (`extra="ignore"`). Verified via `CaseSpec.model_validate({"case_id": "c", ..., "unknown_field": 123})`. Old inputs deserialize without the new fields, and newer inputs containing `role`/`visibility`/`arms` deserialize safely in older workers without crashing.

## 4. Line Counts of Key Modules

| Module | Lines |
|---|---|
| `src/sdlc/cli.py` | 841 |
| `src/sdlc/benchmarks/cli.py` | 330 |
| `src/sdlc/benchmarks/models.py` | 463 |
| `src/sdlc/benchmarks/runs.py` | 496 |
| `src/sdlc/benchmarks/score.py` | 245 |
| `src/sdlc/benchmarks/report.py` | 314 |

All files comfortably below their stop-guard limits (841 < 900 for `src/sdlc/cli.py`; all other files < 800; hard ceiling 1000).
