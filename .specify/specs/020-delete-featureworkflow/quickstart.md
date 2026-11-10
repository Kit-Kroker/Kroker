# Quickstart: validating 020

Run these from the repo root after `uv sync --frozen --extra dev`. The
8 known fast-tier failures on `main` are excepted everywhere (memory
`kroker-backlog-and-fast-tier`).

## 1. PR-1 (FeatureWorkflow still registered)

```bash
pytest tests/test_dashboard_fleet.py tests/test_dashboard_fleet_marks.py \
       tests/test_dashboard_fleet_summary.py tests/test_read_fixtures_fresh.py \
       tests/test_channel_inbox.py tests/test_inbox_query.py -q
pytest tests/calibration tests/test_soft_gate_auto_approval.py -q
(cd interfaces/dashboard/frontend && npm test -- src/api/http.test.ts)
pytest -q && ruff check . && ruff format --check . && mypy
```

Expected:
- a fake closed `FeatureWorkflow` row yields one `closed_legacy` entry;
- the handle factory is called zero times for that row, and `errors == []`;
- a `None`-typed row is still queried;
- the frontend renders "legacy run, summary unavailable".

## 2. Gate run 1

Follow [contracts/gate-runbook.md](contracts/gate-runbook.md) and paste the
output into `verification.md` §Gate-1. All four pass conditions must hold.

## 3. PR-2

```bash
SDLC_CAPTURE_HISTORIES=1 pytest -m temporal tests/replay/test_capture_graph.py
SDLC_CAPTURE_RESEARCH_RETAIN=1 pytest -m temporal tests/replay/test_research_retain_replay.py -k capture
git diff tests/replay/golden/ > .specify/specs/020-delete-featureworkflow/golden-rebaseline.diff
python scripts/check_golden_rebaseline.py   # T042: fails if any hunk touches anything but workflow/source_commit
pytest -m temporal tests/replay tests/durability tests/graph_workflow -q
pytest -q && ruff check . && ruff format --check . && mypy
python scripts/check_clauses.py
grep -rn "FeatureWorkflow" src/            # only the allowed list in plan §SC-002
```

Expected:
- every replay passes with `raise_on_replay_failure=True`, including
  `benchmark_one_cell` and its stripped-marker copy;
- the worker module imports without `workflows.feature`.

## 4. Gate run 2, then deploy

Run the runbook again, under 1 hour before the restart. Then:

```bash
docker compose pull worker && docker compose up -d worker
```

Afterwards:
- `docker compose logs worker` shows `worker running on task queue` and
  no import error;
- `tests/test_worker_registration` (T050) has already pinned the
  registered set;
- the dashboard fleet lists the legacy rows with no errors.
