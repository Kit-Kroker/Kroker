# Checklist: Plan Quality — 003 Temporal Durability Migration

**Purpose**: Unit tests for `plan.md` (with research.md, data-model.md, contracts/loader-build-contract.md, quickstart.md) — completeness against the approved spec, internal consistency, unambiguity, verifiable ordering. Not implementation tests.

**Created**: 2026-09-30

## Plan Completeness

- [ ] CHK001 - Does the plan carry a design decision or explicit deferral for every functional requirement FR-001..FR-021, with none silently dropped? [Completeness, Plan §Design decisions, §Phases]
- [ ] CHK002 - Is every deviation from a spec MUST (e.g., the FR-005.5a research captured history downgraded to name-level in research.md R5) recorded as a deviation requiring a spec ruling, not presented as equivalent compliance? [Consistency, Conflict, Spec §FR-005.5a, research.md §R5]
- [ ] CHK003 - Does the replay-proof strategy address all six FR-005 proof obligations with named evidence artifacts (fixture, 3 histories, payload capture, mixed-prefix)? [Completeness, Plan §Replay-proof strategy, Spec §FR-005]
- [ ] CHK004 - Does the plan give each FR-020 hypothesis (a)-(e) an outcome path and an owning task, with escalation (not ruling) when unresolved? [Completeness, Spec §FR-020, research.md §R4]
- [ ] CHK005 - Does the plan make the Phase-A-before-Phase-B ordering constraint enforceable (orchestrator commit order + fixture base-sha assertion) rather than advisory? [Dependency, Plan §Risks, data-model.md §State transitions]
- [ ] CHK006 - Is FR-021's guard (no new unmarked sandbox-executed module; test or lint) carried into plan work items, including for the contemplated new `src/sdlc/agents/durability.py`? [Completeness, Gap, Spec §FR-021, Plan §Structure Decision]
- [ ] CHK007 - Is FR-014's verification clause (attempt count AND unchanged priced-usage record) fully carried into plan evidence, or a deferral stated? [Completeness, Spec §FR-014]
- [ ] CHK008 - Are risks each paired with a concrete mitigation (task or design element) or an explicit escalation path? [Completeness, Plan §Risks]
- [ ] CHK009 - Is the docs obligation (FR-009) enumerated to file level (which docs, which sections)? [Completeness, Spec §FR-009, Plan §Project Structure]

## Plan Clarity

- [ ] CHK010 - Is the `durability.py`-vs-inline structure decision given a decision criterion and an owner (who decides, against what test), rather than left open? [Clarity, Plan §Structure Decision]
- [ ] CHK011 - Are the plan phases (A-E) mapped unambiguously to the tasks phases (1-6) somewhere in the artifact set? [Clarity, Gap, Plan §Phases, data-model.md §State transitions]
- [ ] CHK012 - Is the plan's Constitution Check accurate against the actual `.specify/memory/constitution.md` (unfilled template, no ratified principles)? [Assumption, Plan §Constitution Check]

## Plan Consistency

- [ ] CHK013 - Is the loader contract stated identically in Plan §Design decisions, contracts/loader-build-contract.md, and data-model.md (signatures, keyword-only `capabilities`, fail-closed list, lazy import)? [Consistency]
- [ ] CHK014 - Are the frozen values (agent names, toolset ids, 600 s / 3 attempts, both named configs) stated identically across spec, plan, contract, and data-model? [Consistency, contracts/loader-build-contract.md §Frozen values]
- [ ] CHK015 - Is the expected registered-set delta (`-event_stream_handler`, `+model_compact_messages`, `+validate_args`) consistent everywhere it appears (research.md R2/D2, data-model fixture, plan §Replay-proof strategy)? [Consistency]
- [ ] CHK016 - Do the plan's environment mechanics (dev container, primary-checkout mount, named-volume venv, one pytest per command, host-hazard note) match quickstart.md and the spec's FR-015 exactly? [Consistency, quickstart.md, Spec §FR-015]
- [ ] CHK017 - Is the heartbeat ruling carried consistently (override to `None` in shared and fan-out factories; fixture heartbeat 0) across plan, contract, research.md R3, and data-model? [Consistency, Spec §FR-019]
- [ ] CHK018 - Are spike-derived facts in research.md labeled as spike evidence, kept separate from the user's GATE 1 rulings? [Assumption, research.md §Method]

## Acceptance & Verification Quality

- [ ] CHK019 - Does the plan state, for each SC, which phase's evidence closes it (SC-001..SC-008 → phases/tasks)? [Traceability, Plan §Phases, Spec §Success Criteria]
- [ ] CHK020 - Is the capture provenance pinned (unmodified main, base sha recorded in the fixture and asserted) for both the names/attributes fixture and the new histories? [Measurability, Plan §Replay-proof strategy, data-model.md §PreMigrationFixture]
- [ ] CHK021 - Is "done" defined at plan level (all SCs green + FR-020 outcomes recorded + follow-up note untouched + no deprecation warning)? [Completeness]
- [ ] CHK022 - Are out-of-scope rulings (A3/B2/C3/D1) respected by every plan element — no deferred work (model forwarding, `max_retries`, zai, 6.2/6.3) implemented or half-implemented? [Consistency, Spec §Resolved Decisions]
- [ ] CHK023 - Is any pending spec amendment (e.g., plan §Proposed spec amendment) tracked to an explicit gate ruling, with the feature not declarable done before the ruling is recorded? [Dependency, Plan §Proposed spec amendment]

## Re-review addendum (reviewer-003-4, 2026-09-30)

- CHK002 re-checked: deviation now handled as a **Proposed spec amendment** section (plan.md:106-108) — evidence-cited, worded, escalated to GATE 2, referenced from T005; acceptable handling pending the GATE 2 ruling (see CHK023).
- CHK006 re-checked: FR-021 guard tasked (T045) including the marking contingency for a new `durability.py`.
- CHK007 re-checked: FR-014 priced-usage verification tasked (T046, `price_usage` inputs / `RoleUsage` records).
- CHK011 re-checked: A-E ↔ 1-6 mapping added (tasks.md numbering note); minor imprecision (T019/T013 placement) noted as cosmetic.
