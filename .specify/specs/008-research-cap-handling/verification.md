# Verification: 008 research cap handling

Recorded by T012 on 2026-10-04, in `kroker-dev` (bound to
`D:\own\Kroker-007`, venv `kroker-007-venv`), branch
`008-research-cap-handling` (base main `c2d9b12`). Every command below
ran as its own invocation, after T010/T011, with the tree clean.

## Quickstart §4 — the E1 scenarios (SC-003, SC-004)

Command (host): `Get-Content <primary>\.workspace\tmp\research-budget-enforcement-e1.py -Raw | docker exec -i kroker-dev python -` (PowerShell has no `<` redirect; same stdin form as the quickstart). RC=0.

| Scenario | Baseline (E1) | Now | Expected |
|---|---|---|---|
| S1 stubborn, two sequential calls | run 5 searches | `run` = 1 search, $0.01; `sq-0` = 1 search, $0.01 | run = 1, equal to sq-0 |
| S2 compliant, two sequential calls | run 2 searches | `run` = 1 search, $0.01; `sq-0` = 1 search, $0.01 | run = 1, equal to sq-0 |
| S3 stubborn, gather of three | run 12 searches | `run` = 1 search, $0.01; `sq-0` = 1 search, $0.01 | run = 1, equal to sq-0 |
| S4 stubborn, through the real handler | stage RAISED UnexpectedModelBehavior | stage returned a finding: `failed=False`, `usage` `calls=1`, `input_tokens=2458`, `output_tokens=150`; gap = `research stopped early: sq-0 allowance: search budget exhausted (1 searches); then Tool 'run_code' exceeded max retries count of 3` | finding, failed False, non-zero usage |

## Quickstart §5 — nothing else moved

| Command | RC | Result |
|---|---|---|
| `pytest tests/research` | 0 | 164 passed, 6 deselected |
| `pytest tests/test_model_forwarding.py` | 5 | 8 deselected — the module is `pytest.mark.temporal` (line 64), so the fast tier selects nothing; re-run as below |
| `pytest -m temporal tests/test_model_forwarding.py` | 0 | 8 passed |
| `pytest tests/test_exa_wrapper.py` | 0 | 6 passed |
| `pytest -m temporal tests/replay` | 0 | 32 passed, 19 skipped, 164 deselected |
| `pytest -m temporal tests/durability/test_single_retry_layer.py` | 0 | 5 passed |
| `git status --short tests/replay/histories tests/replay/golden` | 0 | no output — no fixture modified, none re-recorded (SC-006) |
| `git diff c2d9b12 --stat -- R/step.py R/toolset.py R/models.py R/retain.py R/verify.py src/sdlc/stages/architecture docs/reports/external-ideas-2026-09.md pyproject.toml uv.lock` | 0 | empty diff — the forbidden paths are untouched (FR-012, FR-013) |

## Quickstart §6 — whole feature

| Command | RC | Result | vs baseline |
|---|---|---|---|
| `pytest` | 0 | 5538 passed, 11 skipped, 251 deselected (723.92 s) | +26 passed (5512 → 5538) — exactly this feature's new tests: 7 (usage 5+6a) + 4 (usage 1-4) + 7 (scope 1-5 incl. EC4 pin) + 7 (retry 1-5) + 1 (usage 6b); 0 failed at baseline, 0 now |
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 0 | 1594 files already formatted |
| `mypy` | 0 | Success: no issues found in 379 source files | 0 errors → 0 errors (delta 0) |
| `python scripts/check_file_size.py` | 0 | clean; largest touched: `stage.py` 482, `budget_store.py` 187, `deps.py` 117 lines (ceiling 1000) |

## CodeMode test module wall time (SG-4)

`pytest tests/research/test_research_cap_retry_exhaustion.py --durations=0`:
7 passed in 26.53 s wall. Per-test CodeMode calls: 0.24 / 0.19 / 0.16 /
0.15 s; the three fake-agent branch cases < 0.01 s. The wall is
dominated by the one-time module import floor (~10 s, monty/pydantic
imports) plus container I/O — no individual test approaches the 5 s
SG-4 bound, and no flakiness was observed across every run in this
verification.

## Per-task commit shas

| Task(s) | Commit |
|---|---|
| Spec set onto the branch (pre-T001) | `304053a` |
| T001 baseline | `4e84214` |
| T002 + T003 (the refusal record) | `1f935d8` |
| T004 + T005 (usage at the cap, H1) | `9689052` |
| T006 + T007 (a refused charge writes nothing, H4) | `19d5604` |
| T008 + T009 (retry exhaustion degrades once, N4) | `4fab073` |
| T010 (two Gotchas bullets) | `7246964` |
| T011 (BENCHMARK.md marker) | `7fb2637` |
| T012 (this file + tasks.md checkboxes) | this commit |

Reviewer gates: every task pair and both docs tasks carry a per-task
reviewer APPROVE (T002, T003, T004, T005, T006, T007, T008, T009,
T010+T011); each RED diff was approved on its own before its fix task
started, per the standing rule.

## Notes

- All three defects have at least one test that failed on `c2d9b12`
  and passes now (SC-002): usage cases 1-2, scope cases 1-2, retry
  case 1 (+4, 5a, 6b).
- The user's uncommitted files in the primary checkout were never
  staged, committed or reverted; the spec set, `CLAUDE.md` and
  `.specify/feature.json` were copied read-only, never staged in the
  primary (FR-013).
- Logs live at `/tmp/008-t012-*.log` inside `kroker-dev` (not
  committed); the E1 transcript also at the orchestrator's temp area.
