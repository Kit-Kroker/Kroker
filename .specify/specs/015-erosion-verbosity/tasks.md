# Tasks: Erosion and Verbosity as a Second Quality Axis (round 015)

**Input**: `.specify/specs/015-erosion-verbosity/` (spec.md, plan.md, research.md, data-model.md, contracts/axis.md, quickstart.md)

**Tests**: required (plan "Work order"; contract §7). In every task the failing test is written first and seen red for the stated reason, then the code; both land in that task's one commit, so no commit on the branch is red. A test marked PIN pins behaviour that already exists and must pass on first run; a red PIN is a stop-guard.

**Scope**: user stories 1 to 4, FR-001 to FR-017, SC-001 to SC-006 (report item 2.9, rulings R1-R3).

`B/` = `src/sdlc/benchmarks/`. "Contract" = `contracts/axis.md`. "Names" = `data-model.md`. "R-n" = `research.md`. "Stored test" = `tests/test_benchmark_stored_scores.py`.

## Standing rules for every task

- **Names.** `data-model.md` is the only source of names, field names and fixed strings. Copy; do not retype from memory. A name that is needed and not there is a stop (SG-1).
- **The stored corpus is read-only.** Nothing under an existing `runs/benchmarks/<id>/` is modified, moved, deleted or added. `runs/` is git-ignored, so the check is the **records fingerprint**: on the host, `python -c "import hashlib,pathlib;fs=sorted(pathlib.Path('runs/benchmarks').rglob('*.jsonl'));h=hashlib.sha256();[h.update(str(f.relative_to('runs/benchmarks')).replace(chr(92),'/').encode()+hashlib.sha256(f.read_bytes()).digest()) for f in fs];print(len(fs),h.hexdigest())"`. T001 records its output; it is re-run before every commit and must print the same line. `git ls-files runs/` stays empty. Any score command run during the round carries `--out <a directory outside runs/>`. The smoke run (T012) writes only its own new bench directory.
- **The run is the unit.** The axis rides `Run` objects from `B/runs.py`; no view groups axis records by its own key.
- **No reader guesses.** Absence reads `n/m(<reason>)`, never zero. A figure prints with its count. Under `MIN_OBSERVATIONS` a mean is grey. A mean never crosses a ruleset version.
- **Import discipline.** `B/runs.py`, `B/grid.py`, `B/report.py` import no `temporalio`, no radon, no ast-grep binding. `B/axis.py`'s pure functions (`measure_files`, the constants) import no `temporalio`; only the activity decorator and `axis_record`'s imports may. The tools are imported inside `B/axis.py` only — nowhere else in `src/`.
- **Lockfile discipline.** `pyproject.toml` and `uv.lock` are touched by T002 alone, never again (GATE 2 item 1).
- **Run environment.** Python: the `kroker-dev` container only (`uv run …`), never the host venv (an exec brief may sanction the host repo venv, disclosed as in 013's verification). Git on the branch's worktree: the host only. One test run per shell call, never two chained. `addopts` already has `-q`.
- **Convergence.** A task is not done while its named test files, `uv run ruff check .`, `uv run ruff format --check .` or `uv run mypy` (no new errors against the T001 baseline) are red, or `python scripts/check_file_size.py` reports a file over 1000 lines.
- **Commit**: one per task; subject and body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add` argument; no heredocs; every file written with the Write tool.
- **Reviewer gate** is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N's diff.
- **Read first**: root `AGENTS.md`. Neither `B/` nor `H/` has its own. `src/sdlc/workflows/AGENTS.md` applies to nothing this round edits (the workflow file touched is `B/workflow.py`).
- **Forbidden paths**: everything under `runs/` (T012's new bench dir aside) and `docs/reports/`; every file under `tests/replay/`; everything under `src/sdlc/stages/`, `src/sdlc/workflows/`, `src/sdlc/graph/`, `src/sdlc/dashboard/`; `B/oracle.py`, `B/judge.py`, `B/recorder.py`, `B/record_builder.py`, `B/provenance.py`, `B/paths.py`, `B/drift.py`, `B/task_matrix.py`, `B/error_matrix.py`, `B/calibration.py`, `B/heatmap.py`, `B/heatmap_render.py`, `B/gate_oracle.py`, `B/evidence.py`, `B/sc_rollup.py`, `B/waste_matrix.py`, `B/experiments.py`, `B/agreement_matrix.py`, `B/cell.py`, `B/cli.py`, `B/scoring.py`; `src/sdlc/harness/`; `agents/`; `interfaces/`; every `AGENTS.md`; `CLAUDE.md`; `pyproject.toml` and `uv.lock` (T002 alone); every script; earlier `.specify/specs/*` and `.specify/bugs/*`; the user's uncommitted and untracked files in the primary checkout. The tuples `CANONICAL_STAGES` and `CELL_STAGE_ORDER` are not edited.
- **Tests that must pass unedited**: everything under `tests/replay/`; `tests/test_benchmark_cell.py`; `tests/test_benchmark_workflow.py`; `tests/test_benchmark_legacy_records.py`; `tests/test_benchmark_heatmap.py`; `tests/test_benchmark_heatmap_render.py`; `tests/test_calibration_render.py`; `tests/graph/test_graph_node_types.py`; `tests/test_dashboard_graph_wire.py`; `tests/test_run_state_query.py`; `tests/test_opencode_normalise.py`; `tests/test_session_capture.py`; `tests/test_session_models.py`.
- Line numbers are as of main `c3f6319c`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A name or rule is needed that the spec set does not define; the T001 name check finds a hit; an edit to a forbidden path or to a "must pass unedited" test appears necessary; any test under `tests/replay/` changes result against the T001 baseline. Do not edit a test to pass.
- **SG-2** A T001 "Verify" item fails; T001's grep finds a reader of the totals line or `grid.json` content the plan does not name; code does not reproduce a figure of contract §1 on the fixtures or of contract §4 on the stored corpus. A stored figure is never edited to match the code.
- **SG-3** Any file would pass 800 lines.
- **SG-4** T012: the smoke run is not launched without the orchestrator's explicit go, never in parallel with live pipeline runs, and only per the launch runbook (dedicated temporal server, clean worktree, dedicated scratch repo). If no run can be had, T012 is not done and SC-006 is reported open.
- **SG-5** The records fingerprint differs from the T001 value (T012's new bench dir aside — recompute excluding it), `git ls-files runs/` prints anything, or a score was written under `runs/`.
- **SG-6** A `temporal` test named in a gate reports "deselected"; the stored test reports "skipped" in T011; a test marked RED passes before its code; a PIN is red.
- **SG-7** An import the "Import discipline" rule forbids appears necessary, or the pure measurement would need the network.

## Phase order

| Phase | Purpose | Story | Plan steps | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | known start, assumptions checked | — | 0 | 1 |
| 2 Foundation | dependencies; the bag and the record shape | all | 1 | 2 |
| 3 The writer | measure, rules, activity, wiring | US1, US4 | 2, 3, 4 | 3 |
| 4 The reader | runs/grid/report/score; the negative proof | US2, US3 | 5 | 3 |
| 5 Close-out | documents, gates, verification | — | 6, 7 | 2 |
| 6 Live proof | the smoke run | SC-006 | 8 | 1 |

Phases 2 and 3 block everything. Phase 4 depends on phase 3 (the reader reads what the writer wrote, proven on in-memory records). Phase 6 depends on phase 5 and the orchestrator's go.

---

## Phase 1: Setup and baseline (no source edits)

- [x] T001 Create branch `015-erosion-verbosity` from current main in the worktree the orchestrator names; confirm `kroker-dev` is bound to that tree and that `runs/benchmarks` is visible inside it (`ls runs/benchmarks | head`). If main has moved past `c3f6319c`, on the host run `git diff --stat c3f6319c HEAD -- src/sdlc/benchmarks src/sdlc/worker.py BENCHMARK.md pyproject.toml uv.lock` and report anything it prints (SG-1). Run, one per call, in the container: `uv run pytest`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: `python scripts/check_file_size.py`; `python scripts/check_clauses.py` (always exits 0 — read it). Compute the records fingerprint and record its line. Do the name check of Names §8 (`git grep -nE "AxisBag|AxisInput|measure_code_axis|measure_files|axis_record|AXIS_EROSION_THRESHOLD|RULESET_VERSION|axis_measured|axis_not_measured|mean_erosion|mean_verbosity|015-quality-axis" -- src tests interfaces scripts`): every hit is SG-1. Then the Verify items, each recorded with file:line evidence:
  (a) `B/workflow.py` near line 456 calls `finalize_benchmark_report` last, and nothing between the cell-record write (near line 411) and it deletes the integration branch or the scratch worktree;
  (b) `B/oracle.py` near line 269 forms the branch as `f"sdlc/{inp.run_id}/integration"` and near line 273 adds the detached worktree from `inp.repo_url`;
  (c) `tests/test_benchmark_workflow_sequence.py` near line 106 registers `stub_grade_oracle` in a stub worker — the pattern T006's stub follows;
  (d) `src/sdlc/worker.py` near line 177 lists the benchmark activities — the two places T006 edits;
  (e) grep `src`, `scripts`, `tests`, `interfaces` for readers of the totals line (search `runs started:`) and of `grid.json` content; list every hit. A hit outside `B/`, `tests/` and the places plan.md names is SG-2;
  (f) `tests/test_judge_literal.py` `EMITTED_JUDGES` is the pinned judge set — confirm `"axis"` is absent today;
  (g) confirm no stored record carries `scope: "axis"` (grep the corpus once, read-only): the negative proof's premise;
  (h) `uv run python -c "import radon"` and `uv run python -c "import ast_grep_py"` both fail at base — record the failure (the tools land in T002).
  Write `.specify/specs/015-erosion-verbosity/baseline.md`: base sha, every command's result and counts, mypy error count, the replay result, the fingerprint line, name-check outcome, items (a) to (h), and line counts of `B/models.py`, `B/runs.py`, `B/grid.py`, `B/workflow.py`, `B/report.py`. Any item that contradicts research.md is SG-2: stop and report before committing anything else. Commit (spec set + baseline).

**Checkpoint**: baseline.md exists with every gate's result and items (a) to (h); no source file differs from the base.

---

## Phase 2: Foundation — dependencies and the record shape (blocks every story)

- [ ] T002 The round's only lockfile touch. RED first: none (a dependency pin has no failing test; the proof is the import check). Edit `pyproject.toml` `[project.dependencies]`: add `radon==6.0.1` and `ast-grep-py==0.50.0` (alphabetical, one line each). In the container: `uv lock`, then `uv sync --frozen --extra dev`. Then the import proof, one per call: `uv run python -c "import radon; print(radon.__version__ if hasattr(radon,'__version__') else 'ok')"` and `uv run python -c "import ast_grep_py; print('ok')"` — if the binding's module name differs, discover it (`uv run python -c "import importlib.metadata as m; print(m.version('ast-grep-py'))"` then read its top-level modules) and record the exact import line in the commit body. A failure of either import on the container's Python 3.13 is SG-2 (research R-8's residual): stop, report, do not work around. `uv run pytest` (fast tier) must match the T001 counts. Commit `pyproject.toml` + `uv.lock` only.

- [x] T003 The bag and the record shape. RED first in `tests/test_benchmark_models.py`: `AxisBag` with figures validates and serialises round-trip; the XOR invariant rejects a bag with both `erosion` and `reason` set and a bag with neither (a `model_validator`); a `BenchmarkRecord` with `scope=AXIS` and `axis=<bag>` validates; an axis record's `quality` with `score=None, judge="axis"` validates. RED reason: `AxisBag` does not exist. Also PIN-edit `tests/test_judge_literal.py`: add `"axis"` to `EMITTED_JUDGES` with the round's comment; the existing parametrised body then proves `QualityScore(judge="axis")` validates once the literal lands. Then in `B/models.py`: `BenchmarkScope.AXIS = "axis"`; the `"axis"` literal in `JudgeKind` (with a comment naming this round); `class AxisBag(BaseModel)` exactly as Names §1 (every field, the writer/reader reasons as a comment block, the XOR `model_validator`); `BenchmarkRecord.axis: AxisBag | None = None` beside `cell`. Confirm a stored record still validates (the stored test, unedited, stays green). Commit.

**Checkpoint**: the record shape exists; every pre-existing record and test still loads; US1's storage is ready.

---

## Phase 3: The writer — measure, rules, activity, wiring (delivers US1, US4)

- [x] T004 The measurement core. RED first in new `tests/test_benchmark_axis.py`, on two new fixture trees written under `tests/fixtures/axis/`: `mass_split/` (hand-computed: functions whose CC×sqrt(SLOC) masses split exactly 50/50 across the CC>10 line — e.g. two flat functions and one nested monster, the numbers in the test's comment) and `plain/` (no slop, no over-threshold function). RED cases: `measure_files` on `mass_split` returns `erosion == 0.5` exactly with `functions_total`/`functions_over`/`mass_total`/`mass_over` as hand-counted; on a tree with zero functions `erosion is None`; determinism — `measure_files` twice on the same tree returns equal figures (SC-002); sorted-path order (two trees with equal content under different names measure equal). Then create `B/axis.py`: `AXIS_EROSION_THRESHOLD = 10`, `RULESET_VERSION = "1"`, `AxisInput` (Names §1), and `measure_files(paths) -> AxisBag` — radon `cc_visit` per file for CC and per-function SLOC (`end_lineno - lineno + 1`), mass and erosion per contract §1.1, the bag's measurement fields filled, `reason=None`, `head=None` (the activity fills it). Rules flagged lines return 0 here (the rule set lands in T005; the field is still populated). No `temporalio` import at module scope (SG-7). Commit.

- [x] T005 The rule set. RED first in `tests/test_benchmark_axis.py`: a `slop/` fixture tree (hand-counted: one `except Exception: pass`, one bare `except:`, one `print(` call, one `breakpoint()`, one nested ternary, a quad-nested if — each on its own line, no overlaps unless the test says so) whose `verbosity` equals hand-counted flagged / hand-counted non-blank LOC; a tree with a rule-file that fails to compile makes `measure_files` return `reason="measurement failed: rule <id>"` with both figures None. Then write the six rules as YAML under `src/sdlc/benchmarks/rules/verbosity/` (ids exactly `except-pass`, `bare-except`, `print-call`, `debugger-call`, `nested-ternary`, `if-deep-4` — Names §4), and extend `B/axis.py` with the loader (sorted by id) and the ast-grep application: compile the Python language once, apply each rule, union the match spans. A rule that fails to load or compile fails the measurement with its id in the reason — never silently zero flags. Commit.

- [x] T006 The activity and the wiring. RED first in `tests/test_benchmark_workflow_sequence.py`, with a `stub_measure_code_axis` registered beside `stub_grade_oracle`: (i) a graded cell ends with one axis record after the cell record, `scope=AXIS`, figures from the stub, `head`/`tools`/`ruleset_version` populated by the stub's bag; (ii) a lost cell (`code_finished=False`) writes an axis record with `reason="code stage did not finish"` and the stub's checkout never runs; (iii) a cell of a case with `language="go"`… — use `language="typescript"` if `go` is not a `ToolchainKind` — writes `reason="language not python"`; (iv) a cell whose repo has no integration branch (stub returns the reason) writes `reason="integration branch absent"`. RED reason: no `measure_code_axis` activity exists. Then in `B/axis.py`: `measure_code_axis(AxisInput) -> AxisBag` — the fail-safe activity per contract §2.3 (precondition order, its own `git worktree add --detach` from `repo_url` at `sdlc/<run_id>/integration`, `git diff --name-only <base>...HEAD` filtered to `*.py`, `measure_files`, `head` from `git rev-parse HEAD`, try/except to `measurement failed: <detail>`, worktree removed in `finally`); and `axis_record(...)` the pure builder per Names §3 (identity and provenance fields identical to the cell record's). In `B/workflow.py`: `AXIS_ACT` (Names §3), and after the cell-record write a `workflow.patched("015-quality-axis")` block that calls the activity with `AxisInput(...)` (the five oracle fields + `code_finished=progress.code_finished`) and records `axis_record(...)` through `record_benchmark`; imports passed through. In `src/sdlc/worker.py`: import and register `measure_code_axis` (the two places, item (d)). The unpatched branch is byte-identical to base (the diff shows the block only inside the `if`). Commit.

**Checkpoint**: a benchmark run (sequence test) writes one axis record per started cell; US1 and US4 are delivered in-memory.

---

## Phase 4: The reader — runs, grid, totals; the negative proof (delivers US2, US3)

- [x] T007 The run model side. RED first in `tests/test_benchmark_runs.py`: a run whose records carry one AXIS record gets `Run.axis` equal to its bag; a run with two takes the last; a run with none has `axis=None`; a group of measured runs of one version gets `mean_erosion`/`mean_verbosity` over the measured runs and `axis_n`; the same group with two `ruleset_version` values withholds both means and lists `axis_versions`; `Totals` counts `axis_measured`/`axis_not_measured` over runs (absent record = not measured). RED reason: `Run.axis` does not exist. Then in `B/runs.py`: `Run.axis` (the last AXIS-scope record's bag), the `Group` and `Totals` fields per Names §1, means withheld on version mix. `B/runs.py` imports nothing new (SG-7). Commit.

- [x] T008 The grid and the totals line. RED first in `tests/test_benchmark_grid.py`: the row renders `0.42` figures in the two columns after the code-score columns and `n/m(no record)` for an absent bag; the group header renders `erosion 0.42 (3)` and `verbosity 0.18 (3)` after the all-pass figure, grey-marked under five measured runs, withheld-with-versions when `axis_versions` has two entries. RED first in `tests/test_benchmark_report.py`: `_totals_line` gains exactly the clause `axis: 2 measured, 16 not measured` and changes no other word; `render_markdown` output mentions erosion nowhere outside the grid section. RED first in `tests/test_benchmark_score.py`: `grid.json` rows carry the axis figures and absences; no other output file of the score (`report.md`, `heatmap.*`, `gate-oracle.*`, the matrices) contains the string `erosion` (FR-011 checked by absence). Then in `B/grid.py`: the two `GridRow` fields, `_row_texts` columns, `_figures_pairs`/`_figures_text` header figures, and the JSON/HTML renderers' fields; in `B/report.py`: the `_totals_line` clause. `B/grid.py` and `B/report.py` import nothing new (SG-7). Commit.

- [x] T009 The negative proof on the stored corpus. RED first in the stored test (reads `runs/benchmarks` in place, read-only): for cat-cafe-monitoring and todo-api-greenfield, every run row reads `n/m(no record)`; `axis_measured == 0` and `axis_not_measured == runs started` per case; the totals line carries the clause with those numbers; and one pinned 013 figure per case (the cat-cafe 18/10/8 line; the todo-api three-group figures) is unchanged. RED reason: the rows/fields do not exist yet (T007/T008 landed them; if this test is written before those, it is red for the same reason — write it after). Then verify green, run the fingerprint on the host (SG-5), and commit.

**Checkpoint**: quickstart §2 holds on the stored corpus; US2 and US3 are delivered.

---

## Phase 5: Close-out — documents and gates

- [x] T010 Documents. Edit by finding each passage by its text (plan "Document changes"): `BENCHMARK.md` — new §4.5 (the two definitions as contract §1 states them, measured = the produced diff, the rule set and its six v1 rules with their ids, cloned lines out and why, the not-measured reasons, the axis never enters quality/composite/gate figures) and the outputs passage (the two grid columns, the totals clause); `README.md` — the scoring passages gain the axis columns and what not-measured means; `ARCHITECTURE.md` — the benchmarks package listing gains `axis` and `rules/verbosity/`; `ROADMAP.md` — 2.9 landed, "Last verified" line. Behaviour and clauses in the same diff: the passages describe what T003-T009 landed. Commit.

- [x] T011 Full gates and the stored-record validation. Run quickstart §1 row by row, one command per call; then §2 (the three score commands with `--out` outside `runs/`, the fingerprint before and after, `git ls-files runs/`); then §3 (determinism, the fixture figures, the timing bound on a case-sized tree — under 30 s, recorded). Write `.specify/specs/015-erosion-verbosity/verification.md`: SC-001 to SC-005 with the evidence, SC-006 marked open pending T012, FR-017's smoke half open, every deviation disclosed. Commit.

**Checkpoint**: the round's code is complete and verified; only the live proof remains.

---

## Phase 6: The live proof — the smoke run (SG-4)

- [x] T012 **Stop first (SG-4)**: report to the orchestrator and wait for the explicit go; confirm no live pipeline runs. Then per the launch runbook: dedicated temporal server (7234), a clean worktree of the branch, a dedicated scratch repo; launch one `todo-api-greenfield` cell. After the run: the bench dir's cell `records.jsonl` contains one axis record with figures (erosion and verbosity not None, `head`/`tools`/`ruleset_version` populated); `sdlc benchmark score --bench <id> --out <outside runs/>` shows them on the row and in the group header; the case's oracle and code figures are in their known envelope; the run's opencode waste counters are non-zero (013's parser follow-up closed live). Recompute the fingerprint excluding the new bench dir (SG-5). Append the addendum to `verification.md` (bench run id, the figures, SC-006 closed). Commit (verification.md only).

**Checkpoint**: SC-006 closed; the round is done.

---

## Dependencies

- T001 blocks everything (branch, baseline, fingerprint).
- T002 blocks T004/T005 (the tools) and nothing else; T003 blocks T004's record assertions? — no: T004 tests bags in memory; T003 blocks T006 (the record shape) and T007 (the reader reads bags).
- T004 → T005 (rules extend `measure_files`) → T006 (the activity measures with rules).
- T006 → T007 → T008 → T009 (each reads the previous layer).
- T009 → T010 → T011 → T012.

## Parallel opportunities

- T002 and T003 touch disjoint files (lockfile vs models/tests) and can run in parallel.
- T004's fixture trees and T005's rules are separable up to the union point; a second executor can draft the six YAML rules while T004 lands.
- T010's four documents are four files; parallelisable once T009 is green.

## Implementation strategy

MVP is phase 3: after T006, a benchmark run carries the axis (US1/US4) — the figures exist on records even before any view shows them. Phase 4 makes them visible and honest (US2/US3). The round may pause after T011 (everything verified except the live proof) and resume T012 when the machine is free; SC-006 is the only clause that waits. If T012 cannot happen, the round closes with SC-006 and FR-017's smoke half reported open, exactly as the spec's implementation strategy allows.

## Requirement coverage

| Requirement | Task |
|---|---|
| FR-001, FR-002, FR-005, FR-006, FR-007 | T006 |
| FR-003, FR-004 | T004, T005 |
| FR-008, FR-009, FR-010, FR-014 | T007, T008 |
| FR-011, FR-012, FR-013 | T008, T009 |
| FR-015 | T009, T011 |
| FR-016 | T010 |
| FR-017 | T002 (tools), T012 (the run) |
| SC-001, SC-002, SC-005 | T004, T005, T011 (§3) |
| SC-003, SC-004 | T009 |
| SC-006 | T012 |
