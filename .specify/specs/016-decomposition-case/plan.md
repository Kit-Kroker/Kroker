# Implementation Plan: Decomposition Case (round 016, Phase 3)

**Branch**: orchestrator's call (spec dir `016-decomposition-case`) | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md) | **Base**: main `f61261ba`

**Input**: [spec.md](spec.md). GATE 1 cleared 2026-10-17 with rulings R1 to R7, all as recommended, plus the orchestrator caveat on R1. Scope: user stories 1 to 5, FR-001 to FR-030, SC-001 to SC-007, and amendments A1 to A8 (plan phase, for GATE 2). Source: `docs/reports/2026-10-06-benchmark-improvement-plan.md`, Phase 3 (read-only; never edited, staged or committed).

**Consults**:
- Advisor `.workspace/tmp/advisor-016-1.md` (D1 to D9 plus M1 to M5). Every cited site was spot-checked in the tree. Adopted except M1, which is replaced by amendment A5 (see D-6).
- Skeptic `.workspace/tmp/skeptic-016-1.md`, checked claim by claim against the code and the records. **Upheld and adopted:** R2 is only a label (T-01's retry wrote every module; amendment A1); research egress (A2); exposure hard-coded in `dispatch_accept`; labels path beside the cases root (A4); raw stream never stored; judge built without `max_tokens`. **Not upheld (the figures are wrong in the tree):** no plan validator with `max_tasks=10` / `max_criteria_per_task=4` / 25 attempts exists (grep finds none; the stored plan stage has `fix_attempts: 0`, and `plan-v25` is the shared artifact version counter). The separation margin is 0.15, not 0.10. Cat-cafe is `provisional` 0.833 / 0.472, not `accepted` 1.0 / 0.79. The env var is `SDLC_CASES_ROOT`. "Contradiction between SC-004 and the risks" does not exist (FR-026 and R7 are the contingency rule). Hindsight contamination is not evidenced: the strong-arm summary records `memory_retains: 0` (step 0 verify item V5). **Disagreement carried to GATE 2:** the skeptic wants a two-layer contract so decomposition is "actually tested". This plan keeps FR-002 and rewords R2 instead (A1, GATE 2 item 1).

**Review**: reviewer `.workspace/tmp/reviewer-016-plan-1.md`, plan checklist. VERDICT: approve with fixes (2 major, 5 minor, 5 nits), all folded in. It checked D-1 to D-4, D-6 to D-9, D-12 and D-13 in the code, and they held. **MA-1**: the stored cat-cafe chain is 7 nodes, not 8. The spec and V6 are corrected; the spec now also gives the weak-arm plan (chain 6). **MA-2**: the run half had lost 015's clean detached worktree and absolute roots. It is now in the Runbook and amendment A8. Minor: labelling the private case is unsupported (A4 restated); the A5 cause line has its condition; steps 1 and 2 carry their test commands; a duplicate id exits cleanly at the CLI; the baseline records manifest is back (rule 2, SG-4). Nits: smoke stays on the primary root; the judge budget is read at call time; the first fast-tier run with the store bound is named; committed examples use `<store>`; duplicate handling on the run path is a stated decision.

`B/` = `src/sdlc/benchmarks/`. "Store" = the private store. "Case" = the new case, id `theatre-box-office`.

This round has no separate research, data-model or contract file (015 precedent). The decisions are in "Design decisions", the names in "Names", and the run guide in "Runbook". All are binding in the same way.

## Summary

The round has three halves.

- **Code half** (public repo, merged before any run): a second cases root read alongside the first (the private store); exposure taken from the root; a clearer refusal when a worker cannot see the store; optional `tier` and `feature` on requirement mappings; grading of an arbitrary tree in the per-grade environment; the planner judge given an output budget; opt-in raw stream capture; a leak guard (pre-commit hook and test); the decomposition report script; documents.
- **Authoring half** (private store only, never in the repo): store bootstrap; requirement list (GATE 2); case text, mapping, rubrics; reference and oracle; ablation patches and the free-choice variant; offline acceptance; review record (user read). It never moves the repo commit.
- **Run half** (gated batch by batch): R0 smoke with stream capture, R1 strong then weak, verdict, closing commit.

## The six rules every task is checked against

1. **Nothing private reaches the public repo.** No commit may contain the case text, requirement list, test names, test code, reference code, rubric text or label of the case. The leak guard runs on every commit from the step where it lands. The case id, its role, visibility, exposure, verdict, means, margin and run counts may be published (FR-021).
2. **Baseline records are read-only.** Stored records under `runs/` are never modified, moved or deleted; runs only add files (FR-030). `git ls-files runs/` stays empty. Step 0 writes a per-file manifest of `runs/benchmarks` to `baseline-records.sha256` in this directory (file names and hashes only; no private case has run yet). It is re-checked after each batch and before the closing commit.
3. **A run or a model call costs money and is never implicit.** No code task starts a pipeline run. The only model calls outside the run half are the judge proof of step 6, covered by ruling R3 and capped at $1. Every run task stops for the orchestrator's clearance first.
4. **Nothing reaches an agent that it must not see.** `oracle/`, `reference/`, `verification/`, `review/`, `tasks.yaml` and `acceptance.yaml` of any case, in either root, are never copied into a scratch repository, a worktree or a prompt.
5. **The oracle is not fitted to the arms.** After R1 has produced a score, no file of `oracle/` changes unless a defect is shown against the case text. Such a change starts a new oracle identity, and a re-run needs its own clearance (FR-026).
6. **Names come from this plan.** A needed name that "Names" does not define stops the task.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2, argparse, PyYAML, pydantic-ai at the existing judge only; Temporal Python SDK at existing activities only).

**Primary Dependencies**: existing only. No change to `pyproject.toml` or `uv.lock`.

**Storage**: in-repo cases `benchmarks/cases/` (unchanged). Store on the host at `<store>`, a host directory outside the repository chosen at step 12. Its real path is written only into the git-ignored `docker-compose.override.yml` and `.env`; every committed file, this plan included, says `<store>`. It is a git repository of its own with the layout `cases/<id>/`. Container path `/srv/private-cases` (mapped to `<store>/cases`). Records under `runs/benchmarks/`, raw streams under `runs/ops/raw-stream/` (both git-ignored).

**Testing**: in `kroker-dev`: `uv run pytest` (fast tier) and named files per task. `-m slow` for tests that build a real environment. `-m temporal tests/replay` and `-m temporal tests/test_benchmark_workflow_sequence.py` at baseline and at the end. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`. Host: `python scripts/check_file_size.py`, `python scripts/check_clauses.py`, `pre-commit run --all-files` once the hook lands.

**Target Platform**: CLI on the host through the container; the compose worker for runs.

**Performance Goals**: case resolution adds no measurable time (two `is_dir` checks). The offline acceptance half of the case completes within the oracle timeout (600 s).

**Constraints**: `cases_dir()` keeps its exact meaning and its tests (`tests/test_benchmark_paths.py`). No new workflow command and no `workflow.patched` marker; the replay suite must not change result. The 1000-line ceiling (`B/cli.py` is at 662). Cross-stage call ban: no stage slice is edited. Behaviour and its documents change in one diff. No file under `tests/replay/` is edited.

**Scale/Scope**: 2 new scripts, 1 pre-commit hook, about 9 modified source files, 3 new test files, about 8 modified test files, 2 documents and 1 compose example. In the store: 1 case (manifest, 40 to 60 tests, a 500 to 1,500-line reference, mapping, 4 rubrics, verification set, review record). 3 to 5 pipeline runs.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no constitution gate applies. The binding rules are the root `AGENTS.md`. `B/` has no `AGENTS.md` of its own.

| Rule | Status |
|---|---|
| Cross-stage calls banned | Holds. No stage slice is edited. Raw stream capture lives in `src/sdlc/artifacts/capture.py` (horizontal package), which both callers (`stages/code/activities.py`, `crew/activities.py`) already call. |
| Producer owns its artifacts | Holds. Resolver in `B/paths.py`; mapping fields in `B/tasks.py`; `core/` untouched. |
| Behaviour and its clauses change in one diff | Planned: `BENCHMARK.md` section 5 (private store, how to run a private case, exposure, research off) lands with the storage code. No stage contract changes, because no stage behaviour changes. |
| 1000-line ceiling | Holds. `B/cli.py` 662 grows by about 30; `B/paths.py` 63 by about 70; `B/offline_checks.py` 137 by about 30; `B/judge.py` 317 by about 15; `tests/conftest.py` 345 by about 8. Stop-guard SG-3. |
| Workflow determinism, replay safety | No workflow code changes. The only activity touched (`load_case_assets`) changes its error text, not its control flow. Replay suite at baseline and end. |
| `AGENTS.md` files | Not edited. |

No violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/016-decomposition-case/
├── spec.md, plan.md, tasks.md
├── checklists/requirements.md
└── written during execution: baseline.md, verification.md (aggregates only, rule 1)
```

### Source Code (after the feature, public repo)

```text
src/sdlc/benchmarks/
├── paths.py            M  PRIVATE_CASES_ENV, private_cases_dir, case_roots, case_dir,
│                          require_case_dir, iter_case_dirs, root_exposure, DuplicateCase, CaseNotFound
├── oracle.py           M  :280 cases_dir()/id -> case_dir(id)
├── cell.py             M  :70  same swap
├── judge.py            M  :307,:311 swap; A5 message; JUDGE_MAX_TOKENS on the judge Agent
├── tasks.py            M  TaskSpec.tier, TaskSpec.feature; all-or-none tier validator; :83 swap
├── report.py           M  :298 swap (default branch only)
├── corpus.py           M  corpus_status over iter_case_dirs; exposure from the root; store_note
├── offline_checks.py   M  mode "tree", TreeCheck, run_tree_check
└── cli.py              M  accept / verify-case / corpus resolve by id across roots; exposure from root
src/sdlc/artifacts/capture.py   M  RAW_STREAM_ENV opt-in write of the raw stream
scripts/check_private_leak.py   N  leak guard (hook + library)
scripts/decomposition_report.py N  plan shape and per-tier credit, aggregates only
.pre-commit-config.yaml         M  check-private-leak hook
docker-compose.override.example.yml  M  commented private-store block
tests/
├── test_benchmark_paths.py, test_benchmark_corpus.py, test_benchmark_cli.py,
│   test_benchmark_judge.py, test_tasks_suite.py, test_benchmark_offline_checks.py,
│   test_session_capture.py                                   M (added cases)
├── conftest.py                                               M (autouse: unset private root)
├── test_private_leak.py, test_decomposition_report.py        N
└── fixtures/opencode/<one stream>.jsonl                      N (closing commit, after R1)
BENCHMARK.md                    M  section 5 (and the corpus row in the closing commit)
ROADMAP.md                      M  Phase 3 tally (closing commit)
```

### Private store (never in the public repo)

```text
<store>/                               own git repository
├── cases/theatre-box-office/
│   ├── case.yaml          role corpus, visibility private, research_enabled false, arms, judge
│   ├── tasks.yaml         requirements with error_class, tier, feature
│   ├── rubric-clarifier.md, rubric-architect.md, rubric-planner.md, rubric-qa.md
│   ├── oracle/            40-60 tests, conftest.py, requirements.txt
│   ├── reference/         500-1,500 non-blank lines over >= 4 modules
│   ├── verification/      ablate-<req>.patch per requirement, variant-free/, run_checks.py, check_shape.py
│   ├── review/            requirements.md (GATE 2), record.md (FR-014)
│   └── acceptance.yaml    written by `sdlc benchmark accept`
```

No `labels/`: labelling the private case is unsupported this round (A4).

**Not touched**: stored records; `docs/reports/`; `tests/replay/`; every stage slice under `src/sdlc/stages/`; `src/sdlc/workflows/`; `B/workflow.py`, `B/acceptance.py` (model unchanged; `Exposure` already admits `isolated`), `B/root_cause.py`, `B/calibration.py`, `B/oracle_id.py`, `B/importers/`; `src/sdlc/eval/`; the harness package; `agents/`; `interfaces/`; every `AGENTS.md`; `pyproject.toml`, `uv.lock`; `docker-compose.yml`, `Dockerfile`; every in-repo `case.yaml`; earlier `.specify/specs/*`.

## Names

**Resolver** (`B/paths.py`, still a leaf module)

- `PRIVATE_CASES_ENV = "SDLC_PRIVATE_CASES_ROOT"`. `private_cases_dir() -> Path | None`: the env value as a path, or None when it is unset or empty. Read at call time.
- `cases_dir()` and `calibration_dir()`: **unchanged**.
- `case_roots() -> list[Path]`: `[cases_dir()]`, plus `private_cases_dir()` when configured (whether or not it exists).
- `class DuplicateCase(ValueError)`: the message names both paths.
- `class CaseNotFound(LookupError)`: names every root searched. When the private root is configured but not a directory, it adds `private store configured at <p> but not readable`.
- `case_dir(case_id) -> Path`, **lenient**: the root whose `<root>/<case_id>` is a directory. If both roots have it, raise `DuplicateCase`. If none has it, return `cases_dir() / case_id` (today's path), so every caller that tolerates absence behaves as before.
- `require_case_dir(case_id) -> Path`, **strict**: as `case_dir`, but raise `CaseNotFound` when none has it.
- `iter_case_dirs() -> list[tuple[Path, Path]]`: `(root, case_dir)` for every `<root>/*/case.yaml`, sorted by case id. Raise `DuplicateCase` on an id present in both.
- `root_exposure(case_dir: Path) -> Exposure`: `"isolated"` when the dir is under the configured private root, else `"repo_public"`. Imported as a string literal type, so the leaf rule holds: no import from `acceptance.py`; the `Literal` is restated.

**Mapping** (`B/tasks.py`)

- `TaskSpec.tier: Literal["basic", "rule", "cross"] | None = None`, `TaskSpec.feature: str | None = None`.
- `TaskSuite` validator `_tier_all_or_none`: if any task sets `tier`, every task must.

**Offline checks** (`B/offline_checks.py`)

- `_run_check_async(case_dir, mode: Literal["reference", "floor", "tree"], timeout_s=600, tree_dir: Path | None = None)`. The `tree` mode copies `tree_dir` into the worktree and needs no `reference/`.
- `class TreeCheck(SuiteCheck)`: adds `per_test: dict[str, bool]`.
- `run_tree_check(case_dir: Path | str, tree_dir: Path | str, timeout_s: int = 600) -> TreeCheck`.

**Judge** (`B/judge.py`)

- `JUDGE_MAX_TOKENS_ENV = "SDLC_JUDGE_MAX_TOKENS"`, `DEFAULT_JUDGE_MAX_TOKENS = 16000`, and `judge_max_tokens() -> int`, read at call time (house style, `paths.py`). Passed as `model_settings=ModelSettings(max_tokens=judge_max_tokens())` to the one `Agent(...)` in `_run_judge_agent`. The value 16000 is a start; step 6 may move it, and the final default is written into this plan.

**Corpus** (`B/corpus.py`)

- `corpus_status(cases_root: Path | str | None = None)`: when `cases_root` is given, behaviour is as today. When it is None, it walks `iter_case_dirs()` and takes `exposure` from `root_exposure`, else from the acceptance record as today.
- `render_corpus_status(rows, store_note: str | None = None)`: with None, output is byte-identical to today. `dispatch_corpus` passes one of: `private store: not configured`, `private store: absent at <p>`, `private store: <n> case(s) at <p>`.

**Raw stream** (`src/sdlc/artifacts/capture.py`)

- `RAW_STREAM_ENV = "SDLC_RAW_STREAM_DIR"`. When set, `capture_session` also writes `raw_stdout` unchanged to `<dir>/<safe run_id>/<safe task_id>-a<attempt>.jsonl`, before normalising, inside its own try/except, and logs one INFO line `raw stream captured: <path>`. Default off. A failure stores nothing extra and changes nothing else.

**Leak guard** (`scripts/check_private_leak.py`)

- `collect_tokens(store_cases: Path) -> set[str]`: test node ids and test function names under `oracle/`; requirement ids and `feature` values from `tasks.yaml`; module and top-level function and class names under `reference/`; 8-word shingles of `description` and of each rubric. Id tokens are kept only when they contain `_` or are at least 8 characters long; the six error-class names and the domain words of spec R5 are excluded.
- `scan(paths_or_text) -> list[Finding]`. CLI: `--staged` (scans added lines of `git diff --cached`; the hook mode), `--tracked` (scans `git ls-files` content; the test mode). Exit 1 on any finding. Exit 0 with the note `private store absent; skipped` when the env var is unset or the dir is absent.
- Hook id `check-private-leak` in `.pre-commit-config.yaml`, `language: system`, `entry: python scripts/check_private_leak.py --staged`, `pass_filenames: false`, `always_run: true`.

**Report** (`scripts/decomposition_report.py`)

- `plan_shape(plan_json: dict) -> PlanShape` with `tasks`, `edges` (resolvable `depends_on` entries), `longest_chain` (node count), `dangling` (unresolvable entries, flagged).
- `latest_plan(cell_artifacts: Path) -> Path | None`: the highest numeric `plan-v<N>.json`; the file count is reported beside it.
- `tier_credit(case_id, runs, oracle_id) -> dict[(arm, tier), (mean, n_requirements, n_tests)]`, read through `load_task_suite` (so it finds the store) and the oracle-task records of runs with that identity.
- CLI: `[--case <id> --bench-run <id>...] [--baseline-plan <path>...]`. At least one of the two groups is given. `--case` and `--bench-run` go together (per-run shape and per-tier credit). `--baseline-plan` alone prints only the shape of each named plan file (V6 uses this mode). It prints tier names, counts and means only. It never prints a task id, test name or requirement text.

**CLI**: no new subcommand or flag. `accept --case <id>`, `verify-case --case <id>` and `corpus` resolve across roots when `--cases-root` is not given.

## Design decisions

- **D-1 A second env var, not a path list** (advisor D1). `cases_dir()` and its pinned tests are unchanged. `os.pathsep` differs between host and worker. The Dockerfile's baked `SDLC_CASES_ROOT` keeps its meaning.
- **D-2 `case_dir` is lenient, `require_case_dir` is strict.** Lenient resolution keeps every absence-tolerant caller at today's behaviour (FR-018). The strict form is used only where the plan says so (accept, verify-case). At the CLI (`dispatch_corpus`, `dispatch_accept`, `dispatch_verify_case`), `DuplicateCase` and `CaseNotFound` are caught and turned into `SystemExit(<message>)`, one line naming both paths, with no traceback. On the run path the host passes a `case.yaml` path and never resolves by id. A duplicate there first surfaces in the worker at `load_case_assets`: it raises `DuplicateCase`, the activity retries under its policy, and the run fails before the first cell, at zero model spend. That is accepted as is.
- **D-3 Call sites swapped**: `oracle.py:280`, `cell.py:70`, `judge.py:307,311`, `tasks.py:83` and `report.py:298` (default branches only; an explicit argument still wins), and `cli.py` accept, verify-case and corpus (when `--cases-root` is absent). Nothing else builds a case path (advisor inventory, re-checked by the reviewer). Deliberately not swapped (A4): `dispatch_smoke` (`cli.py:561`, the smoke case is in-repo), the DevEval import destination (`cli.py:629`), prompt eval (`eval/cli.py:83`), calibration (`paths.py:32`) and labels (`root_cause.py:121`).
- **D-4 Exposure comes from the root**, replacing the literals at `cli.py:483,535`. The tally keeps counting `visibility == private` (`corpus.py:153`), so cat-cafe (`repo_public`) and the case (`isolated`) both count.
- **D-5 Store mounting is per machine.** The worker and `kroker-dev` take the store from the git-ignored `docker-compose.override.yml`. The committed `docker-compose.yml` is untouched; `docker-compose.override.example.yml` gets a commented block. The worker mount is `:ro` with `environment: SDLC_PRIVATE_CASES_ROOT: /srv/private-cases` (an explicit `environment:` entry wins over `env_file: .env`). The `kroker-dev` mount is read-write, because `accept` writes `acceptance.yaml` into the case dir. The host `.env` holds the host path. Git on the store runs on the host only.
- **D-6 FR-019 by the existing asset check** (amendment A5, replacing advisor M1). On a worker without the store, the case's registered rubrics are missing and `load_case_assets` already raises non-retryably at zero spend. The step adds the cause to the message: `case <id> is in no cases root (<roots>); private root configured: yes|no`. The line is appended only when the case directory exists in no root. When the directory exists and one registered file is missing (today's case), the existing messages stand alone. A test proves it on a case registered only in a tmp private root that the activity cannot see.
- **D-7 Tree grading reuses the reference path** (advisor D4). A third mode of `_run_check_async`; per-test results from the JUnit dict already computed there. The ablation and free-choice driver lives in the store (it names tests).
- **D-8 The judge fix is one setting**, proven twice. A deterministic test records `model_settings` through a `FunctionModel` (no network). Then step 6 runs a real proof on the two stored 015 R2 cat-cafe plan artifacts: `generate_steps` then the scoring call, logging usage and finish reason per call. Success is `judge == "staged_rubric"` with a non-null score on both. If 16000 does not succeed, the value is raised (SG-6).
- **D-9 Capture lives in `capture_session`, gated by env**, and only on R0 (advisor D7, placed in the horizontal package instead of the stage activity, so no stage slice changes). The worker is recreated with the variable for R0 and recreated without it before R1, and the R1 clearance checks the worker log has no `raw stream captured` line after the recreate.
- **D-10 Two layers of leak guard** (advisor D8): the pre-commit hook on staged lines is primary, and `tests/test_private_leak.py` (skipped with no store) scans tracked files. Unit tests of `collect_tokens` and `scan` run always, on a synthetic store. The spec is public and sketches the domain (Q5, R5). So the case text must not reuse an 8-word run of the spec's wording, or the tracked scan flags the spec. The fix is to reword the case text, never to exempt the spec.
- **D-11 The report script is public and generic**; its output is aggregates only and lands in a git-ignored directory. Numbers are copied by hand into `verification.md` and `BENCHMARK.md`.
- **D-12 Test hermeticity**: an autouse fixture in `tests/conftest.py` unsets `SDLC_PRIVATE_CASES_ROOT`, so a `kroker-dev` with the store bound runs the fast tier exactly as CI. The resolver tests set it explicitly. `tests/test_private_leak.py` and the two "iterate all cases" tests read the real env through a marker-free opt-in: they read `os.environ` captured at import, before the fixture (named `REAL_PRIVATE_ROOT` in the test module).
- **D-13 One commit under test** (amendment A6). All code, the compose example and the `BENCHMARK.md` run instructions merge first. R0 and R1 run on that commit. The fixture, tally, corpus row and `ROADMAP.md` line are one closing commit after R1.
- **D-14 Research off for the case** (amendment A2): `research_enabled: false`, no research rubric.

## Work order

Each test lands with the code that satisfies it, test first, no red commits. The reviewer gate is per task and blocking.

| Step | Half | What | Why here |
|---|---|---|---|
| 0 | code | Baseline (fast tier, ruff, mypy, replay, line counts) at `f61261ba`; `baseline-records.sha256`; verify items V1 to V5. | A known start. |
| 1 | code | Resolver in `B/paths.py`, conftest autouse fixture, resolver tests. Test command: `uv run pytest tests/test_benchmark_paths.py`. | Everything else reads cases through it. **The caveat's own task.** |
| 2 | code | Call-site swaps, exposure from the root, corpus `store_note`, accept/verify-case/corpus across roots with clean CLI errors; the two iterate-all tests over `iter_case_dirs()`, including `verification/` and `review/` in the isolation proof. Test command: `uv run pytest tests/test_benchmark_corpus.py tests/test_benchmark_cli.py`, then (a separate call) `uv run pytest tests/test_benchmark_cell.py tests/test_grade_oracle.py tests/test_tasks_suite.py tests/test_benchmark_report.py`. | FR-017, FR-018, FR-022, US3. |
| 3 | code | A5 message in `load_case_assets`, with its test. | FR-019. |
| 4 | code | `tier` and `feature` on the mapping. | FR-006, FR-007, A3. |
| 5 | code | `run_tree_check`. | FR-011, FR-012, FR-013. |
| 6 | code | Judge `max_tokens` with the deterministic test; then the real proof on the two stored plans (R3; at most $1). | R3. |
| 7 | code | Raw stream capture in `capture_session`. | R4. |
| 8 | code | Leak guard: script, hook, tests. | FR-021, rule 1. Lands before any store content exists on the machine. |
| 9 | code | `scripts/decomposition_report.py` and its test; the V6 reproduction (strong 10 tasks, 18 edges, chain 7; weak 10, 16, 6). | FR-028, US5. |
| 10 | code | Documents: `BENCHMARK.md` section 5 (private store, how to run a private case, exposure `isolated`, research off, rounds 016/017 status); compose example. | FR-029. |
| 11 | code | Full gates; `verification.md` part 1. **The code half ends here and is merged.** | A6. |
| 12 | author | Store bootstrap (host): `git init`, layout, override file, `.env` line, worker and `kroker-dev` recreated with the mounts; `sdlc benchmark corpus` shows `private store: 0 case(s)`. | |
| 13 | author | Requirement list in `review/requirements.md` (15 to 25 requirements with tier and feature, each traced to a sentence of the draft case text; what is left out). **GATE 2.** | FR-009, SG-7. |
| 14 | author | Case text, manifest, mapping, rubrics; `verification/check_shape.py` (FR-005 to FR-007 bounds). | |
| 15 | author | Reference, then oracle, test by test against the approved list. | FR-003, FR-004. |
| 16 | author | Ablation patches, free-choice variant, `verification/run_checks.py`; three identical runs; `accept --case theatre-box-office --offline`; scratch repository created. Then the first full fast tier with the store bound (between steps 14 and 16, `test_committed_records_match_their_cases` is expected to fail, because the case has no `acceptance.yaml` yet). | FR-010 to FR-013, US1. |
| 17 | author | User reads the case text, list and every test; `review/record.md` written. **Review gate.** | FR-014, FR-015, SG-8. |
| 18 | run | R0: worker rebuilt on the merged commit with `KROKER_COMMIT`, recreated with the store mount and `SDLC_RAW_STREAM_DIR`; smoke; stamp; stream captured. | Gate R0. |
| 19 | run | Worker recreated without `SDLC_RAW_STREAM_DIR`; R1 strong arm, then weak arm; repeats per FR-024. | Gate R1. |
| 20 | run | `accept --case theatre-box-office`; report script; `verification.md` part 2 (aggregates only). | SC-005, SC-006. |
| 21 | close | Closing commit: scrubbed stream fixture under `tests/fixtures/opencode/`, `BENCHMARK.md` corpus row and tally, `ROADMAP.md` line. | A6, R4. |

Steps 4 to 9 depend on steps 1 to 3 (step 4 shares `B/tasks.py` with step 2, and step 6 shares `B/judge.py` with step 3) and may be reordered among themselves. Steps 12 to 17 need the merge of step 11 (the store must be readable through the merged resolver), but they move no repo commit. Step 18 needs step 17.

## Verify items (step 0; a failure is SG-2)

- **V1**: in the `kroker-dev` venv, the text "(provider default)" in pydantic-ai's token-limit error is printed when `max_tokens` is None. If not, step 6's fix is restated before coding.
- **V2**: every reader of case files reaches them through `cases_dir()` (re-run the advisor's grep; no new site since `f61261ba`).
- **V3**: `docker-compose.override.yml` is git-ignored and the worker service merges its `volumes` and `environment`.
- **V4**: Logfire on this machine is local or off, or it does not carry prompt text. If it ships prompts to a cloud project, that is a path for the case text, and the R1 clearance must name it.
- **V5**: what `memory_retains: 0` on the 015 R2 strong-arm summary means (retains failed, or none attempted). If benchmark runs retain into a shared bank, the R1 clearance must name it. A fix is out of scope (inbox task).
- **V6** (checked at step 9, not step 0): `scripts/decomposition_report.py` gives 10 tasks, 18 edges and a longest chain of 7 nodes for `runs/pipeline/bench-cat-cafe-monitoring-1792148180/.../artifacts/plan-v25.json`, and 10, 16 and 6 for `...1792137753/.../artifacts/plan-v24.json`. These are the reviewer's recomputed figures; the spec quotes them.

## Existing tests changed on purpose

| File | Change | Why |
|---|---|---|
| `tests/conftest.py` | autouse fixture unsets `SDLC_PRIVATE_CASES_ROOT` | D-12 |
| `tests/test_benchmark_paths.py` | added cases for the resolver | D-1, D-2 |
| `tests/test_benchmark_corpus.py` | `test_reference_isolation_fr031` and `test_committed_records_match_their_cases` iterate `iter_case_dirs()` (real env, D-12); isolation also covers `verification/`, `review/`; added cases for exposure and `store_note` | FR-022, D-4 |
| `tests/test_benchmark_cli.py` | accept, verify-case and corpus across roots; exposure | D-3, D-4 |
| `tests/test_benchmark_judge.py` | A5 message; `model_settings` recorded | D-6, D-8 |
| `tests/test_tasks_suite.py` | `tier`, `feature`, all-or-none; a mapping found only in the private root | A3, D-3 |
| `tests/test_benchmark_cell.py`, `tests/test_grade_oracle.py`, `tests/test_benchmark_report.py` | one added case each: the swapped reader finds a case that exists only in the private root | D-3 |
| `tests/test_benchmark_offline_checks.py` | `run_tree_check` | D-7 |
| `tests/test_session_capture.py` | env on and off | D-9 |

Tests that must pass **unedited** except for added cases: every existing test of `tests/test_benchmark_paths.py` (the `cases_dir()` pins), `tests/test_load_case_assets.py`, `tests/test_benchmark_stored_scores.py`, `tests/test_benchmark_legacy_records.py`, `tests/test_deveval_verify.py`, `tests/test_cat_cafe_case.py`, `tests/test_golden_case_loads.py`, `tests/test_benchmark_workflow_sequence.py`, and everything under `tests/replay/`. A needed edit to an existing assertion in one of these is SG-1.

## Runbook (run half)

- **Checkout and roots** (A8, 015 GATE 2 item 10): every run-half command (smoke, run, accept, corpus, score) runs from a clean detached worktree of the merged commit. `SDLC_BENCHMARKS_ROOT` and `SDLC_OPS_ROOT` are exported as absolute paths to `runs/benchmarks` and `runs/ops` of the primary checkout, in the CLI's shell and in the worker's, so records and stamps land beside the stored ones. The run gate counts untracked files (`smoke.py:166-174`), and the primary checkout always holds the user's own files, so the primary checkout cannot pass it. Check the roots first: from the worktree, `sdlc benchmark score --case cat-cafe-monitoring --out <outside runs/>` must show the stored runs. If it shows none, the roots are wrong; stop.
- **Store mount** (`docker-compose.override.yml`, both services as D-5; the committed example and `BENCHMARK.md` write `<store>` in place of the host path): worker `<store>/cases:/srv/private-cases:ro` plus `SDLC_PRIVATE_CASES_ROOT: /srv/private-cases`; `kroker-dev` the same mount read-write. Host `.env`: `SDLC_PRIVATE_CASES_ROOT=<store>\cases`.
- **Container working tree**: create the detached worktree on the host and rebind `kroker-dev` to it, as the branch worktree is bound at step 0. The run gate reads commit and dirty state from the installed tree's root (`smoke.py`, `_DEFAULT_SOURCE_ROOT`). The worker is untouched by the rebind.
- **R0**: rebuild the worker image on the merged commit with `--build-arg KROKER_COMMIT=<commit>`; recreate the worker with `SDLC_RAW_STREAM_DIR=/app/runs/ops/raw-stream`; `sdlc benchmark smoke` (gate policy off). Pass: a stamp for the commit and at least one file under `runs/ops/raw-stream/`.
- **Before R1**: recreate the worker without `SDLC_RAW_STREAM_DIR`; check the log; per-case scratch repository `/srv/scratch-repos/theatre-box-office` exists; host `.env` sourced; nothing else running on the machine; V4 and V5 results restated in the clearance request.
- **R1**: `sdlc benchmark run --case <store>/cases/theatre-box-office/case.yaml --arm zai-coding-plan-glm-5.3-flash`, then `--arm zai-coding-plan-glm-5.2`, one at a time. A lost run exits 0, so read the report. A lost arm may be repeated once with its own clearance (FR-024).
- **After R1**: `sdlc benchmark accept --case theatre-box-office` (writes into the store); `python scripts/decomposition_report.py ...` (output to `.workspace/tmp/`); commit the store on the host.
- **Fixture scrub** (step 21): replace host and container paths (`D:\`, `/srv/`, `/tmp/sdlc/worktrees/`, `/app/`), the host user name and session ids; run `memory/scrub.py`'s patterns; grep the result for the user name and `D:\`; read the file once; then commit. The fixture comes from the todo-api smoke run only.

## Stop-guards (binding; clearance only from the orchestrator)

- **SG-1**: an existing assertion in a "must pass unedited" test needs an edit; a `tests/replay/` test changes result; an edit to a "not touched" path appears necessary; a needed name is not in "Names".
- **SG-2**: a verify item V1 to V6 fails.
- **SG-3**: `B/cli.py` would pass 800 lines, or any other touched file 900.
- **SG-4**: the leak guard finds anything, or any private string is seen in a staged or committed file. Stop; never `--no-verify`. Also: a file in `baseline-records.sha256` differs, or `git ls-files runs/` prints anything.
- **SG-5**: a run task, or a model call outside step 6. Nothing paid before the orchestrator's clearance for that batch. Step 6 stops at $1. A second lost run of one arm: stop.
- **SG-6**: the judge proof fails at 16000 tokens. Stop and report usage and finish reason before changing the value or the approach.
- **SG-7**: step 13. No oracle test, reference file or variant is written before the orchestrator confirms that GATE 2 approved the requirement list.
- **SG-8**: step 17. No run of the case before the review record exists for the oracle identity to be run.
- **SG-9**: anything of `oracle/`, `reference/`, `verification/`, `review/`, `tasks.yaml` or `acceptance.yaml` is found in a scratch repository, a run's worktree or a prompt.
- **SG-10**: after R1, an `oracle/` change is proposed (rule 5). Stop and show the defect against the case text first.
- **SG-11**: R1 is about to start on a worker whose log shows raw stream capture is active.

## Risks

| Risk | Mitigation |
|---|---|
| The planner rubric still fails on a larger plan | SG-6; the step-6 proof logs usage. A residual failure is reported, and the case stays gradable (separation does not read stage scores). |
| A larger plan loses runs at plan validation (dangling deps, as PSO) | One repeat per arm (FR-024); the report flags dangling deps; a second loss is `not_assessed` for that arm, reported. |
| The private store is lost (single machine, no off-machine backup by ruling R1) | Its own git history; the user may add a private remote later (outward-facing, the user's call). |
| A private token slips past the guard (paraphrase) | Two layers; the domain word is allowed by R5; the reviewer reads every staged diff; rule 1. |
| `kroker-dev` with the store bound sees it in tests | D-12 autouse fixture. |
| The judge change moves stored scores | It only changes calls that previously failed (no score). `judge_mix_notes` is not triggered. Stored records are not re-judged. |
| Arm-order effects (the second run benefits from the first) | V5 settles whether memory carries over. If it does, the clearance names it and the user decides the order. |
| The weak arm wins | `no_separation` with both means, reported; no repair (R7, rule 5). |

## Follow-ups to file (`.workspace/tasks/`)

- The opencode session parser on the captured fixture (FR-041, plan task 2.8). Size M.
- Benchmark runs and Hindsight memory: whether runs retain into a shared bank and recall across cases and arms (V5). Size M, finding first.
- A pipeline option that fences a task to its `files_hint`, which is the property that would let a case *force* decomposition (A1). Size L, register candidate.
- The `analyze` stage rejects every benchmark run (report F8) and still does. Size M.
- `plan_drift.touched_unhinted` counts build and cache artifacts (`*.egg-info`, `__pycache__`), as seen on cat-cafe T-01. Size S.

## Items for GATE 2

1. **Amendment A1**: "exercises", not "forces". Disagreement on record: the skeptic would add frozen component entry points tested in isolation. This plan does not, because that freezes the seams (FR-002).
2. **The requirement list** (`<store>/cases/theatre-box-office/review/requirements.md`), read in the store, never pasted into a public file. Ruling R6 needs approval before any test.
3. **Amendments A2 to A7** (A4 restated after review: labelling the private case is unsupported this round): research off; `feature` and `tier`; labels, prompt eval and calibration stay on the primary root; FR-019 through the asset check; one commit under test; the restated estimate.
4. **A new pre-commit hook** (`check-private-leak`), always run, which skips when no store is configured.
5. **Two new environment variables**: `SDLC_PRIVATE_CASES_ROOT` and `SDLC_RAW_STREAM_DIR` (off by default), plus `SDLC_JUDGE_MAX_TOKENS` (default 16000 until step 6 fixes it).
6. **Run-infrastructure changes for this round**: the override file gains the store mounts, and the worker is recreated twice, for R0 and before R1. Ruled run-phase actions need user confirmation; each is named in its batch's clearance.
7. **The step-6 judge proof spends real money** (Sonnet, at most $1) under ruling R3, before any run batch.
8. **A correction to a figure put to GATE 1.** The stored cat-cafe chain is 7, not 8 (MA-1). The argument of Q2 is unchanged.
9. **Amendment A8**: the run half runs from a clean detached worktree with absolute roots. The user's untracked files in the primary checkout are left alone.
10. **Committed examples name the store `<store>`**, never the host path.

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind.
- Commits via `git commit -F <msgfile>`; one path per `git add` argument; no heredocs. Every file is written with the Write tool.
- Python runs in `kroker-dev` only. Git, on the repo and on the store, runs on the host.
- Never chain two test runs in one shell call. `addopts` already carries `-q`.
- The reviewer gate is per task and blocking. Private content goes into no tracked file. `.workspace/` is git-ignored (`.gitignore:4`), so briefs and answers there may quote it, but the reviewer reads store files in place rather than copying them.
- Runs follow the standing runbook: compose worker on the live Temporal, rebuilt with its commit, serial, gate policy off, nothing else running.
- The files under `docs/reports/` and the other untracked files in the primary tree are the user's; never edit, add or commit them.

## Complexity Tracking

No constitution or repository-rule violation to justify.
