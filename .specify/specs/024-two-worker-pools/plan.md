# Implementation Plan: two worker pools — round 024 (E-91)

**Branch**: none (shared tree; spec dir `024-two-worker-pools`) | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)

**Input**: `.specify/specs/024-two-worker-pools/spec.md`. GATE 1 cleared 2026-11-15, and the advisor and skeptic consults are folded in (`consults/`).

`S/` = `src/sdlc/`. `T/` = `tests/`.

## Split decision (pre-authorized at GATE 1, recorded here)

**Sizing fails one L. 024 runs as two crew rounds, 024-i then 024-ii, from this one plan and one tasks.md.**

Why it does not fit one L (advisor D7, confirmed by counting):
- 33 harness call sites in 13 files (research R3), 8 root inputs, and 11 child-copy sites;
- worker pool modes with a dual `Worker`, the poller check at 8 start paths, the doctor, compose, and the id fix;
- 3 test layers: AST, a dynamic recorder, and a replay proof plus an in-test capture;
- the barrier load test;
- one file at 998 of 1000 lines.

There are also two distinct review surfaces: boot and operations, and workflow determinism.

**The cut is Part A.4's, adjusted per advisor D7.** The poller check and the doctor move into 024-i, because they need no routing. That leaves 024-ii purely workflow-side.

- **024-i — the pools exist; routing is hard-off.** Steps A–F.
  - Shippable alone: a harness worker can boot, and nothing else changes.
  - It does **not** unblock R025, and its close-out must say so.
- **024-ii — routing on.** Steps G–J. It needs 024-i merged.
  - It unblocks R025, and it is the round that marks NFR-2 delivered.

## Summary

ADR-9's two capability pools:
- **Core:** `ai-sdlc`. All workflows plus the core activities.
- **Harness:** `KROKER_HARNESS_QUEUE`. The 28 activities that spawn a CLI, execute repo code, or touch a run's worktree or branches (R2). It is capped by `KROKER_HARNESS_CAP`.

The worker's pool mode comes from `KROKER_WORKER_POOL`, and `all` is today's behaviour (R5). Routing is a `harness_queue` input field set by client start paths. It is omitted from payloads when `None` (R1), applied at each harness call site by `on_harness` (R3), and proven complete by an AST walk plus a temporal-tier recorder (R4).

Start paths refuse to start when routing is on and the harness queue has no fresh poller (R6). Replay needs no patch marker (R7, proven empirically by the skeptic and pinned by a test).

Fleet enablers:
- unique benchmark ids (R8);
- a shared session store on one host (R9);
- a janitor lock (R10);
- a barrier-fake load proof of the cap and of no starvation (R11);
- R025 operating notes (R12).

## Technical Context

**Language/Version**: Python 3.13 (existing).

**Primary Dependencies**:
- `temporalio` 1.31.0 (existing). `Worker(max_concurrent_activities=, identity=)`, `workflow_service.describe_task_queue`, and the outbound interceptor API in the tests only.
- `pydantic` 2.14.1 (`Field(exclude_if=)`, verified).
- No new packages.

**Storage**: none new. Compose gains one named volume, `harness-sessions`.

**Testing**:
- **Fast tier:** `pools.py`, the boot plan, classification, the AST call-site walk, the doctor, ids and the janitor lock.
- **`-m temporal`:** two `Worker` objects on the dev-server with the repo's fakes plus a barrier fake (R11), and a recorder interceptor (R4).
- **Replay tier:** a forced-queue replay of the stored corpus, and an in-test routing-on capture (R7).
- No stored fixture is written.

**Target Platform**: one Linux host. Either one process (`all`) or two processes or containers (`core` + `harness`).

**Project Type**: the worker runtime plus the client start paths inside the `sdlc` package.

**Performance Goals**: SC-003 and SC-004. On fakes: 5 concurrent benchmarks, harness peak ≤ cap, and core schedule-to-start p95 < 5 s (the test asserts < 1 s).

**Constraints**:
- The 1000-line ceiling: `S/stages/code/step.py` is at 998, and step G1 extracts first.
- No `GraphWorkflow` node or handler change.
- No `<stage>.md` change.
- No trust-layer change.
- Shared tree: never `git add -A`, never stash.
- No paid run.

**Scale/Scope**: one host, 2 pools, a cap of about 2–8, and at least 5 concurrent runs.

## Constitution Check

`.specify/memory/constitution.md` is an unfilled template. The binding rules are root `AGENTS.md`, `T/replay/AGENTS.md` and `S/workflows/AGENTS.md`.

| Rule (source) | How the plan complies | Status |
|---|---|---|
| 1000 lines per file | G1 extracts `S/stages/code/acts.py` before any edit to `step.py` (998). `S/cli.py` (959) gets about 12 lines. New modules are each < 250 lines | PASS |
| Cross-stage call ban | `S/pools.py` is a horizontal leaf. Stage steps import a helper, not another stage. `acts.py` stays inside `stages/code/` | PASS |
| Producer owns artifacts | No new artifact. The input fields live on their owners' models | PASS |
| `T/replay/AGENTS.md` (capture-only writers, SG-2/SG-3) | No stored history or golden changes. The routing-on capture is in-test (R7). `git status tests/replay/` must be clean | PASS |
| `S/workflows/AGENTS.md` (host attribute ownership) | No new workflow attribute or handler. Routing is read from existing input fields | PASS |
| Artifact boundary (behaviour change ⇒ clause change) | No stage behaviour changes. Docs (ARCHITECTURE §9, ADR-9, ROADMAP, crew.md) update in J1, in 024-ii's landing diff | PASS |
| Trust layer, ADR-6 | Untouched. Containment, `pre_tool`, the env allowlist, gates and the judge checks run unchanged on whichever pool hosts the activity. Both pools run the same image and boot checks | PASS |

**Post-design re-check:** no violations.

Surfaced for GATE 2:
- the `check_test_drift` registration fix, a latent pre-existing defect (R2);
- the partial rebuttal of skeptic L2, which keeps the Q2 ruling as written (R9).
- the rollback asymmetry: the maintenance family refuses routing-on inputs on a pre-024 worker; remedy in E2 (R1, reviewer gap 7).

## Phases

TDD throughout: RED tests first, and each step lands green on the fast tier.

### 024-i — the pools exist (routing hard-off)

**Phase A — setup**
- **A1.** Capture the baseline per quickstart §0 into `baseline-failures.txt`. Use a throwaway worktree, as 023b's file documents.

**Phase B — the class authority**
- **B1.** Create `S/pools.py`: `HARNESS_ACTIVITIES`, `HARNESS_QUEUE_DEFAULT`, `PoolMode`, `on_harness`, `resolve_harness_queue` (data-model). Pure tests go in `T/test_pools.py`.
- **B2.** Register `check_test_drift` in `S/worker.py:get_worker_activities()`. Write `T/test_pools_classification.py` (R4 static layer 1).

**Phase C — worker boot**
- **C1.** `pool_boot_plan` / `PoolBootPlan` in `S/pools.py`, tested in `T/test_worker_boot_plan.py` against every row of the truth table.
- **C2.** Restructure `S/worker.py:main()`:
  - Build zero, one or two `Worker`s from the plan. Add `core_activities()` and `harness_activities()` filters over `get_worker_activities()` by `activity.defn` name.
  - Set the identities and print lines (contracts/worker-boot.md G-1..G-5). The harness worker starts first.
  - The janitor runs only when `plan.janitor` is set.
  - The single-pool path stays byte-identical in behaviour, and a test asserts its print line and its registered set.
- **C3.** `require_harness_poller` plus `HarnessQueueUnpolled` in `S/pools.py` (R6). Add a temporal-tier proof test, `T/test_pools_failfast.py::test_poller_freshness`, that:
  - measures that a fresh harness worker is seen within 5 s;
  - measures that a stopped worker drops out after the freshness window.

  If the server's poller list proves unusable, **STOP and re-plan R6.**

**Phase D — operations**
- **D1.** `check_worker_pools()` in `S/doctor/checks.py`, wired into the doctor's row list. Tested in `T/test_doctor_pools.py` with an injected client stub.
- **D2.** The janitor lock in `S/vcs/janitor.py:sweep_once` (R10), tested in `T/test_janitor_lock.py`.

**Phase E — deployment and docs**
- **E1.** Confirm the claude and opencode session-store paths in the runtime image: `docker run --rm <image> sh -c 'ls -d /root/.claude /root/.local/share/opencode/storage'`, or the Dockerfile `HOME`. Then add `docker-compose.pools.yml` (contracts/worker-boot.md §Compose).
- **E2.** Write `docs/operations/worker-pools.md`:
  - the modes, the env vars, the compose overlay and the cap;
  - the Q3 sizing rule;
  - the R12 notes for R025;
  - the "024-i: routing not yet available" banner, which E2 writes and J1 removes;
  - the rollback remedy for the maintenance family (R1).

**Phase F — fleet enablers**
- **F1.** Change the benchmark id at `S/benchmarks/cli.py:338` (R8), tested in `T/test_bench_ids.py`.
- **F2.** Add `git worktree prune` in `S/benchmarks/axis.py`'s `finally` (R10), with a unit test on a tmp repo in `T/test_axis_prune.py`.

**024-i close-out (F3).**
- Run quickstart §1a (the 024-i subset), §3 and §4, plus the C3 proof `uv run pytest -q -m temporal tests/test_pools_failfast.py::test_poller_freshness`.
- Write `verification.md` §024-i.
- Commit per task. Do not update ROADMAP's NFR-2.

### 024-ii — routing on

**Phase G — fields and sites**
- **G1.** Line-neutral extraction: move `LONG_ACT`, `_long_act`, `ACT` and the related constants from `S/stages/code/step.py` into `S/stages/code/acts.py`, and re-import them. Assert with `wc -l` that `step.py` is ≤ 975 afterwards.
- **G2.** Add the `harness_queue` field (R1) to the 8 models, with the name validator. Test in `T/test_pools.py::test_inputs_omit_none` that every model dumps with no key when it is `None`, and round-trips when it is set.
- **G3.** Apply `on_harness` at the 33 sites (R3 table).
- **G4.** Add the child copies at the 11 inheritance sites (data-model §Inheritance).
- **G5.** Write `T/test_pools_call_sites.py` (the R4 AST walk). It must be RED before G3 and GREEN after.

**Phase H — start paths and proofs**
- **H1.** In `S/graph/start.py:start_graph_run`, add `resolve_harness_queue` + `require_harness_poller` + setting the field. Do the same at the direct sites `S/cli.py:793, 839, 889`, `S/benchmarks/cli.py:336`, `S/maintenance/cli.py:252` and `S/schedules/apply.py:62` (apply time, with the value baked into the action input). Add the start-path grep test to `T/test_pools_call_sites.py`.
- **H2.** `T/test_pools_failfast.py`: every start path refuses within 10 s with no workflow created (SC-005).
- **H3.** `T/test_pools_routing.py`: the recorder interceptor across the nine workflow types with harness-class sites, plus `ReflectWorkflow` asserted all-core (W-2), with routing on and routing off (SC-002). Assert on harness `Worker` identities.
- **H4.** `T/replay/test_pools_replay.py`: (a) the forced-queue replay of the stored corpus; (b) the in-test routing-on `greenfield_happy` capture, whose projection must equal the stored golden (SC-006).
- **H5.** `T/test_pools_fleet.py` (R11; SC-003 and SC-004).

**Phase J — docs and close-out**
- **J1.** Remove the E2 banner and update the living docs:
  - ARCHITECTURE §9's status note: two queues built, five-pool target open;
  - `docs/adr.md` ADR-9's status line;
  - ROADMAP NFR-2 (`[x]` in two-pool form) and ADR-9's row;
  - `docs/roadmap/agent-architecture-plan.md`: AP-2.5a `[x]`, AP-2.5b open, depending on AP-2.1;
  - the `docs/roadmap/crew.md` boundary: when resume is safe (R9);
  - ROADMAP §8 item 1, the next step being R025;
  - the `Last verified` cell plus `docs/roadmap/last-verified-log.md`, per the AGENTS.md rule.
- **J2.** Run quickstart §1–§4 in full. Write `verification.md` §024-ii, with the SC-001..007 table and the residuals.

## Skeptic / advisor disposition

| Finding | Disposition |
|---|---|
| D1: a field on each root input; children copy it | **Adopted** (R1). Strengthened with `exclude_if`, so payloads are identical too |
| D1/D3: the memo or interceptor alternative | **Not adopted:** `continue_as_new` memo loss, schedule and replayer wiring, and it is not greppable. Kept as the named fallback (R1) |
| D2 / L4: amend A.1(c) to cover reads of run state; the class table | **Adopted** (R2). Both consults agree. `paths_exist` stays **core**: it reads the canonical `repo_path` (`clarify/step.py:149-151`), not a run worktree, which overrides L4's claim. `read_committed_bytes` is **harness** (advisor), not core (skeptic): when unsure, harness |
| D2 / L4: `check_test_drift` | **Adopted, and escalated:** it is unregistered today. Fixed in B2 and surfaced for GATE 2 |
| D3: the `on_harness` helper plus AST and dynamic tests; the `step.py` ceiling | **Adopted** (R3, R4, G1) |
| D4: activity-type `DescribeTaskQueue` with freshness; central plus per-site calls; apply-time for schedules | **Adopted** (R6), proven first in C3 |
| D4.3: a pre-flight activity in `MaintenanceKickWorkflow` | **Not adopted:** queue-wait is the defined F1 semantics, and the doctor and UI show it. Recorded as a residual (R6) |
| D5: `all` runs two `Worker`s; the cap on harness only; `core` needs a queue | **Adopted** (R5) |
| D6 / L1: replay and `patched()` | **Adopted:** no marker. L1's empirical replay proof plus the permanent guard in H4 (R7) |
| L1: a `null` key in payloads | **Adopted:** `exclude_if` (R1), verified |
| D7: split, with the cut adjusted | **Adopted** (§Split decision) |
| L2: shared session store across replicas breaks | **Partly rebutted, ruling kept** (R9). One store under many concurrent CLIs is the status quo (one `HOME` today), and same-host containers share kernel locks. **Adopted:** mount the store subpaths so the `auth.json` bind is not shadowed, and the boundary text "one host only" |
| L3: the janitor in two processes; `axis` registration leak | **Adopted:** the janitor runs only in harness and all modes, with a flock (R10, D2); `axis` prunes (F2) |
| L5: the fake load proof is hollow | **Adopted:** the barrier fake with timing asserts (R11) |
| L6.1: crew wall-clock with cap < concurrent runs | **Ruled (Q3):** semantics unchanged. The sizing rule is documented (E2) |
| L6.2–4: dev-server SQLite, Hindsight and RPM, ports, board WAL | **Documented for R025** (R12). Not fixed in 024 |

## Project Structure

### Documentation (this feature)

```text
.specify/specs/024-two-worker-pools/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/{worker-boot.md, routing-wire.md}
├── consults/{advisor.md, skeptic.md}
├── checklists/requirements.md
├── baseline-failures.txt   (A1)
├── tasks.md                (/speckit-tasks)
└── verification.md         (F3, J2)
```

### Source code touched

```text
024-i
src/sdlc/pools.py                         NEW (B1, C1, C3)
src/sdlc/worker.py                        check_test_drift registered (B2); main() pool modes (C2)
src/sdlc/doctor/checks.py                 check_worker_pools (D1)
src/sdlc/vcs/janitor.py                   flock (D2)
src/sdlc/benchmarks/cli.py                bench id (F1)
src/sdlc/benchmarks/axis.py               worktree prune (F2)
docker-compose.pools.yml                  NEW (E1)
docs/operations/worker-pools.md           NEW (E2)
tests/test_pools.py, test_pools_classification.py, test_worker_boot_plan.py,
tests/test_doctor_pools.py, test_janitor_lock.py, test_bench_ids.py, test_axis_prune.py,
tests/test_pools_failfast.py (C3 freshness proof)

024-ii
src/sdlc/stages/code/acts.py              NEW, extracted (G1)
src/sdlc/core/models.py, workflows/{triage,assessment,tidyup,deployment,crew}.py,
src/sdlc/benchmarks/models.py, maintenance/models.py               fields (G2)
the 13 site files of research R3                                    on_harness (G3)
src/sdlc/benchmarks/workflow.py, workflows/{tidyup,assessment,maintenance,maintenance_execute}.py,
src/sdlc/stages/code/step.py, stages/deploy/step.py                 child copies (G4)
src/sdlc/graph/start.py, cli.py, benchmarks/cli.py, maintenance/cli.py, schedules/apply.py  start paths (H1)
tests/test_pools_call_sites.py, test_pools_routing.py, test_pools_fleet.py, test_pools_failfast.py (H2),
tests/replay/test_pools_replay.py
ARCHITECTURE.md §9, docs/adr.md, ROADMAP.md, docs/roadmap/{agent-architecture-plan,crew,last-verified-log}.md (J1)
```

## Traceability

| Spec | Plan | Validation |
|---|---|---|
| P-FR-001 two queues | B1, C2 | quickstart §1 (boot plan), §2 |
| P-FR-002 class rule | B1, B2 | `test_pools_classification` |
| P-FR-003 pool mode | C1, C2 | `test_worker_boot_plan`; §5 smoke |
| P-FR-004 cap | C1, C2, H5 | the truth table; the fleet peak ≤ cap |
| P-FR-005 routing off by default | G2, G3 | `test_inputs_omit_none`; the AST walk; H3 routing-off leg |
| P-FR-006 inheritance | G4 | H3 across the 9 harness-site workflow types (+ Reflect, all-core) |
| P-FR-007 fail-fast | C3, H1, H2 | `test_pools_failfast` (SC-005) |
| P-FR-008 doctor | D1 | `test_doctor_pools` |
| P-FR-009 bench ids | F1 | `test_bench_ids`; the fleet test's same-second starts |
| P-FR-010 compose | E1 | quickstart §5: `docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q` exits 0 |
| P-FR-011 replay | G2, H4 | quickstart §3 (SC-001, SC-006) |
| P-FR-012 untouched surfaces | all steps | `git diff --stat` shows no `<stage>.md`, `graph_nodes` handler logic, or containment files; J2 records it |
| P-FR-013 docs | E2, J1 | J2 checklist |
| SC-001 | A1, F3, J2 | quickstart §3–§4 |
| SC-002 | H3 | quickstart §2 |
| SC-003 / SC-004 | H5 | quickstart §2 |
| SC-005 | H2 | quickstart §2 |
| SC-006 | H4 | quickstart §3 |
| SC-007 | G1, F3, J2 | `check_file_size.py` |
| GATE 1 Q2 / Q3 | E1, E2, J1 | the docs |

`graph_nodes/precode.py` and `postplan.py` gain `on_harness` at their activity call only. This is an activity-option change, not a node or handler logic change: P-FR-012 is read this way, and the AST test pins it.

## Risks

1. **The poller freshness signal** (`last_access_time`) may lag or linger on the dev-server. C3 proves it first, and a failure means STOP and re-plan R6.
2. **The site count may drift** while 024-ii is in flight. The AST test is the guard.
3. **`step.py` extraction churn.** G1 is a pure move, re-imported under the same names, and existing tests cover it.
4. **The barrier fake must be registered under the real activity name** on the harness `Worker` only. Otherwise the test proves nothing about placement. H5 asserts the identities.
5. **Rollback (R1, reviewer gap 1).** A pre-024 worker routes a routing-on run's harness work to core for 7 of 8 input families, which is benign. For the maintenance family it **fails validation loudly** (`extra="forbid"`). The remedy (re-apply schedules routing-off and drain loops) is in E2, and the item is surfaced at GATE 2.
6. **024-i alone does not unblock R025.** The F3 close-out states it.

## Complexity Tracking

None.
