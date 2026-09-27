# Pipeline Canvas v4 — design feedback against the current pipeline

| | |
|---|---|
| Status | Design brief — **not scope**. Input for the next design pass; nothing here is committed work. |
| Date | 2026-09-27 |
| Design | `Pipeline Canvas v4 (standalone).html` (claude.ai/design project, exported to `docs/reports/`). Four screens — Pipeline (Observe / Design), Runs, Graphs, Interfaces — and a mock data model (`ROOT`, `SUB`, `KIND`, `STAGES`, `CATALOG`, `CONFIGS`, `IFACES`, `MATRIX`). |
| Checked against | `main` @ `eb34fe1` plus working tree: `src/sdlc/workflows/graphs/*.graph.yaml`, `src/sdlc/graph/node_types.py`, `src/sdlc/core/models.py` (gate policies, execution mode), `src/sdlc/stages/code/step.py`, `src/sdlc/workflows/build.py`, `src/sdlc/board/`, and the delivered 002 frontend (`interfaces/dashboard/frontend/src/`, `interfaces/ui/src/components/`, `interfaces/ui/src/tokens/tokens.css`). |
| Companions | `2026-09-27-pydantic-ai-capability-adoption-map.md` §4 (planned node types), `2026-09-27-pydantic-ai-harness-upgrade-matrix.md` §2.6–2.7 (doer variants). |

The design predates the typed graph (E-72 → E-77). Its interaction ideas are sound. Its **model** is the old stage pipeline: node kinds, node set, edges, payload names and the code-task internals all differ from what the code runs. §1 lists what to keep; §2 is the model correction, which is the bulk; §3 goes screen by screen; §4 lists what to add; §5 covers visual alignment.

## 1. Keep

- **Observe and Design on one canvas**, with a mode switch. The code has both halves: the E-77 run mode (`features/run/RunView.vue`, `runGraph.store.ts`) and the graph editor (`features/graphs/GraphEditorView.vue`).
- **The `content_sha` note**, which is exact ADR-11: layout and labels are excluded, edges are not. So is "Save version before Run": a run pins the sha.
- **The run rail**: spend against budget, the path reached and not reached, graph events newest-first, and a "decision waiting" call-to-action.
- **Traversal counters on back edges** ("fix 1 / 2"). This is `max_traversals` made visible.
- **An inspector with typed inputs and outputs**, evidence, and details.
- **The pre-registered selection rule on Compare** (ADR-20), and the idea of a slot-compatibility matrix on Interfaces.
- **Validation as a first-class panel** in Design mode.

## 2. Model corrections

### 2.1 Nodes: design → code

The shipped default graph (`default.graph.yaml`) has 12 nodes. `default-research.graph.yaml` adds `research`, and `seeded.graph.yaml` replaces the pre-code half with `seed.spec` / `seed.plan`.

| Design node (`ROOT`) | Design kind | In the code | Change |
|---|---|---|---|
| `intake` "Intake" | router | `intake` — stage; out-ports `ok` (greenfield), `brownfield`, `reject`, `fail` | Keep. It is a stage whose **two out-ports** do the routing; there is no router kind. |
| `constitution` | det step | **does not exist** | Remove. |
| `context` "Codebase context" | agent | `context` — stage, role-less; in `trigger`, out `map:CodebaseMap`, `reject`, `fail`; wired only from `intake.brownfield` | Keep, and draw it as reachable only on the brownfield port. |
| `requirements` "Requirements" | agent | **does not exist** — `clarify` emits `ClarifiedRequirements` | Remove; fold into clarify. |
| `clarify` "Clarify" | **gate** (soft · 0.80 · rounds 3) | `clarify` — **stage** with role `clarify`. The catalog says: "No gate.clarify: clarify's HITL is a Q&A channel inside its handler". Questions go to the Inbox; the fan-out is E-85. | Draw it as a stage with a question-channel badge, not as a gate. There are no approve/revise ports. |
| — | — | `research` (optional; `default-research`) — stage, role `research`; out `brief:ResearchBrief` | Add, as an optional node, together with `gate.research`. |
| `architecture` | agent | `architect` — stage, role `architect`; in `requirements`, `codebase_map?`, `guidance?`; out `spec:ArchitectureSpec`, `fail` | Rename the id and type. |
| `archgate` "Architecture approval" | gate (hard · rounds 2) | `gate.architecture` (node id `architecture`) — in `artifact:ArchitectureSpec`; out `approve:ArchitectureSpec`, `revise:GateDecision`, `reject` (terminal) | Keep. "Rounds" is **`max_traversals: 2` on the revise edge**, not a gate parameter. |
| `planning` | agent | `plan` (node id `planner`) — role `planner`; out `plan:ImplementationPlan` | Keep. The `ValidationContract` is part of the plan, not a second port. |
| `plangate` "Plan approval" | gate | `gate.plan` (node id `plan`); policy default **SOFT** (`core/models.py:338`) | Keep. Show the policy as it is configured. |
| — | — | `plan_check` — role-less stage; in `plan`; out `ok:ImplementationPlan`, `halt`, `fail` | **Add.** It is a deterministic check between the plan gate and code. |
| `code` "Code task" | subsystem | `code` — a single coarse stage (U1); in `plan:ImplementationPlan`; out `results:BuildResult`, `halt`, `fail` | Keep it as one node; see §2.5 for the drill-down. |
| `analyze` "Quality analysis" | det step | `analyze` — in `results:BuildResult`, `plan:ImplementationPlan`; out `analysis:AnalyzeResult` | Keep; fix the ports. There is no `SecurityReport` input. |
| `secref` "Security review" | graph reference | **does not exist**; there is no graph-reference mechanism | Remove, or mark "planned" (§4). |
| `mergegate` "Merge approval" | gate node | **inside** the `merge` stage — `GateConfig(policy=HARD, on_timeout=HOLD)` (`core/models.py:342`) | Replace with the `merge` stage (in `results`, `plan`, `spec`, `analysis`; out `pr:PullRequest`, `reject`, `fail`) carrying a **gate badge**. |
| `deploy` "PR + deploy" | det step | `deploy` — in `pr:PullRequest`; out `done`, `fail` | Keep; its gate (HARD) is internal, as with merge. |
| `deploygate` "Deploy approval" | gate node | inside `deploy` | Remove as a node; show it as a badge. |
| `retro` | agent | **not a graph node** — runs after the run terminates (E-32, `workflows/feature.py:295`) | Show it outside the graph (run footer / post-run), or as "planned node" (§4). |

### 2.2 Edges are port-to-port data flow, not a chain

The design draws one line from block to block. The default graph fans out and in:

- `context.map` → `clarify.codebase_map` **and** `architect.codebase_map`;
- `clarify.requirements` → `architect.requirements` **and** `planner.requirements`;
- `architecture.approve` → `planner.spec` **and** `merge.spec`;
- `plan_check.ok` → `code.plan`, `analyze.plan` **and** `merge.plan`;
- `code.results` → `analyze.results` **and** `merge.results`;
- back edges: `architecture.revise → architect.guidance` and `plan.revise → planner.guidance`, both `max_traversals: 2`.

The layout needs multi-input nodes and labelled port anchors on both ends. An edge is `source.source_port → target.target_port`.

### 2.3 Ports and terminal outcomes

- Every stage type carries **`fail:NodeFailure`** (terminal `failed`). Some also carry **`reject`** (terminal `rejected`) or **`halt`** (terminal `failed`, domain failure). Gates carry `approve`, `revise`, `reject`.
- The design shows **no terminal ports and no run outcome**. Add:
  - sink markers for `rejected` and `failed`;
  - the run's outcome string (done / rejected / failed / halted);
  - the **unrouted failure** state: a `fail` emitted on a port with no edge (`UnroutedFailure` in `graph/run_view.py`).

### 2.4 Payload types and compatibility

The compatibility rule is `ports_compatible`: **exact nominal equality — no `Any`, no subtypes, and signal ports only to signal ports.**

| Design | Code |
|---|---|
| `IntakeSpec`, `Constitution`, `Requirements` | — (intake ports are signals) / — / `ClarifiedRequirements` |
| `DevTask[]`, `ValidationContract` | inside `ImplementationPlan` |
| `CodeArtifact`, `HandoffSummary[]` | `BuildResult` |
| `QualityReport`, `SecurityReport` | `AnalyzeResult` |
| `MergeDecision` | `PullRequest` (plus the internal gate decision) |
| `DeployReport` | signal `done` |
| `Guidance` (revise) | `GateDecision` |
| — | `CodebaseMap`, `ResearchBrief`, `ArchitectureSpec`, `NodeFailure` |

In Design mode:

- palette templates must not use `in:Any` / `out:Any`;
- `compat(a, 'Any')` must go;
- a mismatched connection must be **refused at drop time**, not accepted with the toast "Connected with a type mismatch — see validation".

### 2.5 Node kinds

The catalog has `kind: stage | gate`, plus `role` (a registry role, i.e. agent-backed, or `None`, i.e. deterministic) and `canonical_stage`. Only two of the design's 13 kinds exist. What the rest become:

| Design kind | In the code |
|---|---|
| agent / det step / harness | `stage` with a `role` / without one. A harness runs *inside* `code`, not as a node. |
| gate | `gate` (`gate.research`, `gate.architecture`, `gate.plan`) |
| router | multiple out-ports on a stage |
| loop | a back edge with `max_traversals` |
| memory, artifact | not nodes: memory is I/O in activities (ADR-5); artifacts go to the claim-check store (ADR-10) |
| subsystem, graph reference, variant, port, activity | do not exist |

**Palette:** build it from the node-type catalog the frontend already loads (`shared/catalog.store.ts`, `ui/components/node_palette`), grouped by `canonical_stage`. Not from the invented Understand / Design / Plan / Build / Verify / Ship templates.

### 2.6 The "Code task" subsystem

`code` is one node. The per-task loop lives in the stage handler (`stages/code/step.py`), the task scheduler (`workflows/build.py`) and the crew child workflow (`workflows/crew.py`). There is no editable subgraph.

What really happens per task:

1. **Scheduling.** `execution_mode` is `serial` or `waves` (`core/models.py:224`). Waves run a ready batch whose `overlaps` are disjoint, in parallel, then merge in order.
2. **A worktree**, then a **harness session**: `claude_code`, `opencode`, `cursor`, or `crew` (lead + critic, child workflow). **Codex is not a harness.**
3. **Test freeze and drift backstop (C2).** A repair attempt cannot edit tests (rule `no-test-edit-during-repair`) unless an operator thaws them.
4. **Tool escalations** from containment: a denied tool call becomes a `DeferredToolUse` and an E-17 gate. The operator answers approve or deny.
5. **Review and QA** in clean context, plus deep review and the adversary lens when enabled. There is a bounded repair budget and session resume (`max_session_resumes`, with a fresh session past the context ceiling).
6. **A per-task gate `task:<id>`** once repairs are exhausted: approve → `done`; revise with guidance (optionally thawing tests) → retry; reject → **`quarantined`** (`step.py:956`).
7. **Merge** of a done task into the integration branch.
8. **Board.** Claims and status go to the board (ADR-21). `quarantined` is a board status, "an operator verdict".

Design changes:

- Make the drill-down **read-only**, as a view of this loop. It is not an editable subsystem.
- Swap the variant list for the real harnesses.
- Fix the escalation card:
  - **Quarantine does not "continue with the other tasks".** A quarantined task makes the build return `failed:quarantined-tasks` after the current wave (`build.py:115`). Say so on the button.
  - "Retry" is **revise with guidance**, with a "thaw tests" checkbox.
  - "Accept" is **approve**.
- A tool escalation is a different card: approve or deny for one tool call, with the rule id.

## 3. Screen by screen

### Pipeline — Observe

- **Budget.** Bind to `PipelineConfig.run_budget_usd`, not a hardcoded "$25". The default is `0.0`, meaning off. Crossing it raises a hard `budget` **gate**; approve grants one more increment, and reject ends the run `rejected:budget`. (`max_run_cost_usd` is the research stage's own ceiling, not the run budget.)
- **Per node:**
  - the model that actually answered;
  - per-role cost (E-33);
  - `canonical_stage` attribution (E-77);
  - traversal count on each revise edge.
- **Run-level outcome and unrouted failure** (§2.3).
- **The events rail** should use the real event kinds: gate decisions, tool escalations, budget halts, task status changes.
- **Decision card** must match the real Inbox cards:
  - `question-v1` from clarify;
  - a gate decision (approve / revise-with-guidance / reject);
  - a tool escalation (approve / deny);
  - a per-task gate (§2.6).

  "Expires … escalates to the approver" should follow the gate's configured timeout action (`TimeoutAction`, e.g. HOLD on merge).
- **Navigation.** The 002 app ships **Fleet**, **Inbox**, and a run page with tabs **Graph · Board · Gates · Cost** (Gates and Cost disabled). The design's top bar (Pipeline / Runs / Graphs / Interfaces) has **no Inbox and no Board**. Add both. The board tab is the task-level view the code drill-down should link to.

### Pipeline — Design

- The palette comes from the catalog (§2.5).
- **Validation.** Keep reachability, port compatibility, bounded cycles and references (drop references until they exist). Add:
  - every **required** in-port is connected;
  - gate shape (`_gate_shape_problems`);
  - every path reaches a terminal outcome;
  - `max_traversals` is present on each back edge.
- Remove the "Memory target missing" and "Critic harness unavailable" issues from the canvas. The first is not a graph concern. The second belongs on Interfaces (worker capability), not in graph validation.

### Runs

- **History.** "Loops" means traversals. Keep the graph `sha` column; add `canonical_stage` of the last node.
- **Compare.** Today the benchmark varies **arms** (model × harness) and **graphs** (`default` vs `default-research`). Serial vs waves is a **configuration** (`execution_mode`), not two graphs with two shas. Crew is a harness choice inside `code`, not a graph (`crew-code` does not exist).

  Show:
  - SC composite and cost per case;
  - the per-`canonical_stage` heatmap;
  - the pre-registered rule.

  Fix the mock: "Graph B · waves" → config `waves`; "crew-code" → arm `harness=crew`.

### Graphs

- **Catalog = shipped graphs:** `default`, `default-research`, `seeded`. Drop `code-task`, `security_review`, `crew-code`, `hotfix-v1`, `tier0-triage` as graphs.
  - Triage and assessment are separate workflows (`workflows/triage.py`, `assessment.py`), not graphs in this catalog.
  - If they should appear, label them as workflows.
- **"Configuration sets"** are `PipelineConfig` plus the role registry (`agents/*/agent.yaml`) plus benchmark arms.
  - Show the gate policies as configured: clarify HARD, architecture HARD, plan SOFT, merge HARD with HOLD, deploy HARD.
  - Show the budget and `execution_mode`.
  - "Reviewer: other family, enforced" is the ADR-6 check (`validate_run_roles`). Show it as a pass/fail status, not prose.

### Interfaces

- **Rows:** `claude_code`, `opencode`, `cursor`, `crew`, plus `pyai` as planned (upgrade matrix §2.6).
- **Columns:**
  - containment layers declared (`native` / `hook`, ADR-17, `strict`);
  - model family ≠ reviewer (ADR-6);
  - harness installed on the worker;
  - checkpoint commit;
  - session captured (ADR-16).
- **Error examples:** replace the Codex and ResearchAgent ones with real adapter facts. opencode has no config flag for the hook layer; cursor surfaces neither layer and fails closed (`ARCHITECTURE.md` "adapter reality").

## 4. Planned nodes to add to the palette (marked "planned")

From the adoption map §4. Each has typed ports and a payload in `graph/payloads.py` when built:

| Node | Purpose | Sketch of ports |
|---|---|---|
| `verify` | independent verification by another model family, blind to the coder's tests | in `results:BuildResult`, `plan:ImplementationPlan` → out `report:VerificationReport`, `fail` |
| `review.static` | Macroscope as an outside lens, advisory | in `results` → out `findings`, `fail` |
| `stack.up` | bring the project's stack up before merge | in `results` → out `stack:StackReport`, `fail` |
| `smoke.browser` | Playwright walk of the DoD against the stack | in `stack:StackReport` → out `smoke:SmokeReport`, `fail` |
| `intake.issue` / `intake.document` | GitHub / Linear issue or a document as the idea | out → same as `intake` |
| `publish.tasks` | project the approved plan to Linear / GitHub issues (observational) | in `plan` → out signal |
| `retro` | as a node instead of post-run | in terminal signal → out `RunSummary` |
| `outcome.watch` | FR-1100 product outcome after deploy | in `done` → out outcome |

The doer slot on Interfaces gains `pyai` (in-process Pydantic AI coder built from Harness parts).

## 5. Visual alignment

- The design ships its own palette and type: IBM Plex, `#0d1015`, a custom status set. The app runs on the 002 pass-three tokens (`interfaces/ui/src/tokens/tokens.css`):
  - grounds: `--ground-0…5`, `--ground-canvas`, `--ground-shell`, `--ground-raised`;
  - ink: `--ink-primary`, `--ink-secondary`, `--ink-muted`, and the rest of the `--ink-*` set;
  - lines: `--line`, `--line-strong`, `--line-faint`;
  - status: `--status-{done,running,waiting,failed,blocked,idle,pending,quarantined,skipped}` with tints;
  - type and spacing: `--font-sans`, `--font-mono`, `--text-*`, `--space-*`, `--radius-*`.

  Re-skin onto these. Note that `quarantined` and `skipped` already have status colours; the design has no equivalent.
- **Compose from the existing component library** rather than bespoke markup: `app_header`, `tab_bar`, `graph_canvas`, `node_palette`, `detail_pane`, `gate_decision`, `status_pip`, `status_tag`, `timeline`, `fleet_table`, `issue_list`, `segmented_control`, `stat`, `toasts`, `yaml_pane`. The Observe/Design switch is a `segmented_control`, the decision card a `gate_decision`, the rail a `timeline`.
- Data in mocks should come from the frontend fixtures (`api/__fixtures__/`, `features/board/__fixtures__/`), so the design and the tests describe the same graph.

## 6. Priority for the next design pass

1. Replace the `ROOT` model with `default.graph.yaml`: nodes, port-to-port edges, terminal outcomes, real payload names (§2.1–2.4).
2. Collapse the kinds to stage and gate; build the palette from the catalog; reject mismatches at connect time (§2.4–2.5).
3. Make the code drill-down read-only with the real task loop and the real escalation, per-task gate and quarantine semantics (§2.6).
4. Add Inbox and Board to navigation; align the decision cards with the real card types (§3).
5. Fix Runs → Compare, Graphs and Interfaces mock data (§3).
6. Re-skin onto tokens and components (§5).
7. Add the planned nodes as a separate palette section (§4).

## 7. v5 review (2026-09-27)

`Pipeline Canvas v5 (standalone).html` was read in full: markup and the data/logic script. It adopts this brief almost entirely. What v5 got right:

- **Catalog and graphs.**
  - The node-type catalog is a faithful mirror of `node_types.py`: ports, required flags, payloads, `canonical_stage`, `budget_after`, gate shape.
  - All three shipped graphs match the YAML edge for edge, including `seeded`.
  - Port-to-port routing with fan-out.
  - `max_traversals` sits on the revise edges, with traversal counters in Observe.
- **Design mode.**
  - Connections are refused at drop time on payload mismatch.
  - Validation follows `graph/validate.py`: refs, gate shape, required inputs, reachability, bounded cycles, a path to a terminal outcome. Planned types are rejected as "not in NODE_TYPES".
  - The palette is the catalog grouped by `canonical_stage`, with planned types dashed.
  - Layout-only saves keep `content_sha`; config is outside the sha.
- **Nodes and config.**
  - Gate policies and `on_timeout` match the `PipelineConfig` defaults (merge `hold`, the rest `reject`; plan SOFT 0.80).
  - Clarify is a Q&A channel, with `clarify_question_cap` and `clarify_probes_enabled`.
  - Merge and deploy show their gate as a badge.
  - `code` is one node with a read-only inner loop.
  - The knobs `max_fix_attempts`, `max_tool_escalations`, `review_enabled` and the `HarnessKind` values are all real.
- **Screens.**
  - Inbox with the three `PendingKind`s (gate, clarify, escalation), plus Fleet, Board, and Compare (arms × graphs, SC weights 0.6 / 0.2 / 0.2, the E-36 heatmap).
  - Interfaces use the real harnesses and containment facts.
  - The per-node "model that answered" shows the override defect (comparison report §3.1).

What still disagrees with the code:

| # | v5 | Code | Change |
|---|---|---|---|
| V1 | Four sinks: completed, rejected, failed, **halted**; `HALT()` has `terminal:'halted'` | `OutcomeState` = `running · completed · rejected · escalated · failed` (`graph/run_view.py:43`). `halt` ports are `terminal="failed"`: the run ends **failed** with the node's result string, e.g. `failed:quarantined-tasks`, `failed:plan-validation:…` (`workflows/graph_nodes/postplan.py`) | Drop the `halted` sink and draw halt into **failed**, showing the result string. Add an **escalated** sink. Fix `HALT()` to `terminal:'failed'`. |
| V2 | No `escalated` outcome | The router ends the run **escalated** when a node emits on an unavailable port: a revise edge past `max_traversals` (`exhausted`) or a dead target (`target_dead`) (`graph/router.py:263`, `:446`) | On a revise edge at `2/2`, show "the next revise escalates the run". Validation copy "rejected, failed or halted" becomes "rejected, failed or escalated". |
| V3 | Completed = `deploy.done` only; unconsumed payload is a warning | Any edgeless **non-terminal** out-port is a completion sink; the run returns `completed:<nodes>` (`outcome_string`, `graph_dispatch.py:328`) | Warning text: "`X.port` has no edge, so it becomes a completion sink". The completed sink lists the sink nodes. |
| V4 | Tool-escalation card offers **Approve · Deny · Halt** ("Halt emits code.halt") | A tool escalation is a HARD gate. The decision grants or denies the one deferred call (`ToolGrant.approved`), and a timeout counts as not approved (`EscalationOutcome.TIMEOUT`). `code.halt` is emitted only when `run_tasks` fails (quarantined tasks, dependency cycle, merge conflict). | Remove Halt. Keep Approve and Deny, and show the timeout behaviour. |
| V5 | The per-task gate is only "then task escalation" in the inner loop | The per-task gate `task:<id>` after `max_fix_attempts`: approve → done; revise with guidance (+ `thaw_tests`) → retry; reject → `quarantined`, and the build ends `failed:quarantined-tasks` after the wave (`step.py:930–956`, `build.py:115`) | Add it as an Inbox gate card with those three actions and the consequence stated on Reject. |
| V6 | Budget $25 on the run; no budget card | `run_budget_usd` (default 0 = off). Crossing it raises a hard **`budget` gate**: approve adds one increment; reject → `rejected:budget` | Show the budget as optional. Add the budget gate to the Inbox kinds and the `rejected:budget` outcome to Fleet. |
| V7 | Board statuses `claimed`, `queued` | Wire `TaskStatus` = `pending · in_progress · done · failed · blocked · quarantined`, with `status` (live claim) separate from `authoritative_status`, plus `fix_attempts` (`features/board/board.types.ts`) | Use the wire statuses. Show live vs authoritative, as the board already does. |
| V8 | ADR-6 example: reviewer `google:gemini-3.5-flash`, dev `zai-coding-plan/glm-5.2` | The registry has reviewer and qa on `anthropic:glm-5.2` and dev on `zai-coding-plan/glm-5.2`. The prefix check passes, but it is the **same weights** (OQ-A4). | Show the real case. It is the more useful picture: "family check passes on prefix · same model weights". |
| V9 | `STAGE_ORDER` / `HEAT_STAGES` with 10 stages | `CANONICAL_STAGES` has 18, adding `constitution`, `requirements`, `review`, `adversary`, `handoff`, `deep_review`, `qa`, `retro`; the heatmap shows the ones present in the data | Order by `CANONICAL_STAGES`. Planned `outcome.watch` with `cs:null` would fail `check_node_types` (`require_mapped`); give it a stage or mark it unmapped. |
| V10 | Arm names `claude-sonnet-4.5` | Registry ids are `anthropic:claude-sonnet-4-5` | Use registry ids verbatim. |
| V11 | Own palette, IBM Plex; waiting colour changed to violet | 002 tokens and the component library (§5) | Still to do: re-skin onto `tokens.css` and compose from `interfaces/ui/src/components`. |
