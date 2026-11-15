# Verification — round 023b (DAPER acts and verifies)

Closed 2026-11-15 against `src/sdlc/workflows/maintenance.py` +
`src/sdlc/workflows/maintenance_execute.py` + `src/sdlc/maintenance/`
(`execution.py`, `render.py`, `cli.py`) + the reuse of
`src/sdlc/memory/activities.py`. T001–T053, one commit per task, a
blocking reviewer gate per commit, qa seats writing the RED suites
first (T046's CLI suite executor-adapted once, disclosed there).

## The T052 battery (SC-B09 anchor)

Commands (quickstart §3) on the final tree, this checkout:

- `ruff check .` clean; `ruff format --check .` 2112 files clean;
  `mypy` clean (447 source files); `python scripts/check_file_size.py`
  clean (ceilings honored; the round's largest file is
  `maintenance_execute.py` at 539).
- `pytest -q` (fast tier): **2 failed, 7686 passed, 22 skipped, 360
  deselected**. The FAILED set is exactly
  `{test_benchmark_acceptance_stalled::test_sc003_recompute_stored_acceptance,
  test_prompt_migration::test_prompt_shas_did_not_move}` — a **strict
  subset** of `baseline-failures.txt`'s four ids, no novel ids. The two
  absent ids are the `test_read_fixtures_fresh.py` checks the baseline
  header itself calls worktree artifacts (they pass on the primary
  checkout, and the round's fixture-regen hygiene commit `1d88d7d3`
  re-aligned them after another workstream's FR-301 graph revision
  stale-d the shipped-graph identity). "Identical" is therefore
  recorded as: observed ⊆ baseline, both extra baseline ids explained
  in the baseline file itself.
- `pytest tests/replay/`: exit 0, 109 tests; `git status --short
  tests/replay/` empty — replay untouched for the whole round.
- `pytest -m temporal tests/maintenance/ tests/test_tidyup*.py
  tests/test_triage_workflow_e2e.py`: exit 0, 93 tests (83 maintenance
  + 9 tidyup + 1 triage e2e).

## SC-B01..SC-B11 mapping

| SC | Evidence (test ids) | Verdict |
|---|---|---|
| SC-B01 — repairing fixes reach `verified` within one cycle of the verdict; non-repairing reopen then escalate at the bound | `test_workflow_exec_us2.py::test_fix_is_verified_and_the_child_keeps_its_merge_gate` (verify pass → verified same cycle); `us2::test_three_nofix_attempts_then_escalated_with_one_notification`, `us2::test_configfail_escalates_after_attempt_one_without_a_reopen`, `us2::test_escalation_is_terminal_with_no_residue_on_the_execute_path` | Met |
| SC-B02 — zero children for a judgement/structural plan without a recorded human decision | `test_execution.py::test_policy_refuses_a_mixed_plan_of_ops_and_code_fix`, `::test_policy_refuses_an_ops_only_plan`, `::test_human_refuses_an_ops_only_plan_with_the_verbatim_outcome`; `may_execute` refuses anything unapproved and the refusal opens a human gate (`us5` refusal cells) | Met |
| SC-B03 — zero ops actions executed | The same `test_execution.py` policy-refusal cells: an ops-only or mixed plan never reaches `may_execute`'s positive path; the loop has no ops execution code at all (grep `maintenance_execute.py`: no ops runner) | Met |
| SC-B04 — no `closed` without a collected default-branch Detect omitting the identity at a commit containing the child's head; no `verified` credit for a finding absent at base | `test_execution.py::test_absent_and_an_ancestor_closes_the_incident`, `::test_absent_and_not_an_ancestor_is_resolved_externally`, `::test_absent_at_base_resolves_externally`; `us4::test_a_merged_fix_seen_on_the_default_branch_is_closed` (the commit-honoring fakes read `ls-tree <sha>`/`git show <sha>:path`); `us2::test_a_verify_triage_that_is_not_collected_stays_verifying` (not-collected never closes) | Met |
| SC-B05 — cycle completion independent of in-flight children | `us5::test_an_overlapping_incident_queues_without_holding_the_cycle_or_starting`; `us2` park cells (cycles advance past a parked child); `durability::test_a_parked_child_re_attaches_after_a_roll_over_with_the_state_carried` | Met |
| SC-B06 — per-cycle and 7-day-window caps; queued incidents never lost or re-gated | `test_execution.py` `choose_starts` cells (`::test_one_cap_starts_the_lowest_number_and_queues_the_rest`, `::test_starts_chosen_earlier_in_the_same_cycle_count_toward_the_window`, `::test_a_queued_incident_starts_on_the_next_call_and_call_one_stamp_counts_toward_it`, `::test_a_path_overlap_with_a_live_incident_queues_without_consuming_a_start`); `us5::test_three_approved_incidents_start_one_per_cycle_and_never_re_gate`, `::test_a_fourth_incident_stays_queued_with_one_window_notice_per_cycle`, `::test_the_window_survives_a_forced_roll_over` | Met |
| SC-B07 — a memory outage causes zero failed cycles; every retained record scrubbed | `us6::test_a_failing_memory_backend_never_stops_the_incident_closing` (the retain activity raises; the incident still closes, cycles advance); `retain_step` swallows and retries deduped (T043); `test_render_023b.py` pins that `render_retention` never echoes `finding.evidence`; the activity-side scrub hook still runs (R13) | Met |
| SC-B08 — zero duplicate children/incidents/gates/retention across restart and retry | `durability::test_a_worker_crash_mid_verify_leaves_one_child_one_record_one_retention` (worker killed mid-verify-probe, both workers at `max_cached_workflows=0`: exactly one child id, one ExecutionRecord, one gate round, one retention); `test_start_repair_child.py` (second call → `attached`, REJECT_DUPLICATE + ABANDON); `us1`'s start-id uniqueness cells | Met |
| SC-B09 — replay fixtures and benchmark records byte-identical; fast tier at the recorded baseline | The battery above: replay exit 0, tree untouched; benchmark registry untouched (the round diff over `benchmarks/` and `agents/registry.yaml` is empty); fast tier a strict subset of the baseline ids | Met |
| SC-B10 — zero PRs from a dirty-verdict child; zero child merge gates approved by the loop | `test_execution.py::test_merge_reject_decision_builds_a_reject_on_the_merge_gate` (+ verbatim-comment and every-verdict-is-reject cells); `us2::test_a_missing_integration_branch_is_recorded_conflicted_and_rejected`, `us2::test_nofix_gets_exactly_one_reject_and_the_incident_reopens`, `us4::test_a_regression_after_merge_is_dirty_and_reopens_without_a_reject`; the loop's gate decision vocabulary is REJECT-only (maintenance/AGENTS.md invariant, pinned by these cells) | Met |
| SC-B11 — a child in flight survives a roll-over and is re-attached | `durability::test_a_parked_child_re_attaches_after_a_roll_over_with_the_state_carried` (byte-equal `model_dump(mode="json")` across a forced `continue_as_new`, then the next history's verify re-attaches to `verified`); `us5::test_the_window_survives_a_forced_roll_over` | Met |

## FR-502 re-read against shipped behaviour

FR-502: "repair `code_fix` as brownfield child runs; risk-classed ops
actions." The **code-fix clause is met**: an approved `code_fix` plan
runs as a real brownfield pipeline child (T010's `start_repair_child`,
REJECT_DUPLICATE + ABANDON, sandboxed per-task worktree, diff admitted
as the artifact), capped, timeout-bounded, verified, and closed or
reopened on its verdict. The **ops clause remains open**: risk-classed
ops actions are proposal-only (023a GATE 2 ruling, unchanged) — the
policy refuses to execute any ops-bearing plan (`test_execution.py`
SC-B02/B03 cells). FR-502 stays `[ ]`: an honest partial at P4 close.

## Residuals (recorded, not fixed)

1. **The live execution run is owner-deferred** (B-FR-022, quickstart
   §5): no paid run of the loop against a real repository happened in
   this round; every cell is fixture-tier (temporal env + git fixtures
   + stub children).
2. **No lesson invalidation**: a lesson retained for `closed` is never
   invalidated if a later regression contradicts it; retention is
   append-only.
3. **No stale-PR handling**: an incident whose child's PR is verified
   but never merged stays `verified` indefinitely (the `UNMERGED_HINT`
   surfaces it; nothing reaps it).
4. **Squash merges are experience-only**: a squash-merged fix resolves
   the incident `resolved_externally` (no provable per-fix provenance),
   recorded as an INCIDENT_EXPERIENCE, never a LESSON
   (`us4::test_a_squash_merged_fix_is_resolved_externally_with_no_lesson`).
5. **Advisory execution is unit-tier only**: the advisory scan executes
   its pipeline in unit tests; no live advisory run happened.
6. **Disable-time retention**: incidents withdrawn by `disable` are
   set terminal in `run()` after the cycle loop, so they are NOT
   retained unless a later cycle runs. Flagged at the T043/T045 gates;
   unpinned by T042/T044 (their cells never disable-then-retain).
7. **T009's outcome — the sha base was accepted**: `build_run_input`
   passes a 40-hex `base_branch` through untouched (intake has no pure
   validator that would reject it), so R3's named fallback (recording
   the child's actual base from `RunState`) was not required; the test
   additionally drives `setup_integration_branch` with a sha `from_ref`
   directly (commit `0232172c`).
8. **Benchmark provenance**: the registry was NOT touched by this round
   (empty range diff over `benchmarks/` and `agents/registry.yaml`);
   no provenance note is needed beyond this line.
9. **T040's capture adaptation**: the pathological-bound cell builds
   its input at `RepairPlan.analysis`'s own `max_length=4000` ceiling —
   qa's original 5400-char fixture was unconstructible against the
   model. The 2000-char render bound still bites (disclosed at T041,
   in the cell).

## Round mechanics

53 tasks, T001–T053; commit 0 (spec artifacts) through this file. The
loop's `GraphWorkflow` was never modified; every new workflow command
sits behind `cfg.execute` AND `workflow.patched("maint-023b-execute")`;
`tests/replay/` untouched throughout; the only child-gate decision the
loop can make is REJECT; ops actions were never executed. tasks.md
boxes are ticked in the same commit as this file.
