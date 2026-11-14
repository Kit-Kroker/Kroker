# SKEPTIC Consult — Round 023 (DAPER Maintenance Loop)

**Scope:** Pressure-testing the LOCKED decisions, scope assumptions, and sizing in `.specify/specs/023-daper-maintenance-loop/spec.md` against `ARCHITECTURE.md` §7, `PRD.md:284-290`, and the actual codebase.

---

## (a) Four-signal Detect set (FR-005)

**Targets probed:** build broken, new critical/high dependency advisory, new secret, deploy liveness.

1. **No `project_key -> repo_dir` mapping exists.** `PipelineConfig.project_key: str = "default"` (`src/sdlc/core/models.py:362`) and `src/sdlc/board/schema.py:81` store a string identifier only, not a repository path, default branch, or deploy config. Meanwhile `triage_resolve_commit` and `triage_build_probe` (`src/sdlc/triage/activities.py:74,442`) run `git rev-parse` and `git clone --local` against a local `repo_dir`. Without a registered project manifest (`project_key -> {repo_dir, base_branch, advisory_source, deploy}`), **none** of the four signals can locate a target.
2. **Deploy liveness (`smoke_check`) is unbuildable from `project_key` alone and useless in a PoC with no deployed project.** `smoke_check` (`src/sdlc/stages/deploy/activities.py:180-235`) requires `SmokeCheckInput(plan: DeployPlan, cfg: DeployConfig, repo_path: str, endpoint: str)`, and `ComposeAdapter.DEFAULT_BASE_URL` defaults to `"http://localhost:8000"` (`src/sdlc/deploy/adapters.py:75`). `DeployPlan` is an ephemeral stage artifact of a `DeploymentWorkflow` run, not persisted per project. With no deployed client project, deploy liveness either cannot run or permanently emits `ERRORED` / `not_collected`.
3. **Advisory signal defaults to `not_collected`.** `TriageDependencyInput.advisory_source` defaults to `"none"` (`src/sdlc/triage/activities.py:213`, `src/sdlc/triage/advisories.py:61-73`). Unless maintenance explicitly enables `"osv"` (and declares outbound egress under FR-703), every cycle returns `not_collected` and triggers FR-005 / Edge Case 2's human escalation.
4. **"New" vs. pre-existing findings is unaddressed.** `triage_dependencies` and `triage_secrets` evaluate a single pinned `commit_sha` snapshot (`src/sdlc/triage/activities.py:217,417`). Without diffing against the prior cycle's `RepoTriage` (via `compute_delta`), cycle 1 treats every legacy finding as "new". Also note `src/sdlc/triage/signals/secrets.py:5-8,35-36` classifies leaked provider credentials as `FixClass.JUDGEMENT` (rotation is human; a PR deleting `.env` while the key is live is worse than an open finding), so "new secret" can never close via an automated PR.
5. **Missing signal:** **Open/stale repair PRs or stuck/quarantined child runs** — without tracking active repair PRs in Detect/Analyze, subsequent cycles on the unmerged default branch will re-detect the same fault.

**VERDICT: change**
**Concrete change:**
- Require an explicit per-project maintenance registration (`project_key -> repo_dir, default_branch, advisory_source="osv", optional deploy_plan/endpoint`).
- Make `deploy_liveness` strictly conditional on an explicit configured endpoint + `DeployPlan` (not merely "has a deploy plan" in repo history), so PoC/non-deployed projects do not endlessly `not_collected`-escalate.
- Define "new" explicitly as `compute_delta(prev_triage, curr_triage)` (with cycle 1 baseline seeding).

---

## (b) Rollback-only, always-human-gated ops actions (FR-011) vs. FR-502 / FR-503

1. **FR-502's risk classification becomes a constant.** If `rollback` is the sole allowed ops action (FR-011) and is unconditionally `human-required` (FR-009 + FR-011), `risk_class(action)` has a 1-element domain `{rollback}` and a 1-element codomain `{HUMAN_REQUIRED}`. That is a hardcoded gate, not risk classification.
2. **FR-503's confidence threshold is dead code for ops actions.** Because confidence can only add a gate and never remove a risk-class gate (FR-009), `rollback` is human-gated at `confidence = 1.0` and `confidence = 0.0` alike. Confidence only gates `code_fix` (which still faces the child run's own `merge` gate).
3. **`deploy_rollback` lacks `to_version`.** `deploy_rollback` (`src/sdlc/stages/deploy/activities.py:238-250`) takes `RollbackInput(plan, cfg, repo_path, to_version)`. `deploy_current_version` (`activities.py:90-107`) only reads the *currently* running (broken) version. `MaintenanceWorkflow` has no prior healthy `to_version` unless it persists `last_healthy_version` across cycles or reads it from prior `DeployReport` records.

**VERDICT: weaken**
**Concrete change:**
- Acknowledge in FR-011/FR-502 traceability that R023 implements a single-tier risk stub (`rollback -> HUMAN_REQUIRED`) pending restart/scale adapters (out of scope), rather than claiming multi-tier risk-classed ops execution is exercised.
- Specify where `to_version` and `DeployPlan` come from (e.g., persisted `last_healthy_version` on the project maintenance state; if absent, `rollback` is refused as unexecutable rather than guessed).

---

## (c) Timeout = inaction enforced so no config can override (FR-008) vs. `GateConfig.on_timeout`

**Conflict confirmed in `src/sdlc/workflows/gates.py` and `src/sdlc/core/models.py`.**
- `GateHost._gate()` (`src/sdlc/workflows/gates.py:200-241`) reads `gate_cfg = settings.gates.get(name, ...)` directly:
  - If `gate_cfg.policy == GatePolicy.OFF` (`gates.py:206-209`), `_gate` auto-approves immediately without waiting.
  - On timeout (`decided is None`, `gates.py:235-239`), `outcome = GateOutcome.APPROVE if gate_cfg.on_timeout is TimeoutAction.APPROVE else GateOutcome.REJECT`.
- `GateConfig` (`src/sdlc/core/models.py:57-68`) permits both `policy=GatePolicy.OFF` and `on_timeout=TimeoutAction.APPROVE`. Passing `GateSettings` through to `GateHost._gate()` therefore **violates** FR-008 ("no configuration may change that").
- Additionally, `TimeoutAction.HOLD` (`core/models.py:54`, used by `"merge"` at line 374) and `TimeoutAction.REJECT` (`core/models.py:66`) behave differently: `HOLD` never times out and never records `"timed out — no action taken"` (US-2 Scenario 2).

**VERDICT: change**
**Concrete change:**
- Add an explicit enforcement guard (either a `forbid_auto_approve: bool = False` / `allowed_timeout_actions` parameter on `GateHost._gate()`, or a Pydantic validator on `MaintenanceConfig.gates`) that rejects/clamps `GatePolicy.OFF` and `TimeoutAction.APPROVE` (and `TimeoutAction.HOLD` if US-2 requires a bounded timeout recording `"timed out — no action taken"`), forcing `TimeoutAction.REJECT` on repair gates.

---

## (d) "Only a clean re-detect closes an incident" (FR-012) given `open_pull_request` never merges

**This is a broken state machine.**
- As `src/sdlc/vcs/integration.py:126-129` explicitly documents: *"open_pull_request OPENS PRs; it does not merge them, so re-triaging the base branch would measure a tree containing none of the fixes."*
- `TidyUpWorkflow` solved this with `build_verification_branch` (`src/sdlc/workflows/tidyup.py:330-345`), which merges fix branches into a disposable local worktree (`sdlc/tidyup-verify/{tidyup_id}`) to measure `after`-triage.
- In R023, both interpretations of FR-012 break:
  1. If Report re-detects the **default branch**: the PR is unmerged, so re-detect is guaranteed dirty → the incident reopens up to the bound (2), burns 2 duplicate repair child runs, and escalates to a human.
  2. If Report re-detects the **child/verification branch** and closes the incident: the default branch is *still* broken, so the very next scheduled Detect sees the same fault and opens a **new** incident + duplicate PR.

**VERDICT: change**
**Concrete change:**
- Split verification from closure by adding an explicit `PR_OPENED` / `AWAITING_MERGE` incident state:
  1. Report runs re-detect on the child's integration/verification branch (`build_verification_branch`). If dirty → reopen (bounded) or escalate. If clean → transition incident to `AWAITING_MERGE` (with `pr_url` and `branch` attached) and **suppress new repair runs** for that incident identity while the PR is open.
  2. Only when a subsequent cycle's Detect on the **default branch** (post-merge) comes back clean does the incident transition from `AWAITING_MERGE` → `CLOSED`.

---

## (e) Code-fix repairs as seeded brownfield child runs (FR-010)

`execute_pipeline_child` (`src/sdlc/workflows/pipeline_child.py:31-51`) and `SHIPPED["seeded"]` (`src/sdlc/workflows/graph_catalog.py:136-137`, `src/sdlc/workflows/graphs/seeded.graph.yaml`) **do** support seeded brownfield child runs, following `TidyUpWorkflow._fix_run` (`src/sdlc/workflows/tidyup.py:217-254`). However, four concrete things break if R023 wires this naively:

1. **`deploy` gate 48-hour hang:** `PipelineConfig().gates["deploy"]` defaults to `GatePolicy.HARD` (`src/sdlc/core/models.py:375`). `TidyUpWorkflow` had to define `_fix_gates()` (`src/sdlc/workflows/tidyup.py:51-69`) to set `gates["deploy"] = GateConfig(policy=GatePolicy.OFF)` and `cfg.deploy.enabled = False`. Without this, every repair child blocks at `deploy` in `seeded.graph.yaml:9`.
2. **`merge` gate blocks the entire project loop:** `PipelineConfig().gates["merge"]` defaults to `GatePolicy.HARD` with `on_timeout=TimeoutAction.HOLD` (`src/sdlc/core/models.py:374`). Because `MaintenanceWorkflow` awaits `execute_pipeline_child` synchronously (and FR-004 forbids concurrent cycles per project), a repair child sitting at `merge` (`HOLD`) **freezes the project's entire maintenance loop** until a human decides the child's merge gate.
3. **`SeededWork` contract gap:** `seeded.graph.yaml` (`seed_spec`, `seed_plan`) requires `SeededWork(arch=ArchitectureSpec, plan=ImplementationPlan)` with a `frozen=True` `ValidationContract` (`src/sdlc/tidyup/backlog.py:63-122`). DAPER's `Plan` emits `RepairPlan{confidence, actions[]}`, not `SeededWork`. A deterministic `RepairPlanAction -> SeededWork` builder is missing.
4. **Build-broken admission paradox:** `TidyUpWorkflow` refuses to run on non-building repos (`tidyup/backlog.py:32-34`) because `build_integration_green` is an absolute merge-gate check. In R023, "build broken" IS a primary Detect signal (FR-005): the repair child will only pass `merge` if its own fix restores the build on the integration branch. That works for a single-cause build break, but any *second* unrelated broken test/build on default will block every other repair child's merge gate.

**VERDICT: change**
**Concrete change:**
- Mandate `_fix_gates()` (`deploy` gate `OFF`, `deploy.enabled = False`) on repair child `PipelineConfig`.
- Define a deterministic `code_fix -> SeededWork` adapter producing `ArchitectureSpec` + 1-task `ImplementationPlan` with a `frozen=True` `ValidationContract` referencing the triggering signal.
- Resolve the `merge`-gate `HOLD` stall: either set a bounded timeout on repair-child `merge` gates, or have `MaintenanceWorkflow` track in-flight repair children asynchronously across cycles rather than blocking the single-project cycle on `execute_pipeline_child`.

---

## (f) Can SC-007's live cycle actually be run by one person with no deployed project?

- **Only for a code/dependency fault, NOT for deploy liveness or PR-merged closure.**
  - `triage_build_probe` + `triage_dependencies(advisory_source="osv")` + `triage_secrets` can run locally against a scratch git repo.
  - With no deployed project, `deploy_liveness` (`smoke_check`) has no live service unless the operator also stands up a local compose/script target.
  - `open_pull_request` (`src/sdlc/stages/merge/activities.py:189`) calls `gh` against a real remote repo; on a local-only sandbox repo with no GitHub remote, `open_pull_request` fails. And if FR-012 is not fixed per (d), a single live cycle cannot both open a PR and close the incident via clean default-branch re-detect without manual mid-cycle PR merging.

**VERDICT: weaken**
**Concrete change:**
- Scope SC-007 explicitly to a scratch GitHub repo (or local repo with `open_pull_request` / `gh` prereq documented) with a seeded code or OSV-dependency fault, `deploy_liveness` disabled/not-applicable, and verification measured on the child/verification branch (`AWAITING_MERGE`) or after an explicit operator merge step.

---

## (g) Is this really size L?

No. Even with the narrow detector/ops set, R023 requires building **8 coupled subsystems**:
1. Project manifest/registry (`project_key -> repo_dir, base_branch, advisory_source, deploy`) — absent today.
2. `MaintenanceWorkflow` (`GateHost` subclass, `continue_as_new` preserving open incidents + pending gates, `nudge` coalescing, `ArtifactRef` claim-checks).
3. Schedule asset + `schedules` apply/dry-run integration + CLI `nudge` and `incidents` query commands.
4. Detect activities + `compute_delta` baseline diffing + `not_collected` escalation tracking.
5. Analyze & Plan Pydantic AI agents + schemas (`DetectionReport`, `Incident`, `RepairPlan`) + code-assigned identity/dedupe/risk-class.
6. `RepairPlan -> SeededWork` compiler + `execute_pipeline_child` orchestration + `deploy_rollback` wiring.
7. Report state machine (`AWAITING_MERGE` / `build_verification_branch` + bounded reopen + escalation) + Memory retain/scrub hook.
8. Full test matrix (replay fixtures, all 4 signal fixtures, timeout=inaction, concurrent-nudge/restart, SC-007 live cycle).

That is **XL** under `.workspace/orchestration-protocol.md:186-194`.

**VERDICT: change**
**Concrete change:** Split R023 into two L-sized rounds:
- **R023a (Detect → Analyze → Plan → Gate + State/CLI):** Project registration, `MaintenanceWorkflow` skeleton (`nudge`, schedule asset, `continue_as_new`, CLI queries), Detect + delta, Analyze + Plan agents, confidence gate (`timeout = inaction`), and memory retention on escalation/timeout.
- **R023b (Execute → Report):** `RepairPlan -> SeededWork` brownfield child execution, `AWAITING_MERGE` / `build_verification_branch` re-verification, `deploy_rollback` execution, memory retention on close, and SC-007 live cycle.
