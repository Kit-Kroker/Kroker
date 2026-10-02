# Quickstart: validating 006 in the dev container

All commands run in `kroker-dev` with the feature worktree mounted at `/app`. One pytest invocation per command; `addopts` already carries `-q`, do not add another. Capture with `> <log> 2>&1; echo RC=$?`.

## Prerequisites

- Worktree based on main `817f819`. No credentials needed.

## 1. B1 — checkpoint warning

```bash
pytest tests/code/test_coding_task_checkpoint.py
```

Expect: non-zero commit → one WARNING with the worktree and git's text, no sha; zero commit → no warning, sha recorded.

## 2. B2 — notify drop warning and doctor

```bash
pytest tests/test_notify_routes.py
pytest tests/doctor
```

Expect: an unset or empty `$VAR` target logs one WARNING per dropped route naming location and variable, and the route is still dropped; `unset_env_targets` returns exactly the unset ones; the doctor check WARNs listing them and is PASS when none.

## 3. B3 — fleet fixture

```bash
pytest tests/test_fleet_fixture_fresh.py
python scripts/dump_dashboard_fixtures.py
git status --short interfaces/dashboard/frontend/src/api/__fixtures__/
python scripts/check_ui.py
```

Expect: both tests green; regenerating leaves the fixture unmodified (empty `git status` line); the frontend gate passes with `http.test.ts` and `client.test.ts` unedited.

## 4. B4, B5, B6 — documents

- `src/sdlc/stages/research/AGENTS.md` has a `## Gotchas` section; `git diff 817f819 --stat -- src/sdlc/stages/research/` shows that one file.
- Both inbox files under `.workspace/tasks/` end with `## Draft register row`.
- `git status --short docs/reports/` shows no `external-ideas` entry; `git log 817f819..HEAD -- docs/reports/` is empty.

## 5. Whole batch

```bash
pytest
ruff check .
ruff format --check .
mypy
python scripts/check_file_size.py
git diff 817f819 --stat -- src/sdlc/stages/code/step.py pyproject.toml uv.lock docs/superpowers docs/reports
```

Expect: fast tier green, pass count = baseline + this batch's new tests; lint, format, types and file-size gates clean (mypy: no new errors against the baseline); the last diff is empty.
