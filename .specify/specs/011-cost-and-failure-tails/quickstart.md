# Quickstart: validating Cost tab and run budget (011, US1 + US2)

How to prove the feature works once built. Names and selectors are in [data-model.md](data-model.md) and [contracts/cost-and-budget.md](contracts/cost-and-budget.md).

## Prerequisites

- Python checks run in the `kroker-dev` container (repo or worktree bind-mounted at `/app`, `uv` venv). Never the host Windows venv.
- UI checks run on the host from the repository root. Node must be present: `scripts/check_ui.py` exits 0 with a loud "skipped" when Node is missing, and **a skip is not a pass**.
- Benchmark agents are live on this machine. Run one suite at a time; never chain two test runs in one shell call. `addopts` already carries `-q`; do not add another.

## 1. Automated gates

One per call.

| Where | Command | Expected |
|---|---|---|
| container | `uv run pytest tests/test_run_budget.py tests/test_cli_budget.py tests/test_dashboard_api.py tests/test_run_state_query.py tests/test_run_state_model.py tests/test_run_summary_build.py tests/test_run_summary_model.py tests/test_fleet_fixture_fresh.py tests/test_code_attempt_usage.py` | green, and the summary line shows no file deselected: every file here is fast tier |
| container | `uv run pytest -m temporal tests/test_budget_gate.py tests/test_model_usage_capture.py` | green, with a non-zero passed count. Both files carry `pytestmark = pytest.mark.temporal`; without `-m temporal` `addopts` deselects them even when named, and **a deselect is not a pass** |
| container | `uv run pytest` | fast tier green; the count rises only by the new tests |
| container | `uv run ruff check .` then `uv run ruff format --check .` then `uv run mypy` | clean; mypy no new errors against the baseline |
| container | `uv run pytest -m temporal tests/replay` | same result as the baseline taken in the first task. `budget_arch_reject-sandboxed` is a known flake (US3, follow-up run): a failure there that matches the baseline is recorded, not fixed here |
| host | `python scripts/check_ui.py` | every step green |
| host | `python scripts/check_clauses.py` | always exits 0, so read it: no `clause with no test` line for CONSOLE-24 to CONSOLE-29 or START_RUN_MODAL-3, no dangling citation |
| host | `python scripts/check_file_size.py` | no file over 1000 lines |

## 2. Manual walk on the mock provider

```text
cd interfaces/dashboard/frontend
VITE_API=mock npm run dev
```

| Step | Expect | Proves |
|---|---|---|
| Open the fleet | the header spend reads a dollar figure followed by "· N not priced" | CONSOLE-27 |
| Open the seeded run with a budget, select Cost | one row per role; one row reads "not priced" with tokens shown; total marked partial; no `$0.00` anywhere | CONSOLE-24, 25 |
| Same tab, budget block | budget, current limit, counted toward budget, percent, crossings, and the sentence naming what is not counted | CONSOLE-26 |
| Copy the URL, reload | Cost tab reopens | CONSOLE-24 |
| Open `?tab=gates` | Graph renders, URL untouched | CONSOLE-10 |
| Open the closed run with no roles | "No breakdown recorded" and its total | N9 |
| Start run, budget `0` | inline message with "omit it to run without a budget"; nothing starts | CONSOLE-28, R7 |
| Start run, budget `5` | run starts; toast carries the notice; its Cost tab shows budget $5.00 | CONSOLE-28 |
| Open `/?mockBudgetGate=1#/inbox`, budget gate entry | the sentence saying what approve grants | CONSOLE-29 |

## 3. Command line

In the container, no Temporal needed for the rejections:

| Command | Expect |
|---|---|
| `uv run python -m sdlc.cli start --title t --budget-usd 0` | exit 2, names `--budget-usd`, says to omit it |
| `uv run python -m sdlc.cli start --title t --budget-usd abc` | exit 2, names `--budget-usd` |

A live start with `--budget-usd 5` needs a Temporal server and spends tokens; it is the orchestrator's optional check, not a task gate. If run, expect the run id, then the notice line, and `budget_usd: 5.0` on the run's row in `GET /runs`.

## 4. What this run does not prove

- That the budget gate trips on coding-harness spend. It does not (R6); the card "budget gate counts all recorded spend" is queued behind the flake fix.
- US3, US4, US5 (follow-up S-batch run).
