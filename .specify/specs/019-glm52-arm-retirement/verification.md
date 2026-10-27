# Round 019 verification: glm-5.2 arm retirement

Branch `019-glm52-arm-retirement`, base `6ba483a6`, closed 2026-10-27.
Commits: T001 `c85d0500` (planning artifacts), T006 `53f5e51b`
(baseline), T010 `6ac3d9b8` (FR-009), T015 `68c46eb5` (FR-003),
T017 `194e3ec6` (FR-004), T029 `38320789` (repo re-pair + re-label),
T039 `026707c1` (docs + marker), plus this closing commit. Private
store: `D:\own\sdlc-private-cases` commit `1fe7eb8` (theatre-box-office).

Container: quickstart §1 throwaway (`r019-verify`) with the worktree at
`/app`, runs root **read-only**, `SDLC_PRIVATE_CASES_ROOT=/srv/private-cases`.
Recorded deviation (baseline.md §Fast tier): the pytest tiers ran from
`/work`, a container-local `git archive` copy of the same tree, because
the `/app` bind mount runs at ~6.6s/test (projected ~14h); mutating
commands (every `benchmark accept`) ran against `/app` as specified.

## FR / SC evidence

- **FR-001 (sweep surface clean)** — T041: the mechanical grep
  `grep -nE "^[^#]*glm-5\.2"` over repo case.yaml, agents/*/agent.yaml,
  benchmarks/config.yaml and the private case.yaml files prints
  **nothing**. The Python-string grep prints only
  `src/sdlc/core/models.py:190` (a `# e.g.` comment). The broad sweep
  shows only allowed history hits (FR-006 blocks, todo-api/crew-probe
  comments, planner route comment, models.py:190).
- **FR-002 (per-case re-pair)** — T029 `38320789`: seven case.yaml
  re-paired per data-model §1 (glm-5.3 arm first, flash byte-for-byte,
  two-entry models, extra_args deleted in cat-cafe); theatre in PRIV
  `1fe7eb8`. T026: the four loader test files green (50 passed) after
  the re-pair.
- **FR-003 (shipped test role)** — T015 `68c46eb5`: agent.yaml +
  PipelineConfig mirror + conftest fixture + both registry test files in
  one change set; targeted set 146 passed; registry mirror validated at
  boot (`test_shipped_registry_loads_and_validates` green).
- **FR-004 (importer default)** — T017 `194e3ec6`: RED
  `test_build_case_dict_default_model_is_glm_5_3` failed on the old
  default, green after the one-line change.
- **FR-005 (re-label, no spend)** — T027/T031: eight online accepts
  (seven repo + theatre), every printed line matched contract §2
  exactly (below). No `benchmark run`, no pipeline run, no model call
  (SG-7 never fired; the runs root was mounted read-only the whole
  round).
- **FR-006 (dated notes)** — each of the eight case.yaml carries the
  R019 2026-10-27 comment above `strong_arm:` with the per-case prior
  verdict from baseline §Records (see T029/T033 diffs).
- **FR-007 (expected verdicts)** — actual printed lines vs the D-3
  table, all exact:

  | case | expected | printed |
  |---|---|---|
  | cat-cafe-monitoring | not_assessed | `cat-cafe-monitoring: not_assessed` |
  | deveval-geotext | not_assessed | `deveval-geotext: not_assessed` |
  | deveval-readtime | not_assessed | `deveval-readtime: not_assessed` |
  | deveval-lice | rejected (reference) | `deveval-lice: rejected (reference)` |
  | deveval-hone | not_assessed | `deveval-hone: not_assessed` |
  | deveval-particle-swarm-optimization | not_assessed | `deveval-particle-swarm-optimization: not_assessed` |
  | deveval-stocktrends | not_assessed | `deveval-stocktrends: not_assessed` |
  | theatre-box-office | not_assessed | `theatre-box-office: not_assessed` |

  Gated fields held on every record: `separation.strong.arm ==
  zai-coding-plan-glm-5.3` with `strong.run_ids == []` (lice included —
  the online re-label computed a separation, per the plan pass-1
  correction); parked trio carries the sentinel. `kroker_commit` =
  `194e3ec6` (repo, T017 HEAD) / `38320789` (theatre, re-read after
  T029), both verified. **SG-2 never fired.**
- **FR-008 (records untouched)** — T003/T040: `baseline-records.sha256`
  (1033 files) re-computed at close and diffed: **identical**. SG-1
  clear.
- **FR-009 (arm-drift staleness)** — T007 RED first (below), T008
  GREEN, `6ac3d9b8`. Phase 3 checkpoint: corpus output after the change
  diffed empty against baseline §Corpus (no row flips, D-6 held).
- **FR-010 (docs)** — T039 `026707c1`: BENCHMARK.md R019 break marker
  with the 8-row verdict table (tally 1 → 0 of 8); README example on
  glm-5.3; config.yaml judge comment states the actual
  anthropic:claude-sonnet-5 rationale; README:316 route note untouched.
- **FR-011 (re-proving out of round)** — follow-up card at
  `D:\own\Kroker\.workspace\tasks\2026-10-27-r019-reprove-separation-reruns.md`
  (outside git): the four `benchmark run --all-arms` commands,
  both-arms-one-commit n ≥ 3, paid-run clearance marker, glm-5.3 429/Q0
  note, dashboard-mock scope, arm-definition-hash candidate. Not
  executed.

- **SC-001** — T041 sweep, pass (above). **SC-002** — all 10 repo cases
  and theatre load (T026/T032 corpus walks + loader tests). **SC-003** —
  every re-label verdict equals its FR-007 row; `benchmark corpus`
  prints `0 of 8 accepted or provisional, 0 of 2 private` (T028/T032),
  no stale row. **SC-004** — manifest 1033/1033 identical at close.
  **SC-005** — RED before / GREEN after for FR-009 and FR-004 (below);
  final fast tier vs baseline below. **SC-006** — $0 model spend: no
  `benchmark run`, no pipeline run; every accept was online-but-local.

## T027/T031 logged count drift (logged, never gated)

oracle_tests, reference and floor totals are unchanged everywhere; only
`not_comparable` moved, exactly as the arm link breaking predicts:

| case | not_comparable old → new | why |
|---|---|---|
| cat-cafe-monitoring | 10 → 11 | +1 glm-5.2 run now incomparable |
| deveval-geotext | 0 → 2 | glm-5.2 run + the stored flash run (case was oracle-drifted at base, so the flash run predates the current oracle identity) |
| deveval-readtime | 0 → 2 | same as geotext |
| deveval-lice | — → 0 | old record had no separation object (offline accept); the online re-label computed one |
| deveval-hone / pso / stocktrends | 0 → 0 | parked sentinel, no graded evidence |
| theatre-box-office | 0 → 1 | +1 glm-5.2 run; the flash run carries (oracle-fresh) |

Consequence: weak.run_ids keeps the flash run only for cat-cafe and
theatre (oracle-fresh at base); geotext/readtime weak.run_ids are empty
because their stored flash runs are oracle-incomparable. Data-model §2's
weak.run_ids cell predicted the carry for all four; the gated fields
(verdict/reason/strong.arm/strong.run_ids) all held. Recorded as a
plan-prediction deviation, not a stop.

## RED evidence

**T007 (FR-009)** — `pytest tests/test_benchmark_corpus.py -k arm_drift`
before the corpus.py change, after the orchestrator-ruled T7 single-root
amendment:

```
FAILED tests/test_benchmark_corpus.py::test_arm_drift_t1_strong_changed - ass...
FAILED tests/test_benchmark_corpus.py::test_arm_drift_t2_weak_changed - asser...
FAILED tests/test_benchmark_corpus.py::test_arm_drift_t3_weak_newly_declared
FAILED tests/test_benchmark_corpus.py::test_arm_drift_t4_no_strong_record_now_declared
4 failed, 3 passed, 12 deselected
```

Exactly T1–T4 failing, T5–T7 passing, per contract §1. Deviation and
ruling: the first RED run (T1+T7 in one cases root, per tasks.md T007's
construction note) showed 5 failed / 2 passed — T7 necessarily failed
pre-fix because both provisional rows counted ("2 of 8"). Per T007's
stop-and-report the round halted; the orchestrator ruled option 1 (T7
single-root, negative pinned by T1's own assertion, contract §1's RED
pattern preserved). GREEN: `-k arm_drift` 7 passed; full file 18 passed
1 failed (pre-existing baseline failure).

**T016 (FR-004)** — `pytest tests/test_deveval_importer.py -k
default_model` before the deveval.py change:

```
FAILED tests/test_deveval_importer.py::test_build_case_dict_default_model_is_glm_5_3
1 failed, 35 deselected
```

**T018 (real-case tests)** — before the case edits:

```
FAILED tests/test_benchmark_corpus.py::test_seven_corpus_cases_have_two_arms_and_matching_base_cells
FAILED tests/test_golden_case_loads.py::test_cat_cafe_case_loads_as_one_cell
2 failed
```

**T012 (role flip)** — pins flipped before the sources:
`pytest tests/test_agents_registry.py tests/test_registry_mirror.py` →
5 failed / 28 passed (all naming the glm-5.2↔glm-5.3 mismatch), green
after the flip.

## Gates (T042, close)

- Fast tier: **10 failed, 6581 passed, 19 skipped, 275 deselected** —
  SG-4 clear: every failing node id is in baseline.md §Fast tier. Two
  baseline failures cleared: `test_committed_records_match_their_cases`
  (the re-labels re-stamped oracle ids) and the promptfoo import-timing
  artifact (warm cache). `test_sc003_recompute_stored_acceptance`
  persists with a changed failure mode (baseline: oracle-drift
  mismatch; now: "at least one case … must be verified, assert 0 > 0" —
  no stored record matches its pre-R019 shape any more).
- Replay: **34 passed, 21 skipped, exit 0** — identical to the T005
  baseline; SG-5 clear after the role flip.
- `ruff check .` — all checks passed. `ruff format --check .` — 1854
  files already formatted. `mypy` — Success, no issues in 407 source
  files (same as base). Host `python scripts/check_file_size.py` —
  exit 0 (BENCHMARK.md 855 lines).

## Bug-crew candidates (main defects outside this round's items, rule 5)

Pre-existing fast-tier failures on main, reported, not fixed here:

1. `tests/test_deveval_corpus.py::test_imported_cases_state_role_and_visibility`
   still asserts `corpus` for the three cases round 017 parked
   (hone/pso/stocktrends).
2. `tests/test_todo_api_case_loads.py::test_todo_api_case_file_exists_and_loads`
   still asserts 1 cell for todo-api-greenfield, re-paired to two arms
   in round 017.
3. `tests/test_prompt_migration.py::test_prompt_shas_did_not_move` —
   pre-migration SHAs no longer satisfied after later prompt edits.
4. `tests/test_benchmark_acceptance_stalled.py::test_sc003_recompute_stored_acceptance`
   (persistent; failure mode changed after R019's honest re-labels as
   described above).

## Known limits and risks

- **D-3 confounder**: carried flash runs were graded on older commits;
  re-proving separation needs both arms on one commit, n ≥ 3 each
  (follow-up card).
- **D-6 limits**: the staleness rule compares arm names only
  (arm-definition hash is a follow-up candidate); `separation: null`
  records are exempt.
- **D-7 risk**: dev and test are now both glm-5.3; plain pipeline runs
  put three roles on the full glm-5.3 quota. The 429/5xx backoff
  (`dea09d36`) is the standing mitigation; glm-5.3 burst survival is
  unmeasured (Q0 proof deferred to the follow-up card).
- glm-5.2 run records remain under `runs/benchmarks` as history, now
  `not_comparable`; old run ids naming the glm-5.2 arm read as history
  only.
