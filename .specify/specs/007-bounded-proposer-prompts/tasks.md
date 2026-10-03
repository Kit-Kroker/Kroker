# Tasks: Bounded Proposer Prompts

**Input**: `.specify/specs/007-bounded-proposer-prompts/` (spec.md, plan.md, research.md, quickstart.md)

**Tests**: required (spec FR-010; plan D5). Every behaviour task is preceded by its RED test task. Tasks marked PIN add tests that are expected to pass on first run because they pin behaviour that already exists; a red PIN test is a stop-guard, not a cue to edit source.

## Standing rules for every task

- All test and lint runs happen in `kroker-dev` (see quickstart.md). Never the host venv. One pytest per command; do not add `-q` (already in `addopts`). Capture with `> <log> 2>&1; echo RC=$?`.
- Read `.workspace/tasks/` for known host hazards before any tier run. `-m temporal` runs in the container only.
- Read the root `AGENTS.md` and `src/sdlc/workflows/AGENTS.md` before T003. `src/sdlc/agents/` has no local `AGENTS.md`.
- RED tasks are written by the qa seat and must be seen failing for the stated reason before the paired fix task starts. A RED task's tests are committed in the commit of the task that turns them green, so no commit on the branch is red. The reviewer gate still applies to the RED diff on its own.
- Commit: subject + body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add`. Host shell is PowerShell 5.1: no heredocs.
- Reviewer gate is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N.
- No edit to `src/sdlc/stages/` (any file), `src/sdlc/workflows/role_host.py`, `pyproject.toml`, `uv.lock`, any prompt or `agents/<role>/` file, `tests/replay/histories/`, `tests/replay/golden/`, or earlier `.specify/specs/*`. No retry, budget or timeout value is changed. The user's uncommitted files in the primary checkout are not touched.
- Tests use synthetic payloads and fake models only. No real model call, no credentials.
- Line numbers in plan.md and research.md are as of main `721a802`; re-locate by symbol, not by number.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** Any existing replay, golden or wire-neutrality test fails after T005. Do not re-record a history or golden. The under-limit path must schedule exactly today's commands.
- **SG-2** A workflow-side model-request path is found that does not pass through `wrap_model_request`, or a PIN test (T006, T007, T008) is red (FR-002: name the path and stop).
- **SG-3** `has_payload_guard` returns false for a real durable agent the guard is attached to. Report the agent's capability tree; do not weaken the boot check.
- **SG-4** `tests/durability/test_first_workflow_task_time.py` regresses after T005.
- **SG-5** An edit to a forbidden path (Standing rules) or a dependency change appears necessary.
- **SG-6** T009 finds an input that can plausibly reach the limit on an ordinary run. Record it in research.md R7 and report it; do not cap it (FR-009).

## Phase order

| Phase | Purpose | Story | Plan | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | — | — | — | 1 |
| 2 Foundational: the guard module | blocks US1 and US2 | — | D1 | 1 |
| 3 Every durable agent is guarded | US1 | US1 | D2, D3, D4, D5 | 3 |
| 4 Growth during a call, assessment | US2 | US2 | D4, D5 | 1 |
| 5 Input inventory | US3 | US3 | D6 | 1 |
| 6 Living docs + verification | — | — | D7 | 3 |

---

## Phase 1: Setup and baseline on unmodified main (no source edits)

- [ ] T001 Create branch `007-bounded-proposer-prompts` from main `721a802` in a worktree of the primary checkout, confirm `kroker-dev` syncs (`uv sync --frozen --extra dev --extra logfire`), run `pytest` and `mypy` once each, and record the base sha, the fast-tier pass count, any pre-existing failures and the mypy error count in `.specify/specs/007-bounded-proposer-prompts/baseline.md`. Commit

**Checkpoint**: baseline.md holds base sha, pass count, mypy count.

---

## Phase 2: Foundational — the guard module (blocks US1 and US2)

**Goal**: `src/sdlc/agents/payload_guard.py` exists with the plan-D1 contract, unit-tested, attached to nothing yet.

**Independent test**: `pytest tests/durability/test_payload_guard.py`.

- [ ] T002 RED: create `tests/durability/test_payload_guard.py` (fast tier, no server) with plan-D5 cases 1–7. Simulate workflow context by monkeypatching `sdlc.agents.payload_guard.workflow.in_workflow` and `.patched`; never attach `TemporalDurability` in this module. (1) `payload_size`: CJK text measures at least 3 bytes per character; request parameters and settings are included; equal inputs give equal sizes. (2) hook, in-workflow, over limit, `patched` true → `ApplicationError` with `non_retryable is True`, `type == "ProposerPayloadTooLarge"`, message starting `agent '<name>': proposer payload `, containing the measured size and the limit, shorter than 300 characters, and NOT containing a sentinel string planted in the oversized payload; the handler is not called. (3) size equal to `PROPOSER_PAYLOAD_LIMIT_BYTES` and a small size → handler called once and its result returned. (4) outside a workflow, over limit → handler called. (5) in-workflow, over limit, `patched` false → handler called; and under the limit `patched` is never called (assert on a recording stub). (6) through `Agent(FunctionModel(...), capabilities=[payload_guard()]).run` with a tool whose returns grow the history past the limit → the error surfaces from `agent.run` as `ApplicationError`, and the model-function call count shows the over-limit request was not made. (7) through `agent.run` with an `int` output type and a model that first answers with non-integers → the hook is entered once per model request (count via a subclass or wrapper). Confirm every case fails on the missing module `sdlc.agents.payload_guard`
- [ ] T003 Create `src/sdlc/agents/payload_guard.py` exactly per plan D1: `PROPOSER_PAYLOAD_LIMIT_BYTES = 1_048_576` (comment citing research R1 and R4), `GUARD_PATCH_ID = "007-proposer-payload-guard"` (comment: wire name, never rename), `OVERSIZE_ERROR_TYPE`, pure `payload_size(messages, model_request_parameters, model_settings)`, `ProposerPayloadGuard(AbstractCapability)` overriding only `wrap_model_request` with the four steps in D1's order (`patched` evaluated only after the size test is true), `payload_guard()` factory, `has_payload_guard(agent)` using `leaf_capabilities(agent.root_capability)` with wrapper unwrapping and returning False for objects without `root_capability`. Import Temporal as `from temporalio import workflow` and call `workflow.in_workflow()` / `workflow.patched(...)` by attribute (T002 patches those attributes; a `from temporalio.workflow import in_workflow` form would bypass the test seam). No logging, no state, no provider SDK import. In the same commit add `"payload_guard"` to `_PINNED_MODULES` in `tests/durability/test_sandbox_module_marking.py`. T002 goes green; run `pytest tests/durability/test_payload_guard.py`, then `pytest tests/durability/test_sandbox_module_marking.py`; commit T002 + T003 together

**Checkpoint**: the guard works in isolation; no agent carries it yet; fast tier otherwise unchanged.

---

## Phase 3: User Story 1 — an oversized proposer payload fails its stage instead of hanging the run (P1)

**Goal**: every durable proposer agent carries the guard, the worker refuses to boot otherwise, and each call site reaches its existing failure outcome (FR-001..FR-004, FR-006, FR-007).

**Independent test**: `pytest tests/durability`, then `pytest -m temporal tests/durability/test_payload_guard_workflow.py`.

- [ ] T004 [US1] RED: (a) in `tests/durability/test_payload_guard.py` add plan-D5 case 8: every agent in `sdlc.agents.roles.ALL_TEMPORAL_AGENTS` satisfies `has_payload_guard`; `build_agents` with a durability factory hands each role a `ProposerPayloadGuard` and no instance is shared between two roles; `build_agents` with `durability_factory=None` hands none; `sdlc.worker.get_worker_activities` raises `RuntimeError` naming the agent when `sdlc.worker.ALL_TEMPORAL_AGENTS` (the worker module's own binding, which is the one the function iterates; patching `sdlc.agents.roles` has no effect) is monkeypatched to include a durable agent built without the guard. (b) update the capability-list pins to the new shape, assertions otherwise unchanged: `tests/durability/test_loader_contract_edges.py` durable-path `len(caps) == 2` → `3` with the third an instance of `ProposerPayloadGuard` (leave the eval-path `== 1`); `tests/durability/test_loader_failclosed_edges.py` both `== 2` → `3`; `tests/durability/test_loader_contract.py` docstring and `_durable_and_retry` split so the guard is not counted as a durability instance. Confirm (a) and (b) fail because nothing attaches the guard
- [ ] T005 [US1] Attach the guard and add the boot check: in `src/sdlc/agents/loader.py` `build_agents`, durable path only, `build_kwargs["capabilities"] = [dur, single_retry_layer(), payload_guard()]` and update the docstring sentence describing the list (eval path unchanged); in `src/sdlc/agents/roles.py` add `payload_guard()` after `single_retry_layer()` in the `capabilities` of `clarify_route_agent` and `clarify_probe_agent`; in `src/sdlc/worker.py` `get_worker_activities`, inside the existing loop and after the durability check, raise `RuntimeError` naming the agent when `has_payload_guard(agent)` is false. T004 goes green. Then run, as separate commands: `pytest tests/durability`; `pytest`; `pytest -m temporal tests/replay`; `pytest -m temporal tests/durability/test_wire_neutrality.py`; `pytest -m temporal tests/durability/test_first_workflow_task_time.py` (SG-1, SG-3, SG-4). Confirm `git status --short tests/replay` is empty. Commit T004 + T005 together
- [ ] T006 [US1] PIN: create `tests/durability/test_payload_guard_callsites.py` (fast tier) with plan-D4's call-site assertions, each using the real error obtained by driving `ProposerPayloadGuard.wrap_model_request` over the limit (not a hand-written message): `RoleHost._run_role` with a fake agent whose `run` raises it → the same exception object propagates (type, `non_retryable`, `type` field intact) and no usage is tracked; `sdlc.stages.review.step.run_adversary` with such an agent → returns None, and `sdlc.stages.review.lenses.classify_lens` for an adversary that ran and returned None yields the undeclared-absent tombstone; the error is an instance of a type in `sdlc.workflows.graph_dispatch.FAILURE_TYPES`. Expected green on first run (SG-2 if not). Commit
- [ ] T007 [US1] PIN: create `tests/durability/test_payload_guard_workflow.py` (marked `temporal`), following the workflow-environment pattern already used under `tests/durability/` and its `fixture_agents/`: a small test workflow that runs a durable fixture agent (fake model, `TemporalDurability` + `payload_guard()`) on a prompt passed as input. Cases: over-limit prompt → the workflow fails with a cause that is an `ApplicationError` of type `ProposerPayloadTooLarge` well inside the test timeout, and some event in its history carries the patch id `007-proposer-payload-guard` (do not pin the event type's spelling; it differs by server build) and no `ActivityTaskScheduled` event exists; under-limit prompt → completes and no event in its history carries that patch id; the over-limit history replays through `Replayer` with no non-determinism error. Run `pytest -m temporal tests/durability/test_payload_guard_workflow.py`. Expected green on first run (SG-2 if not). Commit

**Checkpoint**: US1 acceptance scenarios 1–4 hold; replay and golden suites green and unmodified.

---

## Phase 4: User Story 2 — a payload that grows during a call is caught too (P2)

**Goal**: evidence that a later request and the assessment proposers are covered (FR-002; spec A1). No source change: the mechanism landed in phases 2 and 3.

**Independent test**: `pytest tests/durability/test_payload_guard_callsites.py`, then `pytest -m temporal tests/durability/test_payload_guard_workflow.py`.

- [ ] T008 [US2] PIN: (a) in `tests/durability/test_payload_guard_workflow.py` add a growth case: the durable fixture agent has a tool whose returns push the history past the limit on a later request → the workflow fails with `ProposerPayloadTooLarge`, and the history shows the earlier model-request activities scheduled and completed and none scheduled for the over-limit request. (b) in `tests/durability/test_payload_guard_callsites.py` add the assessment assertions with fakes (no server): with `t_discover.run` raising the guard's error the discover phase returns its existing fail-closed `no_discover` result whose reason names the agent, the size and the limit; with `t_risk.run` raising it the risk phase returns its existing degraded result and the agent name, size and limit all survive the 300-character cut; reuse the scaffolding of the existing assessment workflow tests (`tests/test_assessment_workflow.py`) rather than building a new harness. (c) one assertion that `discover_agent` and `risk_agent` are in `ALL_TEMPORAL_AGENTS` and carry the guard. Expected green on first run (SG-2 if not). Commit

**Checkpoint**: US2 acceptance scenarios 1–2 hold.

---

## Phase 5: User Story 3 — the team knows which inputs can reach the limit (P3)

**Goal**: research.md R7 marks every embedded input capped or uncapped, with no "none found" left unverified (FR-009, SC-005).

**Independent test**: reviewer spot-checks every changed row against the code.

- [ ] T009 [US3] In `.specify/specs/007-bounded-proposer-prompts/research.md` R7, for each cell that says "none found" (idea brief, recall items, QA raw result, clarified requirements' human answers, discover candidate count, risk capability count, and any other): read the producer of that input on the branch and replace the cell with either the cap and its file and symbol, or "uncapped" with a one-line reason; re-estimate "Can it reach 1 MiB?" where the answer changes. Also add a row for each workflow-built research-stage activity input (the plan and synthesis inputs in `src/sdlc/stages/research/`), marked as outside the guard. Cap nothing and edit no source file (SG-6). List in the task report every row changed and the line that proves it. Commit

**Checkpoint**: R7 contains no "none found".

---

## Phase 6: Living docs and verification

- [ ] T010 [P] Add a section to `src/sdlc/workflows/AGENTS.md` after "Single model egress: forwarding and the label guard (004)": the proposer payload guard (007) lives in `src/sdlc/agents/payload_guard.py`, is attached to every durable agent by the loader and to the two clarify fan-out agents in `roles.py`, checks each model request in workflow code before it is scheduled, is inert inside activities, raises the non-retryable `ProposerPayloadTooLarge` above `PROPOSER_PAYLOAD_LIMIT_BYTES`, takes its patch marker only on the failing branch so under-limit runs stay command-identical, and `GUARD_PATCH_ID` is a wire name. State the two things it does not cover: the combined size of parallel requests in one workflow task, and agents run inside activities. No other file. Commit
- [ ] T011 [P] In `ARCHITECTURE.md` §11, row "Payload > limits": replace "oversized payloads rejected in code review by convention + runtime guard" with wording that names what exists: claim-check refs for artifacts; proposer model requests over 1 MiB fail non-retryably before they are scheduled (`agents/payload_guard.py`). Change that one row only. Commit
- [ ] T012 Run quickstart.md §3, §4 and §5 as separate commands and record each result, the pass-count delta against baseline.md, the empty forbidden-path diff, the SG-6 list from T009, and the per-task commit shas in `.specify/specs/007-bounded-proposer-prompts/verification.md`. Commit

---

## Dependencies

- T001 first; T012 last.
- T002 → T003 → T004 → T005. T006 and T007 need T005. T008 needs T007 (same test module) and T006 (same test module).
- T009 depends on nothing but T001. T010 and T011 need T005 (they describe what landed).
- `[P]`: T010 and T011 touch different files and need no gate between them.

## Requirement → task map

| Requirement | Tasks |
|---|---|
| FR-001, SC-001 | T002, T003, T007 |
| FR-002 | T002 (cases 4, 6, 7), T004, T005, T008 |
| FR-003, SC-002 | T002 (case 2), T003, T008 |
| FR-004 | T006, T008 |
| FR-005 | T003 |
| FR-006 | T002 (case 5), T003, T005 (replay suites), T007 (replay case) |
| FR-007, SC-003 | T002 (cases 3, 5), T005, T007 (under-limit case), T012 |
| FR-008, SC-004 | done in research.md R1 during planning; no task |
| FR-009, SC-005 | research.md R7; T009 |
| FR-010 | all test tasks (Standing rules) |
| FR-011, FR-012, FR-013 | Standing rules; T012 (forbidden-path diff) |
| Edge cases E1–E9 | E1 T002 (3); E2 T002 (1); E3 no call, nothing to test; E4 T002 (5), T005, T007; E5 per-request by construction, aggregate is a named residual; E6 one constant, T003; E7 T002 (2); E8 research R3, R4; E9 T002 (4) |

## Implementation strategy

MVP is phases 1–3: after T005 the defect is fixed for every durable agent, and T006–T007 prove it. Phase 4 adds evidence for the growth and assessment cases without changing source. Phase 5 is a document. If time runs out after phase 3, the branch is shippable; phases 4–6 can follow.

**Totals**: 12 tasks — setup 1, foundational 2, US1 4, US2 1, US3 1, docs and verification 3. Ten commits (baseline; module; attachment; call-site pins; workflow pins; US2 pins; inventory; two docs; verification).
