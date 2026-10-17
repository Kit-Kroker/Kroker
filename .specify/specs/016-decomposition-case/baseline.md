# Round 016 baseline — Decomposition Case

Branch `016-decomposition-case`, worktree `D:\own\Kroker-016`, base main
**`b01f9b07`** (spec set commit `076db363` on `f61261ba`, then the
orchestrator's out-of-round replay fix `b01f9b07`; the branch was rebased
onto it mid-T001 after the SG-2 report below). The diff
`git diff --stat f61261ba HEAD -- src/sdlc/benchmarks src/sdlc/artifacts
scripts .pre-commit-config.yaml BENCHMARK.md tests/conftest.py` prints
nothing, so the plan's base facts hold.

**Rebase history (SG-2, resolved):** the first T001 pass, against
`f61261ba`, found the replay tier red (27 failed) — base commit
`89b8a75e` "feat(vcs): A-terminal worktree teardown plus an age-based
janitor" had added `cleanup_run_worktrees` without registering it on the
replay workers or re-recording goldens, and had broken 4 fast-tier tests
(1 vcs activity-set pin, 3 graph-chaos `SimpleNamespace.patched` stubs).
Reported per SG-2; the orchestrator ruled option B and fixed main out of
round in `b01f9b07` (real activity registered in GIT_FAKES, stubs gained
`patched=lambda: False`, vcs pin updated, goldens re-recorded via
`SDLC_CAPTURE_HISTORIES=1`; each golden gains exactly one appended
`activity:cleanup_run_worktrees` plus the source_commit bump). All gates
below were re-run against `b01f9b07` after the rebase.

Container: `kroker-dev` (image `kroker-dev:latest`), worktree at `/app`,
venv volume `kroker-verify-venv`, `runs/` bind from the primary tree
(`D:\own\Kroker\runs` → `/app/runs`; 76 record dirs, `runs/benchmarks`
visible inside). Python 3.13.15, uv 0.12.21. Synced
`uv sync --frozen --extra dev --extra logfire` (RC 0).

Host Python via the `py -3` launcher (3.14.3); bare `python` is not on
PATH.

## §1 Gates (container, one command per call, against `b01f9b07`)

| Command | Result |
|---|---|
| `uv run pytest` | **22 failed, 6229 passed, 12 skipped, 272 deselected, 247 warnings in 677.03s** — see §2 |
| `uv run pytest -m temporal tests/replay` | **32 passed, 21 skipped, 171 deselected, 139 warnings in 124.20s** |
| `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | 9 passed in 18.33s (015's baseline had 5 tests; the suite grew on main, all green) |
| `uv run ruff check .` | All checks passed! (0 issues) |
| `uv run ruff format --check .` | 1776 files already formatted |
| `uv run mypy` | Success: no issues found in 405 source files (0 errors) |

## §2 Fast-tier failures (all pre-existing at base; none caused by this round)

Exactly three groups, 22 tests. (The first T001 pass against `f61261ba`
additionally showed the four `89b8a75e` failures — vcs activity-set pin
and three graph-chaos `.patched` stubs — all cured by `b01f9b07`; the
passed count rose 6225 → 6229 by exactly those four.)

| Group | Tests | Cause |
|---|---|---|
| Stale stored-score pins | 16 in `tests/test_benchmark_stored_scores.py` | Records grew past the pins after R1/R2/R4-r2; the known residual 015 verification §10.6 already carries ("the §12 stored-score pins (16 stale figures pre-dating R1/R2/R4-r2)"). Example: `test_stored_cat_cafe_started_graded_lost` sees `(20, 12, 8)`, pin says `(18, 10, 8)` — the two 015 R2 cat-cafe runs `1792137753`/`1792148180` postdate the pin. |
| DevEval role drift | 3 in `tests/test_deveval_corpus.py` (`hone`, `particle-swarm-optimization`, `stocktrends`) | `fa1d58a1` parked those cases (`case.yaml` role `parked`); the test still asserts `CORPUS` (`tests/test_deveval_corpus.py:57`). |
| Container-git limitation | 3: `test_plans_are_tracked`, `test_prompt_gate`, `test_promptfoo_provider` | The known worktree-pointer issue from 015's baseline (container `.git` file resolves a Windows host path). |

## §3 Replay tier — resolved by the rebase

`uv run pytest -m temporal tests/replay` → **32 passed, 21 skipped**
(139 warnings; 138 before the fix — the registered fake adds one). The
contradiction recorded in the first T001 pass (27 failed, all traced to
`89b8a75e`) was reported per SG-2 and resolved out of round by
`b01f9b07`; this section records the history, the gate now matches
015's green baseline.

## §4 Verify items

- **V1 — PASS.** pydantic-ai-slim 2.51.0. The text `(provider default)`
  is printed at `pydantic_ai/_agent_graph.py:379` and `:2169`:
  `f'Model token limit ({self.last_max_tokens or "provider default"})
  exceeded …'`. `last_max_tokens: int | None = None` (`:338`) is set from
  `model_settings.get('max_tokens') if model_settings else None`
  (`:1782`, `:1956`), so "(provider default)" ⟺ `max_tokens` unset/None;
  T007's `ModelSettings(max_tokens=…)` makes the number print instead.
- **V2 — PASS.** Grep of `cases_dir()` / `_default_cases_dir()` /
  `benchmarks/cases` / `SDLC_CASES_ROOT` over `src/` finds exactly the
  D-3 sites: `B/oracle.py:280`, `B/cell.py:70`, `B/judge.py:307,311`,
  `B/tasks.py:82` (default branch), `B/report.py:298`, and in `B/cli.py`
  `:448` (`dispatch_corpus`), `:467` (`dispatch_accept`), `:659`
  (`dispatch_verify_case`). Non-goals unmoved: `cli.py:561` (smoke),
  `cli.py:629` (DevEval import dest), `eval/cli.py:83`, `root_cause.py:121`
  (labels), `paths.py:32` (calibration). Remaining hits are definitions,
  docstrings or help text. No new site since `f61261ba`.
- **V3 — PASS.** `git check-ignore docker-compose.override.yml` exits 0
  (file currently absent on this machine). With a probe override
  (`COMPOSE_FILE=docker-compose.yml;<probe>.yml`), `docker compose config
  worker` shows the merged worker service: base volumes/environment plus
  the store bind (`target: /srv/private-cases, read_only: true`) and
  `SDLC_PRIVATE_CASES_ROOT: /srv/private-cases`.
- **V4 — PASS (with a naming duty).** `LOGFIRE_TOKEN` is present in the
  host `.env`, so Logfire on this machine is configured to a **cloud
  project** (`logfire.configure(send_to_logfire="if-token-present")` at
  `src/sdlc/observability/logfire_setup.py:38`). Spans carry **no prompt
  text**: `logfire.instrument_pydantic_ai(include_content=False)`
  (`logfire_setup.py:43`); the module mandates metadata-only spans. The
  R1 clearance must still name the cloud project.
- **V5 — PASS (answered).** `memory_retains: 0` in the 015 R2 strong-arm
  cell summary (`runs/pipeline/bench-cat-cafe-monitoring-1792148180/
  cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.3-flash/summary.json`)
  is a **snapshot-ordering artifact, not a failed retain and not "none
  attempted"**: `build_run_summary` runs at `src/sdlc/workflows/
  run_host.py:107` BEFORE `retro.step` (`run_host.py:128`), and
  `retains` counts `MEMORY_RETAINED` events present at that moment
  (`src/sdlc/observability/summary.py:137`). The run DID attempt
  retention: its `events.jsonl` seq 139 is
  `{"kind":"memory_retained","stage":"retro","data":{"item":"run_summary"}}`,
  emitted by `src/sdlc/stages/retro/step.py:62-63` under
  `cfg.memory.enabled`, and the retain activity (`src/sdlc/workflows/
  memory_host.py:59-75`) was scheduled into the shared project bank with
  5 retries. Caveat for the R1 clearance: the activity's own success or
  failure is swallowed (`memory_host.py:74-75`) and recorded nowhere, so
  delivery to the Hindsight bank is unprovable from records; cross-arm
  carryover is possible by design and must be named in the clearance.

## §5 Host checks

| Command | Result |
|---|---|
| `py -3 scripts/check_file_size.py` | RC 0, no output (no file over the ceiling) |
| `py -3 scripts/check_clauses.py` | RC 0: `202 clauses declared, 10 untested, 0 dangling` |

## §6 Records manifest

`.specify/specs/016-decomposition-case/baseline-records.sha256`: 851
lines, one per file under `runs/benchmarks` (141 `.jsonl`, 318 `.json`,
318 `.html`, 74 `.md`), `<sha256>  <forward-slash relpath>`, sorted by
path. `git ls-files runs/` prints nothing. Re-verified after the rebase:
851/851 lines match, 0 mismatches.

## §7 Line counts (physical)

| File | Lines |
|---|---|
| `B/paths.py` | 63 |
| `B/cli.py` | 662 |
| `B/corpus.py` | 167 |
| `B/offline_checks.py` | 137 |
| `B/judge.py` | 317 |
| `B/tasks.py` | 152 |
| `src/sdlc/artifacts/capture.py` | 55 |
| `tests/conftest.py` | 345 |
| `BENCHMARK.md` | 818 |

(matches plan.md's Constitution-check figures for the files it names)
