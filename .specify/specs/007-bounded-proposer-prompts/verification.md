# Verification: 007-bounded-proposer-prompts

T012 record. All commands run in `kroker-dev` on branch
`007-bounded-proposer-prompts` at HEAD `2619de6` (worktree
`D:\own\Kroker-007`), one pytest invocation per command, RC captured per
command. quickstart.md sections 3, 4 and 5, each command separate.

## quickstart.md §3 — in a real workflow (temporal tier)

| Command | Result | RC |
|---|---|---|
| `pytest -m temporal tests/durability/test_payload_guard_workflow.py` | 4 passed (43.49s) | 0 |

## quickstart.md §4 — nothing else moved (temporal tier)

| Command | Result | RC |
|---|---|---|
| `pytest -m temporal tests/replay` | 32 passed, 19 skipped, 164 deselected (151.47s) | 0 |
| `pytest -m temporal tests/durability/test_wire_neutrality.py` | 1 passed (58.20s) | 0 |
| `git status --short tests/replay/histories tests/replay/golden` | empty — no history or golden modified | 0 |

## quickstart.md §5 — whole feature

| Command | Result | RC |
|---|---|---|
| `pytest` (fast tier) | 5506 passed, 1 failed, 11 skipped, 251 deselected (883.47s) | 1 |
| `ruff check .` | All checks passed | 0 |
| `ruff format --check .` | clean | 0 |
| `mypy` | Success: no issues found in 379 source files (baseline 378; +1 = `payload_guard.py`) | 0 |
| `python scripts/check_file_size.py` | clean | 0 |
| `git diff 721a802 --stat -- src/sdlc/stages src/sdlc/workflows/role_host.py pyproject.toml uv.lock agents` | **empty** | 0 |

The single fast-tier failure is the documented ambient flake
`tests/test_promptfoo_provider.py::test_provider_imports_fast_enough_for_the_promptfoo_worker`
(8 s cold-import wall-clock budget under multi-pane load; inbox task
`2026-09-07-flaky-provider-import-test.md`, orchestration protocol "Open
items"). Isolation re-run of the module on the same tree: **15 passed,
RC=0**. Not a 007 regression.

## Pass-count delta against baseline.md

| | Baseline (`721a802`) | Final | Delta |
|---|---|---|---|
| fast tier passed | 5488 | 5506 (+1 ambient flake failing in the full run) | +19 = this feature's new fast-tier tests: 8 (T002/T003 guard module incl. wire pin) + 4 (T004 case 8) + 4 (T006 call sites) + 3 (T008 assessment call sites) |
| temporal tier | not baselined | 4 passed (payload-guard workflow module: 3 T007 + 1 T008 growth) | all green |
| mypy | 0 errors / 378 files | 0 errors / 379 files | +1 file, 0 errors |

## Stop-guards

- SG-1 (replay/golden/wire-neutrality): clear — §4 above; no history or
  golden re-recorded. One anomaly during T005's first full-tier run: two
  replay params (`arch_timeout_reject`, `plan_revise_approve`) tripped
  TMPRL1101 under load; both green in isolation and the whole replay
  module green on the same tree — the documented load-dependent replay
  flake family (006 baseline; `2026-10-02-golden-graph-trace-flake.md`).
- SG-2 (uncovered path / red PIN): clear — T006, T007, T008 all green
  on first effective run; the two disclosed test-side scaffolding
  iterations (qa seats' own harness bugs, each diagnosed and fixed
  without touching `src/`) did not falsify any plan-D4/R6 claim.
- SG-3 (`has_payload_guard` false for a real durable agent): clear —
  `test_every_temporal_agent_carries_the_guard` green over all 16.
- SG-4 (`test_first_workflow_task_time.py` regression): clear — 2
  passed at T005.
- SG-5 (forbidden-path edit or dependency change needed): clear — the
  forbidden-path diff is empty; no dependency changed. One near-miss,
  resolved inside the task: the first T005 draft imported
  `payload_guard` at module level in `loader.py`, which broke two
  import-hygiene pins (`graph_purity`, `calibration`) — fixed with the
  repo's lazy-import pattern inside `build_agents` (roles.py, already
  temporal-heavy, imports at module level).
- SG-6 (T009 finds an input that can plausibly reach the limit on an
  ordinary run): **no fire.** Rows verified and capped: recall items
  (4096-token budget, `hindsight_client.py:107/:222`), QA raw JSON
  (issues slice 2000 chars + failing 50, `qa/activities.py:295/:307/:285`),
  research tool-call count (`deps.py:45-47/:85-91`), synthesis findings
  count (`max_sub_questions` 4, `core/models.py:278`). Still uncapped
  and unchanged in estimate: idea brief / gate text (user input), diff
  stat (very wide change needed), merge verdict dump (many-task runs),
  discover/risk scan counts (large repos), scrubbed transcript (512 KiB
  cap, closest real trigger). Nothing was capped (FR-009).

## Per-task commits

| Task | Commit | Subject |
|---|---|---|
| T001 | `b165e05` | docs(spec): 007 spec set and baseline on unmodified main |
| T002+T003 | `26a32a2` | feat(agents): add the proposer payload guard module (007-T002+T003) |
| T004+T005 | `5c70fac` | feat(agents): attach the payload guard to every durable agent (007-T004+T005) |
| T006 | `1b6b0df` | test(durability): pin the guard error's call-site outcomes (007-T006) |
| T007 | `d2d7ac5` | test(durability): pin the guard end to end in a real workflow (007-T007) |
| T008 | `ef3a0b7` | test(durability): pin growth-during-call and assessment coverage (007-T008) |
| T009 | `05ad6a2` | docs(research): verify R7 input inventory against producers (007-T009) |
| T010 | `f5d4c33` | docs(workflows): living docs section for the payload guard (007-T010) |
| T011 | `2619de6` | docs(architecture): name the runtime payload guard in section 11 (007-T011) |
| T012 | this commit | docs(spec): record 007 verification; all 12 tasks complete |

Every task passed the blocking reviewer gate before the next started
(verdicts: approve on T001, T002-RED, T003, T004-RED, T005, T006, T007,
T008, T009, T010+T011).
