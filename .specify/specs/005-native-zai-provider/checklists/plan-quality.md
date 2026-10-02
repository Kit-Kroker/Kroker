# Checklist: Plan Quality — 005 Native zai Provider

**Purpose**: Unit tests for `plan.md` (with research.md, data-model.md, contracts/zai-route-contract.md, quickstart.md) — completeness against the approved spec (incl. Resolved Decisions and Post-GATE-1 amendments A1–A9), internal consistency, unambiguity, verifiably gated constraints. Not implementation tests.

**Created**: 2026-10-02 (reviewer seat; verified against main `0f4ac11`)

## Plan Completeness

- [ ] CHK001 - Does the plan carry a design decision or explicit exclusion for every functional requirement FR-001..FR-016, with none silently dropped? [Completeness, Plan §Requirement coverage]
- [ ] CHK002 - Is every edge case E1–E7 mapped to a design decision or documented exclusion — including E2's requirement that documentation warn about the `zai:glm-5.2`-answered-by-glm-5.3 label/model mismatch? [Completeness, Gap, Spec §Edge Cases E2]
- [ ] CHK003 - Is the FR-016 construction-site enumeration (plan D2) complete against the code — the seven sites plus the 14 `agents/<role>/agent.py` build functions — and does the guard test's allow-list wording name all of them? [Completeness, Plan §D2, research.md §R3]
- [ ] CHK004 - Is every GATE-1 ruling (Q1, Q2/Q2b, Q3, Q4, Q5) and every adopted amendment A1–A9 carried into a plan element, with rejected consult claims recorded as rejected? [Traceability, Spec §Resolved Decisions, §Post-GATE-1 consult amendments, research.md §Consult disposition]
- [ ] CHK005 - Does each success criterion SC-001..SC-007 have named evidence in the plan (test, diff, or verification record)? [Traceability, Spec §Success Criteria, Plan §Requirement coverage]
- [ ] CHK006 - Does the FR-013/A5 comment sweep enumerate file:line citations with a per-entry disposition, and is every disposition correct for the post-flip registry state (not just the current one)? [Consistency, research.md §R10, Spec §V11]
- [ ] CHK007 - Are the binding constraints (no retry-policy edits, no dependency change, harness roles untouched, `code/step.py` not edited) stated as verifiable gates (diff commands, allow-lists) rather than intentions? [Measurability, Plan §Constraints, quickstart.md §5]

## Plan Clarity

- [ ] CHK008 - Is the `ZAI_BASE_URL` blank semantics (unset, empty, whitespace = default; read at call time, never at import) stated identically in D1, the contract, and the data model? [Clarity, Plan §D1, contracts/zai-route-contract.md §C2, data-model.md §New configuration]
- [ ] CHK009 - Is the `_provider_for(name, single_retry=…)` factory contract unambiguous about the two regimes (retry zeroed only on the single-retry path; non-zai providers exactly what the framework builds)? [Clarity, Plan §D1, contract §C3–C4]
- [ ] CHK010 - Is "site category" (the granularity of the per-site wire-URL pins) defined precisely enough that a task writer knows which stub-server tests are required? [Clarity, Gap, Plan §D5, Spec §A3]
- [ ] CHK011 - Do quickstart steps map one-to-one onto the plan's evidence obligations, each naming its expected outcome and its credential prerequisites? [Traceability, quickstart.md, Plan §D5–D8]

## Plan Consistency

- [ ] CHK012 - Are contract clauses C1–C8 consistent with plan D1/D2 and the data model (no clause weaker or stronger than the design)? [Consistency, contracts/zai-route-contract.md, Plan §D1–D2]
- [ ] CHK013 - Do the data model's before/after values match the spec's registry facts (11 roles → `zai:glm-5.3`; 3 harness `zai-coding-plan/glm-5.2`; 3 claude proposers unchanged; 6 wire `model_id` entries)? [Consistency, data-model.md, Spec §FR-001..FR-003, V1/V2]
- [ ] CHK014 - Is the R7 test-triage manifest consistent with the spec's verified counts (66 occurrences / 30 files, V9) and with V12's protocol-change note — including the durability HTTP stub's role? [Consistency, research.md §R7, Spec §V9, V12]
- [ ] CHK015 - Does the quickstart static-gate list match the FR-010/FR-014 constraints (empty diff over `pyproject.toml`, `uv.lock`, `code/step.py`)? [Consistency, quickstart.md §5, Spec §FR-010, FR-014]
- [ ] CHK016 - Are the post-GATE-1 amendments reflected where they bind: A6 in D4 (warm-up added, measurement still required), A4/A7/A8 in D6/D7/D8? [Traceability, Spec §A4, A6–A8]
- [ ] CHK017 - Does every plan element respect the Out-of-Scope rulings (no retry-policy change, no benchmark re-run, no ADR-6 fix, no harness grammar change, no ARCHITECTURE/ROADMAP edit before merge)? [Consistency, Spec §Out of Scope]

## Acceptance & Verification Quality

- [ ] CHK018 - Does the per-site pin include the request URL observed on the wire (stub server) for the durable path as well, per A3 — not only a client attribute? [Measurability, Spec §A3, Plan §D5, contract §Observable evidence]
- [ ] CHK019 - Is the A2 regression guard's failure condition specified concretely (which scan, which roots, which allow-list, what fails)? [Measurability, Spec §A2, Plan §D2]
- [ ] CHK020 - Does D8 define the live confirmation's prerequisites, stop-and-report condition, and what gets recorded (schema validity, endpoint, endpoint-reported model name per A8)? [Completeness, Plan §D8, Spec §FR-015, A8]
- [ ] CHK021 - Does the plan state how divergence between the R7 manifest and the actual triage-by-failure result is handled (recorded, not silently reconciled)? [Traceability, Plan §D5, Spec §FR-011]
- [ ] CHK022 - Is the in-flight/replay evidence named (which tests, which tier) with the operator guidance (drain or accept mixed-route) carried into the docs? [Completeness, Plan §D6, Spec §E4, A4]

## Dependencies & Assumptions

- [ ] CHK023 - Are dependency claims (R12: zai extra adds nothing beyond `openai`) and version pins scoped to the dev container, with the host venv explicitly excluded as a verification environment? [Assumption, research.md §R12, Plan §Technical Context]
- [ ] CHK024 - Are probe-derived facts labeled with their provenance (orchestrator-run live probes vs plan-author container probes), matching the spec's V13 note? [Assumption, research.md header, Spec §V13]

## Citation Accuracy

- [ ] CHK025 - Are the file:line citations in spec.md, research.md and the contract accurate against main `0f4ac11` (paths and line numbers)? [Traceability, Spec §Context, research.md §R5–R10]
