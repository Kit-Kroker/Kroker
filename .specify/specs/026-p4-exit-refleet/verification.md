# 026 verification

## §026-A (Part A)

> Assembled incrementally; T027 appends the full battery, the T008
> baseline, the T024 summary and the red→green ledger.

### T018 — the "autofix alone" offline conversion read (no model calls)

Method (read-only on the 025 evidence roots; every tree worked on a
`mktemp -d` copy under `/tmp/opencode/t018-*`, the scratch repos and the
025 runs root untouched):

1. `git -C <scratch-repo> archive <surviving integration branch> | tar -x -C $(mktemp -d)`
2. before: `ruff check --statistics --exit-zero --no-cache .`
3. the T013 autofix command, tree-wide for this read:
   `ruff check --fix --force-exclude --exit-zero --no-cache -- .`
4. after: `ruff check --statistics --exit-zero --no-cache .`

ruff 0.16.9 (the repo venv's), each tree's own configuration resolution
(the deveval cases carry richer rule selects than the default set —
UP/RUF/PERF/PLW/SIM/TRY/DTZ/EXE appear).

| Case (025 run) | before | after T013 autofix alone | spec H3 expectation |
|---|---|---|---|
| cat-cafe-monitoring (`…-1794967369-e94f43`) | 22 | **4** | 22→4 ✓ |
| deveval-geotext (`…-1794967369-ea94f8`) | 24 | **15** | 24→15 ✓ |
| deveval-lice (`…-1794958404-f74c98`) | 74 | **42** | 74→42 ✓ |
| deveval-lice, second branch (`…-1794980735-e87339`, secondary read) | 43 | 36 | — |

Reading: safe autofix alone removes 82 % (18/22), 38 % (9/24) and 43 %
(32/74) of the merge-blocking diagnostics on the three H3 trees; what
remains is exactly the non-safe-fixable residue (PERF102/PLW1510/TRY004
on cat-cafe; UP031/PLW1510/F401-in-`__init__`/UP022 on geotext;
RUF059/UP031/PLW1510/SIM117/UP030/EXE001/DTZ005 on lice). The per-task
scoped lint + fix loop (T014–T016) is what addresses that residue;
autofix is the floor, not the cure. Evidence dirs preserved:
`/tmp/opencode/t018-catcafe.*`, `/tmp/opencode/t018-geotext.*`,
`/tmp/opencode/t018-lice1.*` (primary), `/tmp/opencode/t018-lice2.*`
(secondary).

### 025 baseline (T008, the $0 re-score — Part B entry condition)

Command (copy, never the 025 root itself):

```
D=$(mktemp -d -p /tmp/opencode t008-XXXX)   # -> /tmp/opencode/t008-4DJV
cp -a /home/maksim/work/kroker-fleet-runs-025/. "$D"/
SDLC_RUNS_ROOT="$D" uv run python -m sdlc.cli benchmark score --all
```

Outputs written under `$D/benchmarks/_all/score/` (report.md,
sc-rollup.{json,html}, heatmap/grid/gate-oracle, per-case matrices);
the rollup, read from `sc-rollup.json`:

| criterion | rate | n |
|---|---|---|
| SC-1 | 0.00 | 6 |
| SC-1-strict | 0.00 | 6 |
| SC-2 (shipped) | n/a | 1 |
| SC-2-all | n/a | 4 |
| SC-3 | 0.385 | 13 |
| SC-3-non-lint | 0.385 | 13 |
| SC-3-lint | n/a | 0 |
| SC-4 | n/a | 4 |
| SC-6 | 1.00 | 15 |
| SC-6-advisory | 0.067 | 15 |

- commits: `['ce3a36f88d08e54892e8a72c96ceb6165ba4bc13']` — one commit,
  read by the rollup.
- roots line (T006): `records: …/benchmarks (runs_root); summaries:
  …/pipeline (runs_root); 4 of 6 scored runs summarized; no-summary:
  bench-deveval-lice-1794980735-e87339/…: terminated,
  bench-deveval-readtime-1794957781-bccb20/…: crashed; smoke excluded:
  bench-todo-api-greenfield-1794953137-1ba84e/…`
- evidence tier: weak (SOFT: no gate asked a human unless it escalated);
  summary_runs 4, pre-012 records 0.

Every quickstart expectation asserted and met: 4/6 summarized; the
readtime crash and the lice termination named as the no-summary pair;
smoke excluded; the single 025 commit; SC-1/SC-1-strict 0.00 (n=6);
SC-2-all n/a on 4 measured; SC-3 0.385 (n=13) with the new partition
reading non-lint 0.385 (n=13) and lint n/a (n=0) — every 025 loop is
legacy (`failure is None`), which is the before-half of this round's
T013–T016 change. No mismatch; no STOP. This is the baseline T050's
deltas read against.

### Part A battery (T027, 2026-11-18 — fleet `.env` PRESENT at the repo root throughout)

| command | result |
|---|---|
| `uv run pytest -q` | **2 failed, 8307 passed, 21 skipped, 401 deselected** — the 2 are exactly `.specify/specs/024-two-worker-pools/baseline-failures.txt` ids (`test_benchmark_acceptance_stalled.py::test_sc003_recompute_stored_acceptance`, `test_prompt_migration.py::test_prompt_shas_did_not_move`); the read_fixtures pair is worktree-only per the baseline note and passes on the primary checkout. **NOVEL IDS: none.** |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 2204 files already formatted |
| `uv run mypy` | Success: no issues found in 456 source files |
| `uv run python scripts/check_file_size.py` | OK (sc_rollup 479/1000 disclosed at T023; step.py 987/1000; all under the ceiling) |
| `uv run pytest -q tests/replay` | 183 passed, 58 deselected |
| `uv run pytest -q -m temporal -k "replay or golden"` | 46 passed, 24 skipped (the known venv-provisioning skips on this host, no python3-venv/ensurepip — documented pre-existing, not this round's defect) |
| `uv run --no-sync mkdocs build --strict` | built in 1.33 s, INFO only |

**Battery-caught defect, fixed in-round** (`1056feaf`): the full tier — and
only the full tier; no task-level suite runs these two — failed
`tests/test_calibration_run.py::test_importing_calibration_does_not_import_temporalio`
and
`tests/test_benchmark_score.py::test_view_modules_leave_temporalio_out_of_sys_modules`.
T013's `harness/models.py:25` `from ..toolchain.lint_scope import
LintAutofix` chained into `lint_scope → vcs.git → temporalio`, putting
temporalio into every cold import of `benchmarks.models` (pre-round
harness/models.py imported only core.models — verified at `95f1ba26`).
Fix: `_git` imported lazily inside lint_scope's two activity-side
functions (module docstring forbids workflow-code callers, so the
TMPRL1100 lazy-import ban does not apply; research toolset.py sets the
same activity-side precedent). Full tier then: exactly the 2 baseline
ids.

### FR-040 diff guard (`git diff --stat 95f1ba26..HEAD -- <paths>`)

- `src/sdlc/workflows`, `src/sdlc/gate.py`,
  `src/sdlc/calibration/decision.py`, `src/sdlc/stages/merge/step.py`:
  **empty — clean.**
- `src/sdlc/harness`: **one file, +10 — DISCLOSED.** `harness/models.py`
  carries exactly T013's `HarnessRunResult.lint_autofix` field (plus its
  import), the plan's own T013 text ("the result's new `lint_autofix`
  field") and reviewer-approved at T013; no other harness file changed.
  The guard's letter says empty; the plan's T013 requires this field on
  the harness result type. Resolved by disclosure, like the sc_rollup
  size tripwire — flagged for the owner at the Part A→B boundary.
- Sanctioned exceptions, verified to contain only what the plan names:
  `src/sdlc/calibration/store.py` +3/−1 = T002's resolver routing (one
  import, one line to `runs_paths.export_root()`);
  `src/sdlc/benchmarks/workflow.py` +22/−2 = T004's child-failure string
  edit only (`_child_failure_text` carrying the cause type; string-only,
  flows into an activity INPUT, replay-safe per the 021 precedent).

### T024 summary (full table: `triage.md`)

18 rows over the 025 evidence: 5 scored failures + 13 fix loops,
reconciled against the records (13 (run, task) groups, 5 resolved —
matching the fleet report's totals). Classifications: F1 (run 1's
architecture death) agent-tool defect — **fixed by T022**; F4 (cat-cafe,
`lint_clean`-only block, 11/11 QA, oracle 0.861) **harness defect** —
the feedback loop did not exist, **fixed by T013–T016**; F2/F3 (lice,
geotext) case difficulty with the lint component sharing the T013–T016
fix; F5 case difficulty; all 13 loops case difficulty (tests + review
failing checks, first-pass-rate corroboration) — no loop classed harness
or agent-tool, so FR-023's remedy column is empty for section B. No 025
loop was lint-driven (per-task lint did not exist; SC-3-lint reads n/a
on the baseline by construction — the before-half of T013–T016).

### Red → green ledger (every Part A task; all reviewer-approved)

| task | commit | red → green |
|---|---|---|
| T001 RED | `0faf6602` | runs_paths contract fails: module absent |
| T002 GREEN | `30ae486e` | runs_paths resolver wired at 8 sites |
| T003 RED | `b5c984bc` | no-summary classification + smoke exclusion fail |
| T004 GREEN | `0600e130` | crash/terminated named; cause type in the string |
| T005 RED | `bfb9c6bc` (+`e31804c7`, `f74370a4`, `a021a2c3`) | rollup no-summary accounting + roots line fail |
| T006 GREEN | `c3bf362b` | vouching rule, roots line, renderers moved |
| T007 docs | `99fc819d` | SDLC_RUNS_ROOT documented |
| T008 re-score | `5135c06b` | $0 baseline reproduced, all assertions met |
| T009 RED | `6eb32102` | PRD SC-1 rule fails |
| T010 GREEN | `2a0386a3` | SC-1 + SC-1-strict + Clopper-Pearson CI |
| T011 move | `a805a2c4` | lint_scope moved verbatim; merge tests green + identity |
| T012 RED | `889e71ab` | 18 autofix-checkpoint failures |
| T013 GREEN | `55bf60ba` | autofix inside the checkpoint commit |
| T014 RED | `3b13d0e0` | scoped-lint-in-loop failures |
| T015 GREEN | `48e5b0ee` | per-task scoped lint in run_test_suite |
| T016 GREEN | `2fbfc859` | lint wired into loop trigger, verdict, retry prompt |
| T017 proof | `a1c7367f` | task/merge paths element-wise equal |
| T018 read | `575164c3` | autofix-alone conversion: cat-cafe 22→4, geotext 24→15, lice 74→42 (spec H3 exact) |
| T019 RED | `817bbbae` | AttemptFailure contract fails |
| T020 GREEN | `bfff09fc` | failure.checks wired for code/qa/review records |
| T021 RED | `dd844ece` | 6 RED crash-degrade + 4 pins; evidence settled |
| T022 GREEN | `23f7ab1c` | UnexpectedModelBehavior → gap brief, OUR text |
| T023 RED→GREEN | `d71b9d64` | 10 RED → SC-3-non-lint/SC-3-lint partition |
| T024 triage | `f5ee84a2` | 18 rows, evidence-backed classes |
| T025 RED | `941efc56` | .env rider leak reproduced (2 failing) |
| T026 GREEN | `3b023d9d` | conftest import-time shield; six rider files 137/137 with .env present |
| T027 battery | `1056feaf` | full tier exactly the baseline ids; T013 import-chain regression fixed in-round |

**Fleet commit candidate:** the Part A close-out commit that carries this
§026-A (HEAD at review time) — Part B changes no code, so the freeze
target is this commit. Named for T041 at GATE 2.
