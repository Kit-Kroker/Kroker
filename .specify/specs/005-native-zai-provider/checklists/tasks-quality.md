# Checklist: Tasks Quality — 005 Native zai Provider

**Purpose**: Unit tests for `tasks.md` — coverage of every FR/amendment/edge case/plan decision, ordering safety, per-task executability, true parallelism, constraint enforcement, format. Not implementation tests.

**Created**: 2026-10-02 (reviewer seat; verified against main `0f4ac11`)

## Task Completeness

- [ ] CHK001 - Does every functional requirement FR-001..FR-016 map to at least one task, and is each map row accurate (no task claimed as evidence that does not actually evidence it)? [Completeness, tasks.md §Requirement → task map, spec §Requirements]
- [ ] CHK002 - Is every post-GATE-1 amendment A1–A9 carried into a task (A2 guard, A3 durable-path wire URL, A4 in-flight/replay + operator note, A5 sweep, A6 warm-up + measurement, A7 budget note in marker, A8 reported model name, A9 close-out report)? [Traceability, spec §Post-GATE-1 consult amendments]
- [ ] CHK003 - Is every edge case E1–E7 either covered by a task or explicitly dispositioned as design/contract behavior — and does each map row name evidence that the named task's text actually contains? [Consistency, spec §Edge Cases, tasks.md §Requirement → task map]
- [ ] CHK004 - Does every plan design decision D1–D8 have implementing tasks, with no design element silently dropped (incl. the D6 operator note in both its channels)? [Completeness, plan §Design]
- [ ] CHK005 - Are baseline tasks (pass counts, timing, capability-assertion inventory) present so later evidence has a comparison point? [Measurability, tasks.md §Phase 1]

## Ordering & Dependencies

- [ ] CHK006 - Is no commit able to leave the shipped registry pointing at an endpoint the code cannot reach or a key nothing checks (policy and doctor before the flip; flip task explicitly gated)? [Dependency, tasks.md §Phase order, §Dependencies]
- [ ] CHK007 - Does every behaviour task precede its GREEN with a RED test (cross-task or in-task), and is each "Confirm red" instruction scoped to the assertion that is actually red? [Traceability, tasks.md header §Tests]
- [ ] CHK008 - Is the dependency list complete and non-contradictory with the phase order and the [P] pairings (no cross-phase pair claimed parallel under a strict phase sequence)? [Consistency, tasks.md §Dependencies, §Parallel opportunities]
- [ ] CHK009 - Are stop-guards (SG-1..SG-6) attached to the exact task where the failure would appear, with the clearance path named? [Completeness, tasks.md §Stop-guards]

## Executability

- [ ] CHK010 - Does each task name the files it touches, and do all named file paths exist on main `0f4ac11`? [Clarity, tasks.md all tasks]
- [ ] CHK011 - Are the line references in tasks accurate for the current file contents (loader ~530, eval/runner 39-40, judge 140, operator 188, checks 246, env 11-13, registry test 117, runner 59 and 46-57, memo 81, pricing 25-27, provider 46-47, README 128/177, doctor tests 111-145)? [Clarity, tasks.md per-task citations]
- [ ] CHK012 - Is each task executable by an agent with only the spec/plan/research/contract at hand — no unstated context, no ambiguous "as appropriate" steps? [Clarity, Gap]
- [ ] CHK013 - Do test tasks name the file they extend or create, and the tier they run in? [Clarity]

## Parallelism

- [ ] CHK014 - Is every [P]-marked pair free of file overlap and hidden ordering (shared test file, shared fixture, evidence dependency)? [Consistency, tasks.md §Parallel opportunities]
- [ ] CHK015 - Are tasks that share a file (e.g. `test_zai_route.py` extensions) correctly NOT marked [P] against each other? [Consistency]

## Constraint Enforcement

- [ ] CHK016 - Is each binding constraint (no retry-policy edits, no dependency change, harness roles untouched, `code/step.py` not edited, no benchmark re-runs / no fixture edits beyond the one regen) enforced by a standing rule, stop-guard, or diff gate — not just stated? [Measurability, tasks.md §Standing rules, §Stop-guards, T031]
- [ ] CHK017 - Does the final diff gate cover every constrained path (`pyproject.toml`, `uv.lock`, `code/step.py`, `harness/base.py`, the three harness role dirs)? [Completeness, T031]

## Format & Traceability

- [ ] CHK018 - Are all tasks checkbox items with sequential IDs and no gaps or duplicates? [Clarity]
- [ ] CHK019 - Are [US] labels used only in story phases, and does every story-phase task carry one? [Consistency, tasks.md §Phase order]
- [ ] CHK020 - Do phase checkpoints state the verifiable state that defines the phase boundary? [Measurability, tasks.md per phase]
