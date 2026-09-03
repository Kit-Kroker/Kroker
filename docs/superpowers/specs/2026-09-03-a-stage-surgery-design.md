# A — the stage surgery

- **Date:** 2026-09-03
- **Status:** approved design, ready for planning
- **Scope:** A — the surgery itself. Cutting `workflows/feature.py`, `activities.py`, `models.py` and `harness/adapters.py` into the vertical slices B0 specified, and emptying the file-size baseline of all four.
- **Satisfies:** no FR moves. Repo-hardening (`ROADMAP.md` §7, "Structural / repo-hardening items"), executing the contract in `docs/superpowers/specs/2026-09-02-b0-module-shape-and-docs-architecture-design.md`.
- **Baseline:** `main` at `95a5a07`; `temporalio` 1.30.0.
- **Does not cover:** (C) the UI and Claude Design pipeline. **`tests/test_assessment_workflow_e2e.py`** (1177 lines, the fifth entry in `.file-size-baseline.json`) — no stage move shrinks a test of another domain; it belongs to the assessment-domain slice work, which B0 cuts into scan / discover / risk / gates under its own spec. The assessment, triage, tidy-up and benchmark subsystems are untouched except where they import a symbol that moves. No product behaviour changes anywhere: this is relocation, plus three defects fixed in passing that are named individually in §3.

## Problem

B0 settled what a correct module looks like and left the cutting to A. The four files it named are unchanged: `feature.py` is 3673 lines, `activities.py` 1430, `models.py` 1334, `harness/adapters.py` 1092.

B0's own reading of them was made from the outside, and three of its load-bearing claims do not survive contact with the code. They are corrected in §7 rather than quietly worked around, because A's plan is derived from them.

Two facts about the tree are not in B0 at all and change the shape of the work.

**Four slices already exist in the wrong place.** `src/sdlc/clarify/` (522 lines across `merge.py`, `models.py`, `prompts.py`, `routing.py`), `src/sdlc/research/` (1093 across eleven modules), `src/sdlc/context/` (457) and `src/sdlc/deploy/` (376) hold real stage code at `src/sdlc/<stage>/`, not at B0's `src/sdlc/stages/<stage>/`. The clarify pilot cannot begin without deciding what happens to them.

**Stage extraction alone cannot get `feature.py` under the ceiling.** Summing the methods that survive it — `__init__` (`:826-870`), `_stage_record` (`:878-924`), the four board helpers (`:928-1008`), `_record`/`_judge`/`_recall`/`_retain` (`:1012-1096`), the gate callbacks (`:1098-1143`), `_cached_stage` (`:1145-1177`), the queries (`:1184-1222`), `_emit`/`_stage`/`_track_usage` (`:1226-1281`), `_run_role` (`:1283-1326`), `_check_budget` (`:1711-1742`), `_revisable_stage` (`:1773-1805`), `_merge_task` (`:1807-1831`) — gives ~557 lines that no stage body touches. With the module header and the `_pipeline` / `_build_and_merge` / `_dev_task` skeletons, a fully evacuated `feature.py` still lands near 1400. `FeatureWorkflow` is not large only because it inlines fifteen stages; it is large because it is simultaneously a DAG coordinator, a task engine, an event bus, an artifact publisher, a telemetry accumulator and a memoization cache.

## Decision

**Fifteen stages leave. The orchestrator's services leave with them, onto the workflow class's own MRO.**

A is the whole surgery in one spec and a phased plan: all fifteen stages out of `feature.py`, `models.py` and `activities.py` deleted outright, `adapters.py` flattened, and the four `src/` entries gone from `.file-size-baseline.json`. Splitting this across three specs was rejected: `models.py` cannot be emptied without knowing where all fifteen producers live, so a later spec would re-litigate ownership calls an earlier one had already executed across 261 files. One document holds the whole ownership map; phasing lives in the plan, where it belongs.

## 1. The target tree

```
src/sdlc/
  core/
    context.py        # the StageContext Protocol
    models.py         # configuration + envelopes that reference nothing outside core  (~449)
  stages/
    __init__.py       # STAGE_MODULES: explicit, ordered, greppable
    <stage>/          # fifteen
      __init__.py  step.py  activities.py  models.py  prompts.py
      <stage>.md   AGENTS.md
  vcs/                # git and worktree plumbing lifted out of activities.py
  harness/            # base.py claude_code.py opencode.py cursor.py registry.py
                      #   alongside containment.py hook.py session.py models.py
  workflows/          # every @workflow.defn, the service-host mixins, models.py
tests/<stage>/ , tests/integration/
```

The four existing half-slices move **whole** into `stages/`, extra modules included: `routing.py` and `merge.py` ride inside `stages/clarify/`, `tavily.py` and `budget_store.py` inside `stages/research/`. None of the four has a consumer in another stage today. Promotion of a module out of a slice into a horizontal package happens later, if and when a second consumer appears — a small obvious commit, not a judgment made in advance.

`StageContext` gets `core/context.py` rather than riding in `core/models.py`: a Protocol is not a model, and separating them holds `core/models.py` near 450.

## 2. Ownership

### 2.1 Two tests that govern different things

| Test | Governs | Statement |
|---|---|---|
| **Producer-owns** | *type* ownership | A stage's `models.py` holds what that stage produces. Downstream stages import it directly; a type import is not a stage call (B0 §1.4). |
| **Consumer-count** | *module* placement | A module is horizontal iff it has consumers in more than one stage or domain. `harness/` is horizontal because code, qa and the crew consume it; `research/tavily.py` is not. |

They are stated adjacently and labelled because the natural misreading — applying consumer-count to types — deletes every slice's `models.py` back into `core/`, which is precisely the collapse B0 §1.4 rejected. In a pipeline nearly every artifact crosses stages. **On any type, producer-owns wins.**

### 2.2 Seven rules that make the ownership map derivable by reading

P0 must produce a complete placement for 73 models and 16 activities before any of them move. These rules make that mechanical rather than a matter of taste. Rule 5 is the invariant; 6 and 7 exist only to satisfy it, and fire only when it forces them.

1. **Producer.** A type is owned by the stage whose role output schema or activity return type *is* that type.
2. **Aggregate.** A type the orchestrator assembles from several stages' outputs is an envelope — see Rule 7 for its home.
3. **Nesting.** A type appearing only inside another follows its parent. `CriterionTrace` (`:754`) goes with `AnalysisReport` (`:762`) to analyze; `ReviewFinding` (`:588`) with `ReviewReport` (`:595`) to review.
4. **Configuration.** Every configuration class goes to `core/models.py`, without exception. `PipelineConfig` (`:1148-1251`) embeds `GateConfig` (`:68`), `BenchmarkConfig` (`:968`), `RoleConfig` (`:926`), `MemoryConfig` (`:1029`), `ResearchConfig` (`:1089`), `DeployConfig` (`:1133`) and `ContainmentConfig` (`:195`). Any of them living in a slice makes `core` import `stages`, and every slice imports `core`. Consequence, stated rather than discovered: the memory block splits — `MemoryConfig` to `core/`, while `MemoryKind` / `RecallSnapshot` / `RetainItem` (`:994-1021`) stay in `memory/models.py`, because no core type references them.
5. **Layering — the invariant.** `core/` imports nothing from `stages/` and nothing from any horizontal package. Anything a `core/` type references is itself in `core/`. Checkable by grep; it belongs in `core/AGENTS.md`. It costs less than it sounds: today's `models.py:24` imports `CollectionState` and `Measurement` from `measurement.py`, but their only consumers are `SecurityReport.state` (`:584`) and `CoverageReport.coverage` (`:898`) — both stage-side evidence types — so the new `core/models.py` drops that import entirely.
6. **Bare enums a core type needs are core.** An enumeration with no model dependencies that a `core/` type references lives in `core/models.py`. `HarnessKind` (`:37-44`), reached from `RoleConfig`, and `ClarificationDimension` (`:261-274`), reached from `RunSummary` (`:1286`) via `ClarificationOutcome` (`:1263`), both become core. This amends B0's implied placement: `harness/models.py` holds the session and containment payload types but **not** `HarnessKind`. It also improves the Rule 3 story, since the enum whose identity comparisons at `:1891` and `:1927` are load-bearing now lives in a module every slice passes through anyway.
7. **Orchestrator envelopes live with the orchestrator.** An envelope aggregating stage artifacts goes to `workflows/models.py`, not `core/models.py`. `workflows/` may import `stages/`; `core/` may not. `TaskResult` (`:525-535`) is assembled by `_dev_task`, which §3.1 places in `TaskHost` under `workflows/`, so it sits beside the code that builds it; `SeededWork` (`:454-481`) likewise.

**Why not the alternatives.** Declaring `TaskResult` and its five member types core drags `HarnessRunResult`, `QAReport`, `ReviewReport`, `DeepReviewReport` and `HandoffSummary` into `core/` — a ~250-line every-context file, which is the shape B0's Problem section indicts. Assigning `TaskResult` to its *consumer* (`stages/merge/`, which reads it at `:3364`) contradicts producer-owns and would make ownership depend on who reads a type, which changes as the pipeline changes.

**Stages may type-import `workflows/models.py`.** The merge step consumes `TaskResult` (`feature.py:3364`, `:3411`), so the dependency runs stage → workflows for a type. This is blessed as the exact mirror of B0 §1.4's allowance that a type import is not a stage call, and it is acyclic: `workflows/models.py` imports `stages/{code,qa,review}`, never `stages/merge`.

**`core/models.py` inventory** (~449 lines): `ProjectMode`, `HarnessKind`, `ClarificationDimension`, the gate family (`:47-102`, `:901-918`, `gate_key` `:978`), `ArtifactRef`, `IdeaBrief`, `RoleUsage` (`:780-794` — forced core by Rule 5, since `RunSummary.roles` and `RunState.roles` reference it), `RoleConfig`, `ExecutionMode`, every `*Config` including `PipelineConfig`, and the run-summary family (`:1252-1334`).

**`resolve_role_model`** (`feature.py:316-325`) does **not** go to `core/`: it reads `STAGE_ROLES` and `STAGE_MODELS` from `agents/roles.py`, which would violate Rule 5. It moves to `agents/roles.py`.

**Two homes P0 fixes rather than the spec:** the lens outputs. `DeepReviewReport` (`:735`) is produced by `_run_deep_review` (`:1422`), a review lens — default `stages/review/models.py`. `HandoffSummary` / `HandoffClaim` (`:370-392`) flow task → task (FR-805) and are read by the next task's code path via `_handoff_notes` (`:635`) — default `stages/code/models.py`. Neither is one of the fifteen stages and neither creates a cycle wherever it lands; P0 confirms or overrides with evidence.

### 2.3 The `__init__.py` rule

An `__init__.py` may declare a **narrow named surface its package owns** — `step`, `ACTIVITIES`, a registry. It may never re-export a sibling module's contents to preserve an old import path. The first is an interface; the second is the two-homes failure B0 §1.4 bans. A half-populated slice exports only what exists, which is what makes §6's intermediate state legal.

## 3. The orchestrator

### 3.1 Service-host mixins

B0 Rule 1 permits handlers anywhere on the workflow class's MRO and names `GateHost` (`gates.py:54`) as the working precedent, verified against `temporalio/workflow/_definition.py:288`, where `inspect.getmembers` resolves definitions through the MRO. A applies the precedent to the services themselves:

| Host (`workflows/`) | Takes | From |
|---|---|---|
| `GateHost` | `gate` | *exists* (`gates.py:54`) |
| `ReportHost` | `emit`, `stage`, `_track_usage` | `:1226-1281` |
| `RoleHost` | `run_role`, `cached_stage`, `revisable_stage`, `_check_budget` | `:1145-1177`, `:1283-1326`, `:1711-1742`, `:1773-1805` |
| `BenchmarkHost` | `record`, `judge`, `_stage_record`, `_benchmarking` | `:874-924`, `:1012-1061` |
| `MemoryHost` | `recall`, `retain` | `:1062-1096` |
| `QuestionHost` | `ask_and_wait`, `answer_question`, `_pending`, `_question_answers` | `:1184-1187`, `:2845-2887` |
| `BoardHost` | the four publish helpers | `:928-1008` |
| `TaskHost` | `_dev_task`, `_merge_task` | `:1807-2368` |

Flat modules, matching `harness/` and the existing `gates.py`. Benchmark and memory are one group in B0 but two files here: 139 lines whose halves share nothing.

`feature.py` then retains the module header (~150), `__init__` (45), the gate callbacks (46), the `run_summary` / `run_state` queries (33), `run` (23), a ~12-line `_retro` dispatch, and the `_pipeline` and `_build_and_merge` skeletons — **~620-780**. The skeletons are the uncertain term: 156/158 is their floor, not their expectation, since each must retain its intake and integration blocks (`:2513-2549`), the research revise-gate loop, the wave/serial task loop (`:3224-3258`) and the deploy retry tail. The margin under the ceiling is 220-380 lines.

**Two hazards the mixins create.** First, hosts share instance state across the MRO: `answer_question` pops `_pending` (`:1187`), `_stage` writes `_status` (`:1241`), `run_state` reads `_gate_decisions` / `_status` / `_role_usage` / `_trace` (`:1201-1221`). `__init__` (`:826-870`) initialises all of it monolithically today; A partitions it across hosts with a cooperative `super().__init__()` chain and an attribute-ownership table in `workflows/AGENTS.md`. Second, **signal and query names are wire contracts.** `submit_gate_decision`, `answer_question`, `run_summary`, `run_state`, `status`, `pending_gate` and `pending_decisions` carry no `name=` override, so the handler name *is* the function name; moving these methods between modules must not rename them. A duplicate name across two mixins fails loudly at import (`_definition.py:307-328`), which is the failure mode we want.

### 3.2 `StageContext` is constructed, not `self`

`core/context.py` defines the Protocol; `FeatureWorkflow.__init__` builds one frozen `StageServices` from its own bound methods and stores it as `self._ctx`. Construction is unconditional and lives in `__init__` — never lazily inside a step, where a conditional construction could diverge on replay — and the module is passed through the sandbox block. Building a dataclass of bound-method references issues no commands and no I/O, so it is byte-identical on replay.

B0 says passing `self` "would expose everything", and A honours that literally: a step physically cannot reach `self._pending`. The alternative — annotating `self` as the Protocol and letting mypy police it — is rejected on two grounds, and one commonly-cited third ground is explicitly **not** among them. mypy is clean on this tree (`Success: no issues found in 250 source files`), so "the type checker is unreliable here" would be false; the real reasons are that a constructed surface is enforced at runtime rather than only at check time, and that it gives `tests/<stage>/` a natural fake — a step is unit-testable by handing it a `StageServices` of stubs, with no workflow and no Temporal environment at all.

### 3.3 The step contract

```python
async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief,
    codebase_map: CodebaseMap | None,
    clarify_agent: TemporalAgent,
    route_agent: TemporalAgent,
    probe_agent: TemporalAgent,
) -> ClarifiedRequirements: ...
```

Keyword-only after `ctx`. Run context — the codebase map, integration head, brief digest, seeded work — arrives as parameters, never as context fields.

**Agents arrive as parameters too**, and this is not a stylistic choice. `agents/roles.py:21-22` imports `..clarify.models` and `..clarify.prompts` at import time to construct the two fan-out agents. Once clarify moves, that becomes `..stages.clarify.*`, which executes `stages/__init__.py` (holding `STAGE_MODULES`, hence importing every slice) and `stages/clarify/__init__.py` (which exports `step`). A step module that imports the registry for `t_clarify` therefore deadlocks the worker at boot with a partially-initialised module. Passing agent handles in is B0's own parameter-vs-service rule applied to agents, it inverts the dependency to one direction, and `_run_role` (`:1283`) already takes `agent` as a parameter. It also makes "which roles does this stage run?" answerable from the signature.

### 3.4 Artifacts are published by the orchestrator

`_board_publish` is called today from inside the clarify, architecture and plan blocks (`:2910`, `:3085`, `:3147`) but is not one of the eleven services. Rather than grow the protocol to twelve, `_pipeline` publishes the step's return value after it returns. Two envelope fields make this work: the plan publish returns `_plan_version` (`:3147`), which feeds every subsequent board task write (`:974`, `:981`, `:1001`), so the plan step's envelope carries `version_id` back; and the architecture publish passes `approved=gate.approved`, so that envelope carries the gate decision alongside the artifact.

This is the worked example of B0's parameter-vs-service review question, and the spec records it as a refusal rather than an omission.

### 3.5 Slice prompts must salt the memoization key

`_cached_stage` keys on `PROMPT_SHAS[stage]` (`:1166`), and `PROMPT_SHAS` (`agents/roles.py:182`) hashes `agents/<role>/instructions.md` bytes only. Editing a prompt that lives anywhere else serves a stale memo.

**This defect predates A.** `src/sdlc/clarify/prompts.py` is already outside the hash, as are the builders in `src/sdlc/prompts.py`, and `MODEL_SETTINGS` (applied at agent construction, `roles.py:131`, `:139`) affects every output while appearing in no key term. `content_key` (`memoization/cache.py:18-23`) takes `(stage, input_json, prompt_sha, model_id, upstream_recall_ref)`. E-85 already patched the clarify case locally: `_clarify_memo_extra` (`:350-372`) folds `probe_prompt_digest()` into the input.

Moving prompt assembly into fifteen slices turns one local patch into fifteen, so A generalises it: **every slice's `prompts.py` exports `prompt_digest()` over its own prompt constants, templates and effective model settings, and `cached_stage` folds it into the key.** Two migration notes: adding key terms invalidates existing memos once, and `_clarify_memo_extra`'s flag-off guarantee (`:368-371`, an empty extra when the fan-out is disabled, so flag-off runs key exactly as before) must be preserved by the generalisation.

## 4. The four Temporal rules, as they bite here

- **Rule 1 — handlers on the MRO.** Satisfied by construction: every host is a mixin of `FeatureWorkflow`; no step module defines a handler.
- **Rule 2 — one owner for mutable run state.** `_escalation_round` (`:865`, incremented `:2025`) stops being instance state. It becomes a `TaskHost` loop local, passed into `stages/code/step` and returned in its envelope. This is the defect `gates.py:84-88` already documents for gate confidence — under wave mode a second gate opening while one awaits a human overwrites a stashed value — fixed rather than carried across.
- **Rule 3 — the passthrough principle.** Each slice passes through model modules (`core/models.py`, `workflows/models.py`, its own and its upstreams'), third-party and IO-adjacent imports, and child-workflow classes. **`workflows/models.py` joins the passthrough set**, being a model module staged code imports. **The agent registry drops out of the category list for step modules** (§3.3); it remains required for `feature.py` itself.
- **Rule 3a — child-workflow handles.** `CrewTaskWorkflow` (started at `:1937`) and `DeploymentWorkflow` (`:3601`) stay in `workflows/` and are passed through by the slices that start them.
- **Rule 4 — module level is constants only.**

**Child workflow classes stay in `workflows/`; a slice never holds a `@workflow.defn`.** An orchestrator coordinates, and a slice is what an orchestrator calls. `CrewTaskWorkflow` is not code's private machinery — `src/sdlc/crew/` is already a horizontal package, the crew has its own roadmap group and its own `pytest -m crew` tier, and it is reachable independently of a feature run. **The cost is real and is documented rather than left as drift:** the deploy stage ends up with its artifacts and activities in `stages/deploy/` and its child workflow in `workflows/deployment.py`. That is the one stage whose code sits in two directories, justified because a registered workflow class is worker-facing infrastructure and `worker.py:162-171` is the single list a reader consults.

## 5. Cutting the two horizontal files

**`activities.py` is deleted.** Stage-owned activities go to their slice: `run_coding_task` (`:573`) to code; `run_test_suite` (`:707`), `run_lint` (`:850`), `security_scan` (`:951`) to qa; `classify_repo` (`:1342`) and `check_brownfield_delta` (`:1402`) to context; `measure_coverage` (`:985`), `run_integration_checks` (`:1210`), `open_pull_request` (`:1274`) and `evaluate_gate` (`:1331`) to merge, whose call sites are at `:3348` and `:3381`.

The residue is git and worktree plumbing that belongs to no stage: `create_worktree`, `setup_integration_branch`, `merge_into_integration`, `build_verification_branch`, `get_task_diff`, `read_committed_bytes`, and the ~240 lines of private helpers behind them (`_git`, `_ensure_worktree`, `_rmtree_with_retry`, `_find_live_worktree_for_branch`, `:66-302`). These become `src/sdlc/vcs/` with its own `ACTIVITIES` list. The evidence that this is not stage-owned is direct: `build_verification_branch` is imported and executed by `workflows/tidyup.py` (`:24`, `:334`), a different domain, and is never called from `feature.py` at all. `vcs/` rather than `git/`, so it does not read as a vendored wrapper for the `git` CLI. The Windows retry logic is the strongest case for a dedicated home — it is hard-won, has nothing to do with any stage, and is currently invisible at the bottom of a file people import for other reasons.

Four activities that stay stage-side still call `_git` and will import it from `vcs`: `run_coding_task` (checkpoint commits, `:616-639`), `classify_repo` (`:1351-1370`), `check_brownfield_delta` (`:1411-1414`) and `open_pull_request` (`:1304-1314`). P0's map names them, or the split gets discovered mid-P2.

Keeping a shrunken `src/sdlc/activities.py` for the shared few was rejected: a module named for a technical layer is the shape B0's Decision bans, and it would sit on the baseline forever as the place ambiguous activities accumulate.

**`adapters.py` becomes flat modules under `harness/`**: `base.py` (`:55-343` — the scaffolding and the `CodingHarness` ABC), `claude_code.py` (`:344-675`), `opencode.py` (`:676-913`), `cursor.py` (`:914-1053`), `registry.py` (`:1054-1092`). Largest resulting file ~330 lines; 20 importers re-point. A nested `harness/adapters/` package whose `__init__.py` preserved the old paths was rejected under §2.3: it keeps a technical-layer word as the public surface of five cohesive modules and hides `ClaudeCodeHarness`'s home from anyone grepping.

## 6. Migration

Four phases. The baseline is the scoreboard.

**P0 — archaeology, zero code edits.** `docs/reports/2026-09-03-feature-py-archaeology.md`, per `docs/modes/report-first.md`. For each of the fifteen stages: line range in `feature.py`, every `self._x` touched, which of the eleven services each maps to, capabilities no service covers, enum-identity sites, child workflows started. It produces two things A depends on — the **complete ownership map** for all 73 models and 16 activities under §2.2's rules, and the **migration order**. *Exit: the report exists and `git diff --stat` touches nothing outside `docs/reports/`.*

**P1 — machinery and pilots.** `core/context.py`, `core/models.py`, `stages/`, `STAGE_MODULES`, the seven host mixins and `StageServices`, the two slice templates, the clause marker and its report; `clarify` and `qa` moved whole — step, activities, models, prompts, both documents, tests. The hosts alone take roughly a thousand lines off `feature.py`, `TaskHost` accounting for over half of it since `_dev_task` moves whole in P1 and sheds its stage bodies later. *Exit: baseline still five entries with `feature.py` down by a third; `pytest -m temporal` green.*

**P2 — the three horizontal cuts, one sweep.** `models.py` deleted, `activities.py` deleted into `vcs/` and slice files, `adapters.py` flattened. *Exit: baseline **5 → 2**; the `src/` entries reduce to `feature.py` alone.*

**P3 — the remaining thirteen steps**, in P0's order. *Exit: `src/` entries reach **zero**.*

**A is done when `.file-size-baseline.json` holds only `tests/test_assessment_workflow_e2e.py`,** which is out of scope by the `Does not cover` section above and whose owner is named there.

**Order criterion.** Stages sort ascending by count of uncovered needs, then by enum-identity sites, then by child workflows started. Mechanical stages follow the pilots; the ones most likely to force a contract change come last, when the contract has the most evidence behind it.

**The migration table gains a third status.** During P3 an unmigrated stage's types live in `stages/<stage>/` while its step is still inline, so `AGENTS.md`'s table carries `in feature.py` → **`types moved, step pending`** → `migrated`. This is the strongest objection to the phase order and the cost is real: for the length of P3, eleven stages sit in three places rather than two. It is accepted because the table is declared authoritative and stays honest, and because the alternative — every stage carrying its own types out — spreads the same 261-file re-point across thirteen partial commits, each leaving the tree in a different half-state, with `models.py` reading 1334 on the scoreboard until nearly the end.

**The re-point is measured, not adjectival.** Deleting `models.py` touches **261 files and ~286 import statements** (85 in `src/`, 176 across `tests/`, `scripts/` and `interfaces/`). Deleting `activities.py` touches **40 files** — 7 in `src/` (`worker.py`, `workflows/feature.py`, `workflows/tidyup.py`, `crew/activities.py`, `assessment/activities.py`, `triage/activities.py`, `benchmarks/oracle.py`) and 33 tests. Flattening `adapters.py` touches 20. Under B0 §1.4 there are no shims, so each set re-points inside its own commit.

**One test file gates P2.** `tests/fakes/fake_activities.py` imports 17 input/output types from `sdlc.activities` (`:10-27`) plus `sdlc.context.*` and `sdlc.models`, and defines `GIT_FAKES` (`:191`); every `temporal`-marked test routes through it. It re-points in the same commit, and its `@activity.defn(name=...)` strings must keep matching production activity names or Temporal dispatch silently fails to bind.

**The P2/P3 checkpoint.** At the boundary — three monoliths deleted, `feature.py` the only `src/` entry left, eleven slices half-populated — the plan stops for an explicit re-commitment to finish or a decision to stop with the table telling the truth. This is B0's "permanent hybrid" risk, and this phase order is chosen partly so that a stall lands after three files are gone rather than with four merely trimmed.

## 7. Corrections to B0

B0 is write-once and is not edited. A's plan is derived from it, so where it is wrong the correction is recorded here.

1. **`qa` does not force the gate service.** B0 §1.1 and §7 cite `feature.py:2026` and `:2287` as qa's, justifying `StageContext.gate` and the choice of qa as a pilot. Reading `_dev_task`: `:2025-2026` is the tool-approval gate fired when the *coding* harness hits a containment restriction, and `:2287` is the loop-level task gate whose verdict spans all three stages. The enum-identity sites at `:1891`/`:1927` and the crew child workflow at `:1937` are likewise the coding path, not qa. Under §3's shape they belong to `stages/code/` and to `TaskHost`. `gate` stays on the protocol regardless — `_revisable_stage` uses it, and the architecture, plan, merge and deploy steps call it directly — so the inventory holds, but qa forces `record`, `judge` and `run_role`, not `gate`.
2. **A step cannot import the agent registry.** B0 §1.2 Rule 3 states that "a step cannot reference `t_clarify` / `t_qa` / `resolve_role_model` without importing it" and lists the registry as a passthrough category. Doing so deadlocks the worker at boot (§3.3). Agents travel in the signature instead.
3. **`STAGE_MODULES` does not collapse `worker.py`'s import block.** B0 §1.3 presents the 103-line block as what the registration contract removes. Only ~16 of those lines come from `sdlc.activities` (`worker.py:29-46`); the remaining ~87 import from `assessment`, `triage`, `benchmarks`, `crew`, `memoization`, `memory`, `notify` and `observability` — horizontal domains outside `STAGE_MODULES`. The block shrinks; it does not disappear.
4. **Stage extraction alone leaves `feature.py` over the ceiling** (§Problem), which is why §3.1 exists. B0 assumed the surgery was a matter of moving stage bodies.

## 8. Tests

Stage-named test files move to `tests/<stage>/` with **basenames unchanged** — there is no `tests/__init__.py`, so pytest's rootdir collection requires globally unique module basenames once files scatter. `tests/clarify/test_clarify_routing.py`, never shortened to `test_routing.py`. Cross-cutting tests that exercise `FeatureWorkflow` across several stages go to `tests/integration/`. `conftest.py`, `fakes/`, `fixtures/` and `helpers_risk.py` stay at the root permanently; the root does not have to end up empty.

The root holds 451 `.py` files today and the stage-named subset depends on the matching rule — a narrow prefix match gives ~70, a broad one 93 — so **P0 emits the exact move list** rather than the plan trusting an estimate.

## 9. Clauses

Slice documents carry locally numbered clauses anchored to an `FR-xxx`, `NFR-x` or `E-xx`, per B0 §4 and `docs/modes/feature-clause-writing.md`.

B0 deferred one question to A: whether pytest gains a marker citing clause IDs. **It does** — `@pytest.mark.clause("CLARIFY-1.4")`, registered in `pyproject.toml`, plus a script cross-referencing markers against the clause headings in `<stage>.md` and reporting orphans in both directions. Advisory output; nothing fails.

**CI enforcement is refused for now, and the reason is not squeamishness.** Kroker already implements criterion→test traceability *as a product feature* — `untraced_criteria` (`feature.py:528`), FR-106, the analyst stage — and B0 §4 draws a hard line against repurposing the product's machinery as this repository's own development harness without a decision that says so. Building an enforcing second traceability system before two pilot slices have produced a single clause would cross that line on speculation. The advisory report generates the evidence that would justify the gate: if the pilots' orphan report is consistently empty and consistently useful, promoting it is a three-line change to `.pre-commit-config.yaml`.

## 10. Verification

Per stage move and per phase:

```bash
pytest -m "not slow and not temporal"
pytest -m temporal
python scripts/check_file_size.py --full
pre-commit run --all-files
```

`pytest -m temporal` is excluded from the default run by `pyproject.toml`'s `addopts`, so it is named as an **explicit per-phase commit gate**; otherwise the replay invariant is never exercised.

That invariant, stated so a reviewer can check it: **the sequence of activity, timer and signal commands a run issues is unchanged.** Replay validates the command sequence against history, not the source location of the code that issued it, so relocation is safe and reordering awaits is not. Payload identity is a non-issue — `pydantic_data_converter` records no class path — and there is no `workflow.patch` anywhere in `src/`.

## 11. Deliverables

1. `docs/reports/2026-09-03-feature-py-archaeology.md` — the ownership map and the migration order.
2. `src/sdlc/core/{context.py,models.py}` — the `StageContext` Protocol and the shared kernel.
3. The seven host mixins under `src/sdlc/workflows/`, plus `workflows/models.py` and `workflows/AGENTS.md` carrying the attribute-ownership table.
4. `src/sdlc/stages/` with fifteen slices, each with its seven files, and `STAGE_MODULES`.
5. `src/sdlc/vcs/`; `harness/` flattened into five modules.
6. `src/sdlc/models.py` and `src/sdlc/activities.py` deleted; roughly 300 distinct files re-pointed across the three cuts.
7. `tests/<stage>/` and `tests/integration/`, per P0's move list.
8. The `clause` marker, its registration, and the orphan report script.
9. `prompt_digest()` in every slice's `prompts.py`, folded into `content_key`.
10. Root `AGENTS.md` migration table maintained at every move, with the third status.

## Risks

**The permanent hybrid.** Unchanged from B0 and still the top risk, now with a named checkpoint at P2/P3 and a scoreboard that moves 5 → 2 → 1 rather than staying at four until the end.

**Ownership map errors surface in P3**, after P2 has re-pointed. Mitigated by §2.2 making placement mechanical rather than a judgment, and bounded: a misfiled type is one `git mv` plus its importers, not a re-plan.

**The three-location interval** during P3 (§6). Accepted, bounded, and visible in the table.

**`StageContext` accreting.** `board_publish` was the first pressure and was refused (§3.4); the refusal is recorded as the worked example for the next one.

**Mixin state coupling.** Seven hosts sharing instance attributes is a new coupling surface. Mitigated by the attribute-ownership table and by `temporalio`'s loud failure on duplicate handler names; the residual is that a host reading another's attribute is legal Python and only the table forbids it.

**The 1000-line ceiling is deliberately loose.** If slices routinely land near 900, B0 §2 says that is evidence the seam was drawn wrong, not that the number should change. The two to watch are `harness/claude_code.py` (~330) and `core/models.py` (~449).
