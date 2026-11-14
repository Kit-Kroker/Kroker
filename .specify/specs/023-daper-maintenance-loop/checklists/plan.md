VERDICT: approve

Domain: plan (round 023a). Method: spec-kit checklist + analyze-style spec-to-plan consistency. Every load-bearing claim was checked against the tree (30+ `file:line` citations verified; list under "Evidence log"). No blocking gap found. Three minor, non-blocking notes follow; none breaks traceability, concreteness, placeholder-freedom, path exactness, test-command explicitness, or any trust/reuse/constraint/rider claim.

## Gaps / notes (numbered, non-blocking)

1. **Minor — `plan.md` §Skeptic/advisor disposition.** Six 023b-carried findings have no explicit table row: skeptic (a)5 (stale-PR signal), (e)1 (`_fix_gates` on repair children), (e)3 (`RepairPlan → SeededWork` builder), (e)4 (build-broken admission paradox), advisor §7.1 (pinned-commit claim weakening). Each *is* dispositioned in `spec.md` §023b preview, which row 7 ("Carried to 023b (spec §023b preview)") points to, and skeptic (b) is covered by row 12. Suggested: one catch-all "carried to 023b, spec §023b preview" row when tasks.md is authored. Not blocking: the disposition is discoverable and consistent.
2. **Minor — `plan.md` B3 / `quickstart.md` §1.** The spec edge case "a signal disabled by configuration reads as *not configured*, not as a fault, and never escalates" (`spec.md` §Edge Cases) depends on `step` distinguishing configured-off from faulted not-collected. Verified the premise: triage reports `not_collected` for `advisory_source=none` (`src/sdlc/triage/advisories.py:10`), so the discrimination must live in maintenance. B3's "not-collected streaks" is the hook and `data-model.md` (advisory_source row) records the rendering, but the rule (configured-off ⇒ streak never increments) and an expected-outcome bullet are only implicit. Suggested: one line in quickstart §1 at task time. Not blocking: the requirement is traceable (spec edge → B3 → data-model transitions).
3. **Trivial — citation off-by-ones.** `research.md` R8 cites `triage/models.py:19-26` for `FixClass` (class is at :20-27); R6's docstring cite `delta.py:3-17` (docstring spans :1-16). Both resolve to the named artefacts; no claim is affected.

# Plan checklist — round 023a (DAPER maintenance loop)

Feature: `023-daper-maintenance-loop` · Created: 2026-11-14 · Reviewer pass: plan, pass 1
Scope: `plan.md` judged with `spec.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/{workflow-wire,cli}.md`; consults as background. Depth: formal gate. Actor/timing: reviewer before `/speckit-tasks`.

## Requirement traceability (spec → plan → validation)

- [x] CHK001 - Does every spec requirement FR-001..FR-018 map to at least one named plan phase step? [Traceability, plan §Traceability] — Verified: all 18 FRs map to A1..H2 steps and R-decisions; no orphan FR.
- [x] CHK002 - Does every success criterion SC-001..SC-007 map to a validation in quickstart or a named test step? [Traceability, plan §Traceability, quickstart §1–§3, §5] — SC-001→§1 b1/§2; SC-002→§2; SC-003→§1 b4/§2; SC-004→§2; SC-005→§2; SC-006→§3; SC-007→§5 (owner's run, honestly marked).
- [x] CHK003 - Are the Part A riders (Option B override record, stale-path fix, AP-1.0 checkbox, §7 narrowing note, no-PRD-change) each carried by a plan step? [Traceability, plan G2–G7, spec §A.3 riders] — G2/G3/G4/G5/G6/G7 cover all five riders; each target verified stale in the tree (see Evidence log).
- [x] CHK004 - Is every quickstart expected outcome anchored to a spec requirement and a data-model/research rule rather than to implementation behaviour? [Traceability, quickstart §1–§2] — Each bullet names its SC and its data-model/research anchor.

## Step concreteness and sizing honesty

- [x] CHK005 - Is 023a scoped to plan-and-gate only, with no step that executes a repair, opens a PR, or writes the repository? [Consistency, spec FR-016, plan §Phases] — Verified: phases A–H contain no execute/PR/branch-write step; `RepairAction.ops_action` is recorded-as-proposed only (`data-model.md`); E5 asserts no-write.
- [x] CHK006 - Did no 023b item (seeded child runs, verification branch, memory retention, deploy/rollback execution) leak into a 023a phase? [Consistency, spec §Out of scope, §023b preview] — Verified across plan, data-model, contracts, quickstart.
- [x] CHK007 - Are conditional steps decision-complete (named criterion + pre-scoped fallback) rather than open-ended? [Clarity, plan F3, contracts/cli.md] — F3's fallback verb is fully specified in `contracts/cli.md`; C2's "loader.py if needed" is bounded by the R8 wiring pattern.
- [x] CHK008 - Is every phase step concrete enough to author a task from (module, function, or file named)? [Clarity, plan §Phases B1–H2] — Each step names its module/function and its research decision.

## Placeholders and paths

- [x] CHK009 - Is the plan free of placeholders (TBD/TODO/‹blank›/unnamed "something")? [Completeness] — None found; `S/`=`src/sdlc/`, `T/`=`tests/` prefixes declared at plan head.
- [x] CHK010 - Are all cited file paths exact and resolvable in this tree (existing files) or exact and named (new files)? [Clarity, plan §Project Structure] — Verified by direct read of every cited path; new paths follow the package layout (`src/sdlc/maintenance/…`, `src/sdlc/workflows/maintenance.py`, `agents/maintainer/`).
- [x] CHK011 - Are test commands explicit and runnable as written? [Measurability, quickstart §1–§4] — `pytest -q tests/maintenance/ -m "not temporal"`, `pytest -q -m temporal tests/maintenance/`, the §3 battery (`ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py`, `pytest -q`, `pytest -q tests/replay/`, `pytest -q -m temporal tests/test_tidyup*.py tests/test_triage_workflow_e2e.py`) and the §4 CLI smoke are all concrete.

## Consult disposition

- [x] CHK012 - Is every advisor and skeptic finding that bears on 023a dispositioned in plan §Skeptic/advisor disposition, with the disposition reflected in a phase step or research decision? [Traceability, plan §Skeptic/advisor disposition] — All 17 rows check out against the consults; reflections verified (R1–R15, phases B–G, spec §023b preview). Minor note gap 1 records the six 023b-carried findings that rely on the row-7 pointer rather than their own rows.
- [x] CHK013 - Do the dispositions that were "corrected" (secrets fix-class) match the code? [Consistency, `src/sdlc/triage/signals/secrets.py:5-8,35-36`] — Verified: `.env` deletion MECHANICAL (module docstring), provider credentials JUDGEMENT (`_PROVIDER_RULES` comment).

## Trust-layer claims against the code

- [x] CHK014 - R9: is the repair gate's config built in code with no operator-reachable gate field, given what `GateHost._gate` permits? [Consistency, `src/sdlc/workflows/gates.py:188-245`, `src/sdlc/core/models.py:57-68,79-90`] — Verified: `_gate` honours `GatePolicy.OFF` → auto-approve (:206-209) and `on_timeout=APPROVE` (:233-239); `GateConfig` permits both; the plan's `MaintenanceConfig` exposes only `threshold`/`gate_timeout_hours` with `extra="forbid"`, so no configuration reaches a gate field. Claim holds.
- [x] CHK015 - R15: can a disable avoid synthesising a `GateDecision`? [Consistency, `src/sdlc/core/models.py:152-173`] — Verified: `decided_by` is `Literal["human","policy","timeout"]` (:156); withdrawal records `withdrawn` + note with no decision object. Claim holds.
- [x] CHK016 - Is the decider triple (`human`/`policy`/`timeout`) recorded on every path the plan names (approve-by-policy, timeout, human, reject)? [Completeness, spec FR-012, R9] — SOFT auto-approve `decided_by="policy"`, timeout `decided_by="timeout"` (`gates.py:228-241`), human via `submit_gate_decision`. Consistent.

## Reuse claims against the code

- [x] CHK017 - R5: is `TriageWorkflow` reused unchanged with `triage_gates` at the cited site, and is the "other four signals" count right? [Traceability, `src/sdlc/workflows/tidyup.py:150-162`, `src/sdlc/triage/registry.py:34-65`] — Verified: `triage_gates` at :150; registry has 7 signals; 3 kept (secrets, build_probe, dependencies) ⇒ other four (baseline, scaffold, misconfig, outliers). Correct.
- [x] CHK018 - R6/R7: do `compute_delta` and `finding_identity` exist at the cited lines with the claimed semantics? [Traceability, `src/sdlc/triage/delta.py:93`, `src/sdlc/triage/models.py:194-201`] — Verified; delta docstring states "deliberately NOT a set difference".
- [x] CHK019 - R8: is the optional-role wiring pattern (`risk`) and `FixClass` where cited? [Traceability, `src/sdlc/agents/roles.py:132-133,226,323-324`, `src/sdlc/triage/models.py:20-27`] — Verified (see gap 3 for the one-line cite nit); precedent commit `73a809c0` exists and its named tests all exist.
- [x] CHK020 - R10: is the schedules package Reflect-only in the cited places, and is the nightly-reflect asset real? [Traceability, `src/sdlc/schedules/models.py:16-26`, `src/sdlc/schedules/apply.py:41-88`, `schedules/nightly-reflect.yaml`] — Verified: `KNOWN_SCHEDULE_WORKFLOWS={"ReflectWorkflow"}`, `banks` required, `to_temporal` hardcodes `ReflectScheduleInput` (:48), `from_temporal` re-validates it (:73); asset exists.
- [x] CHK021 - R11/R12: are the inbox type list and the CLI subparser-register precedent at the cited lines, and is `cli.py` at 908 lines? [Traceability, `src/sdlc/channels/inbox.py:116`, `src/sdlc/cli.py:357-359`, wc -l] — Verified: `list_open_run_ids(client, "GraphWorkflow", "CrewTaskWorkflow")` at :116; benchmarks hook at :357-359; 908 lines, so the ≤10-line hook keeps it under the 1000 ceiling.

## Repo constraints

- [x] CHK022 - Does the plan respect the 1000-line ceiling on every file it touches or creates? [Consistency, root AGENTS.md, plan §Constitution Check] — `cli.py` 908 + ≤10 = ≤918; new modules each < 400 planned; `scripts/check_file_size.py` is in the §3 battery.
- [x] CHK023 - Does the plan add no fixture writer to `tests/replay/` (rule 1) while still proving workflow determinism? [Consistency, `tests/replay/AGENTS.md:8-13`, R13] — Verified: in-test `Replayer` replay only; no stored fixture; goldens asserted unchanged in quickstart §3.
- [x] CHK024 - Does the plan respect `src/sdlc/workflows/AGENTS.md` ownership (one owning host, handlers on the concrete class, table rows for new attributes)? [Consistency, plan §Constitution Check row 3, G1, contracts/workflow-wire.md §Determinism] — Signals/queries on `MaintenanceWorkflow`; new attribute rows planned (G1); GateHost-only host precedent stated.
- [x] CHK025 - Is the fast-tier baseline-diff method concrete (recorded baseline file, sorted-diff against a named prior file)? [Measurability, plan A1, quickstart §3] — Verified both files exist; 021's holds exactly 11 ids (lines 15-25), matching A1's "11-id file".

## Scenario and edge coverage in the plan's own terms

- [x] CHK026 - Are the spec's edge cases each carried by the data-model transitions or a research rule? [Coverage, data-model §IncidentState, research R6/R7] — Not-collected streaks, UNVERIFIABLE, resolved-externally, one-incident-per-build-rule, JUDGEMENT secrets, proposer failure, zero-action plan, pinned commit, restart, bad-repo refusal all present. (See gap 2 for the not-configured rendering nuance.)
- [x] CHK027 - Are the incident states named in FR-015 exactly the states the data model can reach? [Consistency, spec FR-015, data-model §IncidentState] — open, awaiting_decision, approved_not_executed, rejected, timed_out, resolved_externally, escalated, withdrawn all reachable via the drawn transitions.
- [x] CHK028 - Is the wire contract complete (ids, signals, queries, gate names, schedule asset shape) and rename-protected? [Completeness, contracts/workflow-wire.md] — Workflows, ids, signal payloads, queries, gate names, cron shape and determinism notes all specified.

## Evidence log (spot-checked citations, all verified)

`workflows/gates.py:188-245` · `core/models.py:36-53,57-68,79-90,152-173,374` · `tidyup.py:150-162` · `triage/delta.py:1-16,93` · `triage/models.py:20-27,81-93,194-201` · `agents/roles.py:132-133,226,323-324` · `schedules/models.py:16-26` · `schedules/apply.py:38-88` · `channels/inbox.py:116` · `cli.py:357-359,859-870` (908 lines) · `worker.py:275` · `workflows/triage.py:7-9,70-72` · `workflows/assessment.py:646-681` · `workflows/deployment.py:3-10` · `workflows/reflect.py:1-10` · `triage/registry.py:34-65` (7 signals) · `signals/secrets.py:5-8,35-36` · `signals/dependencies.py:372,376` · `benchmarks/sc_rollup.py:79-80` (SC-1/3/4/6 only — SC-2 absent, H2 confirmed) · `ROADMAP.md:263-264,339-341,474-480,542,565-575` (§8 items 5+8; `:475` stale path) · `agent-architecture-plan.md:26` (stale AP-1.0 box) · `intent/2026-11-11…:35-37` · `filesystem-first.md:78` (E-14 blocked) · `PRD.md:78,284-290` · `ARCHITECTURE.md:537-560` (§7 designed-not-built; Detect inputs incl. CI/quarantine/error-budget to be narrowed) · `ordering.md:3-8` · `orchestration-protocol.md:186-193` · commit `73a809c0` · `agents/{reviewer,dev}/agent.yaml` (independent judge, H4).
