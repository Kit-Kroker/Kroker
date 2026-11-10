# Verification: Delete FeatureWorkflow After Grace-Retention (round 020)

Executor record. Commands run in the active worktree (PR-1: `../Kroker-020-1`
on `020-delete-featureworkflow`; PR-2: `../Kroker-020-2` on
`020-delete-featureworkflow-2`) unless a section says otherwise.

Note on pytest output: this environment's pytest prints no final
`N passed` summary line; exit status plus the progress line are the record.

## §Baseline (T002)

Worktree `../Kroker-020-1` created from `main` at `4f6fc2c3` on branch
`020-delete-featureworkflow`; `uv sync --frozen --extra dev` completed.

`uv run pytest -q` (fast tier) — 8 failures, the known-failure list every
later run is compared against:

```text
FAILED tests/test_benchmark_acceptance_stalled.py::test_sc003_recompute_stored_acceptance
FAILED tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-hone]
FAILED tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-particle-swarm-optimization]
FAILED tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility[deveval-stocktrends]
FAILED tests/test_prompt_migration.py::test_prompt_shas_did_not_move
FAILED tests/test_read_fixtures_fresh.py::test_committed_recordings_equal_a_fresh_build
FAILED tests/test_read_fixtures_fresh.py::test_pristine_copy_passes_the_record_check
FAILED tests/test_todo_api_case_loads.py::test_todo_api_case_file_exists_and_loads
```

`uv run pytest -m temporal tests/replay -q` — exit 0, green (2026-11-10).

`uv run pytest tests/replay/test_feature_replay.py -q` — exit 0, green
(20 tests; `test_feature_replay.py` is fast-tier, so it also ran green
inside the `pytest -q` run above).

## §T006 (T006, plan T013, R-7, C2 — calibration pins on the live gate path)

qa-happy wrote the pin tests (tests only, no `src/` change); qa-chaos
adversarially reviewed them and found one live-path gap (no pin for
`auto_decision=auto` / `confidence=confidence` in the in-loop
`ctx.gate` call), which it then pinned as
`test_only_the_in_loop_gate_call_carries_auto_decision_and_confidence`.
Files: `tests/calibration/test_gate_requires_calibration.py`,
`tests/test_soft_gate_auto_approval.py`,
`tests/calibration/test_calibration_plumbing.py`.

Task-text note: the brief named a `judge_error` argument. No symbol
`judge_error` exists anywhere in `src/`; the C7 concern is the
calibration judge's failure degradation (`_calibration_verdict`'s
`except Exception` → `INSUFFICIENT`), which the pins cover via the
consult-path and lookup-failure tests.

Non-vacuousness proof (executor-run, scratch copy from
`git archive HEAD` + the three modified test files, both source files
restored before each mutation; each mutation applied exactly once):

```text
m1a author_model=author removed (in-loop call)  -> FAILED test_gate_requires_calibration.py::test_gate_node_plumbs_author_model_into_both_gate_calls
m1b author_model=author removed (final call)    -> FAILED test_gate_requires_calibration.py::test_gate_node_plumbs_author_model_into_both_gate_calls
m2 SOFT+confidence predicate deleted             -> FAILED test_soft_gate_auto_approval.py::test_gate_node_reads_calibration_only_under_the_verbatim_soft_predicate
                                                   FAILED test_soft_gate_auto_approval.py::test_the_consult_sits_inside_the_predicate_block_not_after_it
m3 precode plan-node resolved_model -> None      -> FAILED test_calibration_plumbing.py::test_precode_hands_the_resolved_model_to_both_producer_results
m4 author not read from stored payload           -> FAILED test_gate_requires_calibration.py::test_gate_node_takes_the_author_from_the_stored_payload
m5 auto_decision=auto removed (in-loop call)     -> FAILED test_gate_requires_calibration.py::test_only_the_in_loop_gate_call_carries_auto_decision_and_confidence
m6 confidence=confidence removed (in-loop call)  -> FAILED test_gate_requires_calibration.py::test_only_the_in_loop_gate_call_carries_auto_decision_and_confidence
restored -> 35 passed, exit 0
```

qa-chaos ran the same class of mutations independently (m1–m4 plus the
m5/m6 gap before it was pinned) with the same outcome. Green on the real
source: 35 passed, exit 0; `ruff check` clean on the three files.

