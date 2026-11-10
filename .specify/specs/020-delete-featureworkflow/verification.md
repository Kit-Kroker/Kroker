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
