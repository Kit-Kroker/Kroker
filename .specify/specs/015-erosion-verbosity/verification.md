# Round 015 verification — erosion and verbosity

Branch `015-erosion-verbosity` (base main `13a3093c`, code base
`c3f6319c`), verified 2026-10-11 in the `kroker-dev-axis` container
(worktree at /app; a snapshot-venv sibling of `kroker-dev`, which
stayed bound to the parallel `015-corpus-acceptance` round — see the
deviations section). Evidence is the quickstart's rows, one command
per call, plus the stored-corpus checks of §2.

## §1 Automated gates (quickstart §1)

| Row | Command | Result |
|---|---|---|
| 1 | `pytest tests/test_benchmark_axis.py tests/test_benchmark_stored_scores.py` | 33 passed |
| 2 | `pytest tests/test_benchmark_runs.py tests/test_benchmark_grid.py tests/test_benchmark_report.py tests/test_benchmark_score.py tests/test_benchmark_models.py` | 191 passed |
| 3 | `pytest -m temporal tests/test_benchmark_workflow_sequence.py` | 9 passed (5 pre-existing 012 cases + 4 axis cases) |
| 4 | `pytest tests/test_judge_literal.py tests/test_benchmark_scoring.py tests/test_benchmark_heatmap.py tests/test_benchmark_heatmap_render.py` | 73 passed |
| 5 | full fast tier `pytest` | 3 failed, 6089 passed, 12 skipped, 267 deselected in 460.07s (0:07:40) |
| 6 | `pytest -m temporal tests/replay`, then the sequence test again | 32 passed, 21 skipped, 171 deselected / 9 passed in 19.04s |
| 7 | `ruff check .` / `ruff format --check .` / `mypy` | all passed / 1738 files formatted / success, 395 source files |
| 8 | host `check_file_size.py` / `check_clauses.py` | exit 0 / 202 clauses, 10 untested (the same pre-existing ten as the baseline), 0 dangling |

Row 5's delta over the baseline (3/6047/12/263): +42 passed — exactly
this round's new fast-tier tests (6 models, 1 judge-literal
parametrisation, 14 axis, 6 runs, 6 grid, 3 report, 2 score, 4
stored); +4 deselected are the temporal-marked sequence cases; the 3
failures are the baseline's own container-git trio, unchanged.

## §2 The score on the stored corpus (read-only)

Scores written with `--out /tmp/score-015-*` (outside `runs/`; the
container's CLI needs the primary tree's `.env` for its boot-time
loader checks — passed with `docker exec --env-file` on a dequoted
copy; no value was read into any transcript):

1. `--case cat-cafe-monitoring`: totals clause exactly
   `axis: 0 measured, 18 not measured`; 18 run rows each reading
   `n/m(no record)` in both axis columns; the one group header reads
   `erosion n/a (0)`. The 013 figures (18/10/8 with per-stage lost)
   unchanged — pinned by the unedited stored tests in the same run.
2. `--case todo-api-greenfield`: `axis: 0 measured, 8 not measured`;
   8 rows `n/m(no record)`; the 013 three-group figures unchanged.
3. `--all`: `axis: 0 measured, 44 not measured`; elapsed 19 s —
   inside 013 SC-012's one-minute bar.
4. After §2: records fingerprint
   `111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831`
   (byte-identical to the baseline), and `git ls-files runs/` prints
   nothing.

## §3 Determinism and fixture proofs

1. `pytest tests/test_benchmark_axis.py -k deterministic` — 1 passed.
   (The quickstart's `-k determinism` substring does not match the test
   name `test_measure_files_is_deterministic`; the filter was corrected,
   the test is the same.)
2. The mass-split fixture reads erosion exactly 0.50 (masses 6 + 24 +
   30 under, 60 over, every SLOC a perfect square); the slop fixture
   reads verbosity exactly 9/28 — both asserted in row 1's tests,
   hand-counted in the fixtures' docstrings (SC-001).
3. SC-005 timing: `measure_files` over the whole `src/sdlc` tree —
   395 files, 55 152 non-blank lines, 1 972 functions — completes in
   5.43 s, no network. A produced diff is one to two orders of
   magnitude smaller.

## §4 Success criteria

- **SC-001** — proven: the exact fixture figures (row 1; §3.2). Zero
  discrepancies.
- **SC-002** — proven: byte-identical figures on the twice-measured
  tree (T004's determinism test; §3.1's re-run, 1 passed).
- **SC-003** — proven on the stored corpus: 100% `n/m(no record)`
  (both cases, §2), zero axis means anywhere, explicit counts
  (18/8/44), every 013 verification figure unchanged (§2.1-2.2 and
  the unedited stored tests).
- **SC-004** — proven by absence (T008's tests): the figures appear
  in the grid row, the group header and `grid.json` only; no output
  file outside the grid mentions `erosion` or `verbosity`; no
  quality, composite or gate figure changes.
- **SC-005** — proven: §3.3, 5.43 s on a tree far larger than any
  case diff, no network (the tools are pinned local dependencies).
- **SC-006** — **closed** by the smoke run (the addendum below): the
  run row and the group header show both figures with tool
  identifications, beside the oracle. FR-017's smoke half closed.

## §5 Deviations and disclosures

- **Solo session.** No advisor or skeptic seats; the reviewer gate
  ran as per-task self-review of each diff (the plan discloses the
  solo session; GATE 2 items carry the skeptic-grade disclosures).
- **Container isolation.** `kroker-dev` was mid-use by the parallel
  `015-corpus-acceptance` round (its T001 baseline landed the same
  day), so the round ran in a sibling container `kroker-dev-axis`
  with a snapshot copy of the venv volume. Two rounds now claim the
  015 number (ours is on main; theirs is a branch off `c3f6319c`) —
  renumbering at merge is the orchestrator's call, flagged here and
  in baseline.md.
- **Fast-tier environment failures.** The three container-git
  worktree failures of the baseline
  (test_plans_are_tracked/test_prompt_gate/test_promptfoo_provider —
  the `.git` pointer resolves a Windows host path inside the
  container) persist unchanged; they are the baseline the exit
  criterion compares against, not regressions of this round.
- **Replay flake.** The known golden-trace race (open inbox item since
  round 012) fired on several of row 6's runs — `arch_revise_final-
  unsandboxed`, `budget_arch_reject-sandboxed`, `delta_failed-sandboxed`,
  varying 0-3 failures per full run and a different member each time;
  every flaked member passes alone, and the recorded row-6 result is a
  clean full run (32 passed). No `tests/replay/` file was touched; the
  flake predates the round (the baseline's first replay run flaked the
  same way).
- **Rule-set packaging.** `RULES_DIR` resolves module-relative; every
  deployment today is an editable install. A frozen wheel would need
  `**/*.yml` added to the package data — a follow-up, the lockfile
  being closed this round.
- **CLI env.** `sdlc benchmark score` boots the role loader, which
  fails closed without `EXA_API_KEY` — the container needs the env
  file although scoring itself touches no network (FR-013 holds for
  the scoring path; the check is loader-side, not score-side).

## §6 Addendum — the smoke run (T012, SC-006 closed)

**Run `bench-todo-api-greenfield-1791746672`**, cell
`todo-api-greenfield#opencode#zai-coding-plan-glm-5.2` (one cell, the
case's only arm), launched on the orchestrator's go of 2026-10-11 with
`--gate-policy off` (the 012 smoke precedent; the case's research gate
is SOFT without calibration data and would otherwise wait for a human
— see the incidents below). Environment: the compose project
`kroker-bench` (built per the orchestrator's directive after two
ad-hoc attempts): a dedicated temporal dev server on 127.0.0.1:7234
(UI 8234) and a worker on the branch worktree with the branch-synced
venv (radon/ast-grep are branch-only dependencies), the production
stack's binds (runs/, D:/own/sdlc-scratch-repos, the host opencode
auth/models), git identity, and `KROKER_COMMIT=58871313` on the worker
(012's lesson: provenance resolves worker-side — every record of the
run carries the branch head).

Results (the acceptance checks of quickstart §4):

| Check | Result |
|---|---|
| axis record with figures | erosion **0.0**, verbosity **0.0** — a real measured zero: 107 functions, none over CC 10 (mass 546.76 total, 0 over), 0 flagged lines over 921 non-blank LOC of 6 changed `*.py` files; `head=28df0560…`, `ruleset_version "1"`, `tools {radon 6.0.1, ast-grep 0.50.0}`; the measurement itself took 9.49 s (SC-005 live) |
| the score shows them | the regenerated report's totals clause reads `axis: 1 measured, 0 not measured`; the group header carries `erosion 0.00 (1)`, `verbosity 0.00 (1)` after the all-pass figure; the run row carries `0.00 \| 0.00` in the two columns after the code-score columns |
| oracle and code figures in envelope | oracle **1.0 (6/6)**, `held_out_ok`, language match — exactly the 012 smoke's envelope; the cell completed (`graded`, last stage deploy); first attempt 6/7 |
| opencode waste counters (013's live-parser follow-up) | 9 of 9 waste-carrying records with non-zero `tool_calls`, `capture_rev=1` on all — the 014 parser reads real opencode streams |
| corpus integrity | the records fingerprint over everything EXCEPT the new bench dir is byte-identical to the baseline (`111 2a32da97…`); the corpus delta is exactly the one new bench directory; `git ls-files runs/` empty |

**Incidents on the way (all disclosed).**

1. **The sync-activity defect, caught live.** The worker refused to
   boot: `measure_code_axis` was a sync def and the worker runs no
   sync-activity executor (the sequence tests' stub is async, so the
   unit tier never saw it). Fixed in commit `58871313` (async def; the
   unit tests drive it through an asyncio.run wrapper).
2. **Attempt 1 parked at the research stage gate.** `research_enabled:
   true` on this case is newer than 012's smoke (whose research leg was
   4 s); a SOFT gate without a calibrated (gate, model) verdict waits
   for a human decision (48 h deadline). Terminated per the 012
   precedent resolution, relaunched with `--gate-policy off`. The
   aborted dir was removed; the fingerprint returned to baseline.
   (Bonus live proof: the aborted run's axis record — reason
   `code stage did not finish`, figures None, 0.21 s — the fail-safe
   path exercised for real.)
3. **Attempt 2 terminated and its records deleted by an external
   actor.** The child workflow was terminated at 18:36 local via
   temporal-cli executed inside the bench temporal container (identity
   `temporal-cli:temporal@431d580733fe`), and `runs/benchmarks/<id>/`
   was deleted from the host in the same minute. Not this session (its
   two terminate calls were 80 minutes earlier, for attempt 1 only)
   and not the web UI (the identity is the CLI). The parallel
   `015-corpus-acceptance` session was actively editing the benchmarks
   package in that window. All 33 records of that attempt were
   recovered from the temporal histories (evidence file
   `wf015-recovered-records.json`, temp).
4. **Attempt 3's records dir deleted mid-run (22:28) — the same
   external pattern.** The worker self-healed (the recorder mkdirs its
   path on append), losing the four stage records written before the
   deletion (research, clarify, architecture, plan). After the run
   completed, the complete 48-record file was reconstructed in event
   order from the two workflow histories (the payloads ARE the records;
   the reconstruction is byte-faithful) and the bench-dir score was
   regenerated over the complete file — the finalize had scored the
   incomplete one.
5. **Retain DNS noise, tolerated.** 49 `retain` failures on
   `hindsight:8888` unresolvable inside the bench project — the exact
   012-documented tolerance; no stage record affected, the run
   continued.

The compose project was torn down after verification; the run's
records and score outputs remain the corpus's one new directory.
