VERDICT: approve

Domain: tasks (round 023a). Method: spec-kit checklist + analyze-style coverage/dependency audit against `spec.md`, `plan.md` (A1–H2, §Traceability), `research.md`, `data-model.md`, `contracts/*.md`, `quickstart.md`. Coverage, format, sizing, scope, riders, repo rules and citations all pass (see checklist). Five gaps, all cheap marker/wording/order fixes — two violate hard criteria stated for this pass.

## Gaps (numbered, by task id)

1. **T029, T030, T031 — [P] markers dishonest: three [P] tasks write the same file.** All three are `[P]` and all three edit `ROADMAP.md` (T029: FR-501/FR-503 rows + P4 row; T030: §8 items 5/8 re-rank; T031: line 475 path fix), and §Parallel opportunities lists "Riders: T029, T030 and T031" together. This violates the stated invariant that no [P] pair writes the same file. Fix: drop [P] from all three (they are one rider cluster over shared files) or sequence them explicitly.
2. **T015, T021, T028 — implementation tasks not preceded by a RED test task.** The tasks.md header claims "every implementation task is preceded by a RED test task"; these three embed their tests instead (T015: `test_render.py` inside the implementation task; T021: the inbox test and the R11 check inside; T028: the nudge/disable CLI tests inside). Fix: split the RED tests into their own preceding tasks, or scope the header claim to logic-bearing modules.
3. **T025 — placement/order contradiction.** T025 says "Add `MaintenanceKickInput` beside `MaintenanceWorkflow`" (per `contracts/workflow-wire.md` that input belongs to the kick workflow, i.e. `S/workflows/maintenance.py`), yet §Dependencies says "T024→T025 can start right after Phase 2 (schedules are independent of the workflow)" — the module does not exist until T017. Fix: name the file and either let T025 create `S/workflows/maintenance.py` holding the input model, gate T025 on T017, or move `MaintenanceKickInput` to `S/maintenance/models.py`.
4. **T029 — dependency understated.** "T029–T031 can run any time after T017", but T029's own text records FR-501 as "loop + schedule + nudge + gate landed (023a)" — true only after US3 (T025–T028) lands. Fix: gate T029 on T028 (T030/T031 are genuinely independent).
5. **T013/T003 — SC-001's per-signal-kind matrix is implicit.** SC-001 requires 100% of seeded new faults to open exactly one incident *for each of build, advisory, secret*. T003's fixture seeds a build break and two secret kinds but no advisory fault, and T013's bullets don't enumerate the three kinds (the `RepoTriage` builder can cover advisory at the pure tier). Fix: name the three signal kinds in T013's first-cycle/NEW bullets (and optionally add the advisory seed helper to T003).

# Tasks checklist — round 023a (DAPER maintenance loop)

Feature: `023-daper-maintenance-loop` · Created: 2026-11-14 · Reviewer pass: tasks, pass 1
Depth: formal gate. Actor/timing: reviewer before execution dispatch.

## Format

- [x] CHK001 - Does every task line follow `- [ ] T0NN [P?] [USn?] description with exact file path (size)`? [Clarity] — Verified T001–T034: ids sequential, no gaps; size on every line; exact paths throughout (`S/`/`T/` prefixes declared in the header).
- [x] CHK002 - Do story labels appear only in the story phases (3–5)? [Consistency] — Verified: Phases 1, 2 and 6 carry none.
- [x] CHK003 - Are RED tasks labelled and separated from their green-making pairs? [Clarity] — Yes for all paired tasks (T004/005, T006/007, T009/010, T011/012, T013/014, T016/017, T019/020, T022/023, T024/025, T026/027); see gap 2 for the three embedded-test exceptions.

## Coverage

- [x] CHK004 - Is every plan step A1–H2 covered by at least one task? [Traceability] — A1→T001; B1→T004/005; B2→T011/012; B3→T013/014; B4→T006/007; B5→T015; C1–C3→T009/010; D1–D3→T024/025; E1→T008; E2→T017/T023/T027; E3→T026/027; E4→T018+T027; E5→T016/T022/T026; F1→T019/020+T028; F2→T021; F3→T021; F4→T019–T021+T028; G1→T002+T018; G2→T029; G3→T030; G4→T031; G5→T031; G6→T032; G7→T032; H1→T033; H2→T034. No orphan plan step.
- [x] CHK005 - Is every FR-001..FR-018 covered by at least one task? [Traceability] — FR-001→T004/T005/T019/T020; FR-002→T004/T019; FR-003→T024/T025/T028; FR-004→T026–T028; FR-005→T026; FR-006→T013/T016/T017; FR-007/008→T004/T013/T014; FR-009→T016/T017; FR-010→T011/T012/T022; FR-011→T004/T006/T007; FR-012→T022; FR-013→T026/T027; FR-014→T016/T026; FR-015→T019–T021; FR-016→T016; FR-017→T008/T010/T033; FR-018→T026–T028. No orphan FR.
- [x] CHK006 - Is every SC-001..SC-007 covered by a task validation? [Traceability] — SC-001→T013/T016 (see gap 5 on the per-kind matrix); SC-002→T016; SC-003→T004/T006/T022; SC-004→T026; SC-005→T026; SC-006→T008/T010/T033; SC-007→T034 + quickstart §5. No orphan SC.
- [x] CHK007 - Do the RED tasks assert the spec's acceptance scenarios rather than implementation internals? [Clarity] — T013/T016/T022/T026 map bullet-for-bullet to US1–US3 acceptance scenarios and edge cases (including the folded configured-off rule at T013 bullet 8); T004/T006/T011 assert data-model/research rules that carry FR-008/010/011.

## Test-first

- [x] CHK008 - Is every logic-bearing implementation task preceded by a RED test in the same story? [Completeness] — All paired tasks yes; exceptions named in gap 2 (T015, T021, T028 embed their tests).

## Sizing

- [x] CHK009 - Is no task L, and does the size summary match the task lines? [Consistency] — Recounted: 21 S + 13 M + 0 L = 34; per-phase counts (3/7/11/2/5/6) all match.
- [x] CHK010 - Does no M task hide two unrelated deliverables? [Clarity] — T010, T015, T017, T021, T027, T033 each carry one theme; T021 is the widest (inbox type + R11 decision-path check + pre-scoped fallback verb) but both halves serve FR-015 and the fallback is contract-pre-scoped. Acceptable; split only if the fallback fires.

## Dependencies and [P] honesty

- [x] CHK011 - Is the dependency section consistent with file overlaps? [Consistency] — Mostly yes (T004/T006/T008/T009 parallel-safe; US1 chain sound; T026→T027 needs T017; T028 needs T020+T027), with two exceptions named as gaps 3 (T025's input-model placement) and 4 (T029's gate).
- [x] CHK012 - Are the [P] markers honest (no [P] pair writes the same file)? [Consistency] — Violated by T029/T030/T031 on `ROADMAP.md` (gap 1). All other [P] sets write disjoint files (verified against the Project Structure map and per-task paths).

## Scope

- [x] CHK013 - Did no 023b item leak in (execute, PR, verification branch, memory retain, deploy/rollback)? [Consistency, spec §Out of scope] — Verified across all 34 tasks: approved plans terminate at `approved_not_executed` (T016/T017/T022); `ops_action` values appear only as recorded proposals (T015); no task starts a repair child, builds a verification branch, retains to memory, or executes rollback.
- [x] CHK014 - Do T029–T032 carry the riders exactly? [Traceability, plan G2–G7] — Option B override with intent-doc addendum-only (T030: dated addendum at end, body untouched); `ROADMAP.md:475` path fix + repo-wide grep (T031); AP-1.0 `[x]` with the 2026-11-11 landing note (T031); ARCHITECTURE §7 banner + deliberate-narrowing note (T029); no PRD edit, mismatch reported not patched (T029/T032). All five present, none altered.

## Repo rules

- [x] CHK015 - Are the repo constraints enforced by tasks? [Consistency] — 1000-line ceiling: explicit in T020 (`cli.py` < 1000) and T027 (~350–450), checked by T033's `scripts/check_file_size.py`. Replay: T008 and T010 assert zero fixture/golden changes, T033 asserts `git status --short tests/replay/` empty, no task adds a fixture writer (in-test `Replayer` per T016/T022/T026, precedent `tests/replay/harness.py`). Executor commit rules stated in the header (one commit per task, id in subject, no trailers, no `git add -A`, no stash).
- [x] CHK016 - Does T028's sample-asset suffix claim hold? [Traceability] — Verified: `S/schedules/loader.py:37` globs `*.yaml`, so `schedules/maint-example.yaml.sample` is invisible to `schedules apply`, and T028 adds a test asserting it stays ignored.

## Citations (spot-checked, all verified)

`S/workflows/tidyup.py:150-162` (triage_gates) · `S/agents/roles.py:132-133,226,323-324` (risk pattern) · `S/workflows/assessment.py:646-680` (`_judge` degrade) · `S/cli.py:357-359` (benchmarks hook) and `:859-870` (decision path) · `S/channels/inbox.py:116` (type list) · `S/schedules/loader.py:37` (`*.yaml` glob) · `docs/roadmap/filesystem-first.md:78` (E-14) · `docs/roadmap/agent-architecture-plan.md:26` (AP-1.0 box) · `ROADMAP.md:475` (stale path) · `check_adr6_families` (`S/agents/loader.py:295`) · `agents/planner/agent.yaml`, `agents/risk/agent.py` (exist) · commit `73a809c0` and its five named test files (exist) · `.specify/specs/021-recall-snapshot-artifact/baseline-failures.txt` (11 ids) · `schedules/nightly-reflect.yaml` (exists) · existing schedules tests `tests/test_schedule_{apply,loader,reconcile}.py` (T024's extension targets are real).

## Pass 2 (2026-11-14)

Verdict: **approve.** All five pass-1 gaps re-checked against the renumbered `tasks.md` (T001–T037) and the current tree; each is resolved. Fresh format, ID-sequence, placeholder, [P]-disjointness and cross-reference sweeps are clean, and every new citation introduced since pass 1 verifies.

### Gap dispositions

1. **[P] same-file (old T029–T031) — RESOLVED.** T032/T033/T034 carry no [P]; §Dependencies states the reason ("they share `ROADMAP.md` with T032, so T032→T033→T034 run in sequence"); the riders line is gone from §Parallel. The remaining [P] set (T002, T003, T004, T006, T008, T009, T011, T013, T015, T020, T026) is file-disjoint — reverified against each task's paths.
2. **RED-first (old T015/T021/T028) — RESOLVED.** Render RED is now T015→T016; inbox + R11 RED is T022→T023 (with the honest "(b) may already pass, so record its result" framing); CLI nudge/disable RED is T030→T031. The header names its exceptions (T008 pure move; polish guarded by the battery); the only other test-less tasks are infra/docs (T002 skeleton+AGENTS.md, T003 fixture factory, T019 registration+AGENTS.md rows), none logic-bearing. Every logic task now pairs RED→green: T004/005, T006/007, T009/010, T011/012, T013/014, T015/016, T017/018, T020/021, T022/023, T024/025, T026/027, T028/029, T030/031.
3. **`MaintenanceKickInput` placement — RESOLVED.** T027 adds it to `S/maintenance/models.py` "(not the workflow module)"; `data-model.md` §MaintenanceKickInput documents the same placement and rationale ("the schedules package depends on the domain package only"); §Dependencies and §Parallel now consistently allow T026→T027 right after Phase 2.
4. **T032 dependency — RESOLVED.** "T032 needs T031, because its ROADMAP text claims schedule and nudge landed" — T031 is US3's last task. T033/T034 remain honestly independent-but-sequenced.
5. **SC-001 per-kind matrix — RESOLVED.** T013 bullet 2 parametrizes the three detect kinds (build_probe, dependencies advisory, secrets) including recurrence-attach; T003 adds the critical-advisory seed helper at the pure tier with a sound stated reason (workflow tier runs `advisory_source=none`, no OSV egress in tests).

### New-since-pass-1 items (verified)

- **FR-202 VR-3a forwarding (T010/T018) — holds.** `S/workflows/assessment.py:685-695` is exactly the cited pattern (`run_kwargs` empty by default; `OUTPUT_RETRIES.get("risk", 1)`; `retries={"output": n}` only when `n != 1`); T018 mirrors it for `maintainer`. Commit `80692c1b` ("Merge branch 'feat/fr202-validation-retries'") exists; `validation_retries` is a real `agent.yaml` key (`S/agents/loader.py:189-194` names it as the only known key); `OUTPUT_RETRIES` is importable from `agents/roles.py` (assessment.py:29 precedent).
- **Role-wiring cites — hold.** `roles.py:132-133` (`risk_agent = AGENTS.get("risk")`), `:226` (optional-role map), `:310` (`t_risk = risk_agent`), `:338-339` (`ALL_TEMPORAL_AGENTS.append(t_risk)`) — all resolve at the new post-merge line numbers.
- **T034 four stale copies — correct.** `ROADMAP.md:475,479,482,486` each carry `benchmarks/sc_rollup.py`; exactly four copies today, as the task claims.

### Fresh sweeps

- **Format:** all 37 lines match `- [ ] T0NN [P?] [USn?] … (size)`; IDs sequential T001–T037 with no gaps; story labels confined to Phases 3–5; sizes on every line.
- **Size summary:** recount = 24 S + 13 M + 0 L = 37; per-phase 3/7/13/2/6/6 — matches the stated summary.
- **Placeholders:** none. (`2026-11-xx` in T032 is the execution-date token for the roadmap note, filled when the task runs; "extend T/ schedules tests as found" has concrete targets in `tests/test_schedule_{apply,loader,reconcile}.py`.)
- **Cross-references after renumbering:** all checked — header exception T008; "the T003 repo" and "fake maintainer from T010" in T017; "the T016 table" in T020; T022's (a)/(b) consumed by T023; "US2 needs T018"; "T028→T029 needs T018"; "T030→T031 needs T021 and T029"; "T032 needs T031"; T036's baseline ← T001; T037's outputs ← T036; §Parallel ids. No stale pass-1 id survives.
- **Scope:** still zero 023b leakage; the FR-202 forwarding adds config plumbing only, no execution path.
- **Citations re-verified this pass:** `assessment.py:685-695`, `roles.py:132-133,226,310,338-339`, `ROADMAP.md:475,479,482,486`, `80692c1b`, `loader.py:189-194` (`validation_retries`), `data-model.md` §MaintenanceKickInput — on top of the pass-1 set, unchanged.
