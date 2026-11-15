# Plan Stage

The plan stage (Stage 3 / spec A §3.3 / spec A §5) generates a schema-validated `ImplementationPlan` from architecture specifications and clarified requirements. It runs the planner proposer role with memoization caching, records benchmark telemetry and memory summaries, and handles human gate approval through the revisable stage review loop.

The orchestrator (`GraphWorkflow`, since 020 deleted the legacy workflow) composes the plan stage across the `plan` and `gate.plan` graph nodes; the slice itself exports `prepare`, `produce` and `finish`.

## Requirements

### PLAN-1.1
The plan stage slice exports `prompt_digest` and `ACTIVITIES = []` (the legacy-era `step` composite was deleted in 020; `step` remains only as the submodule holding the slice functions). The slice functions (`prepare`, `produce`, `finish`) each accept `ctx: StageContext` as their first argument and receive configuration, architecture spec, requirements, idea brief, and planner agents as keyword arguments, never the workflow instance. [FR-301, spec A §3.3, 020 FR-006]

### PLAN-1.2
`produce` returns an `ImplementationPlan`; the gate decision belongs to the graph's `gate.plan` wiring, and the orchestrator handles board publishing, task synchronization, task graph validation, and gate branching without exposing workflow handlers or state across the slice boundary. [FR-302, spec A §3.4, 020 FR-006]

### PLAN-1.3
The plan stage runs the planner agent with memoization and revisable review loops (the revisable loop is the `gate.plan` node's revise wiring), records benchmark telemetry and memory summary, and retains the task plan summary in the project memory bank. The benchmark record carries tasks_total reflecting the count of dev tasks planned (len(plan.tasks)). [FR-303, E-84, E-85, 020 FR-006]

### PLAN-1.4
The stage is composed of `prepare` (start time, role usage, memory recall, prompt salt), `produce` (one planner round keyed by the memo input of PLAN-1.7) and `finish` (judge, benchmark record, memory retain). The graph's `plan` node calls `prepare` once and `produce` per round; the `gate.plan` node carries the revisable loop. [E-74 spec §4.3, §6.1, 020 FR-006]

### PLAN-1.5
The memo key's recall slot is the run's memory watermark, extended with the stage's recall snapshot hash when memory is on. [FR-402, 021]

### PLAN-1.6
Each `DevTask` carries `covers` — the FR ids from the requirements artifact the task claims to implement (default empty; board rendering omits it deliberately, `board/render.py:_OMITTED`). When the run carries a `requirements_doc` input with stories, the planner prompt carries `render_requirements(requirements_doc)` plus the one instruction line naming the covers field, inserted after the constitution block; an artifact without stories renders no block and no instruction line, so the flag-off path stays byte-identical (FR-010). [FR-205, FR-113, FR-010]

### PLAN-1.7
`produce`'s memo input is the concatenation of the architecture's JSON, the constitution digest (FR-112), the requirements artifact's digest (FR-205 — `""` when there is no `requirements_doc`) and the guidance, each digest joined under the omitted-while-`""` rule so a run that never saw a constitution or a requirements draft keys byte-identically to a run without them (FR-010). [FR-112, FR-205, FR-010]

### PLAN-1.8
Task-graph validation is owned by the orchestrator's `plan_check` node and enforced as an ordered halt family from the shared `sdlc.validators` library (the slice's own `validation.py` was deleted in FR-205 and is not re-created): `ids_unique`, then `deps_resolve`, then `dag_acyclic`, then `covers_all` — run only when a `requirements_doc` input with stories rides the activation (vacuous otherwise) — then `task_size` under `cfg.plan`'s `PlanConfig` limits (`max_files_hint=24`, `max_criteria=12`; the first breach names the offending task). The order is part of the contract: duplicate ids are named before the graph checks because the downstream `{t.id: t}` collapse would silently drop tasks and hide every later fault. Every failure rides the halt port verbatim as `failed:plan-validation:<reason>`; the board task sync runs only after every check passes. [FR-205]

## Failure modes

- **Invalid task graph**: The plan_check halt family (PLAN-1.8) — duplicate ids, unresolved dependencies, cycles, uncovered requirements, oversized tasks — fails before scheduling work as `failed:plan-validation:<reason>`.
- **Planner prompt failure**: Model fails schema validation or structured output; retried with exponential backoff.
- **Gate rejection**: Human reviewer rejects implementation plan; workflow aborts or branches cleanly per gate decision.
