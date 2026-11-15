# Research — round 023a (DAPER: plans, gated, never acts)

`S/` = `src/sdlc/`. Every decision cites the code it rests on. Inputs: `consults/advisor.md`, `consults/skeptic.md`, plus the planner's own reads.

## R1 — Loop shape: one long-lived `MaintenanceWorkflow` per project; the schedule asset starts a tiny kicker

- **Decision.** `MaintenanceWorkflow(GateHost)` runs with id `maint-<project>`. It holds no timer of its own: it waits on `wait_condition(lambda: self._nudged or self._disabling)`. The E-14 schedule asset starts `MaintenanceKickWorkflow(project)`. That kicker sends the `nudge` signal through `workflow.get_external_workflow_handle("maint-<project>")` and finishes. If the target does not exist, it finishes `not-enabled:<project>`, with no retry. The CLI `nudge` signals the same id directly.
- **Rationale.**
  - Incidents and pending gates outlive a cycle. Temporal is the single source of truth (ADR-8), and a per-cycle workflow would need a new incident store (advisor §1).
  - Gates need one stable owner id for inbox and CLI (`workflows/deployment.py:5-7`).
  - A workflow signalling an external workflow needs no client inside an activity. This avoids the advisor's open point: the only client today is the worker's, `worker.py:275`.
  - Schedules can only start workflows (`workflows/reflect.py:1-8`), the same reason `ReflectWorkflow` exists.
- **Alternatives considered.**
  - Per-cycle schedule-started workflow: needs an incident store. Rejected.
  - A signal-with-start activity holding a client: works, but adds client injection into activities. Rejected as unnecessary, because enablement already starts the loop.
  - An internal cron timer: loses the dry-run diff FR-003 asks for. Rejected.

## R2 — Coalescing (FR-005)

- **Decision.** One `bool _nudged`.
  - The `nudge` handler sets it.
  - A cycle clears it at its start.
  - Nudges during a cycle set it again, so exactly one follow-up runs.
- **Rationale.** One workflow runs one cycle at a time by construction (advisor §1).
- **Alternative considered.** A queue or counter. Rejected: it over-counts.

## R3 — Gates do not block cycles

- **Decision.** Each repair-plan gate and each detect-escalation gate runs in its own workflow coroutine, started by the cycle and tracked in `self._gate_tasks`. A cycle completes once its gates are opened, not once they are decided.
  - Every coroutine records its outcome on its incident.
  - Gate names are per incident (`repair:<n>`, `detect_escalation:<signal>:<k>`), so `gate_key` never collides.
- **Rationale.** A HARD gate waits up to `gate_timeout_hours` (48h default). A blocking cycle would stall detection for days. This is the same hazard skeptic (e)2 found for children, one layer up.
- **Alternative considered.** Sequential gate waits inside the cycle. Rejected.

## R4 — History bound (FR-013): first `continue_as_new` in `src/`

- **Decision.**
  - **When:** only at the idle boundary (no cycle running, `_gate_tasks` all done, no signal pending), and when `workflow.info().is_continue_as_new_suggested()` or `cycles_this_history >= cfg.max_cycles_per_history` (default 50; tests set 2).
  - **Carried state:** `MaintenanceState` (config, baseline, the previous filtered triage, incidents, counters, `_nudged`). It is the workflow input on restart, and an enable-time input is a `MaintenanceState` with no baseline.
  - **Signals:** drain pending signal handlers (`workflow.all_handlers_finished()`) before continuing.
- **Rationale.** ARCHITECTURE §7 names it. `grep continue_as_new S/` is empty, so a state round-trip test plus a replay test are required (advisor §1).
- **Alternative considered.** No bound. Rejected: history grows without limit (FR-013).

## R5 — Detect reuses `TriageWorkflow` unchanged, as a child

- **Decision.**
  - **Child:** `execute_child_workflow(TriageWorkflow.run, TriageInput(repo_dir, commit=<default_branch>, build_probe, advisory_source, gates=triage_gates(..., gating=False)))`, id `maint-<project>-c<cycle>-triage`.
  - **Pinning:** the child pins the commit (`triage_resolve_commit`) and degrades per signal (`run_or_degrade`).
  - **Filter:** the loop keeps only the signals in `DETECT_SIGNALS = {secrets.SIGNAL_ID, build_probe.SIGNAL_ID, dependencies.SIGNAL_ID}` (`S/triage/registry.py:41-52`). The other four triage signals run but are ignored in 023a.
- **Rationale.** Zero new detectors (advisor §5). `triage_gates(gating=False)` is the TidyUp precedent for a triage that must not open a readiness gate (`workflows/tidyup.py:150-162`). Filtering, rather than a new "subset" input on `TriageInput`, keeps TriageWorkflow's wire and its replay coverage untouched.
- **Cost accepted.** The extra signals add only seconds; the probe dominates (40 min, `workflows/triage.py:70-72`).
- **Alternative considered.** A `signals:` subset on `TriageInput`. Rejected: it changes another workflow's wire for a few seconds of savings.
- **Lift `triage_gates`.** It moves (unchanged) into a shared module `S/workflows/triage_child.py`, re-exported from `tidyup.py`, so maintenance does not import across workflows (advisor §6).

## R6 — Baseline and "new" (FR-007)

- **Decision.**
  - **Cycle 1** stores `baseline = {identity}` over the filtered triage, plus each signal's version and the filtered `RepoTriage` itself as `prev`. It opens nothing.
  - **Cycle k > 1** runs `compute_delta(prev, curr)` (`S/triage/delta.py:93`).
    - `NEW` ∧ identity ∉ baseline ∧ identity ∉ open incidents → open an incident.
    - `PERSISTED` on an open incident → `last_seen` / `seen_count` + 1.
    - `RESOLVED` on an open incident, with the signal collected on both sides → `resolved_externally`.
    - `UNVERIFIABLE` → no transition.
  - **Signal version change:** the per-signal baseline is re-recorded and the event logged (edge case).
  - Then `prev = curr`.
- **Rationale.** `compute_delta` already refuses to read absence as resolution (`delta.py:1-16`). Both consults flagged cycle 1 opening an incident per legacy finding.
- **Payload note.** `prev` holds three signals' findings, including secrets evidence. That evidence already crosses history in every triage run today (NFR-9 / FR-702 debt, not new). A guard caps `prev`'s findings at `MAX_PREV_FINDINGS = 2000`. Over the cap, the cycle records `detect_truncated` and opens no incidents, so it never guesses.

## R7 — Incident identity (FR-008)

- **Decision.**
  - **Findings:** the incident key is `finding_identity(f)` (`S/triage/models.py:194`), unchanged.
  - **Not-collected escalations:** synthetic key `"<signal>:not_collected::"`.
  - **Uniqueness:** `MaintenanceState` carries a validator rejecting duplicate keys among non-terminal incidents, modelled on `SignalResult`'s uniqueness validator.
- **Rationale.** It is the identity `compute_delta` matches on, and it ignores `line` on purpose (advisor §3).
- **Known limit.** The build probe gives one incident per rule.
- **Alternative considered.** A new (signal kind, scope) identity. Rejected: it would diverge from the identity `compute_delta` matches on (advisor §3).

## R8 — Proposer: one `maintainer` role, one call per incident; code floors its confidence

- **Decision.**
  - **Role:** a new optional registry role `agents/maintainer/` (`kind: proposer`, same model as the other proposers), wired exactly as `risk` is (`S/agents/roles.py:132-133,226,310,338-339`).
  - **Output:** `output_type=RepairProposal`.
  - **Call shape:** called in-workflow as `t_maintainer.run(render_repair_prompt(incident, finding, triage_context), **run_kwargs)`, inside the `_judge` degrade shape of `AssessmentWorkflow` (`workflows/assessment.py:657-700`). `run_kwargs` forwards `retries={"output": n}` only when `OUTPUT_RETRIES.get("maintainer", 1) != 1`, because a direct proposer call bypasses the RoleHost seam (FR-202 VR-3a, merged 2026-11-14 in `80692c1b`; see `assessment.py:685-695`). Any exception becomes `no plan — analysis failed`, retried next cycle, with at most 2 attempts per incident.
  - **Confidence:** `effective = min(proposal.self_confidence, confidence_floor(...))`, in pure `S/maintenance/confidence.py`.
- **Floor table (pure, documented, unit-tested):**

  | Fix class | Ceiling | Then subtract | Floored at |
  |---|---|---|---|
  | `MECHANICAL` | 0.95 | 0.15 if not reproduced on a second consecutive detect, 0.2 per reopen (0 in 023a), 0.05 per action beyond 1 | 0 |
  | `JUDGEMENT` | 0.6 | same | 0 |
  | `STRUCTURAL` | 0.0 | — | 0 |

  `FixClass` comes from `S/triage/models.py:20-27`.
- **Consequence (stated in the spec).** At the default threshold 0.8, only mechanical findings reproduced on two consecutive cycles clear policy. Advisory and secret plans (both `JUDGEMENT`: `triage/signals/dependencies.py:372`, `signals/secrets.py:35-36`) are human-gated by construction.
- **Not a judge.** The maintainer judges no one's output, so ADR-6's judge set is unchanged. It is registered in `ALL_TEMPORAL_AGENTS` so the worker gets its activities.
- **Precedent cost (commit `73a809c0`, the product role).** Adding a role touches `tests/test_agents_registry.py`, `tests/test_agent_folders.py`, `tests/docs_site/test_agent_registry.py`, `tests/test_benchmark_provenance.py` and `tests/conftest.py`. **No replay golden changed** in that commit.
- **Alternatives considered.**
  - Two calls (Analyze, Plan): doubles spend for no independence (advisor §5). Rejected.
  - Trusting the self-rating: the weakest signal in the system. Rejected.

## R9 — The repair-plan gate is built in code (FR-011/012)

- **Decision.**
  - `S/maintenance/gate.py::repair_gate_settings(cfg) -> GateSettings` returns `gates={"repair:*" → GateConfig(policy=SOFT, threshold=cfg.threshold, on_timeout=REJECT)}`, with `gate_timeout_hours=cfg.gate_timeout_hours`.
  - Because `_gate` looks names up exactly, the function is called per incident name. Detect-escalation gates are `HARD`, `on_timeout=REJECT`.
  - `MaintenanceConfig` exposes **only** `threshold: float` (`Field(ge=0.5, le=1.0)`) and `gate_timeout_hours: int` (`ge=1, le=168`). There is no `gates` field to misconfigure.
  - Any attempt to pass gate policy (CLI flags `--gate-policy` / `--on-timeout`) is refused by the CLI with a named-field message, because those fields do not exist on the model (`extra="forbid"`).
- **Decider and auto-approve.**
  - A `_gate` timeout returns `decided_by="timeout"`, `outcome=REJECT` (`workflows/gates.py:228-239`) → incident `timed_out`.
  - The SOFT auto-decision is `GateDecision(outcome=APPROVE, decided_by="policy")`, passed only when `effective > threshold` (corrected 2026-11-15 per 023a verification T025; code is strict — an at-threshold plan stays human-gated).
  - Approved by anyone → `approved_not_executed`, with the decider recorded.
- **Rationale.** `GateConfig` allows `OFF` and `on_timeout=APPROVE` (`core/models.py:57-68`, `gates.py:206-209,233-237`). The only way "no configuration can open it" is true is that no configuration reaches it (advisor §7.3, skeptic (c)).
- **Alternative considered.** A flag on `GateHost._gate`. Rejected: it edits the shared gate used by every workflow.

## R10 — Schedules package generalisation (FR-003)

- **Decision.**
  - **Actions:** `ScheduleAction` becomes a discriminated union on `workflow`: `ReflectAction` (`banks`, `backend`, `base_url`, unchanged) | `MaintenanceKickAction` (`project: str`). `KNOWN_SCHEDULE_WORKFLOWS` gains `"MaintenanceKickWorkflow"`.
  - **Conversion:** `to_temporal` / `from_temporal` (`schedules/apply.py:40-90`) dispatch per action type. `from_temporal` validates `args[0]` against the input model of the action's workflow.
  - **Cadence limit:** `MaintenanceKickAction`'s asset validator requires the cron minute field to be a single integer (≥ hourly cadence) — the "sub-hourly refused" rule.
  - **Ids:** workflow id stays `sched-<id>`.
- **Back-compat.** The existing `schedules/nightly-reflect.yaml` must load, diff and apply byte-identically. A test pins `to_temporal(reflect_asset)` equal to its pre-change value, and existing schedules tests stay green.
- **Rationale.** The package is Reflect-only in four places (advisor §7.4).
- **Alternative considered.** A second, maintenance-only schedules package. Rejected: duplicates the apply/diff machinery.

## R11 — Inbox and decisions

- **Decision.**
  - **Inbox:** `S/channels/inbox.py:116` lists `"GraphWorkflow", "CrewTaskWorkflow"` and gains `"MaintenanceWorkflow"`. GateHost supplies `pending_decisions`.
  - **Dashboard:** the fleet poller (`dashboard/fleet.py`) stays Graph-only (it needs `run_state`). Out of scope.
  - **Decisions:** the CLI decision verbs resolve a pending item by run id and send `submit_gate_decision` (`cli.py:859-870`, `channels/transport.py`). T-task R11 verifies that `sdlc approve maint-<p> …` works unchanged against a GateHost-only workflow. **If it does not**, the fallback is a `sdlc maintain decide` verb over the same transport.
- **Rationale.** FR-015 asks for the existing inbox. CrewTaskWorkflow is the precedent for a non-Graph GateHost in it.
- **Alternative considered.** Adding maintenance to the dashboard fleet poller. Rejected: the poller needs `run_state`, which the loop does not expose.

## R12 — CLI placement

- **Decision.** The new verbs live in `S/maintenance/cli.py::register_maintain_subparsers(sub)` and `run_maintain(args, client)`, wired into `cli.py` with ≤ 10 lines. The precedent is `benchmarks.cli.register_benchmark_subparsers` (`cli.py:357-359`).
- **Rationale.** `cli.py` is 908 lines against the 1000-line ceiling.
- **Alternative considered.** Adding the verbs inline in `cli.py`. Rejected: it would push the file toward the ceiling.

## R13 — Replay and testing

- **Decision.**
  - **New workflow:** maintenance gets `pytest -m temporal` e2e tests with a fake maintainer (the `TestModel` stubs in `tests/fakes/`) and a fixture git repo. Each test also replays its own captured history with `Replayer`, in-test with no stored fixture.
  - **Corpus:** this round adds no writer to `tests/replay/histories/`, so `tests/replay/AGENTS.md` rule 1 is untouched.
  - **Existing goldens:** must replay unchanged, proving GraphWorkflow/Triage/TidyUp command sequences did not move. That includes the `triage_gates` lift, which is an import move with no behaviour change.
- **Rationale.** FR-017 / SC-006.
- **Alternative considered.** A third capture-test writer for maintenance histories. Rejected: in-test replay covers determinism without touching the corpus rules.

## R14 — NFR-9 acknowledgement (FR-002)

- **Decision.** `MaintenanceConfig.build_probe: bool`. When true, `ack_unattended_build_probe: bool` must also be true (validator), and the CLI `enable` requires `--ack-unattended-build-probe` or `--no-build-probe`. The acknowledgement is recorded in state and shown by `maintain incidents --state`.
- **Rationale.** The probe executes the repo's code with network access, as the worker user (`workflows/triage.py:7-9`). An unattended schedule widens the exposure (advisor §7.5).
- **Alternative considered.** Probe always on with no acknowledgement. Rejected: it widens the exposure silently.

## R15 — Disable

- **Decision.** The `disable` signal sets `_disabling`.
  - **Mid-cycle:** the loop finishes the running cycle.
  - **Pending gates:** each open gate coroutine is cancelled. Its incident is recorded as `withdrawn` (reason `maintenance disabled`) with **no** `GateDecision`, because `GateDecision.decided_by` is `Literal["human","policy","timeout"]` (`core/models.py:156`) and a disable is none of those. No approval is ever synthesised.
  - **Terminal:** the workflow returns `disabled:<project>`.
  - **Re-enable:** starts fresh, which is the 023a way to re-baseline.
- **Alternative considered.** Leaving gates open after disable. Rejected: orphaned inbox items.
