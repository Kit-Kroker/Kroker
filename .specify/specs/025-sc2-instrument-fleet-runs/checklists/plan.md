# Plan Quality Checklist: Round 025 — SC-2 instrument + fleet runs (plan domain, pass 1)

**Created**: 2026-11-16 · **Artifact**: [plan.md](../plan.md) judged against [spec.md](../spec.md) · **Domain**: plan
**Pass**: 1 · **Depth**: standard · **Audience/timing**: SPEC & PLAN REVIEWER, before tasks generation
**Method note**: `/speckit-checklist` run with arguments fixed by `reviewer-brief-plan-1.md`; clarifying questions skipped (scope fully pinned by the brief; non-interactive role; defaults: depth standard, audience reviewer). Prerequisite script unavailable on this host (no PowerShell) — FEATURE_DIR resolved directly. No `before_checklist`/`after_checklist` hooks registered in `.specify/extensions.yml`. `.specify/memory/constitution.md` is an unfilled template — no binding principles to check against; the plan's own constitution table (repo seam rules) was verified instead.

## Traceability & Coverage

- [x] CHK001 — Is every functional requirement (FR-001..015, FR-020..025 — 21 total) mapped to a plan step and a validation? [Traceability, plan.md "Traceability"]
- [x] CHK002 — Is every success criterion (SC-A1..A3, SC-B1..B4) mapped to a step and a validation? [Traceability, plan.md "Traceability"]
- [x] CHK003 — Does every named validation resolve to a concrete existing or planned artifact at an exact path? [Clarity, quickstart.md] — existing: `tests/test_run_summary_build.py`, `tests/test_run_summary_model.py`, `tests/test_benchmark_sc_rollup.py`, `tests/test_benchmark_score.py`, `tests/replay/`; planned RED: `tests/test_operator_time.py`
- [x] CHK004 — Are the plan's test commands explicit and runnable from repo root? [Clarity, quickstart.md] — pytest targets, ruff/mypy, replay suite, benchmark CLI verbs; `--arm` name re-verified in T020 before run 1
- [~] CHK005 — Are the forward task references (T001–T033) unambiguous for the tasks pass to realize 1:1? [Traceability] — IDs appear only in the traceability/disposition tables; `tasks.md` does not exist yet (expected at this pass); the 1:1 mapping is judged at the tasks review (Finding 5)

## Step Concreteness

- [x] CHK006 — Is every step A–K concrete (named module, function, mechanism — not a directive)? [Clarity, plan.md "Step list"]
- [x] CHK007 — Are exact file paths used throughout, with prefixes defined? [Clarity, plan.md:5] — `S/` = `src/sdlc/`, `T/` = `tests/`
- [x] CHK008 — Is the plan free of placeholders and unresolved markers? [Ambiguity] — grep over the 025 dir: no TODO/TBD/TKTK/???/`[NEEDS CLARIFICATION]`

## Spec ↔ Plan Consistency

- [x] CHK009 — Does the instrument design implement the A.1/A.6 counting rules verbatim (batch = one interaction capped once; human = `decided_by` not in {policy, timeout}; overlap summed as stated upper bound; no-raise ⇒ not measured)? [Consistency, spec §A.1, §A.6; data-model.md]
- [x] CHK010 — Is the engagement cap a single named constant equal to the Q1 ruling (10 min)? [Consistency, FR-004, GATE 1 Q1] — `ENGAGEMENT_CAP_S = 600`
- [x] CHK011 — Is "not measured" separated from 0 by a persisted marker plus the missing-raise rule? [Consistency, FR-005, A1-AS3/AS4] — `RunSummary.operator_instrumented`
- [x] CHK012 — Are both SC-2 rows present (shipped headline + all-scored companion) with "at target" requiring both ≤ 15 min? [Consistency, FR-012, skeptic A1]
- [x] CHK013 — Are all companion lines required (zero-interaction count, human-touched median/max, uncapped wait, SC-4 fraction beside, policy mix, evidence tier)? [Consistency, FR-007/008/013/015]
- [~] CHK014 — Does FR-011's requirement text still read as written after the B.9 rider outcome found its premise false? [Conflict, spec FR-011 vs spec B.9 "Rider outcome"] — see Finding 1
- [x] CHK015 — Is the B.3 "strong arm on every run" vs B.9 "smoke runs both arms" tension resolved by the amendment? [Consistency, spec B.3/B.9/B.6] — smoke exception documented and budgeted as two arms
- [~] CHK016 — Is B.6's ceiling wording internally unambiguous? [Clarity, spec B.6] — see Finding 2
- [~] CHK017 — Does plan step D name both FR-014 flags (">1 commit" AND "summary with no record")? [Completeness, FR-014, plan "Step list" D] — see Finding 3

## Scope Honesty & GATE 1 Rulings

- [x] CHK018 — Does Part A touch no workflow, gate or trust-layer code, and add no events or signals? [Consistency, FR-009] — code-verified: `GATE_AWAITED`/`CLARIFICATION_ASKED` already carry the needed timestamps; derivation lives in the pure summary builder + a new pure module; replay proof assigned to step E (suite exists)
- [x] CHK019 — Does Part B change no code? [Consistency, plan "Shape"] — steps G–K are operations plus one ops doc (`docs/operations/fleet-runs.md`)
- [x] CHK020 — Is Q2 (SOFT, owner answers escalations) honoured rather than re-litigated? [Consistency, GATE 1 Q2] — quickstart pins `--gate-policy soft`; FR-015 defers P4-close-on-SOFT to GATE 2
- [x] CHK021 — Is Q3 answered with code evidence and separate ceiling lines? [Consistency, GATE 1 Q3, spec B.9] — judge-skip impossible for the smoke stamp (evidence below); z.ai-only holds only for the three deveval runs
- [x] CHK022 — Are all spec open questions resolved with nothing silently re-litigated? [Coverage] — no markers remain; `MIN_RUNS`, SC-1/SC-3 definitions and the shipped definition all kept as ruled

## Consult Dispositions

- [x] CHK023 — Is every advisor finding (D1–D7, including D1 hazards 1–2) dispositioned? [Coverage, consults/advisor.md; plan "Skeptic/advisor disposition"] — hazard 2 adopted via spec §A.6 + data-model not-measured rule
- [x] CHK024 — Is every skeptic finding (A1–E3) dispositioned, with partial adoptions stated as partial? [Coverage, consults/skeptic.md] — A2 partial (self-reported effort in operator note, not instrumented); B1 consciously not blocking rollup MET rendering (owner ruling; P4-close surfaced for GATE 2)

## Verification evidence — claims against code

All 10 brief-mandated locations, plus 5 supporting claims:

| Claim | Location | Verdict |
|---|---|---|
| `GATE_AWAITED` emitted only on the opens-for-a-decision branch (OFF→policy, SOFT+auto→auto, else→pending+emit) | `src/sdlc/workflows/gates.py:231-244` | ✅ |
| `_on_gate_awaited` emits gate+round | `src/sdlc/workflows/run_host.py:50-51` | ✅ |
| Batched ASKED loop / single `wait_condition` / ANSWERED loop; signal handler stores no timestamp | `src/sdlc/workflows/question_host.py:60-106, 36-41` | ✅ |
| `_enrich` merges repeats, later always-present fields win; `(gate, round)` dedup loop in builder | `src/sdlc/observability/summary.py:74-87, 132-138` | ✅ |
| `check_smoke` hard-requires rubric scores on clarify + architecture | `src/sdlc/benchmarks/smoke.py:78-88` | ✅ |
| Floor is 5 | `src/sdlc/benchmarks/runs.py:38`; `sc_rollup.py:26` | ✅ |
| `adversarial_review_enabled` defaults False; `run_budget_usd` defaults 0.0 | `src/sdlc/core/models.py:465, 484` | ✅ |
| No rubric ⇒ no judge call | `src/sdlc/benchmarks/judge.py:89-91` | ✅ |
| SC-1 unattended rule; SC-3 loop denominator + loop floor; SC-6 `decided_by == "human"` | `src/sdlc/benchmarks/sc_rollup.py:92-101, 117-144, 177-181` | ✅ |
| `dispatch_smoke` passes no arm; `_run_matrix` refuses dirty tree / missing stamp / multi-arm corpus without `--arm`/`--all-arms` | `src/sdlc/benchmarks/cli.py:619, 299-328` | ✅ |
| Merge override emit can set `decided_by` to a reviewer name | `src/sdlc/stages/merge/step.py:568-577` (574) | ✅ |
| Smoke case: Anthropic judge, 2 rubrics, 2 arms | `benchmarks/cases/todo-api-greenfield/case.yaml:27-37` | ✅ |
| `CaseSpec` carries no budget field | `src/sdlc/benchmarks/models.py:349-410` | ✅ |
| `score.py` already passes records into `build_sc_rollup` | `src/sdlc/benchmarks/score.py:153` | ✅ |
| Touched-file sizes 632 / 199 / 275 | `wc -l` | ✅ exact |

This also closes the one open box in `checklists/requirements.md` ("Cost ceiling carries no dollar figure — plan must source it"): the plan sources it by derivation (smoke run's measured judge cost scaled by rubric count, announced before run 1) rather than inventing a number — resolved by mechanism.

## Findings

1. **FR-011 text vs B.9 rider outcome — non-blocking.** FR-011 still mandates correcting "the stale `benchmarks/sc_rollup.py` path in the ROADMAP SC rows", but R9 (verified: `ROADMAP.md:477-488` already cites `src/sdlc/benchmarks/sc_rollup.py`) and B.9's "Rider outcome" found nothing to correct; the rider reduces to updating the SC-2 row and the P4 line with the measured read. Plan step K / T033 implements the amended intent, so implementability is unaffected. Recommend a one-line FR-011 annotation at the next owner-visible spec touch, or carrying the note into T033.
2. **B.6 ceiling wording — non-blocking.** "The ceiling covers the z.ai spend and the judge spend separately" sits beside "the z.ai spend … has no dollar ceiling". The operative rule (dollar lines = Anthropic judge + research provider; z.ai recorded, flat) is stated and the plan's E3 disposition follows it. Recommend tightening the sentence when the ops doc is written (step E / T013).
3. **Step D flag naming — non-blocking.** FR-014 requires flagging both ">1 commit" and "a summary with no record"; plan step D names the join and the multi-commit flag only. The requirement text plus T007–T010 carry the second flag; name both in step D or in the tasks so the no-record flag cannot be dropped at implementation.
4. **Baseline provenance — non-blocking.** quickstart.md compares the fast tier against "the 11-failure baseline in `memory/kroker-backlog-and-fast-tier`", which is not resolvable inside the repo. Record the numeric baseline in verification.md §025-A (or the ops doc) when the comparison is made, so SC-A3 does not depend on an out-of-repo memory.
5. **Tasks pass note — not a plan gap.** T001–T033 do not exist yet; the plan↔tasks 1:1 mapping, bite-sized task granularity and explicit per-task test commands are judged at the tasks review pass.

## Metrics

- Checklist items: 24 — pass 20, partial 4 (CHK005, CHK014, CHK016, CHK017), fail 0
- FRs mapped: 21/21 · SCs mapped: 7/7
- Advisor findings dispositioned: 7/7 (+2 hazards) · Skeptic findings: 15/15 (A1–E3)
- Code claims verified: 15/15 (10/10 brief-mandated)
- BLOCKING gaps: 0 · non-blocking: 4

VERDICT: approve
