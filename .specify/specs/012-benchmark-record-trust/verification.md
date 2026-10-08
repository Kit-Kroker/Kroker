# Verification: round 012 (T023 §1–§2; §3 pending the smoke run)

Tree: commit `9761c729` (T023 working tree, identical content). Date:
2026-10-08. All Python rows in `kroker-dev` with this worktree bound at
`/app`; binding confirmed first (md5 of `src/sdlc/benchmarks/models.py`
host = container = `b747689d295e7cc813afc66f551d3566`). One suite per
shell call. Baseline numbers from `baseline.md` (T001, at `7f5191d0`
plus the authorized pins-fix `378a2345`).

## §1 Automated gates

| Where | Command | Result | vs baseline |
|---|---|---|---|
| container | `uv run pytest tests/test_benchmark_paths.py tests/test_benchmark_provenance.py tests/test_benchmark_cell.py tests/test_benchmark_legacy_records.py tests/test_benchmark_record_builder.py tests/test_aggregate_benchmarks.py` | **76 passed** in 63.25 s | all green, none deselected |
| container | `uv run pytest tests/test_benchmark_judge.py tests/test_benchmark_cli.py tests/test_benchmark_recorder.py tests/test_benchmark_scoring.py tests/test_benchmark_report.py tests/test_benchmark_workflow.py tests/test_grade_oracle.py tests/test_calibration_render.py` | **128 passed, 4 deselected** in 94.53 s | green; the 4 deselected are the slow-marked subset, run in the slow row below |
| container | `uv run pytest tests/code tests/review tests/qa tests/analyze tests/merge` | **242 passed, 1 skipped, 4 deselected** in 72.76 s | green; the skip is the documented §5.8 qa-lens-unreachable case, the 4 deselected are crew-marked |
| container | `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | **5 passed** in 28.30 s | non-zero passed, not deselected (T013's suite) |
| container | `uv run pytest -m slow tests/test_grade_oracle.py` | **4 passed, 13 deselected** in 153.78 s | baseline 1 passed; now 4 slow tests (T016) — non-zero, not deselected |
| container | `uv run pytest` | **3 failed, 5849 passed, 12 skipped, 263 deselected** in 624.74 s | baseline 13 failed / 5674 / 11 / 255. The 3 failures are the same three git-reading tests as the baseline (in-container git cannot read the bind-mounted worktree; recorded there). The baseline's ten registry-mirror failures were fixed by the authorized pins-fix `378a2345`. Passes +175 (this round's new tests, and only those), skips +1 (documented), deselected +8 (new opt-in tests) |
| container | `uv run pytest -m temporal tests/replay` | **32 passed, 21 skipped, 171 deselected** in 106.76 s | identical to baseline (32/21/171 in 148.91 s) |
| container | `uv run ruff check .` | **All checks passed** | clean |
| container | `uv run ruff format --check .` | **1701 files already formatted** | clean (baseline 1684 files; count grew with the round's new files) |
| container | `uv run mypy` | **Success: no issues found in 390 source files** | no new errors (baseline 387 files, 0 errors; +3 modules this round) |
| host | `python scripts/check_file_size.py` | **exit 0, no output**; `src/sdlc/stages/code/step.py` at 997 lines (ceiling 1000, SG-3 margin 3) | clean |
| host | `python scripts/check_clauses.py` | **exit 0; 202 clauses declared, 10 untested, 0 dangling** — the 10 are the identical pre-existing baseline list (ARCH-1.4, CODE-1.6/1.7, MERGE-1.6–1.9, PLAN-1.4, RETRO-1.6, REVIEW-1.6) | no new untested clause, none dangling |

## §2 Checks on stored data (no run)

| Step | Result |
|---|---|
| `uv run python -m sdlc.cli benchmark score --case cat-cafe-monitoring` (container) | **completes**. Environment note: invoked with the same four dummy API keys `tests/conftest.py` sets, because the registry loader fails closed without them; scoring is read-only over the stored records, no model is called. The regenerated report at `runs/benchmarks/_case/cat-cafe-monitoring/score/report.md` has a `## Pre-012 records (untrusted)` section (12 rows, all pre-012), the line `includes 653 pre-012 records (untrusted)`, **no `## Cells` section** (grep count 0) and an empty 012 header table — no 012 rows anywhere. Score outputs are derived artifacts; the fingerprint below covers only `*.jsonl` records and is unchanged. |
| records fingerprint + `git ls-files runs/` (host) | `108 7d335188d0a0a47e0234a9a3cea64f3e42d80e958996a4e3fb89e2bb76a4306c` — equals the T001 baseline; `git ls-files runs/` prints nothing (exit 0) |
| `f3-reproduction.md` | outcome recorded: **not reproduced** — the direct sequence plus every environment seam was tried; the residue hypothesis (pruned by a venv re-sync) explains but can no longer be demonstrated; no cause outside the oracle's environment, SG-4 not fired |
| `gate-diagnosis.md` | a cause per gate and a decision per gate: merge (five of six subjects) — absolute `lint_clean`/scoped-test checks failing on genuine produced-code defects, right-reasoned rejections; the sixth — the advisory path acting on analyze's traceability; analyze — exact-`(task_id, criterion)`-text tracing with the analyst report not stored. Decision (orchestrator, SG-5): both gates stay rejections, no not-evaluated gate, causes on the record from T020; T021 carried the contract lines |

## §3 The validation smoke run

Run (the round's one permitted run, on the orchestrator's go of
2026-10-08; dedicated Temporal `kroker-temporal-bench` at
host.docker.internal:7234, worker in `kroker-dev` with cwd /app):

- run id: `bench-todo-api-greenfield-1791472617`
- cell: `todo-api-greenfield#opencode#zai-coding-plan-glm-5.2` (one arm)
- started 15:16:57Z, finished ~17:04Z; 41 records, 7 tasks, all gates off
- `KROKER_COMMIT=b3344416` was set on the run/CLI shell per the go; the
  records came out `unknown` — see row 2.

| Check | Result |
|---|---|
| number of `*.jsonl` files | **PASS — exactly 1** (`todo-api-greenfield#opencode#zai-coding-plan-glm-5.2.jsonl`) |
| `kroker_commit` on every line | **MISS — `unknown` on all 41 lines** (identical, but not the branch head). Cause: the override was exported on the CLI shell; `resolve_provenance` runs as a worker-side activity (`benchmarks/workflow.py:306`), so it read the WORKER's environment, which did not carry `KROKER_COMMIT`. The quickstart's "the worker must know the commit" is the operative reading; the value is resolved once per run and memoized in workflow state, so this run could not recover it mid-flight |
| `prompt_sha` on every line | **PASS** — 64-hex for every prompted role, `none:...` otherwise, no empty value |
| `arm` and `cell_id` | **PASS** — one distinct pair on all 41 lines |
| clarify / architecture `quality.score` | **MISS — `judge: "error"`, score null on both.** The cross-family judge (`google:gemini-3.5-flash`) failed during the run; the judge never raises by design and recorded not-measured. A standalone probe after the run (same container, same key from /app/.env, resolve_model + Agent.run_sync) succeeds, and GEMINI_API_KEY was in the worker's env (worker.py `load_dotenv()`). First attributed to a transient environment failure — **refuted by the re-run (§3b): the failure is deterministic and 012-side (async activity calling the sync judge on the event loop); see §3b for the proof** |
| code/qa/review `speed` per attempt | **PASS** — all 7 tasks: code.ended = qa.started, qa.ended = review.started (the T017 partition is exact on real data); every record inside its attempt |
| review `cost.input_tokens` | **PASS** — present on every review record |
| the cell record | **PASS** — `grading: graded`, `last_stage: merge`, `completed: true` |
| analyze / merge records | **PASS** — analyze FAIL names its cause (`11 untraced criterion(s): TASK-1: ...`); merge FAIL names the absolute blockers with details (`build_integration_green`, `lint_clean`, head test run exit 4) — both code-inspecting causes exactly as gate-diagnosis.md predicted; no benchmark-only condition |
| `report.md` | **PASS** — exactly one `## Cells` section, no pre-012 section |

Also recorded: the oracle graded the cell **1.0** (6/6 oracle_task rows
at 1.0 — full pass of the held-out suite in the per-grade isolated
venv). `SDLC_MEMORY_BASE_URL` points at the compose hostname
`http://hindsight:8888`, unresolvable in the standalone bench container:
34 retain items and 1 reflect exhausted their retries on DNS errors —
tolerated by design (the workflow continued; memory retention simply
absent), no stage record affected.

Fingerprint after the run: **`109
bc953e00ec51b5715adc9bbc2a97e1979f121ff0da1d0e4c3e9ead707cc488ff`** —
the permitted change from `108 7d335188...`, exactly the new cell's one
jsonl file (score outputs are not records). `git ls-files runs/` still
prints nothing.

**Verdict (first run): the run completed and 8 of 10 rows pass; the exit
criterion is NOT met** (SC-002's commit row missed on the worker-env
placement, SC-001's rubric row missed on what the first report called a
transient judge failure). No second run started; per SG-7 the re-run
decision went to the orchestrator.

### §3b The re-run (orchestrator-cleared, SG-7 retry)

Cleared with the environment fixed on the WORKER process:
`KROKER_COMMIT=b3344416`, `KROKER_TREE_DIRTY=0`,
`SDLC_MEMORY_BASE_URL=http://host.docker.internal:8888` (memory kept
on, exercised through the real path — zero DNS errors this run, where
the first run burned 35×5 retry attempts). Everything else identical.

- run id: `bench-todo-api-greenfield-1791479569`, 17:12:49Z–18:37Z,
  41 records, 7 tasks, gates off.

| Check | Result |
|---|---|
| `*.jsonl` files | **PASS** — exactly 1 |
| `kroker_commit` | **PASS — `b3344416` on all 41 lines**, `tree_dirty: false` |
| `prompt_sha` | **PASS** — 64-hex / `none:<reason>`, no empty |
| `arm` / `cell_id` | **PASS** — one pair on all lines |
| clarify / architecture `quality.score` | **MISS — `judge: "error"` again, deterministically.** Root cause now PROVEN and it is 012-side, not transient: `judge_artifact` is an `async def` activity that calls the sync `_judge_sync` → `agent.run_sync` **on the running event loop** → `RuntimeError: This event loop is already running` (pydantic-ai run_sync wraps `run_until_complete`), swallowed by the judge's broad except into `judge="error"`. Reproduced standalone three ways: (1) the exact activity inputs recovered from Temporal history judge cleanly in a fresh process (clarify 1.0, architecture 0.94); (2) the same input through `_judge_sync` called from inside `asyncio.run` reproduces `judge='error'`; (3) a bare `agent.run_sync` inside a running loop raises the RuntimeError above. The path never executed pre-012 (the judge never found the case rubrics — the gap T003/T004 closed), which is why it was never seen. Candidate fix, one line: `judge_artifact` runs `_judge_sync` via `asyncio.to_thread`. Not applied: code changes need a task and the reviewer gate |
| code/qa/review timings | **PASS** — exact partition on all 7 tasks |
| review `input_tokens` | **PASS** |
| cell record | **PASS** — `graded`, `last_stage: merge`, `completed: true` |
| analyze / merge | **PASS** — analyze names 10 untraced criteria; merge names `lint_clean` (3 introduced) with details — code-inspecting causes, no benchmark-only condition |
| `report.md` | **PASS** — one `## Cells` section, no pre-012 section |

Oracle again **1.0** (full held-out pass in the per-grade venv). First
run's directory kept as evidence (per the ruling). Fingerprint after
the re-run: **`110
8695b5956712df5aad4ecb0061a95934472c1debed8a0ddef400f1be7d1cfea1`** —
the two permitted additions (one jsonl per run directory); `git ls-files
runs/` empty.

**Verdict (re-run): 9 of 10 rows pass. SC-002 met on the re-run.
SC-001's rubric row is not met, and the miss is now a proven 012-side
defect (async/sync judge seam), not an environment condition.** The
fix and any third run belong to the orchestrator.
