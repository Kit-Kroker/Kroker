# Reviewer brief — round 024 plan, pass 2

The context is the same as pass 1 (`checklists/reviewer-brief-plan-1.md`); its rules all apply. Your pass-1 verdict was `fixes-needed`, with gaps 1–6 in `checklists/plan.md`. The spec lead has applied fixes:

1. **Gap 1 (blocking).** `research.md` §R1 now has "Rollback differs by input family": 7 of 8 inputs are benign; the maintenance family is `extra="forbid"`, so it gets a loud refusal plus a remedy. `plan.md` Risk 5 is restated, and E2 now carries the remedy. It is surfaced at GATE 2.
2. **Gap 2.** The R3 ceiling paragraph is corrected (`assessment.py` 843, `cli.py` about 12 lines). The constitution table matches.
3. **Gap 3.** quickstart §5 now has the required `docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q`. The plan's P-FR-010 traceability row cites it.
4. **Gap 4.** quickstart §1 is split into §1a (024-i) and §1b (024-ii). F3 names §1a plus the C3 proof command.
5. **Gap 5.** `ReflectWorkflow` is named as all-core in W-2, H3, the traceability row and R4. R4's list now includes deploy.
6. **Gap 6.** The D1 hash check is recorded in R1. Also, the data-model `pipeline_child.py` lines are corrected to 53 and 82.

Do: re-verify each fix against the artifacts and the code. Check that nothing else regressed. Update `checklists/plan.md`: put the new verdict on line 1, exactly `VERDICT: approve` or `VERDICT: fixes-needed`, then a "Pass 2" section listing each gap as resolved or not, plus any new gaps. Reply in the pane with only the verdict word.
