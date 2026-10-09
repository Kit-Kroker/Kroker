# Baseline: round 013 (T001)

Date: 2026-10-10. Branch `013-benchmark-scoring-output`, base main `35d1b056`
(branch HEAD `3c87abb7` = base + the spec set and a one-line `CLAUDE.md`
change; zero source diff against base, verified with `git diff --stat
35d1b056 HEAD` on the round's paths: empty).

## Environment

- The `kroker-dev` container is NOT running (Docker daemon absent on the
  host). Per the orchestrator exec brief ("Run pytest and the score command
  on the host through the repo venv, or through kroker-dev"), all Python
  below ran on the host through the repo venv (`.venv`, Python 3.13.14,
  `sdlc` importable). One command per shell call throughout.
- `runs/benchmarks` present on the host (46 directories, 111 `.jsonl`
  files). Git on the host, branch checked out at `D:\own\Kroker`.

## Gate results (one command per call)

| Command (venv prefix) | Result |
|---|---|
| `python -m pytest` | 5848 passed, 2 failed, 15 skipped, 263 deselected (787 s) |
| `python -m pytest -m temporal tests/replay` | 32 passed, 21 skipped, 171 deselected (94 s) |
| `python -m pytest -m temporal tests/test_benchmark_workflow_sequence.py` | 5 passed (14 s) |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 1633 files already formatted |
| `python -m mypy` | Success: no issues found in 390 source files (0 errors) |
| `python scripts/check_file_size.py` | exit 0, no output (no file over 1000 lines) |
| `python scripts/check_clauses.py` | 202 clauses declared, 10 untested, 0 dangling (exit 0) |
| `python scripts/aggregate_benchmarks.py --runs runs/benchmarks --out <temp>` | `runs=44 with_data=44 passed=19 records=1331`; output 596,979 bytes kept at `C:\Users\start\AppData\Local\Temp\opencode\013\aggregate-baseline.md` for T013/T017 |
| `git ls-files runs/` | empty |

Pre-existing fast-tier failures (both unrelated to this round, present with
zero source diff against base, so not introduced by it and no contradiction
of research.md):

- `tests/qa/test_qa_task_venv_provisioning.py::test_run_test_suite_skips_provisioning_without_a_python_adapter`
- `tests/test_grade_oracle.py::test_test_command_receives_only_the_filtered_environment`

mypy error count: **0**. Replay result: **32 passed, 21 skipped** (the 21
skips are the baseline; T017 compares against this line).

## Records fingerprint (T001 value; re-run before every commit)

```text
111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831
```

## Name check (data-model §8)

`git grep -nE "<§8 alternation>" -- src tests interfaces scripts` → no hits
(exit 1). Clean: none of the round's new names exists with another meaning.

## Verify items (a) to (i)

**(a) R-2 — derived status equals recorded on the three 012 todo-api runs.**
All three cell records found (one per bench directory):
`bench-todo-api-greenfield-1791472617` (commit `unknown`, code finished,
merge, graded), `...-1791479569` (`b3344416`, code finished, merge, graded),
`...-1791488612` (`b3344416`, code not finished, clarify, not_graded).
Derived (code_finished = a record at analyze/merge/deploy; last stage by
`CELL_STAGE_ORDER`, src/sdlc/benchmarks/models.py:305-320; POST_CODE_STAGES
:323) equals recorded `(code_finished, last_stage)` on all three, and the
run status matches on all three (two graded; one lost — recorded grading
`not_graded` and code not finished both map to `lost` per research R-2's
table). Nuance recorded: on the lost run the recorded grading label is
`not_graded` (the writer's `has_oracle` comes from the case spec, which a
record-only reader does not have) while a record-only derivation of the
label would read `no_oracle` (no oracle-scope record exists for that run);
both map to `lost`, so no figure of the round is affected. Writer body:
src/sdlc/benchmarks/cell.py:51-89 (`summarize_cell`, `grading_status`).

**(b) R-3 — every stored non-drift record's `run_id` shape.** Scanned all
111 `.jsonl` files, every non-drift line: **0** records with a `run_id` not
of the shape `<bench_run_id>/<case>#<harness>[:lead]#<arm>`.

**(c) R-3 — the child id.** src/sdlc/benchmarks/workflow.py:308:
`child_id = f"{bench_run_id}/{cell.cell_id}"` (cell_id =
`case#harness[:lead]#arm`, src/sdlc/benchmarks/models.py:296-299). Exact.

**(d) R-9 — REVISED writers.** src/sdlc/stages/merge/step.py:652-654:
approval path writes `quality_score 1.0`, `outcome REVISED if overrides
else PASS`. Rejections write `FAIL` earlier in the file (fail-closed paths,
src/sdlc/stages/merge/step.py:641). Architecture
src/sdlc/stages/architecture/step.py:264, plan
src/sdlc/stages/plan/step.py:158, deploy src/sdlc/stages/deploy/step.py:176
each write `PASS if gate.approved else REVISED` — `REVISED` exactly when
the gate did not approve. Confirms R-9's rule inputs.

**(e) R-12 — benchmark run summaries.** Exactly two exist:
`runs/pipeline/bench-todo-api-greenfield-1791472617/todo-api-greenfield#opencode#zai-coding-plan-glm-5.2/summary.json`
and the same under `...-1791479569`; each file's own `run_id` field equals
the full record `run_id` (`bench-todo-api-greenfield-<n>/todo-api-greenfield#opencode#zai-coding-plan-glm-5.2`),
and src/sdlc/observability/activities.py:28-29 writes `root / inp.run_id`
(`SDLC_EXPORT_ROOT`, default `./runs/pipeline`) — benchmark summaries sit
one level deeper because the run id contains `/`. 79 non-benchmark
summaries (`bf-intake-*`, `bf-e2e-*`, `demo-*`) sit directly under the
root. No cat-cafe run left a summary.

**(f) R-15 — harness kind of a crew cell's code records.** All 47 stored
crew-probe code records carry `harness='crew'`, `lead_harness=None`
(run ids `crew-probe#crew#crew-glm-5.3`, model `zai-coding-plan/glm-5.3`).
The session itself is captured under the ROLE's CLI:
src/sdlc/crew/activities.py:290 `harness = HARNESSES[inp.harness]` → :349
`capture_session(harness, result._raw_stdout, ...)`; `HarnessKind.CREW` is
deliberately absent from HARNESSES (src/sdlc/core/models.py:30-33,
src/sdlc/harness/registry.py:18-22), and the crew's coder/lead role runs
`harness: opencode` (crew/roles/coder.yaml:5). So: **"harness or lead
harness is opencode" does NOT cover crew records as stored** — the record
identity says `crew`/`None` even when the session was parsed by
OpenCodeHarness. Stored waste-bag records by (harness, lead): `opencode`
214, `crew` 27, `herdr` 51 (the 51 `herdr` lines fail HarnessKind
validation at base and stay skipped — the known pre-existing skips). All
292 bags have `tool_calls == 0`; 27 crew bags included (model_turns 5).
T014's `waste_measured` case list ("a crew record per T001(f)'s finding")
must treat a `crew`-harness zero-tool unmarked bag as not measured, or
SC-011 fails on those 27.

**(g) R-15 — SessionDigest safety.** The only model nesting `SessionDigest`
is `HarnessRunResult` (src/sdlc/harness/models.py:180); it declares no
`model_config` (`extra="forbid"` occurs nowhere in harness/models.py), and
no other src model nests a digest (grep over src: 9 hits, all in
harness/models.py, harness/session.py, benchmarks/models.py where
`WasteBag.from_digest` only reads one). No file under `tests/replay/`
embeds a SessionDigest (grep: no hits). An added optional field is
replay-safe.

**(h) readers of changed outputs.** `git grep -nE "heatmap\.json|HeatmapCell|
build_heatmap|max_density|## Cells|sc-rollup|agreement-matrix" -- src
scripts tests interfaces` — every hit is inside `src/sdlc/benchmarks/`
(heatmap.py, report.py, score.py), inside `tests/`
(test_benchmark_heatmap.py, test_benchmark_heatmap_fix_inflation.py,
test_benchmark_heatmap_render.py, test_benchmark_report.py,
test_benchmark_score.py, test_benchmark_cli.py), or the one comment the
plan names (src/sdlc/eval/verdict.py:226, updated by T008). No reader of
`heatmap.json` *content* anywhere (hits are file names in writers and
existence checks in tests); nothing in `scripts/` or `interfaces/`. No
SG-2.

**(i) tests asserting on `composite`, `_TABLE_HEADER`, `MIN_RUNS`,
`load_run_summaries`.** No test references `_TABLE_HEADER` (private, only
src/sdlc/benchmarks/report.py). The others:

- `tests/test_benchmark_scoring.py`: composite at :46-63 (ranks better
  quality higher), :66-74 (judge-error record excluded), :85, :110-136
  (tasks.yaml does not blend), :153 (row-key separation), :313 (value
  0.52).
- `tests/test_benchmark_report.py`: :50 (`sonnet.composite > opus.composite`),
  :63 ("composite" in markdown), :245 (fixture `composite=0.9`).
- `tests/test_benchmark_models.py`: :75 (CompositeWeights defaults — a
  different model, untouched), :136-138 and :418 (`BenchmarkSummary`
  constructions with `composite=0.88`; the field stays required).
- `tests/test_benchmark_sc_rollup.py`: `MIN_RUNS` import :11 and 17 uses
  (:153-:350), including `assert MIN_RUNS == 5` at :255 — stays true via
  the `runs.MIN_OBSERVATIONS` alias.
- `tests/test_benchmark_evidence.py`: `load_run_summaries` at :5, :89,
  :102, :108, :126 (stays; PIN per T010).

## Line counts (base)

| File | Lines |
|---|---|
| `src/sdlc/benchmarks/models.py` | 379 |
| `src/sdlc/benchmarks/report.py` | 234 |
| `src/sdlc/benchmarks/heatmap.py` | 249 |
| `src/sdlc/benchmarks/scoring.py` | 131 |
| `src/sdlc/benchmarks/score.py` | 213 |
| `src/sdlc/benchmarks/sc_rollup.py` | 259 |
| `scripts/aggregate_benchmarks.py` | 657 |

## Stop-guard review

No Verify item contradicts research.md (SG-2 clear); the name check is
clean; the fingerprint is recorded and `git ls-files runs/` is empty
(SG-5 clear); no forbidden path was touched.
