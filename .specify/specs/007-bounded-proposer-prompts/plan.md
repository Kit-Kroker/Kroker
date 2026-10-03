# Implementation Plan: Bounded Proposer Prompts

**Branch**: none (spec directory `007-bounded-proposer-prompts`) | **Date**: 2026-10-03 | **Spec**: [spec.md](spec.md)

**Status**: Reviewer-validated 2026-10-03 (plan: `.workspace/tmp/reviewer-007-plan-1.md`, fixes-needed with no blocking finding, F1–F3 applied, re-checked: approve in `.workspace/tmp/reviewer-007-tasks-1.md`; tasks: `reviewer-007-tasks-1.md` fixes-needed with no blocking finding, F1–F3 applied, `reviewer-007-tasks-2.md` approve). GATE 2 cleared 2026-10-03: limit 1 MiB as a code constant; the aggregate-overflow and silent-absorption residuals are filed to the inbox (`.workspace/tasks/2026-10-03-aggregate-payload-overflow-terminates-run.md`, `2026-10-03-deep-review-handoff-failures-leave-no-record.md`)

**Input**: approved spec (GATE 1: Q1 guard only; Q2 every workflow-scheduled model request of every durable proposer agent; Q3 each call site's existing failure semantics; limit is a code constant) plus consult amendments A1-A8. Design inputs: advisor `.workspace/tmp/advisor-007-1.md`, skeptic `.workspace/tmp/skeptic-007-1.md`, and two probes run in the dev container. Every adopted claim was re-checked in code or by probe (see [research.md](research.md), "Consult disposition").

## Summary

Today a proposer model request whose input exceeds 2,097,152 encoded bytes leaves the run open forever, with the worker retrying the workflow task about 15 times a second (measured, research R1). This feature adds one capability, attached to every durable proposer agent, that measures each model request in workflow code before it is scheduled and, above 1 MiB, raises the repo's existing non-retryable failure. Each call site then takes the failure path it already has. Under-limit runs schedule exactly the commands they schedule today. One new source module, two attachment sites, one boot check.

## Technical Context

**Language/Version**: Python 3.13 (dev container; the host venv is not a verification environment).

**Primary Dependencies**: none added or changed. Uses installed `pydantic-ai-slim` 2.51.0 (`AbstractCapability.wrap_model_request`) and `temporalio` 1.31.0 (`workflow.in_workflow`, `workflow.patched`, `ApplicationError`).

**Storage**: N/A.

**Testing**: pytest fast tier (`pyproject.toml` `addopts`) for everything except one `temporal`-marked workflow test. One pytest invocation per command; do not add `-q`. Ruff, mypy (`src/` only), `scripts/check_file_size.py`.

**Target Platform**: Linux container (`kroker-dev`).

**Project Type**: single repo, Temporal worker + workflows.

**Performance Goals**: the measurement serializes the request once more per model request. About 1 MB serializes in a few milliseconds (R3); typical requests are tens of KB. No measurable change to workflow-task time; `tests/durability/test_first_workflow_task_time.py` stays green.

**Constraints**:
- No edit to `src/sdlc/stages/code/step.py` (991/1000), `src/sdlc/stages/review/`, `src/sdlc/workflows/role_host.py`, `pyproject.toml`, `uv.lock`, or any prompt text. No retry, timeout or budget value changes. No payload codec (FR-012).
- The user's uncommitted files are not touched: `agents/dev/agent.yaml`, `agents/devops/agent.yaml`, `src/sdlc/core/models.py`, `docs/reports/2026-09-22-neon-welcome-session-retro.md`, the two `Pipeline Canvas` HTML files. (`CLAUDE.md` and `.specify/feature.json` are also modified in the primary checkout: those are this feature's own spec-kit pointer updates, not user work, and no task edits them.)
- Replay and golden suites pass unmodified; no history or golden file is re-recorded (FR-006).
- The repo has no `src/sdlc/agents/AGENTS.md`; the root `AGENTS.md` applies, plus `src/sdlc/workflows/AGENTS.md` for the patch-marker rule. Read both before editing.
- All runs in `kroker-dev`. Commits: `git commit -F <msgfile>`, one path per `git add`, no attribution trailers. RC capture `> log 2>&1; echo RC=$?`. Host shell is PowerShell 5.1 (no heredocs).
- TDD: RED tests are written by the qa seat and seen failing before the fix task starts. Reviewer gate is per task and blocking.
- Read `.workspace/tasks/` for known host hazards before any tier run. The `temporal` tier runs in the container only.
- Base: main `721a802`.

**Scale/Scope**: 1 new source module (about 90 lines), 3 source files edited (`loader.py`, `roles.py`, `worker.py`), 3 new test modules, 4 existing test modules edited (capability-list pins), 2 docs. 12 tasks.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo rules from `AGENTS.md` are carried as constraints above. Post-design re-check: no violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/007-bounded-proposer-prompts/
├── spec.md
├── plan.md          # this file
├── research.md      # R1 reproduction, R2-R6 decisions, R7 input inventory, consult disposition, residuals
├── quickstart.md    # dev-container validation runbook
├── checklists/
└── tasks.md         # /speckit-tasks
```

No `data-model.md` and no `contracts/`: the feature adds no persisted entity and no external interface. The guard's behaviour contract is D1 below.

### Source Code (repository root)

```text
src/sdlc/agents/payload_guard.py          # NEW: limit, size measure, capability, factory, lookup
src/sdlc/agents/loader.py                 # build_agents: third capability on the durable path
src/sdlc/agents/roles.py                  # the two hand-built clarify fan-out agents
src/sdlc/worker.py                        # boot check beside the durability check

tests/durability/test_payload_guard.py            # NEW, fast tier: the guard and its attachment
tests/durability/test_payload_guard_callsites.py  # NEW, fast tier: call-site outcomes (D4)
tests/durability/test_payload_guard_workflow.py   # NEW, temporal tier (one module)
tests/durability/test_sandbox_module_marking.py   # pin: add "payload_guard"
tests/durability/test_loader_contract.py          # pin: capability list shape
tests/durability/test_loader_contract_edges.py    # pin: list length 2 -> 3 (durable path only)
tests/durability/test_loader_failclosed_edges.py  # pin: list length 2 -> 3

src/sdlc/workflows/AGENTS.md              # one section: the payload guard
ARCHITECTURE.md                           # §11 row: name the runtime guard that now exists
```

**Structure Decision**: one new module in `src/sdlc/agents/`, which is already passed through the workflow sandbox as a package (`agents/runner.py:40`), so the module needs no sandbox marker of its own. It is separate from `model_ids.py` because that file is already the seam for three other concerns. Tests sit in `tests/durability/`, where the other per-agent capability pins live.

## Design

### D1 — The guard (FR-001, FR-002, FR-003, FR-005, FR-006; research R2-R5)

`src/sdlc/agents/payload_guard.py` exposes:

- `PROPOSER_PAYLOAD_LIMIT_BYTES = 1_048_576`. One constant (FR-005). The comment beside it cites R1 (cap 2,097,152; aggregate 4,194,304) and R4.
- `GUARD_PATCH_ID = "007-proposer-payload-guard"`. A wire name: never renamed once shipped.
- `OVERSIZE_ERROR_TYPE = "ProposerPayloadTooLarge"`.
- `payload_size(messages, model_request_parameters, model_settings) -> int`: bytes of `ModelMessagesTypeAdapter.dump_json(messages)` plus bytes of the request-parameters adapter's `dump_json` plus bytes of the JSON of the settings (empty settings count as `{}`). Pure; no I/O; the parameters adapter is built once at module level.
- `class ProposerPayloadGuard(AbstractCapability)` overriding only `wrap_model_request`:
  1. If not `workflow.in_workflow()`: return `await handler(request_context)` (E9, A1).
  2. `size = payload_size(...)` from `request_context`.
  3. If `size > PROPOSER_PAYLOAD_LIMIT_BYTES` and `workflow.patched(GUARD_PATCH_ID)`: raise `ApplicationError(message, type=OVERSIZE_ERROR_TYPE, non_retryable=True)`.
  4. Otherwise return `await handler(request_context)`.
- `payload_guard() -> ProposerPayloadGuard`: a fresh instance per agent, like `single_retry_layer()`.
- `has_payload_guard(agent) -> bool`: walks `leaf_capabilities(agent.root_capability)`, unwrapping wrapper capabilities, the same traversal `TemporalDurability.from_agent` uses (`pydantic_ai/durable_exec/_base.py:537-554`). Agents without `root_capability` (test stubs) return False.

Rules that are part of the contract:

- **Order of the two conditions in step 3 matters.** `patched` is evaluated only when the size is over the limit, so an under-limit run records no marker and its command sequence is unchanged (R5). Do not hoist the `patched` call.
- **Limit is inclusive**: a size equal to the limit passes (E1).
- **Message** (A7, E7): `agent '<name>': proposer payload <size> bytes exceeds the <limit>-byte limit (007; the request was NOT sent)`. `<name>` is `ctx.agent.name`, or `unknown` if absent. Numbers only; nothing from the payload; under 300 characters for any agent name in the registry.
- **No logging in the guard.** Call sites already log or propagate; a guard log line would duplicate them.
- **No state.** The capability holds nothing per run, so the framework's per-agent copy on bind is harmless.
- Imports: `pydantic_ai` and `temporalio.workflow` at module level are fine here (the package is sandbox-passthrough and `roles.py` already imports both). No provider SDK import.

### D2 — Attachment (FR-002)

- `src/sdlc/agents/loader.py`, `build_agents`, durable path only: `build_kwargs["capabilities"] = [dur, single_retry_layer(), payload_guard()]`. The eval path (`durability_factory is None`) is unchanged: it never runs in a workflow. Update the docstring sentence that describes the list.
- `src/sdlc/agents/roles.py`: add `payload_guard()` to the `capabilities` list of `clarify_route_agent` and `clarify_probe_agent`, after `single_retry_layer()`.
- No `agents/<role>/agent.py` changes: every asset already forwards `capabilities` verbatim.

Existing tests that pin the list and are edited deliberately (same assertions, new expected shape): `test_loader_contract.py`, `test_loader_contract_edges.py` (`len(caps) == 2` → 3 on the durable path; the eval-path `== 1` stays), `test_loader_failclosed_edges.py` (two `== 2` → 3), and `test_sandbox_module_marking.py` (`_PINNED_MODULES` gains `"payload_guard"`). These edits ride in the same commit as D2 so no commit is red.

### D3 — Boot check (FR-002 "never a partial guard described as complete")

`src/sdlc/worker.py`, `get_worker_activities`: inside the existing loop over `ALL_TEMPORAL_AGENTS`, after the durability check, raise `RuntimeError` naming the agent if `has_payload_guard(agent)` is false. Same shape and wording style as the durability check at `worker.py:138-148`. A worker with an unguarded durable agent does not boot.

### D4 — Failure path at call sites (FR-004)

No call-site code changes. Research R6 lists what each site does with a non-retryable `ApplicationError` today; tests pin three representative sites with a fake agent that raises the guard's error (built by calling the guard, not by hand-writing the message):

- `_run_role` propagates it unchanged (type, `non_retryable`, `type` field).
- `run_adversary` returns None (fail-open) and the caller's lens classification yields the "ran but produced no report" tombstone.
- Assessment risk: the degraded reason still contains the agent name, the size and the limit after the 300-character cut.
- `ApplicationError` is an instance of a type in `graph_dispatch.FAILURE_TYPES` (one assertion; the fail-port routing itself is already covered by the graph suites).

### D5 — Tests

**Fast tier, `tests/durability/test_payload_guard.py`** (no server, no real model). Workflow context is simulated by monkeypatching `sdlc.agents.payload_guard.workflow.in_workflow` and `.patched`; the durable capability is not attached in these tests, so nothing tries to schedule an activity.

1. `payload_size`: counts bytes not characters (CJK text: size ≥ 3 × characters); includes parameters and settings; equal inputs give equal sizes.
2. Hook, in-workflow, over limit, `patched` true: raises `ApplicationError` with `non_retryable`, the error type, the message shape (starts with the agent name, contains size and limit, under 300 characters, does not contain a marker string planted in the payload); handler not called.
3. Hook at exactly the limit, and under it: handler called once, result returned.
4. Hook outside a workflow, over limit: handler called (E9).
5. Hook in-workflow, over limit, `patched` false: handler called (replay of an old history, R5). And: `patched` is not called at all when under the limit.
6. Through `agent.run` with a `FunctionModel` and a tool whose returns grow the history: the failure arrives on a later request, the model-call count shows the over-limit request was never made (US2 scenario 1).
7. Through `agent.run` with an output type whose first answers are invalid: the hook is entered once per retry.
8. Coverage: every agent in `ALL_TEMPORAL_AGENTS` has the guard (`has_payload_guard`); `build_agents` hands a distinct guard instance per role on the durable path and none on the eval path; `get_worker_activities` raises for an agent without one.
9. Call sites: the four assertions of D4, in their own module `tests/durability/test_payload_guard_callsites.py` (the discover phase's fail-closed result is asserted there too).

**Temporal tier, `tests/durability/test_payload_guard_workflow.py`** (marked `temporal`; container only). One small workflow using a fixture durable agent with a fake model, in the suite's existing `WorkflowEnvironment` pattern:

- Over-limit prompt: the workflow fails with an `ApplicationError` of type `ProposerPayloadTooLarge` within the test timeout; its history contains the patch marker and no `ActivityTaskScheduled` for a model request (SC-001).
- Under-limit prompt: completes; history contains no marker (FR-007).
- Replay: the over-limit history replays without a non-determinism error.

**Unmodified suites that are the regression check** (FR-006, FR-007, SC-003): `tests/replay/` (feature replay, graph golden), `tests/durability/test_wire_neutrality.py`, `test_first_workflow_task_time.py`, `test_worker_registration.py`.

### D6 — Evidence artifacts (FR-008, FR-009)

- FR-008 is satisfied by research R1 (run during planning). No task re-runs it; the probe scripts stay in `.workspace/tmp/probe-007/` and are not committed.
- FR-009 is satisfied by research R7. One task re-verifies the rows marked "none found" against their producers and corrects the table; it caps nothing.

### D7 — Living docs

- `src/sdlc/workflows/AGENTS.md`: a short section after "Single model egress": the guard exists, lives in `agents/payload_guard.py`, acts per model request in workflow code, uses a patch marker on the failing branch only, and `GUARD_PATCH_ID` is a wire name.
- `ARCHITECTURE.md` §11, row "Payload > limits": replace the unbacked "runtime guard" with what now exists (proposer model requests over 1 MiB fail non-retryably before scheduling; claim-check refs for artifacts unchanged). Docs describe main: this lands in the same branch, last.

## Requirement coverage

| Requirement | Where |
|---|---|
| FR-001 fail before scheduling, no retry | D1 step 3; tests 2, 6; temporal test |
| FR-002 every workflow-scheduled request of all 16; inert in activity | D1 step 1, D2, D3; tests 4, 6, 7, 8 |
| FR-003 failure shape and message | D1 message rule; test 2; D4 risk test |
| FR-004 existing call-site outcomes | D4; test 9 |
| FR-005 one constant with margin | D1; research R4 |
| FR-006 replay | D1 step-3 order; test 5; temporal replay; unmodified replay suites |
| FR-007 under-limit unchanged | test 3, 5; temporal under-limit; wire neutrality |
| FR-008 reproduction | research R1 (done) |
| FR-009 inventory | research R7; verification task |
| FR-010 synthetic payloads, fakes | D5 |
| FR-011, FR-012, FR-013 boundaries | Constraints |
| SC-001 | temporal test (fails within one workflow task, no hang) |
| SC-002 | message rule; test 2 |
| SC-003 | unmodified suites |
| SC-004 | research R1 |
| SC-005 | research R7 + verification task |

## Stop-guards (binding; clearance from the orchestrator only)

1. Any existing replay or golden test fails after D2: stop. Do not re-record. The under-limit path must be command-neutral; a failure means the capability changed scheduled commands.
2. The executor finds a workflow-side model-request path that does not pass through `wrap_model_request`: stop (FR-002).
3. `has_payload_guard` cannot find the guard on a real durable agent although it is attached (the framework wrapped or copied it in a way the traversal misses): stop and report the capability tree; do not weaken the boot check.
4. `test_first_workflow_task_time.py` regresses: stop.

## Residuals (accepted, reported at GATE 2)

From research "Residuals": aggregate overflow of parallel calls; silent absorption in deep review and handoff; prompts between 1 and 2 MiB refused for large-window override models; a mid-call failure discards that call's earlier work; the suspended-response continuation path is unmeasured; three inventory follow-up candidates.

## Complexity Tracking

Empty: no constitution violations.
