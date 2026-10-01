# Research: TemporalAgent -> TemporalDurability migration

Feature: `003-temporal-durability-migration` | Date: 2026-09-30 | Base: main 203e7dd

Method: read the installed pydantic-ai 2.51 source (`.venv`, read-only), read the Kroker call sites, ran a **throwaway spike in the dev container** (`kroker-dev`, Temporal dev server from the image; script outside the repo, not committed), consulted advisor (`.workspace/tmp/advisor-003-1.md`, `advisor-003-2.md`) and skeptic (`skeptic-003-1.md`). Every skeptic claim was checked against source; results below. Nothing here is a decision by the user; the FR-019 default (heartbeat to none) is the user's GATE 1 ruling.

## R1. Attachment and registration API (verified)

- Durability is a **capability** attached at construction: `Agent(..., capabilities=[TemporalDurability(...)])`. The agent binds a **copy** of the capability, so the instance you constructed does *not* expose the activities. The handle is `TemporalDurability.from_agent(agent)` (returns `None` if absent, raises `UserError` if two are attached). **Spike bug that proved this:** using the constructed instance's `temporal_activities` gave `[]` and the model activity was scheduled but never picked up (workflow hung).
- `PydanticAIPlugin` (already used) accepts agents in `__pydantic_ai_agents__` on a workflow class, and `AgentPlugin` registers an agent's activities on a worker; both go through `from_agent`. Kroker's worker today collects `ta.temporal_activities` by hand (`worker.py:131`).
- The agent `name` and toolset `id` flow into activity names identically to `TemporalAgent`.
- `run_context_type` defaults are the same as the wrapper's.

**Decision D1:** loader takes a **zero-argument factory** returning a fresh `TemporalDurability` per role and passes it to each `build()` as keyword-only `capabilities`; assets pass it through to `Agent(capabilities=[*capabilities, *own])`. Config stays central in `roles.py` (advisor-003-2). Alternatives rejected: each asset builds its own `TemporalDurability` (import cycle `roles`<->`loader`; lets a role pick an unbounded retry policy, the e2e-proposer-hang regression); loader wrapping after build (impossible: capability is construction-time).

## R2. Activity names: registered vs scheduled (verified by spike)

Spike agent `spike_agent` (plain, no tools), both mechanisms:

| | TemporalAgent (old) | TemporalDurability (new) |
|---|---|---|
| model request | `agent__X__model_request` | `agent__X__model_request` (identical) |
| streamed request | `..__model_request_stream` | `..__model_request_stream` |
| cancel suspended | `..__model_cancel_suspended_response` | same name |
| tool | `..__toolset__<agent>__call_tool` | same name |
| event stream handler | `..__event_stream_handler` registered | **not registered** (no handler configured) |
| compact | none | `..__model_compact_messages` **added** |
| args validation | none | `..__toolset__<agent>__validate_args` **added** (registered for every agent) |

Scheduled command for the model request under both: same activity type, same start-to-close (600 s), same `maximum_attempts`, same `non_retryable_error_types` list (`UserError, PydanticUserError, UnexpectedModelBehavior, FallbackExceptionGroup, PayloadsTooLarge, PayloadSizeError`). Only `heartbeat_timeout` differs (R3).

The captured histories only ever schedule `..__model_request` (the other names in `tests/replay/histories/*` occur inside a "not registered on this worker" error text). So the added/dropped **registered** names cannot break replay of any recorded history; they matter only for FR-007 exactly-once registration and for any future workflow that would schedule them.

**Decision D2:** the fixture asserts the scheduled set for each agent is *exactly equal* before/after (FR-005.3) and that every name a history can schedule is *registered*; the deliberate registered-set differences (`-event_stream_handler`, `+model_compact_messages`, `+validate_args`) are listed in the fixture as expected.

## R3. FR-019 heartbeat (verified by source and by spike)

- `_durability.py:83, 278-286`: `TemporalDurability` sets `heartbeat_timeout=30s` on **model** activities unless `heartbeat_timeout` appears in `activity_config` or `model_activity_config`.
- Spike, scheduled command `heartbeat_timeout`: old = 0; new default = **30 s**; new with `model_activity_config={"heartbeat_timeout": None}` = **0**; with `timedelta(0)` = **0**. Both overrides make the command match the old one; the same `retry_policy`/timeout attributes.
- Side effect that cannot be switched off: every durability activity runs a background `heartbeating()` task (5 s cadence when no timeout is configured, "inert but harmless"). `TemporalAgent`'s **tool** activity also used it; its **model** activity did not. With no `heartbeat_timeout` on the command the heartbeats do not affect the server, but they make workflow *cancellation* reach a model activity at the next heartbeat (previously only at completion). Recorded as a **ruled-candidate difference** (benign; not attempt- or spend-affecting) for the orchestrator.

**Decision D3 (per GATE 1):** `TemporalDurability(activity_config=AGENT_ACTIVITY_CONFIG, model_activity_config={"heartbeat_timeout": None})` for the shared config; the fan-out config gets the same override.

## R4. FR-020 outcomes

| # | Hypothesis | Outcome | Evidence | Plan task |
|---|---|---|---|---|
| a | Worker no longer re-prepares messages against the concrete model | **UNRESOLVED by reading.** Old `_reprepare_messages` (`_model.py:477`) runs only when `params.model_id` is a runtime string outside the registry; the durability path (`_base.py:1515`) has no such step. Kroker builds agents from model-id strings and never passes `model=` at run time, so what `model_id` the old wrapper sent (None vs the string) decides whether the step ran. | source read | **T-A3 / T-D5**: differential capture of the provider-level request messages (patch the concrete `request` method, record args) on main before, on the branch after, over a multi-turn tool run (architect). Recorded outcome required. |
| b | Kroker triggers the `validate_args` activity | **Verified-neutral (with test).** No `args_validator`, `DynamicToolset`, MCP toolset or `event_stream_handler` anywhere in `src/` or `agents/` (search: 0 hits). The activity exists (registered) but is scheduled only for those paths. | grep | **T-D3**: architect history replay + a test asserting no shipped agent schedules it. |
| c | `model_cancel_suspended_response` arity differs | **Verified difference, not reachable by Kroker.** Old: one argument `_CancelParams(response, model_id, serialized_run_context, deps)` (`_model.py:53`); new: two arguments `(_CancelParams(no deps), deps)` (`_transports.py:223, 336`). Scheduled only when a suspended (deferred/streamed) response is cancelled; Kroker runs non-streaming `agent.run` with no event stream handler. No captured history contains it. | source read | **T-D4**: test proving no shipped-agent path schedules it; **residual risk reported to orchestrator**. Escalate if a shipped path can. |
| d | Model-id strings resolved inside the workflow sandbox break or stall | **Partly confirmed, real hazard.** No sandbox violation: the run completes (spike). But under the new path the **first workflow task trips the 2 s deadlock detector** in a cold dev-container worker (`TMPRL1101: workflow didn't yield within 2 second(s)`, stack in pydantic schema generation); Temporal retries the workflow task and the run then completes. The old path did not trip it (same spike, same container). With `debug_mode` (deadlock detection off) all runs succeed. | spike (old vs new, with/without debug mode) | **T-D6**: measure first-task duration old vs new with the real registry in the temporal tier; if it reproduces, mitigate (import/warm-up outside the sandbox, passthrough) or **escalate**. |
| e | Strict tool-result decoding rejects recorded results | **Verified-neutral.** `TemporalAgent`'s function toolset also calls the strict `unwrap_tool_call_result` on `CallToolResult` (`_function_toolset.py:~106`); the same wrapper types. `tool_call_result_upgrade_lenient=False` is the same behaviour. | source read | **T-D3**: architect history (tool call) replays. |

Nothing in (a)-(e) is known to break replay of an existing history; (d) is a runtime risk and (a) is unproven. If T-A3/T-D5 shows a payload difference or T-D6 shows repeated workflow-task failures, the plan escalates to the orchestrator instead of ruling.

## R5. Corrections to earlier inputs (verified in code)

- **The research agent's activities are never scheduled by any workflow.** `t_research.run` is called only from inside the architect's `research` tool activity (`stages/research/toolset.py:48`) and the research stage runs the plain agent inside activities (`stage.py:206`). Inside an activity `in_durable_context` is false and the run is a transparent plain run. So no history needs the research agent's scheduled names, and advisor-003-1's "capture a research history" is downgraded to **name-level + the in-activity path test** (FR-011). The **architect** history is still required: the workflow schedules `agent__architect_agent__toolset__<agent>__call_tool` for its `research` tool.
- **`exa_wrapper.py`** sets `toolset._id = "exa_search"` because the old wrapper refused an id-less toolset; the capability path keeps the same need (stable id). No change beyond comments.
- **`ALL_TEMPORAL_AGENTS`** is asserted by tests; keep the name and list-of-agents shape.

## R6. Existing proof infrastructure

- `tests/replay/test_feature_replay.py`: 16 `FeatureWorkflow` histories through `Replayer(PydanticAIPlugin)`; guards SG-2 (never re-record).
- `tests/replay/test_graph_golden.py`: `GraphWorkflow` golden traces, sandboxed and unsandboxed; SG-3.
- D8 pins: `tests/graph_workflow/test_graph_dispatch_chaos.py:327` and `test_feature_replay.py::test_replayer_matches_the_production_worker_effect`.
- The histories were recorded with `tests/fakes/fake_agents.py` (real agent names, `TestModel`).
- All of `tests/` that use the wrapper (13 files): `fake_agents.py`, `test_research_{budget_store,e2e,spike}.py`, `test_assessment_workflow_e2e*.py`, `test_deployment_workflow.py`, `test_factory_purity.py`, `test_memory_wiring.py`, `test_module_imports.py`, `test_operator_layering.py`, `test_promptfoo_provider.py`, `test_spike_agent_stub.py`.

## R7. Environment

Dev container per the run-env directive: `docker run --rm -v "D:\own\Kroker:/app" -v kroker-verify-venv:/app/.venv -w /app kroker-dev sh -c "uv sync --frozen --extra dev --extra logfire && uv run --no-sync pytest ..."`. Mount the primary checkout (real `.git`), not a worktree (worktree pointer trap). Read `.workspace/tasks/2026-09-09-temporal-tier-hangs-on-windows.md` (host hazard: never run the temporal tier on the host). Never chain two pytest runs in one Bash call. The temporal tier is opt-in (`-m temporal`), excluded from the default fast run.

## R8. Baseline (T002, recorded 2026-10-01 on main 203e7dd, unmodified tree)

Commands: dev container, one pytest per file, in-container `timeout <N>` watchdog per
file (`.venv/bin/pytest -m temporal <file> --tb=no -p no:warnings`); fast tier one shot
(`pytest --tb=no -p no:warnings --durations=15`).

| Tier | Result |
|---|---|
| temporal (35 files, chunked) | **160 passed, 17 skipped, 1 xfailed, 0 failed** (matches the expected 160) |
| temporal (single full-process run on this box) | flakes: `test_graph_golden[budget_arch_reject-{sandboxed,unsandboxed}]` (SG-3 projection diff: actual `publish_artifact_version` where golden has `timer` + `apply_session_retention`) and `tests/deploy/test_deploy_workflow_paths.py::test_6_disabled_deploy_starts_no_child`; both pass standalone |
| tests/replay as one directory run | replay tests flake under directory-level load on this box, any member can fail and each PASSES standalone: `architect_research_tool` (orchestrator run), `delta_failed` + `partial_awaiting_architecture` (executor run; clean rerun 163 passed / 0 failed). Same contention-flake family as `research_greenfield`; T042 comparisons must use chunked/standalone shapes |
| fast | **2 failed, 5327 passed, 11 skipped, 222 deselected** in 17m19s |

Fast-tier failures, both pre-existing and not migration-related:

1. `test_feature_replay.py::test_feature_workflow_replays_captured_history[research_greenfield]` — full-run only; the whole file is 17 passed standalone. Contention flake on this workstation.
2. `test_promptfoo_provider.py::test_provider_imports_fast_enough_for_the_promptfoo_worker` — asserts provider import < 8.0 s; this box's Windows bind-mount container measures ~10.4 s. Environment performance budget; fails standalone here, passes in CI's native Linux.

Host-hazard notes added during this run:

- **Do not add `-q` to pytest commands**: repo `addopts` already include `-q`; a second `-q`
  (`-qq`, verbosity −2) makes pytest omit the final counts line — it looks exactly like a
  torn-down hang.
- **A killed `docker run` client leaves its container running** (`--rm` fires only on
  container exit). One leftover tier container spun at ~44% CPU and starved later runs.
  Mitigation: wrap pytest in the container's own `timeout <N>` so pytest always exits and
  the container always terminates; check `docker ps --filter ancestor=kroker-dev` after any
  tool-side timeout.
- PowerShell strips inner double quotes from `sh -c` arguments; avoid double quotes inside
  the command string (single-quote the outer PowerShell string, no `"..."` inside).
- Full-suite single-process temporal runs on this workstation flake; per-file chunked runs
  are the trustworthy shape. Tier-level claims in T014/T023/T026/T042 should use chunked
  runs or narrow selections.
