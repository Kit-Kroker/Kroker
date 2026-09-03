# Archaeology Report: FeatureWorkflow, Models, and Activities

- **Date:** 2026-09-03
- **Status:** Complete (Reviewed & Approved by reviewer3 pending minor symbol coverage)
- **Author:** Antigravity (Executor)
- **Audited Subsystem:** `src/sdlc/workflows/feature.py`, `src/sdlc/models.py`, `src/sdlc/activities.py`, `tests/`
- **Scope:** Phase P0 deliverable for Plan `docs/superpowers/plans/2026-09-03-a-stage-surgery.md` and Spec `docs/superpowers/specs/2026-09-03-a-stage-surgery-design.md`.

## Executive Summary

This archaeology report establishes the authoritative baseline and migration blueprint for Spec A (Stage Surgery):
1. **Stage Anatomy Audit:** Catalogs the 13 live pipeline stages in `feature.py` across `_pipeline`, `_dev_task`, and `_build_and_merge`, detailing line ranges, `self._x` access, StageContext service mappings, uncovered capabilities, enum comparison sites, and child workflows.
2. **Stage Count Clarification (13 Live vs 15 Conceptual):** Aligns the PRD's 15-stage DAG concept (stages 0-14) with reality — Stage 1 (`constitution`) and Stage 3 (`requirements`) are unbuilt / conflated into `clarify`, leaving exactly 13 live pipeline stages (2 pilots in P1: `clarify`, `qa`; 11 non-pilot stages in P3).
3. **Models Ownership Map:** Applies the 7 spec rules mechanically to all 88 module-level symbols in `src/sdlc/models.py` (84 classes, `gate_key`, `compute_plan_drift`, and two helper functions), assigning each symbol to exactly one destination module (`core/models.py`, `workflows/models.py`, `harness/models.py`, `memory/models.py`, `schedules/models.py`, or stage-owned `stages/<stage>/models.py`). Note: Spec A originally estimated ~73 models; this audit inventories all 84 classes and 4 functions (88 symbols total).
4. **Activities Placement Map:** Classifies all 16 activities in `src/sdlc/activities.py` into `vcs/` (6 git plumbing activities) and stage-owned slices (10 activities), explicitly noting the 4 stage-side activities that import `_git` from `vcs`.
5. **Exact Test Move List:** Enumerates all 451 root `.py` test files in `tests/`, specifying exactly 82 files moving to `tests/<stage>/` or `tests/integration/` (with basenames strictly preserved) and 369 files remaining at root.
6. **Ranked Migration Order:** Ranks the 11 non-pilot stages deterministically by ascending uncovered-need count, enum-identity sites, and child workflows.

---

## 1. Stage Inventory and Per-Stage Anatomy Table

### 1.1 Stage Count Note: 13 Live Stages vs 15-Stage DAG

`ROADMAP.md` §1 and PRD document a 15-stage DAG (`0 - intake` through `14 - retro`). However, as noted in `ROADMAP.md` §1:
- Stage 1 (`constitution`) has no `Constitution` model and no stage implementation.
- Stage 3 (`requirements`) is conflated into `clarify` (no separate Product proposer or `Requirements` artifact).

Consequently, exactly **13 live stages** exist in `feature.py`. Two of them (`clarify` and `qa`) are pilots migrated in Phase P1. The remaining **11 stages** are migrated in Phase P3 in the deterministic order derived in §5.

### 1.2 Per-Stage Anatomy Table

*Convention note:* Enum-identity sites list distinct comparison types in the stage body. Child workflows name the target workflow definition.

| Stage | Lines in `feature.py` | `self._x` touched | Maps to service | Uncovered need | Enum-identity sites | Child workflows |
|---|---|---|---|---|---|---|
| **intake** | `:2510-2524` | `_stage`, `_emit` | `stage`, `emit` | None | None (0) | None (0) |
| **context** | `:2474-2491`, `:2551-2562` | `_stage`, `_context`, `_codebase_map`, `_integration_head` | `stage` | None (run context parameters: `repo_path`, `commit_sha`) | `idea.mode is ProjectMode.BROWNFIELD` (`:2554`), `state is not CollectionState.MEASURED` (`:2557`) (2) | None (0) |
| **research** | `:1328-1420`, `:2563-2770` | `_stage`, `_gate`, `_judge`, `_record`, `_retain`, `_check_budget`, `_fan_out_research`, `_fold_research_usage`, `_memory_watermark`, `_stage_record`, `_track_usage` | `stage`, `gate`, `judge`, `record`, `retain` | None (orchestrator handles serial budget check; agents passed as params) | None (0) | None (0) |
| **clarify** (pilot) | `:2771-2921` | `_stage`, `_run_role`, `_cached_stage`, `_judge`, `_record`, `_retain`, `_emit`, `_recall`, `_board_publish`, `_pending`, `_question_answers`, `_status`, `_check_budget`, `_stage_record` | `stage`, `run_role`, `cached_stage`, `judge`, `record`, `retain`, `emit`, `recall`, `ask_and_wait` | 1 (`_board_publish` -> returns `ClarifiedRequirements`; orchestrator publishes) | None (0) | None (0) |
| **architecture** | `:2922-3090` | `_stage`, `_recall`, `_run_role`, `_cached_stage`, `_revisable_stage`, `_judge`, `_record`, `_retain`, `_board_publish`, `_check_budget`, `_stage_record`, `_codebase_map`, `_memory_watermark` | `stage`, `recall`, `run_role`, `cached_stage`, `revisable_stage`, `judge`, `record`, `retain` | 1 (`_board_publish` -> returns `ArchitectureSpec` + gate decision; orchestrator publishes) | None (0) | None (0) |
| **plan** | `:3091-3159` | `_recall`, `_run_role`, `_cached_stage`, `_revisable_stage`, `_judge`, `_record`, `_retain`, `_board_publish`, `_board_sync_tasks`, `_plan_version`, `_check_budget`, `_stage_record` | `recall`, `run_role`, `cached_stage`, `revisable_stage`, `judge`, `record`, `retain` | 1 (`_board_publish` / `_board_sync_tasks` -> returns envelope with `version_id`; orchestrator publishes) | None (0) | None (0) |
| **code** | `:1593-1709`, `:1833-2089` | `_emit`, `_run_role`, `_gate`, `_record`, `_escalation_round`, `_record_escalation`, `_session_refs`, `_stage_record`, `_track_usage` | `emit`, `run_role`, `gate`, `record` | None (`escalation_round` becomes TaskHost local; passes CrewTaskWorkflow handle) | `role_cfg.harness is HarnessKind.CREW` (`:1891`, `:1927`), `esc.outcome is EscalationOutcome.APPROVED` (`:1703`) (2) | `CrewTaskWorkflow.run` (`:1938`) (1) |
| **review** | `:1422-1591`, `:2120-2134`, `:2195-2250` | `_run_role`, `_record`, `_retain`, `_run_deep_review`, `_run_adversary`, `_run_handoff`, `_stage_record` | `run_role`, `record`, `retain` | None (adversary and deep_review run as review lenses; outputs returned) | None (0) | None (0) |
| **qa** (pilot) | `:2090-2117`, `:2167-2194` | `_run_role`, `_judge`, `_record`, `_stage_record` | `run_role`, `judge`, `record` | None | None (0) | None (0) |
| **analyze** | `:3260-3326` | `_stage`, `_run_role`, `_record`, `_retain`, `_check_budget`, `_integration_wt`, `_stage_record` | `stage`, `run_role`, `record`, `retain` | None (takes `integration_wt` as parameter) | None (0) | None (0) |
| **merge** | `:3327-3574` | `_gate`, `_emit`, `_record`, `_retain`, `_run_role`, `_integration_wt`, `_stage_record` | `gate`, `emit`, `record`, `retain`, `run_role` | None (takes `integration_wt` and task results as parameter) | `c.classification is CheckClass.ABSOLUTE` (`:3445`), `c.classification is CheckClass.ADVISORY` (`:3478`), `cov.coverage.state is CollectionState.MEASURED` (`:3382`, `:3399`) (3) | None (0) |
| **deploy** | `:1744-1771`, `:3575-3673` | `_stage`, `_gate`, `_record`, `_deploy_plan`, `_stage_record` | `stage`, `gate`, `record` | None (starts `DeploymentWorkflow` child workflow) | `decision.outcome is GateOutcome.REVISE` (`:3654`) (1) | `DeploymentWorkflow.run` (`:3601`) (1) |
| **retro** | `:2396-2472` | `_emit`, `_retain`, `_memory_watermark`, `_run_summary`, `_session_refs`, `_trace` | `emit`, `retain` | None (best-effort summary, reflection, and artifact export) | None (0) | None (0) |

---

## 2. Models Ownership Map

### 2.1 Sign-Off Acceptance Criteria (Verbatim)

1. **`RoleUsage` (`models.py:780-794`) is listed in the `core/models.py` inventory.** It is forced core by Rule 5, since `RunSummary.roles` (`:1302`) and `RunState.roles` (`:1331`) reference it; `ResearchPlan.usage` (`:871`) and `SubQuestionFinding.usage` (`:885`) then import it from core.
2. **The lens outputs get a decided home.** Default `DeepReviewReport` (`:735`) -> `stages/review/models.py` (produced by `_run_deep_review`, `:1422`); `HandoffSummary`/`HandoffClaim` (`:370-392`) -> `stages/code/models.py` (FR-805 task->task, read via `_handoff_notes`, `:635`). Confirm or override with evidence; record which.
   - *Confirmation with evidence:* Confirmed. `_run_deep_review` is called in review context as a secondary analysis lens, and its report is part of review verdict evaluation; assigning `DeepReviewReport` to `stages/review/models.py` satisfies Rule 1. `HandoffSummary` / `HandoffClaim` flow task-to-task via git notes in `_dev_task`, consumed exclusively by the coding harness execution path in `_dev_task:1867-1875`; assigning them to `stages/code/models.py` satisfies Rule 1 without inducing any cross-stage dependencies.
3. **`workflows/models.py` is listed in the Rule 3 passthrough set that every slice's `AGENTS.md` will carry, alongside `core/models.py` and the slice's own upstreams.**

### 2.2 Complete Placement Table for All 88 Symbols in `src/sdlc/models.py`

`src/sdlc/models.py` defines 84 classes and 4 module-level functions (88 symbols total). Spec A estimated ~73 models; this audit accounts for every definition in the file with exact line numbers.

| Symbol Name | Current Line Range | Destination Path | Governing Rule & Rationale |
|---|---|---|---|
| `ProjectMode` | `:32-34` | `src/sdlc/core/models.py` | Rule 4 / Rule 5 (configuration mode enum, referenced by `IdeaBrief` and `RunSummary`) |
| `HarnessKind` | `:37-44` | `src/sdlc/core/models.py` | Rule 6 (bare enum referenced by `RoleConfig` in core) |
| `GatePolicy` | `:47-50` | `src/sdlc/core/models.py` | Rule 4 (embedded in `GateConfig`) |
| `GateOutcome` | `:53-56` | `src/sdlc/core/models.py` | Rule 4 (embedded in `GateDecision`) |
| `TimeoutAction` | `:59-65` | `src/sdlc/core/models.py` | Rule 4 (embedded in `GateConfig`) |
| `GateConfig` | `:68-87` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `GateSettings` | `:90-100` | `src/sdlc/core/models.py` | Rule 4 (gate parameter model) |
| `ArtifactRef` | `:103-108` | `src/sdlc/core/models.py` | Rule 5 (referenced in core envelopes and `RunSummary`) |
| `SessionEvent` | `:111-123` | `src/sdlc/harness/models.py` | Rule 1 (harness telemetry event) |
| `HarnessSession` | `:126-136` | `src/sdlc/harness/models.py` | Rule 1 (harness execution session) |
| `SessionDigest` | `:139-156` | `src/sdlc/harness/models.py` | Rule 1 (harness summary digest) |
| `ContainmentLayer` | `:159-163` | `src/sdlc/harness/models.py` | Rule 1 (containment classification) |
| `ToolDenial` | `:166-178` | `src/sdlc/harness/models.py` | Rule 1 (containment enforcement record) |
| `ContainmentReport` | `:181-192` | `src/sdlc/harness/models.py` | Rule 1 (containment audit summary) |
| `ContainmentConfig` | `:195-200` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `DeferredToolUse` | `:203-213` | `src/sdlc/harness/models.py` | Rule 1 (E-17 harness tool deferral) |
| `ToolGrant` | `:216-226` | `src/sdlc/harness/models.py` | Rule 1 (E-17 human tool grant) |
| `EscalationOutcome` | `:229-236` | `src/sdlc/harness/models.py` | Rule 1 (E-17 escalation verdict) |
| `ToolEscalation` | `:239-247` | `src/sdlc/harness/models.py` | Rule 1 (E-17 escalation request) |
| `IdeaBrief` | `:250-258` | `src/sdlc/core/models.py` | Rule 5 (pipeline run input envelope) |
| `ClarificationDimension` | `:261-274` | `src/sdlc/core/models.py` | Rule 6 (bare enum referenced by `ClarificationOutcome` in core) |
| `OpenQuestion` | `:277-287` | `src/sdlc/stages/clarify/models.py` | Rule 1 (produced by clarifier agent) |
| `ClarifiedRequirements` | `:290-301` | `src/sdlc/stages/clarify/models.py` | Rule 1 (clarify stage output artifact) |
| `ArchitectureDecision` | `:304-308` | `src/sdlc/stages/architecture/models.py` | Rule 3 (nested in `ArchitectureSpec`) |
| `BrownfieldDelta` | `:311-321` | `src/sdlc/stages/context/models.py` | Rule 1 (produced by brownfield delta check) |
| `ArchitectureSpec` | `:324-348` | `src/sdlc/stages/architecture/models.py` | Rule 1 (architecture stage output artifact) |
| `ValidationContract` | `:351-367` | `src/sdlc/stages/architecture/models.py` | Rule 1 (architecture validation contract) |
| `HandoffClaim` | `:370-375` | `src/sdlc/stages/code/models.py` | Rule 1 / Lens (FR-805 task-to-task claim) |
| `HandoffSummary` | `:378-391` | `src/sdlc/stages/code/models.py` | Rule 1 / Lens (FR-805 task-to-task notes) |
| `DevTask` | `:394-406` | `src/sdlc/stages/plan/models.py` | Rule 3 (nested in `ImplementationPlan`) |
| `PlanDrift` | `:409-424` | `src/sdlc/stages/plan/models.py` | Rule 3 (plan evaluation artifact) |
| `_norm_path` (fn) | `:427-429` | `src/sdlc/stages/plan/models.py` | Rule 3 (helper for `compute_plan_drift`) |
| `compute_plan_drift` (fn) | `:432-445` | `src/sdlc/stages/plan/models.py` | Rule 1 (pure drift calculator producing `PlanDrift`) |
| `ImplementationPlan` | `:448-451` | `src/sdlc/stages/plan/models.py` | Rule 1 (plan stage output artifact) |
| `SeededWork` | `:454-481` | `src/sdlc/workflows/models.py` | Rule 7 (orchestrator envelope for intake bypass) |
| `HarnessRunResult` | `:484-522` | `src/sdlc/harness/models.py` | Rule 1 (harness execution output) |
| `TaskResult` | `:525-535` | `src/sdlc/workflows/models.py` | Rule 7 (orchestrator envelope aggregating task outputs) |
| `QAReport` | `:538-562` | `src/sdlc/stages/qa/models.py` | Rule 1 (qa stage output artifact) |
| `SecurityFinding` | `:565-569` | `src/sdlc/stages/qa/models.py` | Rule 3 (nested in `SecurityReport`) |
| `SecurityReport` | `:572-585` | `src/sdlc/stages/qa/models.py` | Rule 1 (produced by `security_scan` activity) |
| `ReviewFinding` | `:588-592` | `src/sdlc/stages/review/models.py` | Rule 3 (nested in `ReviewReport`) |
| `ReviewReport` | `:595-607` | `src/sdlc/stages/review/models.py` | Rule 1 (review stage output artifact) |
| `FeatureFlag` | `:610-616` | `src/sdlc/stages/deploy/models.py` | Rule 3 (nested in `DeployPlan`) |
| `SmokeCheck` | `:619-638` | `src/sdlc/stages/deploy/models.py` | Rule 3 (nested in `DeployPlan`) |
| `SmokeState` | `:641-644` | `src/sdlc/stages/deploy/models.py` | Rule 3 (nested in `SmokeCheckResult`) |
| `SmokeCheckResult` | `:647-665` | `src/sdlc/stages/deploy/models.py` | Rule 3 (nested in `DeployReport`) |
| `RollbackPolicy` | `:668-670` | `src/sdlc/stages/deploy/models.py` | Rule 3 (nested in `DeployPlan`) |
| `DeployPlan` | `:673-686` | `src/sdlc/stages/deploy/models.py` | Rule 1 (deploy stage plan artifact) |
| `DeployReport` | `:689-711` | `src/sdlc/stages/deploy/models.py` | Rule 1 (deploy stage execution report) |
| `IntegrityFlag` | `:714-719` | `src/sdlc/stages/code/models.py` | Rule 3 (code execution integrity marker) |
| `PlanDeviation` | `:722-732` | `src/sdlc/stages/plan/models.py` | Rule 3 (plan deviation tracking) |
| `DeepReviewReport` | `:735-751` | `src/sdlc/stages/review/models.py` | Rule 1 / Lens (produced by `_run_deep_review`) |
| `CriterionTrace` | `:754-759` | `src/sdlc/stages/analyze/models.py` | Rule 3 (nested in `AnalysisReport`) |
| `AnalysisReport` | `:762-777` | `src/sdlc/stages/analyze/models.py` | Rule 1 (analyze stage output artifact) |
| `RoleUsage` | `:780-794` | `src/sdlc/core/models.py` | Rule 5 (forced core: referenced by `RunSummary` and `RunState`) |
| `SubQuestion` | `:797-799` | `src/sdlc/stages/research/models.py` | Rule 3 (nested in `ResearchPlan`) |
| `ConsultedSource` | `:802-808` | `src/sdlc/stages/research/models.py` | Rule 3 (nested in `ResearchBrief`) |
| `GroundedFinding` | `:811-819` | `src/sdlc/stages/research/models.py` | Rule 3 (nested in `ResearchBrief`) |
| `InferredFinding` | `:822-829` | `src/sdlc/stages/research/models.py` | Rule 3 (nested in `ResearchBrief`) |
| `Contradiction` | `:832-836` | `src/sdlc/stages/research/models.py` | Rule 3 (nested in `ResearchBrief`) |
| `Gap` | `:839-842` | `src/sdlc/stages/research/models.py` | Rule 3 (nested in `ResearchBrief`) |
| `ResearchBrief` | `:845-859` | `src/sdlc/stages/research/models.py` | Rule 1 (research stage output artifact) |
| `ResearchPlan` | `:862-871` | `src/sdlc/stages/research/models.py` | Rule 1 (research planning artifact) |
| `SubQuestionFinding` | `:874-887` | `src/sdlc/stages/research/models.py` | Rule 1 (research subquestion output) |
| `CoverageReport` | `:890-898` | `src/sdlc/stages/merge/models.py` | Rule 1 (produced by `measure_coverage` activity) |
| `GateDecision` | `:901-916` | `src/sdlc/core/models.py` | Rule 4 / Rule 5 (human decision envelope) |
| `DeploymentResult` | `:919-923` | `src/sdlc/stages/deploy/models.py` | Rule 1 (deployment activity result) |
| `RoleConfig` | `:926-960` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `ExecutionMode` | `:963-965` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `BenchmarkConfig` | `:968-975` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `gate_key` (fn) | `:978-980` | `src/sdlc/core/models.py` | Rule 4 (gate helper function) |
| `MergeVerdict` | `:983-991` | `src/sdlc/stages/merge/models.py` | Rule 1 (merge verdict role output) |
| `MemoryKind` | `:994-999` | `src/sdlc/memory/models.py` | Rule 1 (memory horizontal domain enum) |
| `RecallSnapshot` | `:1002-1012` | `src/sdlc/memory/models.py` | Rule 1 (memory recall artifact) |
| `RetainItem` | `:1015-1019` | `src/sdlc/memory/models.py` | Rule 1 (memory retention item) |
| `_memory_backend_default` (fn) | `:1022-1026` | `src/sdlc/core/models.py` | Rule 4 (default factory for `MemoryConfig.backend`) |
| `MemoryConfig` | `:1029-1043` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `ScheduleAction` | `:1049-1063` | `src/sdlc/schedules/models.py` | Rule 1 (schedule horizontal package model) |
| `ScheduleSpecAsset` | `:1066-1077` | `src/sdlc/schedules/models.py` | Rule 1 (schedule horizontal package model) |
| `ScheduleAsset` | `:1080-1086` | `src/sdlc/schedules/models.py` | Rule 1 (schedule horizontal package model) |
| `ResearchConfig` | `:1089-1130` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `DeployConfig` | `:1133-1145` | `src/sdlc/core/models.py` | Rule 4 (embedded in `PipelineConfig`) |
| `PipelineConfig` | `:1148-1249` | `src/sdlc/core/models.py` | Rule 4 (central configuration class) |
| `StageOutcome` | `:1252-1260` | `src/sdlc/core/models.py` | Rule 5 (embedded in `RunSummary`) |
| `ClarificationOutcome` | `:1263-1270` | `src/sdlc/core/models.py` | Rule 5 (embedded in `RunSummary`) |
| `GateOutcomeSummary` | `:1273-1283` | `src/sdlc/core/models.py` | Rule 5 (embedded in `RunSummary`) |
| `RunSummary` | `:1286-1308` | `src/sdlc/core/models.py` | Rule 5 (workflow run terminal summary) |
| `RunState` | `:1311-1334` | `src/sdlc/core/models.py` | Rule 5 (workflow run live state query output) |

---

## 3. Activities Placement Map

`src/sdlc/activities.py` holds 16 activities. In Phase P2 (Task 16), `activities.py` is deleted. Git and worktree plumbing moves to `src/sdlc/vcs/`, and stage-specific activities move into their respective slices.

### 3.1 The 16 Activities Placement

| Activity Name | Current Lines | Destination Module | Package / Slice |
|---|---|---|---|
| `create_worktree` | `:318-336` | `src/sdlc/vcs/worktree.py` | Horizontal (`vcs`) |
| `setup_integration_branch` | `:362-376` | `src/sdlc/vcs/integration.py` | Horizontal (`vcs`) |
| `merge_into_integration` | `:401-428` | `src/sdlc/vcs/integration.py` | Horizontal (`vcs`) |
| `build_verification_branch` | `:448-514` | `src/sdlc/vcs/integration.py` | Horizontal (`vcs`) |
| `run_coding_task` | `:573-640` | `src/sdlc/stages/code/activities.py` | Stage (`code`) — calls `_git` from `vcs` |
| `get_task_diff` | `:651-659` | `src/sdlc/vcs/git.py` | Horizontal (`vcs`) |
| `run_test_suite` | `:707-787` | `src/sdlc/stages/qa/activities.py` | Stage (`qa`) |
| `run_lint` | `:850-879` | `src/sdlc/stages/qa/activities.py` | Stage (`qa`) |
| `security_scan` | `:951-975` | `src/sdlc/stages/qa/activities.py` | Stage (`qa`) |
| `measure_coverage` | `:985-1049` | `src/sdlc/stages/merge/activities.py` | Stage (`merge`) |
| `read_committed_bytes` | `:1060-1085` | `src/sdlc/vcs/git.py` | Horizontal (`vcs`) |
| `run_integration_checks` | `:1210-1262` | `src/sdlc/stages/merge/activities.py` | Stage (`merge`) |
| `open_pull_request` | `:1274-1327` | `src/sdlc/stages/merge/activities.py` | Stage (`merge`) — calls `_git` from `vcs` |
| `evaluate_gate` | `:1331-1333` | `src/sdlc/stages/merge/activities.py` | Stage (`merge`) |
| `classify_repo` | `:1342-1392` | `src/sdlc/stages/context/activities.py` | Stage (`context`) — calls `_git` from `vcs` |
| `check_brownfield_delta` | `:1402-1430` | `src/sdlc/stages/context/activities.py` | Stage (`context`) — calls `_git` from `vcs` |

### 3.2 Private Git Plumbing Helpers Moving to `src/sdlc/vcs/`

The private helper functions behind git execution and Windows file-locking retry mechanisms move to `src/sdlc/vcs/git.py` and `worktree.py`:
- `_git` (`:66-105`)
- `_ensure_worktree` (`:108-164`)
- `_chmod_retry` (`:173-181`)
- `_rmtree_with_retry` (`:184-219`)
- `_find_live_worktree_for_branch` (`:222-261`)
- `_clear_worktree_dir` (`:264-302`)

### 3.3 Four Stage-Side Activities Calling `_git`

The four stage-side activities that call `_git` will import `_git` from `sdlc.vcs.git`:
1. `run_coding_task` (`activities.py:616-639` — checkpoint commits)
2. `classify_repo` (`activities.py:1351-1370` — branch inspection)
3. `check_brownfield_delta` (`activities.py:1411-1414` — diff against base branch)
4. `open_pull_request` (`activities.py:1304-1314` — git push)

---

## 4. Test Relocation Map

`tests/` currently contains 451 root `.py` files. In accordance with Spec A §8, stage-named test files move to `tests/<stage>/` and cross-cutting workflow tests move to `tests/integration/`. Basenames remain strictly unchanged (no `tests/__init__.py`).

Summary: **82 files move**; **369 files remain at root**.

### 4.1 Test Files Moving (82 files)

| Source Path | Destination Path | Target Slice / Domain |
|---|---|---|
| `tests/test_adversary_registry.py` | `tests/review/test_adversary_registry.py` | `review` |
| `tests/test_adversary_workflow.py` | `tests/review/test_adversary_workflow.py` | `review` |
| `tests/test_analyst_models.py` | `tests/analyze/test_analyst_models.py` | `analyze` |
| `tests/test_analyst_stage_wiring.py` | `tests/analyze/test_analyst_stage_wiring.py` | `analyze` |
| `tests/test_analyst_wiring.py` | `tests/analyze/test_analyst_wiring.py` | `analyze` |
| `tests/test_architect_brownfield_prompt.py` | `tests/architecture/test_architect_brownfield_prompt.py` | `architecture` |
| `tests/test_architect_research_tool.py` | `tests/architecture/test_architect_research_tool.py` | `architecture` |
| `tests/test_clarify_agents.py` | `tests/clarify/test_clarify_agents.py` | `clarify` |
| `tests/test_clarify_config.py` | `tests/clarify/test_clarify_config.py` | `clarify` |
| `tests/test_clarify_memo_key.py` | `tests/clarify/test_clarify_memo_key.py` | `clarify` |
| `tests/test_clarify_merge.py` | `tests/clarify/test_clarify_merge.py` | `clarify` |
| `tests/test_clarify_models.py` | `tests/clarify/test_clarify_models.py` | `clarify` |
| `tests/test_clarify_observability.py` | `tests/clarify/test_clarify_observability.py` | `clarify` |
| `tests/test_clarify_prompt_cacheable.py` | `tests/clarify/test_clarify_prompt_cacheable.py` | `clarify` |
| `tests/test_clarify_routing.py` | `tests/clarify/test_clarify_routing.py` | `clarify` |
| `tests/test_clarify_stage_types.py` | `tests/clarify/test_clarify_stage_types.py` | `clarify` |
| `tests/test_clarify_stage_wiring.py` | `tests/clarify/test_clarify_stage_wiring.py` | `clarify` |
| `tests/test_coding_task_checkpoint.py` | `tests/code/test_coding_task_checkpoint.py` | `code` |
| `tests/test_context_ceiling_trigger.py` | `tests/context/test_context_ceiling_trigger.py` | `context` |
| `tests/test_context_classify.py` | `tests/context/test_context_classify.py` | `context` |
| `tests/test_context_classify_activity.py` | `tests/context/test_context_classify_activity.py` | `context` |
| `tests/test_context_delta.py` | `tests/context/test_context_delta.py` | `context` |
| `tests/test_context_delta_activity.py` | `tests/context/test_context_delta_activity.py` | `context` |
| `tests/test_context_project.py` | `tests/context/test_context_project.py` | `context` |
| `tests/test_context_render.py` | `tests/context/test_context_render.py` | `context` |
| `tests/test_deep_review_agent.py` | `tests/review/test_deep_review_agent.py` | `review` |
| `tests/test_deep_review_flag_verification.py` | `tests/review/test_deep_review_flag_verification.py` | `review` |
| `tests/test_deep_review_models.py` | `tests/review/test_deep_review_models.py` | `review` |
| `tests/test_deep_review_read.py` | `tests/review/test_deep_review_read.py` | `review` |
| `tests/test_deep_review_wiring.py` | `tests/review/test_deep_review_wiring.py` | `review` |
| `tests/test_deploy_activities.py` | `tests/deploy/test_deploy_activities.py` | `deploy` |
| `tests/test_deploy_adapters.py` | `tests/deploy/test_deploy_adapters.py` | `deploy` |
| `tests/test_deploy_benchmark_optin.py` | `tests/deploy/test_deploy_benchmark_optin.py` | `deploy` |
| `tests/test_deploy_compose_integration.py` | `tests/deploy/test_deploy_compose_integration.py` | `deploy` |
| `tests/test_deploy_config.py` | `tests/deploy/test_deploy_config.py` | `deploy` |
| `tests/test_deploy_contracts.py` | `tests/deploy/test_deploy_contracts.py` | `deploy` |
| `tests/test_deploy_stage.py` | `tests/deploy/test_deploy_stage.py` | `deploy` |
| `tests/test_deploy_workflow_paths.py` | `tests/deploy/test_deploy_workflow_paths.py` | `deploy` |
| `tests/test_deployment_workflow.py` | `tests/deploy/test_deployment_workflow.py` | `deploy` |
| `tests/test_feature_brownfield_stages.py` | `tests/integration/test_feature_brownfield_stages.py` | `integration` |
| `tests/test_feature_delta_gate.py` | `tests/integration/test_feature_delta_gate.py` | `integration` |
| `tests/test_handoff_crosscheck.py` | `tests/code/test_handoff_crosscheck.py` | `code` |
| `tests/test_handoff_role.py` | `tests/code/test_handoff_role.py` | `code` |
| `tests/test_handoff_workflow.py` | `tests/code/test_handoff_workflow.py` | `code` |
| `tests/test_merge_gate_wiring.py` | `tests/merge/test_merge_gate_wiring.py` | `merge` |
| `tests/test_plan_deviations.py` | `tests/plan/test_plan_deviations.py` | `plan` |
| `tests/test_plan_drift.py` | `tests/plan/test_plan_drift.py` | `plan` |
| `tests/test_plan_graph_validation.py` | `tests/plan/test_plan_graph_validation.py` | `plan` |
| `tests/test_planner_agent_retries.py` | `tests/plan/test_planner_agent_retries.py` | `plan` |
| `tests/test_qa_diagnostic_survives.py` | `tests/qa/test_qa_diagnostic_survives.py` | `qa` |
| `tests/test_qa_no_tests_collected.py` | `tests/qa/test_qa_no_tests_collected.py` | `qa` |
| `tests/test_qa_stage_judging.py` | `tests/qa/test_qa_stage_judging.py` | `qa` |
| `tests/test_qa_task_venv_provisioning.py` | `tests/qa/test_qa_task_venv_provisioning.py` | `qa` |
| `tests/test_qa_timeout.py` | `tests/qa/test_qa_timeout.py` | `qa` |
| `tests/test_reflect_workflow.py` | `tests/retro/test_reflect_workflow.py` | `retro` |
| `tests/test_research_budget_scope.py` | `tests/research/test_research_budget_scope.py` | `research` |
| `tests/test_research_budget_store.py` | `tests/research/test_research_budget_store.py` | `research` |
| `tests/test_research_degradation.py` | `tests/research/test_research_degradation.py` | `research` |
| `tests/test_research_e2e.py` | `tests/research/test_research_e2e.py` | `research` |
| `tests/test_research_fanout_wiring.py` | `tests/research/test_research_fanout_wiring.py` | `research` |
| `tests/test_research_grounding.py` | `tests/research/test_research_grounding.py` | `research` |
| `tests/test_research_instructions.py` | `tests/research/test_research_instructions.py` | `research` |
| `tests/test_research_merge.py` | `tests/research/test_research_merge.py` | `research` |
| `tests/test_research_models.py` | `tests/research/test_research_models.py` | `research` |
| `tests/test_research_page_write.py` | `tests/research/test_research_page_write.py` | `research` |
| `tests/test_research_plan_activity.py` | `tests/research/test_research_plan_activity.py` | `research` |
| `tests/test_research_prompt_cacheable.py` | `tests/research/test_research_prompt_cacheable.py` | `research` |
| `tests/test_research_provider.py` | `tests/research/test_research_provider.py` | `research` |
| `tests/test_research_refine_round.py` | `tests/research/test_research_refine_round.py` | `research` |
| `tests/test_research_registry.py` | `tests/research/test_research_registry.py` | `research` |
| `tests/test_research_spike.py` | `tests/research/test_research_spike.py` | `research` |
| `tests/test_research_stage_judging.py` | `tests/research/test_research_stage_judging.py` | `research` |
| `tests/test_research_stage_types.py` | `tests/research/test_research_stage_types.py` | `research` |
| `tests/test_research_stage_wiring.py` | `tests/research/test_research_stage_wiring.py` | `research` |
| `tests/test_research_subquestion_activity.py` | `tests/research/test_research_subquestion_activity.py` | `research` |
| `tests/test_research_synthesize_activity.py` | `tests/research/test_research_synthesize_activity.py` | `research` |
| `tests/test_research_tools.py` | `tests/research/test_research_tools.py` | `research` |
| `tests/test_research_verify.py` | `tests/research/test_research_verify.py` | `research` |
| `tests/test_retro_stage.py` | `tests/retro/test_retro_stage.py` | `retro` |
| `tests/test_review_models.py` | `tests/review/test_review_models.py` | `review` |
| `tests/test_review_wiring.py` | `tests/review/test_review_wiring.py` | `review` |
| `tests/test_reviewer_agent.py` | `tests/review/test_reviewer_agent.py` | `review` |

### 4.2 Test Files Remaining at Root (369 files)

The following 369 root test files stay at `tests/` permanently (framework infrastructure, conftest, fakes, fixtures, or non-pipeline domains such as assessment, triage, tidyup, benchmarks, operator, containment, crew):

- `tests/conftest.py`
- `tests/helpers_risk.py`
- `tests/test_actor_channel.py`
- `tests/test_agent_capabilities.py`
- `tests/test_agent_folders.py`
- `tests/test_agents_registry.py`
- `tests/test_artifact_store.py`
- `tests/test_assessment_activities.py`
- `tests/test_assessment_admission.py`
- `tests/test_assessment_cli_wiring.py`
- `tests/test_assessment_models.py`
- `tests/test_assessment_resolve_tree.py`
- `tests/test_assessment_scan_phase.py`
- `tests/test_assessment_verification.py`
- `tests/test_assessment_worker_registration.py`
- `tests/test_assessment_workflow.py`
- `tests/test_assessment_workflow_e2e.py`
- `tests/test_assessment_workflow_risk_gate_e2e.py`
- `tests/test_benchmark_agreement_matrix.py`
- `tests/test_benchmark_arms.py`
- `tests/test_benchmark_cli.py`
- `tests/test_benchmark_config.py`
- `tests/test_benchmark_evidence.py`
- `tests/test_benchmark_experiments.py`
- `tests/test_benchmark_heatmap.py`
- `tests/test_benchmark_heatmap_render.py`
- `tests/test_benchmark_judge.py`
- `tests/test_benchmark_matrix.py`
- `tests/test_benchmark_models.py`
- `tests/test_benchmark_recorder.py`
- `tests/test_benchmark_report.py`
- `tests/test_benchmark_sc_rollup.py`
- `tests/test_benchmark_score.py`
- `tests/test_benchmark_scoring.py`
- `tests/test_benchmark_waste_bag.py`
- `tests/test_benchmark_waste_matrix.py`
- `tests/test_benchmark_workflow.py`
- `tests/test_board_activities.py`
- `tests/test_board_api_reads.py`
- `tests/test_board_api_writes.py`
- `tests/test_board_artifacts.py`
- `tests/test_board_project_key.py`
- `tests/test_board_schema.py`
- `tests/test_board_stats.py`
- `tests/test_board_tasks.py`
- `tests/test_board_wiring.py`
- `tests/test_board_workflow.py`
- `tests/test_bootstrap.py`
- `tests/test_budget_gate.py`
- `tests/test_calibration_agreement.py`
- `tests/test_calibration_capture.py`
- `tests/test_calibration_cli.py`
- `tests/test_calibration_fixtures.py`
- `tests/test_calibration_render.py`
- `tests/test_calibration_run.py`
- `tests/test_capability_assignment.py`
- `tests/test_capability_cli.py`
- `tests/test_capability_corrections.py`
- `tests/test_capability_export.py`
- `tests/test_capability_fingerprint.py`
- `tests/test_capability_models.py`
- `tests/test_capability_refactor_corpus.py`
- `tests/test_capability_resolve.py`
- `tests/test_capability_rows.py`
- `tests/test_capability_store.py`
- `tests/test_cat_cafe_oracle.py`
- `tests/test_cell_config.py`
- `tests/test_channel_contract.py`
- `tests/test_channel_inbox.py`
- `tests/test_channel_transport.py`
- `tests/test_chat_mount.py`
- `tests/test_check_file_size.py`
- `tests/test_claude_stream_normalise.py`
- `tests/test_cli_local_only.py`
- `tests/test_cli_role_model.py`
- `tests/test_containment_activity.py`
- `tests/test_containment_adapters.py`
- `tests/test_containment_adapters_other.py`
- `tests/test_containment_evaluate.py`
- `tests/test_containment_grants.py`
- `tests/test_containment_hook.py`
- `tests/test_containment_live.py`
- `tests/test_containment_models.py`
- `tests/test_containment_policy.py`
- `tests/test_containment_write_root.py`
- `tests/test_crew_checkpoint.py`
- `tests/test_crew_config.py`
- `tests/test_crew_critic_round.py`
- `tests/test_crew_drift.py`
- `tests/test_crew_families.py`
- `tests/test_crew_feature_wiring.py`
- `tests/test_crew_fs_activities.py`
- `tests/test_crew_gates.py`
- `tests/test_crew_live_contract.py`
- `tests/test_crew_loader.py`
- `tests/test_crew_models.py`
- `tests/test_crew_protocol.py`
- `tests/test_crew_stage_wiring.py`
- `tests/test_crew_turn.py`
- `tests/test_crew_workflow.py`
- `tests/test_crew_worktree.py`
- `tests/test_cursor_harness.py`
- `tests/test_dashboard_api.py`
- `tests/test_dashboard_channel.py`
- `tests/test_dashboard_e2e.py`
- `tests/test_dashboard_entrypoint.py`
- `tests/test_dashboard_fleet.py`
- `tests/test_dashboard_poller.py`
- `tests/test_dashboard_sse.py`
- `tests/test_deveval_corpus.py`
- `tests/test_deveval_importer.py`
- `tests/test_deveval_verify.py`
- `tests/test_discover_apply.py`
- `tests/test_discover_attribution.py`
- `tests/test_discover_baseline.py`
- `tests/test_discover_blueprint.py`
- `tests/test_discover_cohesion_coupling.py`
- `tests/test_discover_context.py`
- `tests/test_discover_context_activity.py`
- `tests/test_discover_dead_guard.py`
- `tests/test_discover_degradation.py`
- `tests/test_discover_domain.py`
- `tests/test_discover_finalize_activity.py`
- `tests/test_discover_guard.py`
- `tests/test_discover_lock_activity.py`
- `tests/test_discover_map_artifact.py`
- `tests/test_discover_map_build.py`
- `tests/test_discover_map_context.py`
- `tests/test_discover_map_dispositions.py`
- `tests/test_discover_memo.py`
- `tests/test_discover_models.py`
- `tests/test_discover_mutation_corpus.py`
- `tests/test_discover_operations.py`
- `tests/test_discover_ownership.py`
- `tests/test_discover_refgraph_forms.py`
- `tests/test_discover_refgraph_resolve.py`
- `tests/test_discover_role.py`
- `tests/test_discover_seam.py`
- `tests/test_discover_stamp.py`
- `tests/test_discover_tiers.py`
- `tests/test_discover_verify.py`
- `tests/test_discover_verify_activity.py`
- `tests/test_dispositions_cli.py`
- `tests/test_dispositions_models.py`
- `tests/test_dispositions_store.py`
- `tests/test_drift_harvester.py`
- `tests/test_e2e_greenfield.py`
- `tests/test_e36_imports.py`
- `tests/test_env_allowlist.py`
- `tests/test_error_matrix.py`
- `tests/test_error_matrix_render.py`
- `tests/test_eval_absolute_vetoes.py`
- `tests/test_eval_cli_render.py`
- `tests/test_eval_cli_wiring.py`
- `tests/test_eval_fixture_build.py`
- `tests/test_eval_mutation_seam.py`
- `tests/test_eval_runner.py`
- `tests/test_eval_verdict.py`
- `tests/test_exa_wrapper.py`
- `tests/test_export_activity.py`
- `tests/test_factory_purity.py`
- `tests/test_factory_recorder.py`
- `tests/test_fix_loop_feedback.py`
- `tests/test_gate_config.py`
- `tests/test_gate_decision.py`
- `tests/test_gate_host.py`
- `tests/test_gate_notifications.py`
- `tests/test_gate_revision_loop.py`
- `tests/test_gate_settings.py`
- `tests/test_gate_timeout_action.py`
- `tests/test_gates_checks.py`
- `tests/test_gates_models.py`
- `tests/test_golden_case_loads.py`
- `tests/test_grade_oracle.py`
- `tests/test_grounding.py`
- `tests/test_harness_observability.py`
- `tests/test_harness_parse.py`
- `tests/test_harness_result.py`
- `tests/test_hindsight_api_constants.py`
- `tests/test_hindsight_client_core.py`
- `tests/test_hindsight_contract_harness.py`
- `tests/test_hindsight_live.py`
- `tests/test_hindsight_recall.py`
- `tests/test_hindsight_reflect.py`
- `tests/test_hindsight_retain.py`
- `tests/test_inbox_query.py`
- `tests/test_integration_activities.py`
- `tests/test_integration_branch_wired.py`
- `tests/test_integration_checks.py`
- `tests/test_integration_checks_wiring.py`
- `tests/test_judge_literal.py`
- `tests/test_load_case_assets.py`
- `tests/test_logfire_setup.py`
- `tests/test_measure_coverage.py`
- `tests/test_measurement.py`
- `tests/test_memoization_cache.py`
- `tests/test_memoization_wiring.py`
- `tests/test_memory_activities.py`
- `tests/test_memory_backend_selection.py`
- `tests/test_memory_fake.py`
- `tests/test_memory_models.py`
- `tests/test_memory_protocol.py`
- `tests/test_memory_purity.py`
- `tests/test_memory_scrub.py`
- `tests/test_memory_wiring.py`
- `tests/test_model_usage_capture.py`
- `tests/test_module_imports.py`
- `tests/test_nightly_reflect_asset.py`
- `tests/test_notify_activity.py`
- `tests/test_notify_notifiers.py`
- `tests/test_notify_render.py`
- `tests/test_notify_routes.py`
- `tests/test_notify_schedule.py`
- `tests/test_observability_export.py`
- `tests/test_observability_trace.py`
- `tests/test_open_pull_request.py`
- `tests/test_opencode_normalise.py`
- `tests/test_operator_agent.py`
- `tests/test_operator_deps.py`
- `tests/test_operator_e2e.py`
- `tests/test_operator_errors.py`
- `tests/test_operator_follow.py`
- `tests/test_operator_layering.py`
- `tests/test_operator_read_artifact.py`
- `tests/test_operator_render.py`
- `tests/test_operator_tools_board.py`
- `tests/test_operator_tools_runs.py`
- `tests/test_operator_writes.py`
- `tests/test_oracle.py`
- `tests/test_pending_builders.py`
- `tests/test_pending_opened_at.py`
- `tests/test_pending_types.py`
- `tests/test_pending_wiring.py`
- `tests/test_price_usage.py`
- `tests/test_process.py`
- `tests/test_prompt_confidence_instruction.py`
- `tests/test_prompt_gate.py`
- `tests/test_prompt_gate_mutations.py`
- `tests/test_prompt_migration.py`
- `tests/test_promptfoo_absolute.py`
- `tests/test_promptfoo_assertion.py`
- `tests/test_promptfoo_config.py`
- `tests/test_promptfoo_contract.py`
- `tests/test_promptfoo_provider.py`
- `tests/test_prompts_characterization.py`
- `tests/test_py_launcher_provisioning.py`
- `tests/test_quality_gate.py`
- `tests/test_read_committed_bytes.py`
- `tests/test_recall_query_hash.py`
- `tests/test_reference_oracle.py`
- `tests/test_registry_ignores_fixtures.py`
- `tests/test_registry_mirror.py`
- `tests/test_registry_packaging.py`
- `tests/test_registry_resolution.py`
- `tests/test_risk_activity.py`
- `tests/test_risk_apply.py`
- `tests/test_risk_build.py`
- `tests/test_risk_composite.py`
- `tests/test_risk_composites.py`
- `tests/test_risk_controls.py`
- `tests/test_risk_crosscap.py`
- `tests/test_risk_crosscap_candidates.py`
- `tests/test_risk_factors.py`
- `tests/test_risk_memo.py`
- `tests/test_risk_models.py`
- `tests/test_risk_prompt.py`
- `tests/test_risk_proposal_models.py`
- `tests/test_risk_role.py`
- `tests/test_risk_rules_sha.py`
- `tests/test_risk_severity.py`
- `tests/test_risk_system_view.py`
- `tests/test_risk_verify_activity.py`
- `tests/test_role_model_resolution.py`
- `tests/test_role_usage.py`
- `tests/test_run_roles_validation.py`
- `tests/test_run_state_model.py`
- `tests/test_run_state_query.py`
- `tests/test_run_summary_build.py`
- `tests/test_run_summary_model.py`
- `tests/test_sarif.py`
- `tests/test_scan_activities_s1_s3.py`
- `tests/test_scan_candidate.py`
- `tests/test_scan_configpaths.py`
- `tests/test_scan_determinism.py`
- `tests/test_scan_inherit.py`
- `tests/test_scan_memo.py`
- `tests/test_scan_merge.py`
- `tests/test_scan_models.py`
- `tests/test_scan_naming.py`
- `tests/test_scan_payloads.py`
- `tests/test_scan_qs1_tests_inventory.py`
- `tests/test_scan_qs2_coverage.py`
- `tests/test_scan_qs3_testability.py`
- `tests/test_scan_qs4_ci.py`
- `tests/test_scan_registry.py`
- `tests/test_scan_result.py`
- `tests/test_scan_rules_sha.py`
- `tests/test_scan_s1_packages.py`
- `tests/test_scan_s2_schema.py`
- `tests/test_scan_s3_entrypoints.py`
- `tests/test_scan_s4_frontend.py`
- `tests/test_scan_signal_result.py`
- `tests/test_scan_source_candidate.py`
- `tests/test_scan_ss1_security_static.py`
- `tests/test_scan_ss3_config_infra.py`
- `tests/test_scan_ss4_sensitivity.py`
- `tests/test_scan_stub_activities.py`
- `tests/test_scan_summary.py`
- `tests/test_scan_testpaths.py`
- `tests/test_scan_tree_shared.py`
- `tests/test_scan_upstream.py`
- `tests/test_schedule_apply.py`
- `tests/test_schedule_loader.py`
- `tests/test_schedule_reconcile.py`
- `tests/test_score_judge_mix.py`
- `tests/test_security_collection_gate.py`
- `tests/test_security_floor.py`
- `tests/test_seeded_work.py`
- `tests/test_session_capture.py`
- `tests/test_session_models.py`
- `tests/test_session_retention.py`
- `tests/test_smoke_check.py`
- `tests/test_soft_gate_auto_approval.py`
- `tests/test_spike_agent_stub.py`
- `tests/test_stack_contract.py`
- `tests/test_stage_models.py`
- `tests/test_staged_judge.py`
- `tests/test_task_gate_revise_loop.py`
- `tests/test_task_matrix.py`
- `tests/test_task_matrix_render.py`
- `tests/test_tasks_suite.py`
- `tests/test_tidyup_backlog.py`
- `tests/test_tidyup_cli_wiring.py`
- `tests/test_tidyup_workflow.py`
- `tests/test_todo_api_case_loads.py`
- `tests/test_tool_approval_gate.py`
- `tests/test_toolchain_adapters.py`
- `tests/test_toolchain_triage_extension.py`
- `tests/test_triage_advisories.py`
- `tests/test_triage_baseline.py`
- `tests/test_triage_build_probe.py`
- `tests/test_triage_cli_wiring.py`
- `tests/test_triage_delta.py`
- `tests/test_triage_dependencies.py`
- `tests/test_triage_finding_identity.py`
- `tests/test_triage_gitread.py`
- `tests/test_triage_misconfig.py`
- `tests/test_triage_models.py`
- `tests/test_triage_outliers.py`
- `tests/test_triage_override.py`
- `tests/test_triage_readiness.py`
- `tests/test_triage_readiness_gate.py`
- `tests/test_triage_registry.py`
- `tests/test_triage_registry_readiness_keys.py`
- `tests/test_triage_resolve_commit.py`
- `tests/test_triage_scaffold.py`
- `tests/test_triage_secrets.py`
- `tests/test_triage_workflow.py`
- `tests/test_triage_workflow_e2e.py`
- `tests/test_untraced_criteria.py`
- `tests/test_verification_branch.py`
- `tests/test_verify.py`
- `tests/test_vetoes.py`
- `tests/test_waste_population_wiring.py`
- `tests/test_worker_image.py`
- `tests/test_worker_registration.py`
- `tests/test_worker_registry_gate.py`
- `tests/test_workflow_fanout.py`
- `tests/test_worktree_idempotency.py`

---

## 5. Ranked Migration Order for Non-Pilot Stages

The 11 non-pilot stages are ordered ascending by:
1. Count of uncovered capabilities (needs outside the 11 `StageContext` services).
2. Count of enum-identity comparison sites (`is` / `is not`).
3. Count of child workflows executed.

### Ranking Vector Summary

| Rank | Stage | Uncovered Needs | Enum Sites | Child Workflows | Rationale |
|---|---|---|---|---|---|
| 1 | `intake` | 0 | 0 | 0 | Purely mechanical repo probe activity; no LLM role call, zero uncovered needs. |
| 2 | `retro` | 0 | 0 | 0 | Best-effort summary retention, reflection, and artifact export. |
| 3 | `analyze` | 0 | 0 | 0 | Clean-context analyst role proposing criterion->test traceability; receives integration worktree. |
| 4 | `research` | 0 | 0 | 0 | Web research proposer and query fan-out; roles passed as parameters. |
| 5 | `review` | 0 | 0 | 0 | Primary reviewer proposer + adversary/deep-review secondary lenses. |
| 6 | `context` | 0 | 2 | 0 | Brownfield map generation; 2 enum identity checks (`ProjectMode.BROWNFIELD`, `CollectionState.MEASURED`). |
| 7 | `merge` | 0 | 3 | 0 | Deterministic quality gate + merge verdict role; 3 enum identity sites (`CheckClass`, `CollectionState`). |
| 8 | `deploy` | 0 | 1 | 1 | Single-liveness deploy plan; 1 enum site (`GateOutcome.REVISE`), 1 child workflow (`DeploymentWorkflow`). |
| 9 | `code` | 0 | 2 | 1 | Developer harness execution; 2 enum sites (`HarnessKind.CREW`, `EscalationOutcome`), 1 child workflow (`CrewTaskWorkflow`). |
| 10 | `architecture` | 1 | 0 | 0 | Architect role + revise loop; 1 uncovered need (`_board_publish` -> returns artifact + gate decision). |
| 11 | `plan` | 1 | 0 | 0 | Planner role + revise loop; 1 uncovered need (`_board_publish` / `_board_sync_tasks` -> returns `version_id`). |

### Authoritative Migration Sequence for Phase P3 (Task 19/20)

1. **Stage `intake`**
2. **Stage `retro`**
3. **Stage `analyze`**
4. **Stage `research`**
5. **Stage `review`**
6. **Stage `context`**
7. **Stage `merge`**
8. **Stage `deploy`**
9. **Stage `code`**
10. **Stage `architecture`**
11. **Stage `plan`**
