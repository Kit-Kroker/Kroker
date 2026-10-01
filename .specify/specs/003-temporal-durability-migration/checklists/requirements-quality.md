# Checklist: Requirements Quality — 003 Temporal Durability Migration

**Purpose**: Unit tests for the requirements in `spec.md` — completeness, testability, unambiguity, consistency (including FR-005/FR-019/FR-020 vs the Resolved Decisions, and B2-removed scope survival). Not implementation tests.

**Created**: 2026-09-30

**Scope note**: Spec-only review (plan.md/tasks.md do not yet exist for this feature).

## Requirement Completeness

- [ ] CHK001 - Is the complete set of 16 durable agents enumerated (V1: 10 unconditional + 6 optional, by name) so that every requirement saying "every agent" is checkable against a fixed list? [Completeness, Spec §V1, §FR-001]
- [ ] CHK002 - Are creation rules specified for both pre-migration evidence artifacts — the names fixture (FR-005.5b) and the command-attributes fixture (SC-006a/FR-019) — including commit provenance (main 203e7dd) and a MUST NOT be generated at test time from the code under test rule for each? [Completeness, Gap, Spec §FR-005.5, §SC-006a]
- [ ] CHK003 - Is a requirement present that carries the sandbox module-marking rule stated only in Edge Cases ("the migration must not introduce new sandbox-executed modules without marking them"), or is that "must" intentionally unenforced prose? [Completeness, Gap, Spec §Edge Cases]
- [ ] CHK004 - Are requirements defined for the mixed-fleet rollout window (old and new workers polling the same task queue before the old drains), beyond the single-worker in-flight scenario US1.3? [Coverage, Gap]
- [ ] CHK005 - Are recovery/rollback requirements defined for a failed migration deploy (e.g., a replay failure seen in production after the new worker rolls out), or is the absence of state migration stated as making rollback trivial? [Recovery, Gap]
- [ ] CHK006 - Is it specified what the plan must do if a MUST-level proof cannot be met (e.g., FR-020(e) resolving as "rejects tool results recorded by TemporalAgent" would contradict FR-005.1's no-failure replay)? [Coverage, Gap, Spec §FR-005.1, §FR-020e]
- [ ] CHK007 - Does any requirement quantify or bound the sequencing constraint that new captured histories (FR-005.5a) and fixtures MUST be recorded before pre-migration code (main 203e7dd) is replaced on the branch the histories are captured from? [Dependency, Gap]

## Requirement Clarity

- [ ] CHK008 - Is the required relation for the FR-005.5b tool-free assertion against the literal fixture stated (equality vs superset vs subset), matching whichever relation FR-005.3 mandates? [Clarity, Spec §FR-005.3, §FR-005.5]
- [ ] CHK009 - Does "the same durable activity configuration that its wrapper used to supply" (US2 Independent Test) include or exclude `heartbeat_timeout`, given FR-019's verified 30-second default difference? [Ambiguity, Spec §US2, §FR-019]
- [ ] CHK010 - Are "model pricing" and "any per-run spend figure" (FR-014) defined with measurable verification, and is a matching success criterion present (no SC covers spend)? [Measurability, Gap, Spec §FR-014, §Success Criteria]
- [ ] CHK011 - Are the decision criteria for FR-019's plan-level choice (override heartbeat to none vs accept as ruled change) specified, or is the choice left unguided? [Measurability, Spec §FR-019]
- [ ] CHK012 - Is the exact loader→`build` contract change described at requirements level (what must be passable) while implementation shape is deferred to the plan, and is that spec/plan boundary stated? [Clarity, Spec §FR-003]
- [ ] CHK013 - Is "behaviour-neutral" (Decision B2, FR-014) given a single definition reconcilable with FR-019's "accepting it as a ruled change" option — i.e., is a ruled difference neutral or not? [Ambiguity, Spec §Resolved Decisions B, §FR-014, §FR-019]

## Requirement Consistency

- [ ] CHK014 - Is the scheduled-names comparison defined once and consistently: FR-005.3 says "superset of the scheduled names found in all captured histories" (additions permitted), while SC-003 says "a name diff … is empty" (direction undefined) and V7 says the scheduled set "must not" change (additions forbidden)? [Conflict, Spec §FR-005.3, §SC-003, §V7]
- [ ] CHK015 - Does FR-014's absolute "MUST NOT change … the number of HTTP attempts per request" admit FR-019's ruled-difference mechanism (an accepted 30s heartbeat default can cut a >30s blocked attempt and re-issue HTTP requests the old wrapper would not), and is precedence between the two defined? [Conflict, Spec §FR-014, §FR-019]
- [ ] CHK016 - Do FR-005, FR-019 and FR-020 contain any B2/C3-removed scope (model forwarding, `max_retries`/SDK retry disabling, native zai provider) as an active requirement rather than as an out-of-scope reference? [Consistency, Spec §Resolved Decisions B/C, §FR-005, §FR-019, §FR-020]
- [ ] CHK017 - Does Decision B's "FR-014..017 and SC-007 removed" collide with the live, re-used numbers FR-014–FR-017 and SC-007 now in the spec, and is the former-vs-current numbering disambiguated for a reader cross-checking the ruling? [Ambiguity, Conflict, Spec §Resolved Decisions B]
- [ ] CHK018 - Is FR-020's outcome taxonomy (verified-neutral / mitigated / ruled difference) consistent with the MUST-level replay proofs in FR-005 — can every admissible outcome coexist with FR-005.1? [Consistency, Spec §FR-005.1, §FR-020]
- [ ] CHK019 - Are each of the six FR-005 proof obligations traceable to a success criterion or scenario (SC-001, SC-002, SC-003, SC-006, SC-006a, V4 pins) with none orphaned in either direction? [Traceability, Spec §FR-005, §Success Criteria]
- [ ] CHK020 - Is V3's consequence ("the spec requires either a new captured history or an explicit name-level assertion") exactly what FR-005.5 mandates — including for the assessment agents (`discover`, `risk`) whose SHOULD-level history capture is optional? [Consistency, Spec §V3, §FR-005.5c]
- [ ] CHK021 - Are the Resolved Decisions' exclusions (A3 inventory, B2 split-out, C3 zai feature, D1 defects 6.2/6.3) each reflected as negative scope in requirements (FR-014, FR-018) with no surviving contrary requirement anywhere in the spec? [Consistency, Spec §Resolved Decisions]
- [ ] CHK022 - Is FR-006's prohibition (no re-recording or editing of existing histories/goldens) consistent with FR-005.5a's requirement to add new histories — is add-vs-edit unambiguous? [Consistency, Spec §FR-005.5, §FR-006]
- [ ] CHK023 - Is the requirement-numbering order (FR-019/FR-020 appearing between FR-014 and FR-015 in document order) intentional and harmless for cross-references, given every internal citation resolves? [Clarity, Spec §Requirements]

## Acceptance Criteria Quality

- [ ] CHK024 - Is SC-005's "at least the pre-migration count of passing tests (160)" pinned to the same tier/marker selection so the count is comparable? [Measurability, Spec §SC-005]
- [ ] CHK025 - Can SC-004's "verified by search" be executed unambiguously (search roots, patterns, what counts as production code vs test fakes, which FR-008 also rewrites)? [Measurability, Spec §SC-004, §FR-008]
- [ ] CHK026 - Is every User Story acceptance scenario traceable to an Independent Test or Success Criterion (e.g., US1.3's in-flight continuation → SC-006; US3.3's name assertion → FR-005.5b fixture)? [Traceability, Spec §User Stories, §Success Criteria]
- [ ] CHK027 - Is US2's Independent Test statement ("each exposes the same durable activity configuration") consistent with SC-006a's "or each difference is listed … as a ruled change" escape hatch? [Consistency, Spec §US2, §SC-006a]

## Scenario Coverage

- [ ] CHK028 - Are exception-flow requirements defined for registry load failures (FR-003 fail-closed) beyond "an error naming the role" — e.g., is partial load (some roles attached, one not) excluded? [Exception Flow, Spec §FR-003]
- [ ] CHK029 - Does the nested durable-call edge (V8: `t_research` from inside an activity, "must behave as a plain run, not attempt to schedule further workflow activities") map to a required assertion in FR-011/US3.1, or only to prose? [Coverage, Spec §V8, §FR-011, §US3.1]
- [ ] CHK030 - Is the never-scheduled suspended-response cancel activity (edge, FR-020c) given a coverage decision — captured history, name-level assertion, or explicitly accepted as unproven? [Edge Case, Spec §Edge Cases, §FR-020c]
- [ ] CHK031 - Are zero/absent-state scenarios (optional role folders absent at worker boot, FR-007 "iff present", FR-012) consistent with the registration-exactly-once assertion in US1 scenario 4? [Consistency, Spec §FR-007, §FR-012, §US1.4]

## Non-Functional Requirements

- [ ] CHK032 - Are the timing/performance consequences of the verified 30s heartbeat default (FR-019) on long-running or event-loop-blocked model activities specified or explicitly deferred to the plan's ruling, with the deferral itself stated as a requirement? [NFR, Clarity, Spec §FR-019]
- [ ] CHK033 - Is the dev-container-only verification constraint (FR-015) reflected in every success criterion that involves running tiers (SC-005, SC-006), or is the environment left implicit in them? [Consistency, Spec §FR-015, §SC-005]

## Dependencies & Assumptions

- [ ] CHK034 - Is each Assumption (pins on main, tier green at 160, no args_validator, no event stream handler, V8 legitimacy) marked with its re-verification owner and phase (plan vs implementation), as some but not all currently are? [Assumption, Spec §Assumptions]
- [ ] CHK035 - Is the dependency of SC-006's mixed-prefix test on FR-005.5a's newly captured tool-bearing histories stated (SC-006 cannot be built before those histories exist)? [Dependency, Spec §FR-005.6, §SC-006]
- [ ] CHK036 - Is the follow-up-note path in FR-018 and the Resolved Decisions footer the same artifact, and is its existence a requirement of 003 (it is written as MUST) while its content is not? [Dependency, Traceability, Spec §FR-018, §Resolved Decisions]

## Ambiguities & Conflicts (author must resolve)

- [ ] CHK037 - Resolve CHK014: pick one scheduled-names comparison (direction and strictness) and use it in FR-005.3, SC-003, and V7's consequence column. [Conflict]
- [ ] CHK038 - Resolve CHK015/CHK013: state whether FR-014's neutrality carve-out exists for FR-019-ruled differences, and define "behaviour-neutral" once. [Conflict, Ambiguity]
- [ ] CHK039 - Resolve CHK017: annotate Decision B's "FR-014..017 and SC-007 removed" as referring to the former (pre-GATE-1) items, given the numbers are now re-used. [Ambiguity]
- [ ] CHK040 - Resolve CHK006/CHK018: add the missing outcome path when an FR-020 hypothesis cannot be neutral, mitigated, or ruled without breaking FR-005.1. [Gap]
