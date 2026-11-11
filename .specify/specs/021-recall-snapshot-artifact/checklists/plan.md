VERDICT: approve

Four gaps, all doc-level; no task's work, ordering or safety argument changes.
Fix them and this plan is approvable without another full pass.

1. **Spec §Testing Scope, "New tests needed" last bullet still tells the
   pre-E-1 story** (spec.md, Requirements → Testing Scope, final bullet: "a
   `temporal`-marked replay test showing an in-flight history replays **with
   the new activity behind `workflow.patched`**"). There is no new activity
   and no patch in the design: Errata E-1 corrected exactly this claim
   ("defaulted payload fields do not change the command sequence; only
   adding/removing activities does"), D3 was rewritten to match, research
   R-1 rules "persist inside the existing activity — no new activity, no new
   workflow command, no `workflow.patched`", and plan T050 is the unpatched
   check ("passes **without** editing `research_retain_grounded.json`"). The
   advisor explicitly instructed planning the replay test as "old history
   replays unpatched, not 'replays behind a patch'" (advisor D1). As
   written, the bullet contradicts E-1/D3/R-1/T050 and would direct
   `/speckit-tasks` to add a patch marker that must not exist. Fix: reword to
   "replays unpatched, without editing the history (no new activity; E-1)".
2. **Plan §Traceability: FR-009 and SC-005 name no plan task (T0xx)**
   (plan.md, Traceability table). Both rows carry "Phase B design" in the
   Tasks column. The validations are real (T050), and the implementing tasks
   are identifiable (T011 defaulted fields + validator, T013 in-activity
   persistence, T021 emit), but the table does not name them — the
   FR→task→validation chain breaks exactly where the reviewer brief checks
   it. Fix: replace "Phase B design" with the task ids (T011, T013, T021)
   in both rows.
3. **Plan §Scale/Scope counts disagree with the task list** (plan.md,
   Technical Context → Scale/Scope). "src: 9 files" counts only Phases A/B;
   T030–T032 edit three more src files (the stage `step.py` files) — 12
   edited `.py` files. "tests: 10 files edited" double-counts T040's two
   lists, which share three files (`test_plan_step_chaos.py`,
   `test_plan_step_split.py`, `test_architecture_step_split.py`): 7
   distinct + `test_graph_golden.py` (T041) + `test_memory_models.py`
   (T042) = 9. "4 new" test files: only three are named (T043, T044, T045).
4. **Off-by-one cite (nit):** plan T013 puts `RecallInput` at
   `src/sdlc/memory/activities.py:50`; the class is at `:51` (the skeptic's
   `:50-58` range has the same off-by-one). One-character fix.

# Plan Quality Checklist: RecallSnapshot persisted input (round 021, pass 1)

**Purpose**: validate plan.md by spec-kit's checklist method — traceability
(FR/SC → plan task → validation), concrete steps, exact paths, explicit test
commands, no placeholders — plus the reviewer brief's consistency checks
(GATE 1 rulings, replay safety vs R-1, FR-007 by construction, skeptic
adoption, citation spot-checks).
**Created**: 2026-11-11 | **Feature**: [plan.md](../plan.md) · [spec.md](../spec.md)
**Base**: `main` at `067e1408` (verified: current HEAD).

## Content quality

- [x] CHK001 - Placeholder sweep over all six artifacts? [Clarity] — Clean
  (TODO/TBD/TKTK/FIXME/???/NEEDS CLARIFICATION: zero hits in spec, plan,
  research, data-model, quickstart, contract).
- [x] CHK002 - Steps concrete with exact paths and line anchors? [Clarity] —
  Every task T010–T070 names its file(s) with `:line` anchors and the exact
  edit; new files are explicitly new. Verified in the tree (see CHK016).
- [x] CHK003 - Test commands explicit? [Measurability] — T050 and T070 are
  exact command batches; quickstart Q1–Q8 give per-concern commands with
  expected outcomes; T041 prescribes the capture-by-print method for the
  re-pinned constant.

## Traceability (FR-001..FR-011, SC-001..SC-005)

- [x] CHK004 - FR-001..FR-008, FR-010, FR-011 each map to task(s) and a
  validation? [Traceability] — plan §Traceability rows verified against the
  task list and quickstart: FR-001→T013/T043,Q2; FR-002→T010,T011/Q1;
  FR-003→T010 no-edit + `test_recall_query_hash.py` unmodified/T042,Q1;
  FR-004→T021,T022,T030–T032/T044,T045; FR-005→T013/T043; FR-006→T011
  (degraded inside the hashed content)/T043,T044; FR-007→T021,T022/T044,
  T045,Q3,Q6,T070; FR-008→T013,T021 (R-5 double fault)/T043,T045,Q2;
  FR-010→T022/T044,Q3; FR-011→T013,T021 + contract §3/T045 (no items).
- [ ] CHK005 - FR-009 and SC-005 map to a plan **task (T0xx)**? [Traceability]
  — **No**: both rows say "Phase B design" (gap 2). Validation T050 exists
  and is blocking, but the task column names no task.
- [x] CHK006 - SC-001..SC-004 map to tasks and validations? [Traceability] —
  SC-001→T013,T014,T021/T043 reader,T045,Q4; SC-002→T022/T044,Q3;
  SC-003→T021,T022/Q6,T044,T070 goldens; SC-004→T013,T011/T043,T044,Q2.
  SC-005 → gap 2 (same row defect as FR-009).

## GATE 1 rulings honoured exactly

- [x] CHK007 - Q1 (alongside)? [Consistency] — FR-010 wording mirrored in
  T022: slot is `wm` when `recall_ref == ""`, else `f"{wm}|{recall_ref}"`;
  the watermark is never removed from the key (R-4, data-model §Memo key).
- [x] CHK008 - Q2 (artifact store only)? [Consistency] — R-6 + contract §3 +
  T045: the stage record (the `memory_recalled` event) carries hash, uri and
  flags, never items; nothing is added to the export bundle anywhere in the
  plan; data-model §RunEvent has no items field.
- [x] CHK009 - Q3 (continue as degraded)? [Consistency] — R-5 + T013: put
  failure → `degraded=True, items=[], persist_failed=True, ref=None`, hash
  recomputed over the degraded content, never raised; logged and marked via
  the event (`persist_failed`); double fault (backend + put) covered by the
  same `_persisted` helper; T043 tests both.

## Replay safety (FR-009) vs research R-1

- [x] CHK010 - No new activity, no `workflow.patched`, anywhere? [Consistency]
  — R-1, plan Constraints ("no new workflow command"), Constitution row 2
  ("No activity is added or removed"), and §Replay-safety analysis agree;
  persistence lives inside `recall_snapshot`; T014's reader is a plain
  function, not an activity.
- [x] CHK011 - T050 a blocking check? [Measurability] — Yes: "`pytest -m
  temporal T/replay/test_research_retain_replay.py` passes **without**
  editing `research_retain_grounded.json` … **This is a blocking check, not
  a code task**." Also Q5.
- [ ] CHK012 - Does the **spec's** required new-test list agree with the
  unpatched design? [Consistency] — **No**: spec Testing Scope's last "new
  tests needed" bullet still says "behind `workflow.patched`" (gap 1),
  contradicting E-1/D3/R-1/T050.

## FR-007 (memory-off byte identity)

- [x] CHK013 - Holds by construction in T021/T022? [Consistency] — T021:
  the disabled branch (`memory_host.py:50-51`) is untouched and emits
  nothing; the disabled snapshot keeps `snapshot_hash == ""` (R-3 validator
  condition: `query_hash or degraded`). T022: `f"{wm}|{recall_ref}" if
  recall_ref else wm` yields exactly `wm` for `""` — never `"none|"`. This
  is skeptic 1B's mitigation 2, honoured. Stubs keep working: new fields
  defaulted (T011), `recall_ref` keyword-only with default (T022/T023),
  six stub signatures + four `SimpleNamespace` stubs updated in T040 with
  assertions unchanged.
- [x] CHK014 - Tested? [Measurability] — T044 (`recall_ref=""` → the exact
  pre-021 slot), T045 (memory off emits nothing), Q3, Q6 (goldens
  byte-identical; only `MEMO_PARITY_KEYS` re-pinned), T070.

## Skeptic adoption

- [x] CHK015 - Every skeptic finding adopted in R-1..R-8 or deferred as a
  GATE 2 item (R-9)? [Coverage] — L1/1A→R-4 (T041 re-pin) and 4A→R-9/GATE 2
  item 4; L1/1B→R-4 (kwarg on `_cached_stage`, hash carried on
  `prep.snapshot`; scalar-on-MemoryHost and `input_json` alternatives
  rejected with test citations); L2/2A→R-6 (dedicated event covers
  non-benchmark runs; `BenchmarkRecord` drop verified);
  L2/2B→R-2 (`RecallInput.run_id`, empty skips persistence, direct-call
  tests keep working); L3/3A→R-5 (items discarded, hash recomputed);
  L3/3B→R-5 (double fault never raises) with the `cache_put` split flagged
  as GATE 2 item 5; L4→R-3/T010 (sibling hash def) with the `fake.py` fix
  deferred (GATE 2 item 4); L5/5A→R-1/R-3 (defaults + validator, no new
  activity); probe 1→GATE 2 item 1 (+T061 ADR-5 text); probe 2→covered by
  L5/L1; probe 3→R-7 (reader + kind + sha check; multi-host shared volumes
  scoped out in R-7 with the `harness_session` precedent); probe 4→E-2 +
  T040 (four files, including the fourth `test_architect_research_deps.py`
  the skeptic itself missed); probe 5→GATE 2 item 2; probe 6A→R-8 (scrub
  before put); probe 6B→R-9/GATE 2 item 3. Nothing unaccounted.

## Citation spot-checks (30+ verified at `067e1408`)

- [x] CHK016 - Do cited paths and `file:line` exist? [Traceability] —
  Verified in the tree: `memory/models.py:23` (`@dataclass` RecallSnapshot),
  `memory/activities.py:61` (`recall_snapshot`), `activities.py:51`
  (`RecallInput` — plan cites `:50`, gap 4), `workflows/memory_host.py:47-52`
  (disabled branch at `:50-51` exactly as T021 says),
  `workflows/role_host.py:88` (`_cached_stage`), `:114-120` (the
  `content_key(` call, fifth arg at `:119`), `graph.py:73`
  (`cached_stage=self._cached_stage` — the binding passes the method, so
  T023's "unchanged" claim holds), `graph.py:171` (`workflow_id`),
  `core/context.py:36` (Protocol `cached_stage` with keyword-only
  `prompt_digest`), `core/models.py:92` (`ArtifactRef`),
  `artifacts/store.py:22` (`_SUBDIRS` dict, room for the new kind),
  `artifacts/read.py` exists, `observability/trace.py:16` (`RunEventKind`),
  `workflows/report_host.py:38` (`_emit(kind, stage=None, **data: str)`),
  `memory/fake.py:44` (`int(watermark)` crash), `memory/scrub.py:18`
  (`scrub`), `memoization/cache.py:42` (`upstream_recall_ref` fifth slot),
  `hindsight_client.py:183`, `agents/research/tools/recall_leads.py:14`,
  stage call sites `clarify/step.py:199`, `plan/step.py:122`,
  `architecture/step.py:204` (all `await ctx.cached_stage(`), clause anchors
  `clarify.md:40`, `plan.md:19`, `architecture.md:19` (memo-key wording),
  `ARCHITECTURE.md:210-224` (ADR-5, including the false "Recall is itself a
  cached activity" sentence T061 corrects), `ROADMAP.md:327` (FR-402
  unticked), `PRD.md:261`; tests: `test_graph_golden.py:28-50`
  (`MEMO_PARITY_KEYS`), `:121` (monkeypatch), `:126-127`
  (`memoization_enabled=True`, `watermark="wm-e74"`), `:148`
  (`args[-1] == "wm-e74"`), the six stub-signature cites and four
  `SimpleNamespace` cites of T040 (all exact), `test_memory_models.py:12`,
  `test_hindsight_recall.py:143`, `test_memory_activities.py:26,61`,
  `test_clarify_memo_key.py:151,238`. Fixture claims verified:
  `research_retain_grounded.json` is the only history scheduling
  `recall_snapshot`; no `tests/replay/golden/*.json` contains
  `recall_snapshot` or `memory_retained` (R-6's SC-003 basis).

## Consistency of counts

- [ ] CHK017 - Do §Scale/Scope numbers match the task list? [Consistency] —
  **No** (gap 3): src edited is 12 `.py` files (9 + T030–T032), tests edited
  is 9 distinct files (T040's lists share 3), new test files are 3
  (T043–T045), not "9 / 10 / 4".

## Notes

- The plan's substance is sound: the hash definition (R-3), in-activity
  persistence (R-1/R-2), degrade-never-raise (R-5), memo threading
  (R-4), the event-based stage record (R-6), the reader (R-7) and scrub
  (R-8) are each concrete, tested, and traceable. All four gaps are
  documentation-level; none changes a task's work, the ordering, the
  blocking checks or the safety argument.
- Per the 020 precedent (plan pass 2: one doc-level gap still drew
  fixes-needed), gaps 1–3 require a fixes-needed verdict; gap 1 in
  particular would misdirect `/speckit-tasks`.

## Pass 2 (2026-11-11)

The four pass-1 gaps re-checked against the edited artifacts, plus a fresh
placeholder and stale-reference sweep. **All resolved.**

1. **RESOLVED — spec Testing Scope bullet.** spec.md:145 now reads "a
   `temporal`-marked replay **check** showing a pre-021 memory-on history
   **replays unpatched, without editing the history (no new activity;
   E-1)**". Consistent with Errata E-1, design D3, research R-1 and plan
   T050. The remaining `workflow.patched` mentions in spec.md (D3, which
   explains why a patch is *not* needed; Assumptions, about the mechanism in
   general) are correct usages.
2. **RESOLVED — Traceability rows.** plan.md §Traceability: FR-009 →
   `T011, T013, T021 | T050` and SC-005 → `T011, T013, T021 | T050`. The
   named tasks are exactly the replay-safety implementers (T011 defaulted
   fields + validator, T013 in-activity persistence, T021 emit); T050 stays
   the validation and is blocking.
3. **RESOLVED — Scale/Scope.** plan.md now says src 12 `.py` files
   (9 + the 3 stage `step.py`), tests 9 edited (7 distinct in T040, plus
   T041 and T042) and 3 new (T043–T045), docs 4 + the 3 stage contracts.
   Matches the task list as counted in pass 1.
4. **RESOLVED — `RecallInput` cite.** plan T013 (plan.md:59) and
   data-model.md:29 now cite `activities.py:51` (the class line, verified
   in pass 1). The plan's other `:50-51` cite (T021, the disabled branch)
   refers to `workflows/memory_host.py:50-51` and was already verified
   correct.

Sweeps: placeholder sweep over all six artifacts clean; all 26 task ids
referenced in plan.md (T010–T014, T020–T023, T030–T032, T035, T040–T045,
T050, T060–T064, T070) are defined in §Phases; no stale references.

**plan.md is approved.** All pass-1 checklist items (CHK001–CHK016) stand;
CHK005, CHK012 and CHK017 now pass with the gaps above closed.
