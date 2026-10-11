# Implementation Plan: Corpus Acceptance (round 015, Phase 3)

**Branch**: orchestrator's call (spec dir `015-corpus-acceptance`) | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md) | **Base**: main `c3f6319c`

**Input**: [spec.md](spec.md), GATE 1 cleared 2026-10-11 with rulings R1 to R9 (all as recommended; R4 names the weak arm `zai-coding-plan/glm-5.3-flash`). Scope: user stories 1 to 7; FR-001 to FR-040; SC-001 to SC-012. Source: `docs/reports/2026-10-06-benchmark-improvement-plan.md` section 4, Phase 3 (read-only; never edited, staged or committed).

**Consults**: advisor `.workspace/tmp/advisor-015-1.md`, `-2.md`, `-3.md` (spec phase). The plan phase read the code named below and changed five statements of the approved spec; the spec carries them as amendments A1 to A5 and they are items for GATE 2.

**Review**: reviewer `.workspace/tmp/reviewer-015-plan-1.md` — VERDICT: approve with fixes; 2 major, 4 minor, 4 nits, all folded in. Every design decision it tested held in the code. Major: the cat-cafe one-cell test in `tests/test_golden_case_loads.py` cannot stay pinned once the case has two arms (now a named change); run-phase commands from a detached worktree would write records into that worktree (now run with absolute records and ops roots). Minor: the offline acceptance half runs on any case with an oracle, which is what proves SC-002's sentence on todo-api; the "unedited" rule allows the one new function in the stored-records test; a corpus run with more than one cell is refused without `--arm` or `--all-arms`; row 13 of the cat-cafe list no longer reads as a claim about the flag's value after one reading.

`B/` = `src/sdlc/benchmarks/`. "Cases" = `benchmarks/cases/`.

This round has no separate research, data-model or contract file. The names are in "Names" below and are binding in the same way.

## Summary

The round has a code half and a run half. The code half merges on its own. The run half spends model budget and is gated batch by batch.

- **Case metadata** (DAG node A): a case states its role, its visibility and which of its arms is strong and which is weak.
- **Oracle identity** (B): a hash of a case's oracle files, written on the cell, oracle and oracle-task records of every new run. Runs of different identities are never grouped.
- **Acceptance, offline half** (C): `sdlc benchmark accept` runs the reference and the empty tree against the oracle in the per-grade environment of round 012 and writes `acceptance.yaml` into the case directory.
- **Smoke** (D): `sdlc benchmark smoke` runs the smoke case, checks four conditions and writes a stamp keyed by commit. `sdlc benchmark run` refuses a corpus case without a passing stamp.
- **cat-cafe** (E): 36 oracle tests, a requirement mapping, a reference solution.
- **Root cause** (F): a second view beside the error-class matrix. Lost runs are labelled by rule; failed requirements of graded runs only by a person.
- **Licence note** (G): the NL2Repo-Bench finding, written down. Nothing imported.
- **Acceptance, separation half** (H): strong arm against weak arm on recorded runs; the full verdict.
- **Runs** (R0 to R3) and **records and tally** (I).

## The five rules every task is checked against

1. **Baseline records are read-only.** The 111 record files present at the base are never modified, moved or deleted. Until batch R0 the records fingerprint is unchanged. From R0 on, the check is the manifest `baseline-records.sha256` in this directory. `git ls-files runs/` stays empty. Scores made during the round are written with `--out` to a directory outside `runs/`.
2. **No reader guesses.** Absent reads as "not recorded" or "not assessed". A verdict is never stronger than its evidence: `accepted` needs three graded runs per arm.
3. **A run costs money and is never implicit.** No task of the code half starts a pipeline run or calls a model. Every run task stops for the orchestrator's clearance first.
4. **Nothing reaches an agent that the agent must not see.** `reference/`, `oracle/`, `tasks.yaml` and `acceptance.yaml` are never copied into a scratch repository, a worktree or a prompt.
5. **Names come from this plan.** A name that is needed and not in "Names" stops the task.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2, argparse, PyYAML; Temporal Python SDK at the existing activities only).

**Primary Dependencies**: existing only. No change to `pyproject.toml` or `uv.lock`.

**Storage**: record files under `runs/benchmarks/<bench_run_id>/` (new runs add files; one additive optional field). Stamps under `runs/ops/smoke/` (git-ignored). `acceptance.yaml` per case and `benchmarks/labels/` in git.

**Testing**: in the `kroker-dev` container: `uv run pytest` (fast tier), named files per task; `-m slow` for the tests that build a real environment; `-m temporal tests/replay` and `-m temporal tests/test_benchmark_workflow_sequence.py` at baseline and at the end. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`. Host: `python scripts/check_file_size.py`, `python scripts/check_clauses.py`.

**Target Platform**: CLI on the developer host through the container; the worker for runs.

**Performance Goals**: the refusal of FR-018 returns in under five seconds (SC-004). The offline acceptance half of one case completes within the oracle's own timeout (600 s).

**Constraints**: baseline records read-only; no new workflow command (the replay suite must not change result); `sdlc benchmark score` stays free of worker, server and network; the offline acceptance half uses the network only to install packages; 1000-line ceiling; cross-stage call ban; producer owns its artifacts; behaviour and its documents change in the same diff; no file under `tests/replay/` is edited.

**Scale/Scope**: 6 new source modules, about 9 modified source files, 7 new test files, about 10 modified test files, 7 case manifests and 3 other manifests edited, 1 case grown (24 tests, a mapping, a reference), 3 documents, about 15 pipeline runs.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no constitution gate applies. The binding rules are the root `AGENTS.md`. `B/` has no `AGENTS.md` of its own.

| Rule | Status |
|---|---|
| Cross-stage calls banned | Holds. No stage is edited. `B/offline_checks.py` imports the environment helper through `B/oracle.py`, which already imports it. |
| Producer owns its artifacts | Holds. Acceptance, stamp, label and root-cause models live in the benchmark package. `core/` is not touched. |
| Behaviour and its clauses change in one diff | Planned per task: `BENCHMARK.md` sections 4.4 and 5, `README.md`, `ROADMAP.md`. No stage contract changes. |
| 1000-line ceiling | Holds. New subcommands are registered from `B/cli.py`, so `src/sdlc/cli.py` grows by under 15 lines; `B/runs.py` by about 25; `B/cli.py` by about 170. Step 0 records the base line counts. Stop-guard SG-3. |
| Workflow determinism | The workflow gains no activity call and no branch. It passes one more field, taken from an activity result it already awaits, into records it already writes. |
| Replay safety | `CellProgress` gains an optional field with a default; a stored history without it still validates. The replay suite is run at baseline and at the end. |
| `AGENTS.md` files | Not edited. |

No violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/015-corpus-acceptance/
├── spec.md, plan.md, tasks.md
├── cat-cafe-requirements.md      the requirement list for GATE 2 (ruling R9)
└── written during execution:
    baseline.md, baseline-records.sha256, licence-nl2repo.md, verification.md
```

### Source Code (after the feature)

```text
src/sdlc/benchmarks/
├── oracle_id.py          N  oracle_identity
├── corpus.py             N  load_corpus, smoke_case, corpus_status, render_corpus_status
├── acceptance.py         N  AcceptanceRecord and its checks, separation, decide, load/save
├── offline_checks.py     N  run_reference_check, run_floor_check
├── smoke.py              N  SmokeStamp, check_smoke, stamp I/O
├── root_cause.py         N  labels, build_root_cause, renderers
├── models.py             M  CaseRole, CaseVisibility; CaseSpec fields; BenchmarkRecord.oracle_id
├── cell.py               M  CellProgress.oracle_id; summarize_cell fills it; cell_record writes it
├── workflow.py           M  passes the identity into the oracle and oracle-task records
├── runs.py               M  Run.oracle_id; group key
├── scoring.py, heatmap.py, gate_oracle.py, grid.py   M  row and header keys carry the identity
├── score.py              M  writes root-cause.*
├── report.py             M  the root-cause section in report.md
└── cli.py                M  accept, corpus, smoke; --arm, --skip-smoke, --allow-parked on run
src/sdlc/cli.py           M  registers the new subcommands through one call into B/cli.py

benchmarks/
├── cases/*/case.yaml                 M  role, visibility; arms on the seven corpus cases
├── cases/cat-cafe-monitoring/        M  oracle/ (36 tests), N tasks.yaml, N reference/
├── cases/*/acceptance.yaml           N  written by the command, committed
└── labels/README.md                  N  the labels file format

tests/
├── test_benchmark_oracle_id.py, test_benchmark_corpus.py, test_benchmark_acceptance.py,
│   test_benchmark_offline_checks.py, test_benchmark_smoke.py, test_benchmark_root_cause.py,
│   test_cat_cafe_case.py                                             N
└── test_benchmark_models.py, test_benchmark_cell.py, test_benchmark_workflow.py,
    test_benchmark_runs.py, test_benchmark_grid.py, test_benchmark_heatmap.py,
    test_benchmark_scoring.py, test_benchmark_gate_oracle.py, test_benchmark_score.py,
    test_benchmark_cli.py, test_benchmark_report.py, test_deveval_corpus.py   M

BENCHMARK.md, README.md, ROADMAP.md   M
```

**Not touched**: the 111 baseline record files; `docs/reports/`; `tests/replay/`; every stage slice under `src/sdlc/stages/`; `src/sdlc/workflows/`; `B/oracle.py` (imported, not edited), `B/judge.py`, `B/recorder.py`, `B/record_builder.py`, `B/provenance.py`, `B/paths.py`, `B/tasks.py`, `B/error_matrix.py`, `B/task_matrix.py`, `B/importers/`; the harness package; `agents/`; `interfaces/`; every `AGENTS.md`; `pyproject.toml`, `uv.lock`; the `description` of any `case.yaml`; earlier `.specify/specs/*`.

## Names

**Case metadata** (`B/models.py`)

- `CaseRole`: `corpus`, `smoke`, `probe`, `parked`. `CaseSpec.role: CaseRole = CaseRole.CORPUS`.
- `CaseVisibility`: `private`, `public`. `CaseSpec.visibility: CaseVisibility | None = None`.
- `CaseSpec.strong_arm: str | None = None`, `CaseSpec.weak_arm: str | None = None`. Each, when set, must equal the name of an arm in `arms`, and the two must differ; validated on the model.
- Arm names on the seven corpus cases: `zai-coding-plan-glm-5.2` (strong) and `zai-coding-plan-glm-5.3-flash` (weak). The strong name is exactly what the matrix produces today from `models:`, so cell ids do not change. Each arm sets `role_models` for `dev`, `test`, `devops` only.

**Oracle identity** (`B/oracle_id.py`)

- `oracle_identity(oracle_dir: Path) -> str`: `"sha256:" + hex`. Over every file under the directory, in sorted order of forward-slash relative path, skipping any path with a part in `IGNORED_DIRS = ("__pycache__", ".pytest_cache")` and any `*.pyc`; each file contributes its relative path and its bytes with `\r\n` replaced by `\n`.
- `BenchmarkRecord.oracle_id: str | None = None`. `CellProgress.oracle_id: str | None = None`. `Run.oracle_id: str | None = None`.
- Shown as `oracle <first 8 hex>`; a run without one shows nothing.

**Acceptance** (`B/acceptance.py`)

- `SEPARATION_MARGIN = 0.15`, `MIN_RUNS_PER_ARM = 3`.
- `Verdict`: `accepted`, `provisional`, `rejected`, `not_assessed`. `Reason`: `reference`, `floor`, `saturated`, `degenerate`, `no_separation`.
- `SuiteCheck` (reference and floor): `passed: bool | None`, `tests_passed: int`, `tests_total: int`, `detail: str`.
- `ArmEvidence`: `arm`, `run_ids`, `scores`, `mean`.
- `SeparationCheck`: `passed: bool | None`, `strong: ArmEvidence | None`, `weak: ArmEvidence | None`, `margin: float | None`, `not_comparable: int`, `detail`.
- `AcceptanceRecord`: `case_id`, `verdict`, `reason`, `note`, `oracle_id`, `oracle_tests`, `reference`, `floor`, `separation`, `role`, `visibility`, `exposure`, `kroker_commit`, `updated`.
- `exposure` values: `repo_public`, `isolated`.
- File: `<case dir>/acceptance.yaml`. Functions: `separation(runs, strong, weak, oracle_id)`, `decide(reference, floor, separation)`, `load_acceptance`, `save_acceptance`.

**Offline checks** (`B/offline_checks.py`): `run_reference_check(case_dir, timeout_s=600) -> SuiteCheck`, `run_floor_check(case_dir, timeout_s=600) -> SuiteCheck`.

**Corpus** (`B/corpus.py`): `load_corpus(cases_root) -> list[CaseSpec]`, `smoke_case(cases_root) -> CaseSpec`, `CorpusRow`, `corpus_status(cases_root) -> list[CorpusRow]`, `render_corpus_status(rows) -> str`, `EXIT_CASES = 8`, `EXIT_PRIVATE = 2`.

**Smoke** (`B/smoke.py`)

- `SMOKE_CONDITIONS = ("rubric_scores", "commit_on_records", "one_file_per_cell", "oracle_all_pass")`.
- `SmokeStamp`: `kroker_commit`, `bench_run_id`, `passed`, `failed_conditions`, `written`.
- `ops_root()`: `SDLC_OPS_ROOT`, default `runs/ops`. Stamp file: `<ops root>/smoke/<commit>.json`.
- `check_smoke(records, record_files, n_cells) -> list[str]`, `write_stamp`, `passing_stamp(commit) -> SmokeStamp | None`.

**Root cause** (`B/root_cause.py`)

- `ROOT_CAUSES = ("planning", "execution", "verification", "unattributed")`.
- `Label`: `run_id`, `task_id`, `cause`, `note`. Labels file: `<cases root>/../labels/<case_id>/<bench_run_id>.yaml`, a list under the key `labels`.
- `RootCauseCell`, `RootCauseMatrix`, `build_root_cause(case_id, runs, records, suite, labels)`, `load_labels(case_id, labels_root)`, `render_root_cause_html`, `render_root_cause_json`, `render_root_cause_markdown`.
- Output files of a score: `root-cause.html`, `root-cause.json`.

**CLI**: `sdlc benchmark accept --case <id> [--offline]`; `sdlc benchmark corpus`; `sdlc benchmark smoke`; on `run`: `--arm <name>`, `--all-arms`, `--skip-smoke`, `--allow-parked`. A `corpus` case whose matrix has more than one cell is refused unless `--arm` names one arm or `--all-arms` is given.

## Design decisions

- **D-1 The identity rides an activity the workflow already calls.** `summarize_cell` runs for every cell and reads files. It computes the identity of the cell's case and returns it on `CellProgress`. The workflow puts it on the cell, oracle and oracle-task records. No new activity, no patch marker, lost runs get the identity too. The case id comes from the cell id, which starts with it.
- **D-2 The identity is a split key, like the record generation.** `Run.oracle_id` joins the group key in `B/runs.py` and the row keys in `B/scoring.py`, `B/heatmap.py` and `B/gate_oracle.py`. Every baseline record has none, so every pinned figure of round 013 is unchanged; the stored-records test proves it.
- **D-3 The offline checks use the grader's own environment functions.** A temporary directory; the tree under test copied in; `_provision_oracle_env` and `_oracle_run_env` from `B/oracle.py`; the oracle copied in beside it; the adapter's oracle command; the JUnit report read by `grade_from_junit`. For the reference check the tree is `reference/`, plus `reference_env/requirements.txt` copied to the root as `requirements.txt` when the reference has none (amendment A3). For the floor check the tree is empty.
- **D-4 The floor compares tests passed.** Floor passes when its tests passed are fewer than the reference's. A suite that cannot be imported on an empty tree reports either errors or no gradable test at all (`grade_from_junit` then returns no score and zero passed); both read as zero tests passed. Step 0 records which.
- **D-5 `verify-case` is left as it is.** `accept` is the new command; the import-time gate keeps its behaviour and its tests.
- **D-6 Separation reads runs, not records.** `separation()` takes `Run` objects from `build_runs`, keeps graded runs of the current identity under the two named arms, and counts the rest as not comparable. The reference and floor checks run for any case with an oracle. The separation check runs for `corpus` cases only: for a `smoke`, `probe` or `parked` case it reads not assessed, and a failed reference or floor still gives `rejected`.
- **D-7 The verdict is decided in one function**, in the order of FR-009: reference, floor, saturated, degenerate, then separation. Saturated and degenerate need strong-arm runs only.
- **D-8 The run gate lives in the CLI, before the Temporal client.** It reads the case's role, resolves the commit and the dirty flag by the same git calls provenance uses, and looks for a stamp. The worker is not involved.
- **D-9 The smoke command is the run command plus a check.** It starts the smoke case, waits for the workflow, loads the bench run's records, checks the four conditions and writes the stamp. The stamp's commit is the one on the records; a record commit of `unknown` fails `commit_on_records`.
- **D-10 Root cause is computed at score time from runs, oracle-task records and labels.** Lost runs by `last_stage` position against `code` in `CELL_STAGE_ORDER`, with the task-loop stages folded to `code` as round 013 does. Graded runs: each oracle-task record with a score below 1 is one failed requirement; unlabelled means `unattributed`. A graded run with no oracle-task record is counted as "no requirement results".
- **D-11 The view renders without a mapping.** The root-cause files are written for every scored case, also when the case has no `tasks.yaml`, because lost runs need none.
- **D-12 One commit under test for all batches** (amendment A5). The code half is merged; R0 to R3 run from a detached worktree of that commit; result commits come after.

## Work order

Each test lands with the code that satisfies it, test first, no red commits.

| Step | DAG | What | Why here |
|---|---|---|---|
| 0 | | Baseline; the manifest of the 111 files; verify items. | A known start. |
| 1 | A | Case metadata and the ten manifests. | Everything reads the role. |
| 2 | B | Identity function, record field, cell summary, workflow. | New records must carry it before any run. |
| 3 | B | Identity in runs, groups and rows. | FR-015. |
| 4 | C | Acceptance record and the offline verdict. | The unit the round counts. |
| 5 | C | Offline checks, the `accept` command, the isolation proof. | SC-001 for the DevEval cases. |
| 6 | D | Smoke conditions and stamp. | |
| 7 | D | Run gate, `--arm`, the `smoke` command. | Needed by R0. |
| 8 | F | Root-cause build and labels. | Independent of C, D, E. |
| 9 | F | Root-cause rendering and score wiring. | SC-005. |
| 10 | G | Licence note. | Independent. |
| 11 | E | cat-cafe mapping of the 12 tests, and the reference. | Needs GATE 2 on the requirement list. |
| 12 | E | cat-cafe oracle grown to 36. | Tests are written against a reference that already passes 12. |
| 13 | H | Separation and the full verdict. | Built on fixtures. |
| 14 | I | Corpus status and the tally. | Reads acceptance records. |
| 15 | I | Offline acceptance records for the seven corpus cases, committed. | SC-001, SC-007. |
| 16 | | Documents. | |
| 17 | | Full gates; `verification.md`. **The code half ends here and is merged.** | |
| 18 | R0 | Smoke run. | Gate. |
| 19 | R1 | Six DevEval screening runs; roles and records. | Gate. |
| 20 | R2 | Weak-model probe; cat-cafe strong and weak. | Gate. |
| 21 | R3 | Weak arm on the cases that screened in. | Gate. |
| 22 | I | Final records, tally, `verification.md` updated. | |

Steps 6 to 7, 8 to 9 and 10 depend only on step 1 and may be reordered. Steps 11 and 12 need steps 2 and 5.

## Existing tests changed on purpose

| File | Change | Why |
|---|---|---|
| `tests/test_benchmark_models.py` | cases for the new `CaseSpec` fields and `oracle_id` | A, B |
| `tests/test_benchmark_cell.py` | `summarize_cell` returns the identity; `cell_record` writes it | D-1 |
| `tests/test_benchmark_workflow.py` | oracle and oracle-task records carry the identity | D-1 |
| `tests/test_benchmark_runs.py`, `test_benchmark_grid.py`, `test_benchmark_heatmap.py`, `test_benchmark_scoring.py`, `test_benchmark_gate_oracle.py` | new cases: two identities never share a group or row; header text | D-2 |
| `tests/test_benchmark_score.py`, `test_benchmark_cli.py` | file list gains `root-cause.*`; new subcommands; run flags | F, CLI |
| `tests/test_benchmark_report.py` | the root-cause section | F |
| `tests/test_deveval_corpus.py` | every imported case states role and visibility | A |
| `tests/test_golden_case_loads.py` | `test_cat_cafe_case_loads_as_one_cell` only: cat-cafe now expands to two cells, and the strong cell keeps the base cell id | A (two arms) |

Tests that must pass **unedited**: `tests/test_benchmark_stored_scores.py` (every figure round 013 pinned); `tests/test_benchmark_legacy_records.py`; `tests/test_deveval_verify.py`; `tests/test_deveval_importer.py`; `tests/test_benchmark_matrix.py` and `tests/test_benchmark_arms.py` except for added cases; the tests of `B/error_matrix.py` and `B/task_matrix.py` (step 0 lists the files); everything under `tests/replay/`. A needed edit to one of these is SG-1.

## Document changes

| File | Change to |
|---|---|
| `BENCHMARK.md` section 5 | the acceptance rule (three checks, margin, `provisional`); roles and visibility; exposure; the corpus table with each case's verdict; parked cases; the two follow-up rounds |
| `BENCHMARK.md` section 4.4 | the root-cause view, its rule and its limits; the labels file |
| `BENCHMARK.md`, how to run | the smoke command and the run gate; `--arm` |
| `README.md` | the new subcommands |
| `ROADMAP.md` | Phase 3 status with the honest tally |
| `benchmarks/labels/README.md` | the labels file format |

## Stop-guards (binding; clearance only from the orchestrator)

- **SG-1**: a test listed as "must pass unedited" needs an edit; a test under `tests/replay/` changes result against the baseline; an edit to a "not touched" path appears necessary; a name is needed that "Names" does not define.
- **SG-2**: a step-0 verify item fails.
- **SG-3**: `src/sdlc/cli.py` would pass 900 lines, or any other file 800.
- **SG-4**: before R0, the records fingerprint differs from the base value; at any time, a file of the manifest differs, `git ls-files runs/` prints anything, or a score is written under `runs/`.
- **SG-5**: a run task. No run, probe or model call before the orchestrator's clearance for that batch. A second lost run of one case: stop, do not retry again.
- **SG-6**: step 11. No cat-cafe test, mapping or reference file is written before the orchestrator confirms that the requirement list was approved at GATE 2.
- **SG-7**: the cat-cafe reference fails one of the 12 existing tests and the cause is the test, not the reference. Stop; an existing test is changed only by ruling.
- **SG-8**: a `temporal` test named in a gate reports "deselected"; a test marked RED passes before its code; a PIN is red.
- **SG-9**: anything of `reference/`, `oracle/`, `tasks.yaml` or `acceptance.yaml` is found in a scratch repository, a run's worktree or a prompt.
- **SG-10**: the offline acceptance half is red for a DevEval case. Stop and report: it is a finding about the case, not a defect to fix in the case's files.

## Risks

| Risk | Mitigation |
|---|---|
| A DevEval reference fails its oracle in a clean environment (it has only ever been checked in the developer environment) | SG-10. The case is recorded as rejected with reason `reference`; the count drops and is reported. |
| The identity differs between host and container (line endings, stray files) | Line endings are normalised; caches are skipped; a test hashes one tree twice with `\r\n` and `\n`. |
| A group-key change moves a pinned figure | The stored-records test must pass unedited; baseline identities are all absent. |
| The weak model is not served to opencode | The probe of FR-034 before R2; SG-5. |
| The weak arm scores zero everywhere | That is `no_separation` data on a floor, recorded as such. The user chose the model knowing the risk (R4). |
| cat-cafe tests encode a free choice | The requirement list is approved first; each test cites its row; the reviewer gate checks rule 3 of that file. |
| A run is lost for an infrastructure reason | One retry, then `no result` (FR-032); the cause goes to the task inbox. |
| A smoke stamp from a commit that is not the one under test | The stamp is keyed by the commit on the records; the gate compares with the worktree's commit. |

## Follow-ups to file (`.workspace/tasks/`)

- Round 016: second private case and storage outside the public repository.
- Round 017: public cases from licence-checked sources.
- An automatic root-cause labeller, with calibration (Phase 4).
- `verify-case` depends on the caller's environment; fold it into the offline reference check. Size S.
- A research-enabled run can reach this project's public repository. Size M.
- Per-task gate-versus-oracle agreement, now that cat-cafe has a mapping (round 013 follow-up).

## Items for GATE 2

1. **The cat-cafe requirement list** (`cat-cafe-requirements.md`): 15 requirements, 36 tests, and what is left out. Ruling R9 asks for approval before any test is written.
2. **Five spec amendments** (A1 to A5).
3. **Four new flags on `run`**: `--arm`, `--all-arms`, `--skip-smoke`, `--allow-parked`. A corpus case now has two arms, so a bare `run` is refused: it would start both and double the spend.
4. **One additive record field** written by future runs: `oracle_id`.
5. **Seven manifests gain `arms`.** The strong arm keeps today's cell id.
6. **`report.md` gains a root-cause section** and a score writes two more files.
7. **The code half is merged before any run**, and all four batches run on that commit.
8. **A DevEval case whose reference fails in a clean environment is rejected**, not repaired, in this round.
9. **The offline acceptance half runs on any case with an oracle**, smoke and parked cases included; only the separation check and the tally are limited to corpus cases. That is how todo-api reads rejected with reason `reference` (SC-002).
10. **Run-phase commands use absolute records and ops roots** in the primary checkout, so records written from the detached worktree land beside the stored ones.

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind.
- Commits via `git commit -F <msgfile>`; one path per `git add` argument; no heredocs. Every file is written with the Write tool.
- Python runs in `kroker-dev` only. Git on a worktree runs on the host.
- Never chain two test runs in one shell call. `addopts` already carries `-q`.
- The reviewer gate is per task and blocking.
- Runs follow the benchmark launch runbook: dedicated Temporal on port 7234, a clean detached worktree, serial, gate policy off, no pipeline run executing.
- The files under `docs/reports/` and the other untracked or modified files in the primary tree are the user's; never edit, add or commit them.

## Complexity Tracking

No constitution or repository-rule violation to justify.
