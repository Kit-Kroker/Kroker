VERDICT: approve

## Pass 2 (2026-11-08)

Re-checked the five pass-1 gaps plus a fresh placeholder and stale-ref
sweep. Four gaps are resolved; gap 1 is resolved everywhere it drives
execution, but its spec-side fix stopped halfway inside User Story 4.

1. **RESOLVED — counts and the Feature/non-Feature split.** Spec C1
   ("19 of 22", "the 18 `SCENARIOS` plus `research_retain_grounded`"),
   the card-table golden row (19 goldens = 18 FW-captured +
   `assessment_discover_risk`, AssessmentWorkflow, unchanged), plan
   §Summary ("19 histories (18 scenarios plus `research_retain_grounded`)
   and 18 goldens"), §Scale/Scope ("37 fixture `.json` files … 19
   histories, 18 goldens"), T041 ("all 18 `SCENARIOS`"), the replay-safety
   row ("18 scenario histories"), research R-4 ("all 18 `SCENARIOS`"),
   data-model §4 (18/18, `golden/assessment_discover_risk.json` listed
   unchanged) and the test-inventory header (19 FW histories, 18 FW
   goldens) all now match the tree at `d57c381d` (`SCENARIOS` = 18;
   `write_fixtures` writes one history + one golden per scenario).
2. **RESOLVED — `DEFAULT_LINT_CMD` target.** test-inventory §Known
   special cases and plan T012 now point at `sdlc.stages.merge.step`
   (`merge/step.py:66`, verified).
3. **RESOLVED — stale task ids.** No `T020`/`T031`/`T061` remains; a full
   `T0xx` sweep across all nine artifacts finds zero referenced-but-
   undefined tasks (T010–T019, T030, T040–T046, T050–T054, T059, T070,
   T080–T082, T089–T092).
4. **RESOLVED — line cite.** spec Card-verification now reads
   `_fetch_closed` (`fleet.py:105`) — verified against the tree.
5. **RESOLVED — citation nits.** R-7 now cites
   `tests/calibration/test_calibration_plumbing.py:188` (exists); T012
   states the `_validate_task_graph` → `validate_task_graph` rename
   (plan.md:161) and the `DEFAULT_LINT_CMD` source (plan.md:162).

**NEW GAP (open):**

6. **User Story 4's acceptance scenarios still tell the pre-C1 story**
   (spec.md §User Story 4, scenarios 2–3). Scenario 2 says "the four
   non-Feature histories (benchmark, assessment, architect-research
   usage, research-retain)" — per C1 there are **three**, and
   `research_retain_grounded` is FeatureWorkflow (it is re-captured by
   T041) — and "**When** FeatureWorkflow histories are removed". Scenario
   3 says "Given the FeatureWorkflow-captured histories are deleted".
   FR-010 and C1 rule **replacement in place** by a GraphWorkflow
   re-capture, not removal or deletion; the histories are re-captured in
   place (T041) and only the replay *test* goes (`test_feature_replay.py`,
   T044). Scenario 1 of the same story was corrected in pass 2 ("the 18
   FeatureWorkflow-captured goldens"); scenarios 2–3 were not, and as
   written they contradict FR-010/C1 and the pass-2 claim that US4 was
   fixed. One-paragraph rewording: three non-Feature histories
   (benchmark, assessment, architect-research usage), "replaced in place
   by GraphWorkflow captures" instead of "removed"/"deleted".
   Sub-nit, same class: the card-verification row at spec.md:43 still
   lists `research_retain_grounded` among the "Four histories [that] are
   not FeatureWorkflow runs"; C1's header ("These correct the
   verification table above") supersedes it, but the cell contradicts the
   corrected C1 arithmetic one paragraph later.

Placeholder sweep: clean across all nine artifacts. New citations added
in pass 2 all verify (`merge/step.py:66`, `feature.py:67`,
`tests/calibration/test_calibration_plumbing.py:188`,
`tests/replay/scenarios.py`).

# Plan Quality Checklist: Delete FeatureWorkflow (round 020)

## Pass 1 checklist — superseded summary

Pass 1 (2026-11-08) returned fixes-needed with five gaps:
1. fixture counts / FW split wrong across spec C1 + card table, plan
   Summary/Scale/T041/replay table, research R-4, data-model §4,
   test-inventory header — **resolved** (item 1 above);
2. `DEFAULT_LINT_CMD` repoint target pointed at `qa.step` — **resolved**
   (item 2);
3. stale task ids T020/T031/T061 — **resolved** (item 3);
4. `fleet.py:104` off by one — **resolved** (item 4);
5. R-7 path unqualified; `_validate_task_graph` rename unstated —
   **resolved** (item 5).

The pass-1 traceability, gate-discipline, replay-safety, classification,
PR-1 grace-edit and file:line spot-check records (CHK001–CHK014, 25+
citations verified) all stand; none was affected by the pass-2 edits.

## Pass 2 checklist

- [x] CHK-P2-01 - Are the five pass-1 gaps fixed? [Traceability] — Yes
  for 2–5 fully; for 1, every execution-driving artifact (plan, research,
  data-model, test-inventory, contracts, quickstart) is corrected and
  self-consistent; the spec-side fix is incomplete inside US4 (gap 6).
- [x] CHK-P2-02 - Placeholder sweep over all nine artifacts? [Clarity] —
  Clean (TODO/TBD/TKTK/FIXME/??? none).
- [x] CHK-P2-03 - Stale-reference sweep (task ids and `file:line`)?
  [Consistency] — Zero undefined `T0xx` references; every `file:line`
  newly cited in pass 2 exists in the tree.
- [ ] CHK-P2-04 - Do US4's acceptance scenarios agree with FR-010/C1's
  replace-in-place ruling? [Consistency, spec §US4] — **No**; gap 6
  ("four non-Feature histories" including research-retain; "removed"/
  "deleted" instead of "replaced in place").

## Notes

- Gap 6 is doc-level and one paragraph wide; no task, gate, PR split or
  safety argument changes. Everything the executor reads to do the work
  (plan, data-model, research R-4, test-inventory, contracts, quickstart)
  is consistent and correct at `d57c381d`.

## Pass 3 (2026-11-08)

Gap 6 re-checked, plus the requested sweep. **Resolved.**

- spec.md:43 (card-verification row) now reads "Three histories are not
  FeatureWorkflow runs" (`benchmark_one_cell`, `assessment_discover_risk`,
  `architect_research_usage`), states that `research_retain_grounded` is a
  FeatureWorkflow history a live test loads, and carries a "(see C1)"
  pointer. Consistent with C1's 19-of-22 arithmetic. The row's first cell
  still says "deleted wholesale" — that is the card's own hypothesis under
  verdict, which is the table's purpose; not a defect.
- US4 scenario 2 now says "the three non-Feature histories" and "the 19
  FeatureWorkflow histories (the 18 scenarios and
  `research_retain_grounded`) are replaced in place by GraphWorkflow
  captures", with the three byte-unchanged and every replay/chaos test
  still finding its history. US4 scenario 3 says the histories are
  "replaced in place" and only `test_feature_replay.py` is removed, with a
  GraphWorkflow replay test replaying every one. Both match FR-010/C1.
- Sweep of spec.md (and the rest of the artifact set) for "removed"/
  "deleted" wording about histories: clean. Remaining hits are the
  FeatureWorkflow class/code deletion, gate and deletion-task prose,
  FR-003/005/007 removals, the "never removed" query note, and the card's
  quoted hypothesis — all correct usages.
- Placeholder sweep: clean.

All pass-1 gaps (1–5) and pass-2 gap (6) are resolved. The plan is
approved: FR-001..FR-016 and SC-001..SC-007 trace to tasks and
validations, both gates are blocking and were not run during planning,
the replay-safety table covers every execution class, FR-009 matches
R-1, the 76-file classification is concrete with a closed class set and
counterpart rule, PR-1 stays off FeatureWorkflow's command sequence, and
every cited `file:line` verified against the tree at `d57c381d`.
