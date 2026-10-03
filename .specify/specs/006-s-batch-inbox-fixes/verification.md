# Verification: 006-s-batch-inbox-fixes

T014. All runs in `kroker-dev` (worktree `D:\own\Kroker-006` at /app),
one command per invocation, RC captured. Quickstart §5 order.

## §5 gate results

| Gate | Command | Result |
|---|---|---|
| Fast tier | `pytest` | **5488 passed, 11 skipped, 247 deselected, RC=0**, 546.92s |
| Lint | `ruff check .` | RC=0, all checks passed |
| Format | `ruff format --check .` | RC=0, 1561 files already formatted |
| Types | `mypy` | RC=0, **0 errors in 378 source files** (baseline: 0/378) |
| File size | `python scripts/check_file_size.py` | RC=0 |
| UI | `python scripts/check_ui.py` | RC=1 both runs — see the SG-2 record below; FR-009 substance holds in every run |
| FR-015 | `git diff 817f819 --stat -- src/sdlc/stages/code/step.py pyproject.toml uv.lock docs/superpowers docs/reports` | **empty** (no output) |

## Pass-count delta vs baseline.md

Baseline (unmodified base `6de8489`): 5469 passed, 1 failed (the replay
`clarify_fanout` flake), 11 skipped. Now: 5488 passed, 0 failed.

- +18 new tests from this batch: B1 +4 (`tests/code/test_coding_task_checkpoint.py`
  2→6: three contract cases + the control), B2a +5 (`tests/test_notify_routes.py`
  9→14), B2b +7 (routes 14→18 and `tests/doctor/test_doctor_checks_delegated.py`
  +3; doctor suite 102→105), B3 +2 (`tests/test_fleet_fixture_fresh.py`).
- +1: the baseline replay flake passed this run (it was green in isolation
  on the base sha too — load flakiness, recorded in baseline.md).
- 5469 + 18 + 1 = 5488. No pre-existing test regressed (SG-4 never fired).

## SG-2 record (fire, evidence, ruling)

Fired after T010: `check_ui.py` failed at `vitest-dashboard` on
`src/app/boundaries.test.ts › shared split shape (T004) › shared/fleet.store
exports useFleetStore and stores/fleet is gone` — `Test timed out in 5000ms`
(1 failed / 373 passed), reproduced 3/3 through the wrapper path. Evidence
matrix: direct `npx vitest run` in the frontend dir passed **374/374 twice
with BOTH the stale and the regenerated fixture**; `boundaries.test.ts`
passed **48/48 isolated** (its jsdom environment setup alone takes ~30 s in
this container); the failing test is a static import-graph check that reads
no fixture data; `http.test.ts` and `client.test.ts` passed **unedited in
every run**. Full report: `.workspace/tmp/executor-006-SG2-report.md`.

**Ruling (orchestrator, same day): CLEARED as environment flake** on that
matrix, corroborated by host memory pressure (background processes reaped
while the diagnosis ran), with conditions: (1) this record; (2) T014
re-runs `check_ui.py`, and on a wrapper-timeout trip re-runs once warm and
records BOTH outcomes — the recorded fact, not a pass, is the deliverable;
(3) the flake goes to the inbox, not this batch.

T014 check_ui outcomes, both recorded:

| Run | vitest-dashboard | vitest-ui | playwright |
|---|---|---|---|
| 1 (cold-ish) | 1 failed / 373 passed — the same single boundaries 5 s timeout | 147/147 | 86 passed |
| 2 (warm re-run) | same single boundaries 5 s timeout (1/373) | 147/147 | RC≠0: one `app.pw.ts` browser test exceeded a 30 s locator timeout; npm lifecycle error surfaced at the ui workspace — consistent with the documented host memory pressure |

No third run was made (ruling: re-run once). The flake is filed to the
inbox for the orchestrator to task (condition 3); nothing in this batch
edits `http.test.ts` / `client.test.ts` or any dashboard config.

## SG-5 defect candidates (from T011; documented, not fixed)

1. Exhaustion zeroed usage under-reports research spend in benchmark
   records (`stage.py` returns a fresh `RoleUsage` on the degrade path).
2. Exhaustion discards the sub-question's partial work — no salvage of the
   in-flight brief.
3. The budget write is not atomic (`budget_store.py` writes in place;
   `write_page` got tmp+`os.replace`, `charge_persisted` did not) — a
   truncated counter wedges its scope.
4. The run counter is never rolled back when the sub-question scope
   refuses its charge — the run budget leaks refused charges.
5. `retain.py` re-runs the verifier (page I/O) in workflow context —
   replay/sandbox determinism hazard (reading-verified only).

Plus the SG-2 flake above (condition 3): `boundaries.test.ts` per-test
5 s timeout under the npm-wrapper invocation path in this container.

## Per-item commit shas (branch `006-s-batch-inbox-fixes`)

| Item | Tasks | Commit |
|---|---|---|
| Baseline | T001 | `7411f2d` |
| B1 checkpoint warning | T002 + T003 (paired) | `2c44675` |
| B2 notify drop warning | T004 + T005 (paired) | `cc12130` |
| B2 doctor half | T006 + T007 (paired) | `869a174` |
| B3 generator refactor | T008 | `cf70d5f` |
| B3 taught rows + regen | T009 + T010 (paired) | `ede50d8` |
| B4 research Gotchas | T011 | `f7bf90c` |
| B5 + B6 register-row drafts | T012, T013 | **no commit** — git-ignored working-tree deliverables in the primary checkout's `.workspace/tasks/`; reviewer gate = reviewer read both files (approve, `reviewer-006-T012-T013.md`) |
| Verification | T014 | this commit |

Every RED task's tests ride the commit that turned them green; no red
commit exists on the branch (FR-014). Each reviewer gate verdict is at
`.workspace/tmp/reviewer-006-T00{1..14}*.md`, all approve.

## B5/B6 evidence (FR-012, FR-013)

- Both inbox files end with `## Draft register row`
  (`.workspace/tasks/2026-09-07-flaky-provider-import-test.md`,
  `.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md`).
- `git status --short docs/reports/` (primary checkout): no
  `external-ideas` entry — only the user's pre-existing WIP, untouched.
- `git log 817f819..HEAD --oneline -- docs/reports/` (branch): empty.
