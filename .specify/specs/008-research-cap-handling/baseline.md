# Baseline: 008 research cap handling

Recorded by T001 on 2026-10-04, in `kroker-dev` (bound to `D:\own\Kroker-007`,
venv `kroker-007-venv`), on unmodified main plus the spec-set commit.

| Item | Value |
|---|---|
| Base sha | `c2d9b12` (main; worktree branch cut from it, spec-set commit `304053a` on top) |
| Branch | `008-research-cap-handling` |
| Sync | `uv sync --frozen --extra dev --extra logfire` — RC=0 |
| Fast tier (`pytest`) | 5512 passed, 11 skipped, 251 deselected, 0 failed — RC=0, 806.62 s |
| Pre-existing failures | none |
| `mypy` | Success: no issues found in 379 source files — RC=0, 0 errors |

Notes:

- Fast tier and mypy each run once, after the spec-set commit; no source
  file differs from `c2d9b12` at this point (`git diff c2d9b12 --stat`
  over `src/` is empty; the only branch commit touches `.specify/` and
  `CLAUDE.md`).
- Known ambient hazard re-checked before the runs
  (`.workspace/tasks/2026-09-07-flaky-provider-import-test.md`): the
  provider-import wall-clock test can blow its budget under concurrent
  load; it passed here, so no anomaly to record.
- Logs: `/tmp/008-t001-pytest.log` and `/tmp/008-t001-mypy.log` inside
  `kroker-dev` (not committed).
