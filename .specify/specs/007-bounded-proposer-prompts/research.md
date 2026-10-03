# Research: Bounded Proposer Prompts (007)

**Date**: 2026-10-03 | **Base**: main `721a802` | **Spec**: [spec.md](spec.md)

Two probes were run in the dev container (`kroker-dev`, Python 3.13, `temporalio` 1.31.0, `pydantic-ai-slim` 2.51.0). Everything else was read in code. The probe scripts and condensed output are in `.workspace/tmp/probe-007/` (git-ignored; throwaway).

## R1 — What happens today (FR-008, closes H1 / V7)

**Method.** A second instance of the project's own server image (`temporalio/temporal:latest`, dev mode) on port 7244; the live server on 7233 was not touched and the instance was removed afterwards. A minimal workflow builds a string of N bytes in workflow code and passes it to an activity with `RetryPolicy(maximum_attempts=3)`, the same bound the proposers use. Script: `.workspace/tmp/probe-007/probe.py`; output: `run1-condensed.txt`.

| Case | Encoded input | Result |
|---|---|---|
| one activity, 0.5 / 1.0 / 1.9 MiB | under cap | Completes. The SDK logged a `TMPRL1103 … exceeded the warning limit` line (limit 524,288) for each; those lines were dropped from the condensed log. |
| one activity, 2 MiB − 64 bytes | 2,097,124 | Completes. |
| one activity, 2 MiB + 64 bytes | 2,097,252 | **Hangs.** Workflow task fails with cause `PAYLOADS_TOO_LARGE` (`[TMPRL1103] … exceeded the error limit`). Run stays `RUNNING`. |
| one activity, 2.1 / 3.9 / 4.5 MiB | over cap | **Hangs**, same as above. |
| 3 parallel activities × 1.0 MiB | 3 MiB in one task | Completes. |
| 3 × 1.5 MiB, 4 × 1.0 MiB, 5 × 1.0 MiB | ≥ 4 MiB in one task | **Server terminates the run.** `WorkflowExecutionTerminated`, reason `GrpcMessageTooLarge` (server log: "received message after decompression larger than max 4194304"). |
| activity *returns* 2.1 MiB | over cap | Fails cleanly in about 3 s: activity failure, retry state non-retryable, workflow fails. |

**Findings.**

1. **H1 is confirmed.** A single activity input over the cap leaves the run open with no error. The activity retry bound never applies: no activity is ever scheduled.
2. **The cap is exactly 2,097,152 bytes of encoded payload**, checked by the SDK's core before upload (`path: commands[0].schedule_activity_task_command_attributes.input, class: Blob`). The encoded payload was 36 bytes larger than the raw string.
3. **The hang is also a hot loop.** The worker retried the failing workflow task roughly 15 times a second (about 400 attempts in 26 s per case) and logged three lines per attempt. The history shows a single `WORKFLOW_TASK_FAILED` event, so the Temporal UI understates it. The probe's raw log reached 2 MB in five minutes.
4. **There is a second, different failure: the aggregate.** All activities scheduled in one workflow task travel in one message with a 4,194,304-byte limit (after decompression). Over it, the server terminates the run. That is not a hang, but it is also not a stage failure: no failure path runs.
5. **Activity outputs are already safe.** An over-cap result fails the activity non-retryably and the workflow fails. The spec's assumption holds and matches the installed framework's own guard (`pydantic_ai/durable_exec/temporal/_toolset.py:142-173`).

**Consequence for the spec.** US1's wording ("hangs") stands. SC-004 is met by this section. The aggregate case (finding 4) is spec amendment A5: measured, named as a residual, not fixed here.

**Caveat.** `latest` is a moving tag; the image pulled today is the one measured. The per-payload cap is enforced SDK-side from a limit the server reports, so a server configured with a different blob limit would move it.

## R2 — Where the guard sits (D1)

**Decision.** A capability that overrides `wrap_model_request`, attached to each durable agent beside `TemporalDurability` and the single-retry resolver.

**Rationale.**

- `TemporalDurability` schedules the model activity from its own `wrap_model_request` (`pydantic_ai/durable_exec/_base.py:1371-1446`) and declares itself innermost (`_base.py:1595-1598`). A capability with default ordering wraps outside it, so its hook runs in workflow code before anything is scheduled.
- The hook receives the final message list for that request (`pydantic_ai/_agent_graph.py:1577-1594`), and every request, including tool round trips and output-validation retries, is a new pass through it.
- One attachment covers the assessment agents too, because the guard is on the agent, not on `_run_role`.

**Probe (offline, no server).** `.workspace/tmp/probe-007/probe2.py`, output `run2.log`:

- A tool-using agent whose tool returns 400 KB per call: the hook saw 1.4 KB, 402 KB, 804 KB, 1,205 KB on successive requests and raised on the fourth. Three model calls were made; the fourth was not.
- The raised `ApplicationError(non_retryable=True)` reached the caller of `agent.run` as itself: same type, flag intact, message intact.
- An output-validation retry re-entered the hook on each retry.
- `ctx.agent.name` is available in the hook, so the guard needs no constructor argument to name the agent.

**Alternatives rejected.** A history processor (earlier stage, no run context). Subclassing the durable model (private classes). A check in `_run_role` only (misses assessment and every request after the first; rejected at GATE 1). A Temporal outbound interceptor (skeptic's suggestion): it would see every activity, not only model requests, and would have to recognise model-request activities by name; the capability hook is the framework's own extension point for this.

**Open residuals, named.**

- *Suspended-response continuation.* The framework can re-issue a request for a paused or background response with one extra message appended (`_agent_graph.py:1041-1170`). The guard measures the request before that message. None of the registry's agents use this today; the margin (R4) absorbs one response.
- *Whether the suspended-resume path reaches `wrap_model_request`* was not verified. If the executor finds a workflow-side request path that skips the hook, FR-002 says stop and escalate.

## R3 — What to measure (D2)

**Decision.** `len(ModelMessagesTypeAdapter.dump_json(messages)) + len(TypeAdapter(ModelRequestParameters).dump_json(parameters)) + len(json of model_settings)`, in bytes.

**Rationale.** The activity input is the message list, the request parameters, the model settings, a serialized run context and the deps. The first three are the parts that grow or are large. The payload converter uses the same pydantic encoders, so the measure is not an estimate.

**Probe (same script).** For four text shapes the measure equalled the real converter's output for messages plus parameters to the byte (ratio 1.0000):

| Shape | Characters | Encoded bytes (prompt + one tool return of the same text) |
|---|---|---|
| ASCII prose | 420,000 | 842,586 |
| code / JSON heavy (quotes, backslashes, newlines) | 396,000 | 1,178,586 |
| CJK | 180,000 | 1,082,584 |
| emoji (astral) | 80,000 | 642,584 |

So character counts are not a usable proxy: JSON escaping grows code-like text by about 1.5×, and CJK is 3 bytes a character (E2). Two runs on the same input gave identical sizes (determinism, FR-006). Serializing about 1 MB took a few milliseconds, far under the 2 s workflow deadlock detector.

**Not measured by the guard, absorbed by the margin:** the serialized run context, the deps (`ResearchDeps` for the architect, static per run), the payload envelope (36 bytes in R1), a continuation message (R2).

**Alternatives rejected.** Summing part lengths (misses escaping, tool arguments, base64). Measuring the prompt string in `_run_role` (first request only). Calling the payload converter itself in the hook (same bytes, but couples the guard to the converter's API and to the private request-params class).

## R4 — The limit's value (FR-005)

**Decision.** `1_048_576` bytes (1 MiB) of the R3 measure.

**Rationale.**

- *Per payload.* The cap is 2,097,152 (R1). 1 MiB leaves 1 MiB for the unmeasured parts; they are kilobytes in practice.
- *Aggregate.* Three parallel requests at the limit total 3 MiB and complete (R1 measured exactly this). Four at the limit would terminate the run. No lower per-request limit removes the aggregate case entirely (five siblings at 0.8 MiB also exceed 4 MiB), so the limit is chosen for the per-payload cap and the aggregate is a named residual.
- *Not refusing useful work.* 1 MiB is about 250,000 tokens of plain text, more than the registry's models accept. Per spec A3 it is less than a 1,000,000-token model could accept, so an override naming such a model loses prompts between 1 MiB and 2 MiB. Accepted trade, reported at GATE 2: the alternative (1.5 MiB) halves the room for parallel calls.
- It sits above the SDK's own 524,288-byte warning, so a request between the two still logs the SDK warning.

**Alternatives considered.** 1.5 MiB (two siblings safe instead of three). 1.9 MiB (no room for unmeasured parts). 512 KiB (matches the SDK warning; deep review's transcript alone can reach it, so it would turn today's working large reviews into "lens did not run").

## R5 — Replay safety (FR-006, D4)

**Decision.** `workflow.patched("007-proposer-payload-guard")` is evaluated only when the measured size is over the limit. The guard raises only if it returns true.

**Rationale.** Read from `temporalio/worker/_workflow_instance.py:1415-1442`:

- Not replaying: `patched` returns true and records a marker. So a marker is written only by a run that is about to fail on the guard. Under-limit runs issue no new command; the golden projections do not change (FR-007).
- Replaying a history without the marker: returns false. So a captured history that recorded a *successful* call above the limit replays as recorded: the activity is scheduled, no divergence.
- Replaying a history where the guard fired: the marker is present, returns true, the guard raises again. Deterministic.

**Known property.** The result is memoized per run. A pre-upgrade run that replays past an over-limit success keeps the guard off for the rest of that run and behaves as today. Accepted: such a run is one that already succeeded above the limit.

**Consult disposition.** The advisor recommended no marker (a marker on every run breaks the goldens) plus a test pinning the limit above every recorded payload. The skeptic required a marker. The conditional marker satisfies both: no command on under-limit runs, and correctness does not depend on what the recorded histories happen to contain. The advisor's pin test is not adopted; it would guard a property that now holds by construction.

**Does adding the capability change under-limit commands?** No by construction: activity names come from `TemporalDurability`'s own name, the guard registers no activities or toolsets, and the scheduled input is built after the guard returns from the same objects. `tests/durability/test_wire_neutrality.py` and the replay suites are the check.

## R6 — How the failure travels (FR-003, FR-004, D3)

The hook raises `ApplicationError(message, type="ProposerPayloadTooLarge", non_retryable=True)`. Probe R2 shows it reaches the caller of `agent.run` unchanged. `ApplicationError` is a `FailureError` and an `Exception`, so:

| Call site | Today's handling of a non-retryable proposer failure | Evidence |
|---|---|---|
| clarify (single, route), architect, planner, QA, primary reviewer, analyst, merge verdict | No catch at the call; the failure propagates and the stage fails. | `role_host.py:152-164` has no catch; the 004 label guard takes the same route. |
| graph node | Routes to the node's fail port. | `FailureError` is in `FAILURE_TYPES`, `workflows/graph_dispatch.py:65-71`. |
| clarify probes | `gather(return_exceptions=True)`; that dimension asks nothing. | `stages/clarify/step.py:98-103`. |
| adversary lens | Caught, WARNING, returns None; a lens tombstone is recorded. | `stages/review/step.py:243-249`; `stages/code/step.py:854`. |
| deep-review lens | Caught, WARNING, returns None; **no record**. | `review/step.py:361-367`; `code/step.py:884-885`. |
| handoff extractor | Caught, WARNING, mechanical handoff used; **no record**. | `code/step.py:464-470`. |
| assessment discover | Caught; phase returns `no_discover("…: {type}: {message}")`. | `workflows/assessment.py:457-461`. |
| assessment risk | Caught; phase returns `degraded(…)`, message cut to 300 characters. | `assessment.py:678-681`. |

Message shape (A7): `agent '<name>': proposer payload <size> bytes exceeds the <limit>-byte limit (007; the request was NOT sent)`. Numbers only, under 300 characters, nothing from the payload.

## R7 — Input inventory (FR-009, US3)

Every proposer call site, what it embeds, and whether each input is capped. "None found" means no cap exists at the call site or in the producer I read; task T009 re-verifies those rows against their producers before the feature closes. Sizes are estimates, not measurements. Recommendation "guard" means: leave it to the guard.

| # | Call site | Embedded input | Cap | Can it reach 1 MiB? | Recommendation |
|---|---|---|---|---|---|
| 1 | clarify single / route (`stages/clarify/step.py:166, :189`) | idea brief JSON | none found (user-supplied) | Only with a pasted document of that size. | guard |
| | | recall items | none found | Unlikely (short memory items). | guard |
| 2 | clarify probes (`clarify/step.py:90-95`) | idea JSON; route output JSON | none; model output | As row 1. Up to one probe per live dimension in one workflow task: the aggregate case. | guard; aggregate residual |
| | | codebase-map grounding | capped: 40 modules with 5 member paths each, 60 contracts, 25 hot spots (`render_for_prompt`, `context/render.py:35, :26-30, :40`) | No. | — |
| 3 | architect (`stages/architecture/step.py:168-174`) | clarified requirements | model output plus human answers | No. | guard |
| | | codebase-map block | capped, same renderer (`stages/architecture/step.py:110`; `context/render.py:35`) | No. | — |
| | | recall items | none found | Unlikely (short memory items). | guard |
| | | gate revision guidance; delta guidance | none (human text; generated) | No in practice. | guard |
| | | research tool returns, accumulated across requests | each is model output; number of calls not capped by the workflow | Possible on a long research loop: the US2 case. | guard |
| 4 | planner (`stages/plan/step.py:105`) | architecture JSON; recall; guidance | model output; none found; none | No. | guard |
| 5 | QA (`stages/qa/step.py:171-176`) | assertions; QA raw result JSON | none found | Depends on how much test output the raw result keeps. | guard; T009 traces the producer |
| | | diff stat | **none** (`vcs/git.py:102, :115`) | About 80 bytes a file: 13,000 changed files. | follow-up candidate (cap with marker) |
| | | diff patch | 60,000 characters (`vcs/git.py:93, :115`), silent (N1) | No. | — |
| 6 | reviewer, adversary (`stages/review/step.py:141, :203`) | assertions; QA raw JSON; patch | as row 5 | As row 5. | guard |
| 7 | deep review (`review/step.py:296`) | assertions; task JSON; patch | as above | No. | — |
| | | scrubbed transcript | 512 KiB of raw session before conversion (`artifacts/read.py:21, :39-41`), plus digest | Close: 512 KiB of code-like text can pass 700 KB once JSON-escaped (R3). | guard; the most likely real trigger |
| 8 | handoff (`stages/code/step.py:427-431`) | assertions; patch; transcript | as row 7 | As row 7. | guard |
| 9 | analyst (`stages/analyze/step.py:141-146`) | criteria lines; one QA line per task | none | No. | guard |
| | | integration diff stat; patch | none; 60,000 | As row 5, on the whole run's diff. | follow-up candidate |
| 10 | merge verdict (`stages/merge/step.py:548-561`) | full dump of every task result | none | Grows with task count and with each result's embedded reports. Plausible on a run of many tasks. | follow-up candidate (summarise) |
| 11 | assessment discover (`workflows/assessment.py:453`) | discover context | 20 members per candidate (`assessment/discover/context.py:201, :250`); candidate count none found | Large repository only. | guard |
| 12 | assessment risk (`assessment.py:675`) | risk baseline | 30 vulnerabilities per capability and per-family caps (`assessment/risk/prompt.py:19-23`); capability count none | Large repository only. | guard |
| 13 | devops planner | no call site in `src/` | — | — | — |
| 14 | research stage and the architect's research tool | run inside activities; history does not cross as activity input (A1) | — | Not this defect. Workflow-built activity inputs here (idea JSON, merged findings) are the same class as rows 1 and 3. | guard does not apply; follow-up only if T009 finds a reachable one |

**Reading.** No input is shown to reach the limit on an ordinary run. The nearest are the transcript-carrying prompts (rows 7, 8), the merge verdict's task dump (row 10), and a long architect research loop (row 3). The uncapped diff stat (rows 5, 9) needs a very wide change. This supports the GATE 1 ruling: the guard is the fix, and per-input caps are separate, optional follow-ups.

## Consult disposition

Advisor: `.workspace/tmp/advisor-007-1.md`. Skeptic: `.workspace/tmp/skeptic-007-1.md`. Each adopted claim was re-checked in code or by probe.

| Source | Claim | Disposition |
|---|---|---|
| Advisor D1 | `wrap_model_request` capability, workflow-side, sees every request | **Adopted**; confirmed by probe (R2). |
| Advisor D1 trap 1 | Guard must be inert outside a workflow | **Adopted** (spec A1, E9). |
| Advisor D1 trap 2 | Name the agent through a constructor argument | **Not needed**: `ctx.agent.name` is available (probe). |
| Advisor D1 trap 3 | Boot-time check that every durable agent carries the guard | **Adopted** (plan D3). |
| Advisor D1 trap 4 | `_verify_durability` may pin the capability list | **Checked**: it verifies the durability instance only (`agents/loader.py:447-495`). Two existing tests pin the list length at 2; they are updated (plan D2). |
| Advisor D2 | Sum of three pydantic dumps | **Adopted**; exact to the byte (R3). |
| Advisor D3 | Failure passes through unchanged | **Adopted**; confirmed by probe (R2, R6). |
| Advisor D4 | No patch marker | **Modified**: conditional marker (R5). |
| Advisor D5 | Dedicated dev server; 1 MiB; aggregate limit matters | **Adopted**; measured (R1, R4). |
| Advisor D6 | Tool-call inputs left to the inventory | **Adopted** (R7 row 14 and the spec assumption). |
| Skeptic 1 | Diff `stat` uncapped; raw-string diff bypass | **Adopted** as inventory rows 5 and 9 (spec A4). The raw-string branch of `_get_patch` has no production caller: all four pass the `get_task_diff` dict. Fixing either is out of scope (FR-012). |
| Skeptic 2 | FR-002 "unachievable"; research agent runs in an activity | **Partly adopted**: wording corrected (spec A1). Not a blocker: the guard is attached to all 16 and acts wherever a request is workflow-scheduled. The "interceptor" alternative is rejected in R2. |
| Skeptic 3 | `devops_planner` has no call site | **Confirmed** (R7 row 13). No action. |
| Skeptic 4 | Deep review and handoff leave no record | **Confirmed** (spec A2). Reported at GATE 2. Fixing the records is out of scope. |
| Skeptic 5 | Replay needs a patch marker; serialization must be canonical | **Adopted** as the conditional marker (R5). Determinism confirmed by probe; pydantic's JSON output follows field and insertion order, not hash order. |
| Skeptic 6 | Measure serialized bytes, not prompt characters | **Adopted** (R3). |
| Skeptic 7 | N3 is false for 1,000,000-token models | **Adopted** (spec A3; R4 trade). |
| Skeptic 8 | Guard-only leaves large inputs unrunnable, and a mid-call failure discards finished turns | **Acknowledged** as accepted consequences of the Q1 ruling; listed in the plan's residuals. |
| Skeptic 9a | `code/step.py` line ceiling | **No conflict**: the plan does not edit it (991 of 1000). |
| Skeptic 9b | FR-008 could disprove the premise after GATE 1 | **Closed**: R1 confirms the hang. |

## Residuals carried to GATE 2

1. **Aggregate overflow** (R1 finding 4, spec A5): parallel proposer calls whose inputs total over 4 MiB in one workflow task still terminate the run. Each would have to be large; the guard caps each at 1 MiB, so it takes four or more near-limit siblings. Candidate inbox task.
2. **Silent absorption** (spec A2): an oversized deep-review or handoff prompt leaves only a worker-log warning.
3. **Large-window models** (spec A3, R4): prompts between 1 MiB and 2 MiB are refused even for a model that could serve them.
4. **Mid-call failure**: a guard failure on a later request discards the earlier requests' work and spend for that call.
5. **Unmeasured path**: suspended-response continuation (R2).
6. **Follow-up candidates from the inventory**: cap `stat` with a marker; summarise the merge verdict's task dump; N1 (silent patch cut, already filed by the orchestrator).
