# Verification — round 013 benchmark scoring output (T017)

Date: 2026-10-10. Branch `013-benchmark-scoring-output` at T016 (`325f06de`)
for every command below. Baseline: `baseline.md` (T001).

**Environment disclosure.** The Docker daemon was down (kroker-dev
unavailable), so every Python gate and score command ran on the host through
the repo venv (`D:\own\Kroker\.venv\Scripts\python.exe`), as the exec brief
sanctions ("Run pytest and the score command on the host through the repo
venv, or through kroker-dev"). One command per shell call throughout; output
tailed.

## Quickstart §1 — automated gates

| Where | Command | Result | Baseline comparison |
|---|---|---|---|
| row 1 | pytest tests/test_benchmark_runs.py tests/test_benchmark_grid.py tests/test_benchmark_gate_oracle.py tests/test_benchmark_stored_scores.py | 108 passed | green; the stored test reports **passed**, not skipped (no `s` in the progress) |
| row 2 | pytest tests/test_benchmark_heatmap.py tests/test_benchmark_heatmap_render.py tests/test_benchmark_scoring.py tests/test_benchmark_report.py tests/test_benchmark_score.py tests/test_benchmark_evidence.py tests/test_benchmark_sc_rollup.py | 150 passed | green |
| row 3 | pytest tests/test_benchmark_waste_bag.py tests/test_benchmark_waste_matrix.py tests/test_benchmark_agreement_matrix.py tests/test_benchmark_experiments.py tests/test_benchmark_cell.py tests/test_benchmark_models.py tests/test_benchmark_legacy_records.py tests/test_aggregate_benchmarks.py | 142 passed | green |
| row 4 | pytest tests/test_opencode_normalise.py tests/test_session_capture.py tests/test_session_models.py tests/test_claude_stream_normalise.py | 21 passed | green; **the captured-stream test is not present** — T015 is parked (SG-4), so no fixture exists and none may be created; this clause is red and owned by T015 (FR-041 open) |
| row 5 | pytest tests/graph/test_graph_node_types.py tests/test_dashboard_graph_wire.py tests/test_run_state_query.py tests/test_calibration_render.py tests/test_e36_imports.py | 115 passed | green; no file edited this round (they import `CANONICAL_STAGES`) |
| row 6 | pytest (fast tier) | 6041 passed, 2 failed, 15 skipped, 263 deselected (638 s) | the 2 failures are exactly the pre-existing baseline pair (`tests/qa/test_qa_task_venv_provisioning.py`, `tests/test_grade_oracle.py`, baseline.md); the count differs from the baseline only by this round's added/removed tests |
| row 7 | pytest -m temporal tests/replay | run 1: 1 failed (`test_graph_golden.py::...[budget_arch_reject-unsandboxed]`), 31 passed, 21 skipped; run 2: **32 passed, 21 skipped** | the T014-disclosed concurrent-load flake (retention-timer vs completion race, a different unsandboxed golden param each time, green in isolation and on rerun); the row's result is the rerun, identical to the baseline |
| row 8 | pytest -m temporal tests/test_benchmark_workflow_sequence.py | 5 passed | green, non-zero, not deselected |
| row 9a | ruff check . | All checks passed | clean |
| row 9b | ruff format --check . | 1642 files already formatted | clean |
| row 9c | mypy | Success: no issues found in 394 source files | 0 errors, the baseline count |
| row 10 | python scripts/check_file_size.py | exit 0 | no file over 1000 lines |
| row 11 | python scripts/check_clauses.py | 202 clauses declared, 10 untested, 0 dangling | identical to baseline.md line 29; no new `clause with no test` line |

## Quickstart §2 — the score on stored records

All three commands ran with `--out` under
`C:\Users\start\AppData\Local\Temp\opencode\013\qs2\` (outside `runs/`),
one per call, exit 0 each.

| Check on cat-cafe | Expected | Seen | Criterion |
|---|---|---|---|
| totals line | 18 started, 10 graded, 8 lost (research 4, clarify 4), 8 discarded oracle records, 18 statuses derived | `runs started: 18, graded: 10, lost: 8 (clarify: 4, research: 4), grading failed: 0, no oracle: 0, discarded oracle records: 8, statuses derived: 18` | SC-001 |
| first section | run grid: one group, 18 rows, header mean 0.708, all-pass 1/10 | `## Runs` first; one `###` group; 18 table rows; `mean 0.708 ... all-pass 1/10` | SC-002, FR-007 |
| arm on the group | `zai-coding-plan-glm-5.2`, recovered and untrusted | `... / zai-coding-plan-glm-5.2 / commit not recorded untrusted (pre-012) arm recovered` | SC-003 |
| code row | first attempt 84/113, after repair 111/113, quality n/a | `code ... n/a | 111/153 | 84/113 | 111/113` | SC-005 |
| composite | no column or key with a value; one line says why | no composite column in any table; `composite` occurs only in the two note lines (`composite not shown for cat-cafe-monitoring: 1 arm(s) with a graded run; it needs two`) and in no `.json`/`.html` file | SC-006 |
| heatmap attrition | research 4/18, clarify 4/14, no value in later columns; header 8 of 18 lost before code | research `0.22 (4/18)` class hm-s3, clarify `0.29 (4/14)` class hm-s4, header `18 started, 8 lost before code`. Note: the later columns carry `0.00 (0/k)` values, not blanks — contract §3.2 blanks a column only when no run wrote a record at it, and the 10 graded runs wrote records through merge; §12's figures (4/18 step 3, 4/14 step 4, 8/18 before code) reproduce exactly. The quickstart phrase is looser than the contract; the code follows the contract (SG-2: a §12 figure is never edited to match) | SC-001, FR-014 |
| heatmap cells | every non-blank cell shows num/den; nothing under five observations coloured | every non-empty `<td>` prints `(num/den)`; the sub-five cells (`0.00 (0/3)`) take the grey `hm-low` class, never a step class; oracle column blank in the three layers | SC-007 |
| gate-oracle | analyze: rejected 10, one an oracle pass, escape n/a; merge: rejected 7, passed 3, escape 3/3 grey; qa copy of code | analyze `reject/pass 1, reject/fail 9, escape n/a (0)`; merge `pass/fail 3, reject/pass 1, reject/fail 6, escape 3/3 (low n)` in the grey span; qa `copy of code (pre-012)` | SC-009 |
| success criteria | `0 of 18 runs left a run summary`; no bf-e2e id anywhere | the section opens with that line; `bf-e2e` matches zero files in the whole output tree | SC-008 |
| wall time | under one minute | **12.2 s** | SC-012 |

| Check on todo-api | Expected | Seen |
|---|---|---|
| groups | three: pre-012 (5 started, 4 graded, 1 lost), 012 unknown (1 graded), 012 b3344416 (1 graded, 1 lost at clarify) | exactly those three `###` groups with those figures; totals line `8, graded: 6, lost: 2 (clarify: 1, handoff: 1)` |
| every group header | grey figures | every figure carries `(low n)` in markdown (the grey class in HTML) |

| Check on all | Expected | Seen |
|---|---|---|
| the command | exits 0 | exit 0 |
| every case | started = graded + lost + grading failed + no oracle | combined line `44 = 16 + 22 + 0 + 6`; per case cat-cafe `18 = 10 + 8 + 0 + 0`, todo-api `8 = 6 + 2 + 0 + 0` |

Host rows after §2:

| Step | Expected | Seen | Proves |
|---|---|---|---|
| records fingerprint | equals baseline | `111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831`, identical before T016's commit, after it, and after all three scores | SC-010 |
| `git ls-files runs/` | prints nothing | nothing | FR-043 |
| aggregate script | output equal to baseline | 596,979 bytes, `runs=44 with_data=44 passed=19 records=1331`; file diff vs the T001 output shows only the regenerated `generated_at` timestamp | FR-047 |

## Success criteria SC-001 to SC-012

- **SC-001** — the run model's totals reproduce §12 on the stored records:
  18/10/8, lost by stage, 8 discarded oracle records, 18 derived (totals
  line; stored test passed in row 1).
- **SC-002** — the grid is the report's first section with the §12 group
  figures (one group, 18 rows, mean 0.708, all-pass 1/10).
- **SC-003** — the pre-012 arm is `zai-coding-plan-glm-5.2`, marked
  recovered and untrusted in the group header.
- **SC-004** — `totals` and the §1.7 invariant hold for every case (row 1
  tests; the `all` line above).
- **SC-005** — the code row reads first attempt 84/113, after repair
  111/113, quality n/a (the 012 attempt-share 0.725 is gone).
- **SC-006** — no composite anywhere; the note names the reason (one arm).
- **SC-007** — every cell prints its denominator; grey under five
  observations; the same value gives the same class in any report
  (`tests/test_benchmark_heatmap_render.py`, row 2).
- **SC-008** — success criteria scoped to the scored runs' own summaries:
  `0 of 18 runs left a run summary`, no `bf-e2e` id in any output file.
- **SC-009** — gate versus oracle: analyze 10 rejected (1 oracle pass,
  escape n/a), merge 7 rejected / 3 passed (escape 3/3 low n), qa copy.
- **SC-010** — the records fingerprint is byte-identical to T001's before
  and after every score; `git ls-files runs/` empty.
- **SC-011** — **not closed**: the captured-stream parser test does not
  exist (T015 parked, SG-4). The waste side of FR-042/SC-011's neighbourhood
  that landed (not-measured rule, capture mark) is proven by row 3.
- **SC-012** — the cat-cafe score ran in 12.2 s, under the one-minute bar.

## FR-041 state

**Open.** T015 is parked on the orchestrator's SG-4 hold (a stream file
from the user or clearance for one paid opencode call). No parser code was
written; `H/opencode.py` is untouched this round; no file exists under
`tests/fixtures/opencode/`. The round closes with FR-041 open, per the
implementation strategy ("the round can close with T015 open and FR-041
reported open").

## Open follow-ups of plan.md

1. Round for report item 2.9 (erosion and verbosity).
2. A stage that dies before it writes a record is invisible to attrition; a
   "stage started" record would place the eight lost runs exactly (S-M).
3. Three vocabularies for one stage (`CANONICAL_STAGES`,
   `CELL_STAGE_ORDER`, rubric keys), carried over from 012 (M).
4. The export of a crew cell's run summary uses an unsanitised id with `:`
   in the path (S).
5. `B/task_matrix.py` and `B/error_matrix.py` still key by `cell_key`, so a
   pre-012 cell is several columns there (S; out of this round).
6. Live confirmation of the opencode parser on the next benchmark run.

Filed under `.workspace/tasks/` only on the orchestrator's request (none
made).

## Deviations and judgement calls

1. Host venv instead of the container (Docker down; exec-brief sanction) —
   disclosed above.
2. Replay row: first run hit the T014-disclosed load flake once; the
   immediate rerun reproduced the baseline exactly. Recorded, not chased
   (no workflow code changed this round).
3. Quickstart §2's "no value in later columns" attrition phrase is looser
   than contract §3.2/§12; the code follows the contract (see the table).
4. The stored `report.md` files under `runs/` were never rewritten by this
   round's commands (fingerprint proof); the T001 aggregate output they
   feed is reproduced byte-for-byte modulo `generated_at`.
