# Baseline: 009 research retain path

Recorded by T001 on 2026-10-04, in `kroker-dev` (bound to `D:\own\Kroker-007`,
venv `kroker-007-venv`), on unmodified main `d51eef5` plus this branch's
spec-set files (uncommitted at run time; the only tracked differences from
`d51eef5` are `.specify/` and `CLAUDE.md`).

| Item | Value |
|---|---|
| Base sha | `d51eef5` (main; branch cut from it, `git diff d51eef5 --stat -- src` empty) |
| Branch | `009-research-retain-path` |
| Sync | `uv sync --frozen --extra dev --extra logfire` — RC=0 |
| Fast tier (`pytest`) | 2 failed, 5536 passed, 11 skipped, 251 deselected — RC=1, 718.24 s |
| Pre-existing failures | 2, both in `tests/test_grade_oracle.py` (below) |
| `mypy` | Success: no issues found in 379 source files — RC=0, 0 errors |
| `R/step.py` lines | 387 |
| `R/retain.py` lines | 32 |
| `tests/replay/scenarios.py` lines | 906 |

Pre-existing failures (reproduced in isolation on unmodified main,
`.venv/bin/python -m pytest tests/test_grade_oracle.py` — RC=1, 2 failed,
4 passed, 1 deselected):

- `test_grade_oracle_populates_oracle_mapped_task_grades` —
  `assert (None == 1.0)`; the oracle judge reports
  `none of ['test_crud.py::test_ok'] found in oracle report`.
- `test_grade_oracle_malformed_tasks_yaml_never_fails_case_grade` —
  `assert 0 == 2`; `OracleGrade(... total=0 ... detail='no junit report')`.

Neither touches the research stage, replay, memory or grounding. Recorded
as a baseline anomaly for the orchestrator (SG-2 reference point: these two
fail before any change this feature makes). The 008 baseline (same host,
same container, 2026-10-04 earlier) had 5512 passed / 0 failed; main has
since gained tests and whatever broke these two.

Notes:

- Fast tier and mypy each run once, as T001 requires; no source file
  differs from `d51eef5`.
- Logs: `/tmp/009-t001-pytest.log`, `/tmp/009-t001-grade.log` and
  `/tmp/009-t001-mypy.log` inside `kroker-dev` (not committed).
