# Quickstart — validating 021

Prereqs: `uv sync --frozen --extra dev`.

| # | Proves | Command | Expected |
|---|---|---|---|
| Q1 | FR-002/003, hash stability, order sensitivity, degraded≠healthy, persisted bytes == hash | `pytest tests/test_recall_query_hash.py tests/test_recall_snapshot_artifact.py` | all pass; the 4 pre-existing query-hash tests are unmodified |
| Q2 | FR-001/005/008, R-5 double fault, no-run-id skip, scrub | `pytest tests/test_memory_activities.py tests/test_recall_snapshot_artifact.py` | pass; tests set `SDLC_ARTIFACT_ROOT` to `tmp_path` |
| Q3 | FR-004/010, FR-007 key identity, US2 | `pytest tests/test_recall_memo_key.py tests/clarify/test_clarify_memo_key.py tests/plan tests/architecture` | pass |
| Q4 | SC-001 reader + event, cache-hit coverage | `pytest tests/test_recall_snapshot_event.py` | pass |
| Q5 | FR-009/SC-005 replay of a pre-021 memory-on history | `pytest -m temporal tests/replay/test_research_retain_replay.py` | pass with no history edit |
| Q6 | SC-003 goldens + memo pins | `pytest -m temporal tests/replay/test_graph_golden.py` | goldens byte-identical; only `MEMO_PARITY_KEYS` re-pinned (T041) |
| Q7 | Fast tier | `pytest` | no new failures beyond the 8 pre-existing ones on `main` |
| Q8 | Lint/types | `ruff check . && ruff format --check . && mypy src` | clean |
