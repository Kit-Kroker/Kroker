# Constitution stage (stage 1) — design

Date: 2026-11-11
Status: draft — awaiting human approval (builder check pending)
Owner: brainstorming session (superpowers), picked approach: **agent-drafted, off by default**

## Intent

Close FR-101's stage-1 box: build the constitution stage. Today there is no
`Constitution` model, no node, no consumer — yet the spec reserves it the top
of the context hierarchy ("recall can never override the constitution",
SDLC-spec-v2 §5). The human partner chose the FR-107 pattern: a proposer agent
*drafts* governing principles from the target repo's own conventions;
deterministic code validates and freezes them; the whole stage is off by
default (`constitution_enabled`), so default runs change nothing.

The human partner also asked: *which pydantic-ai-harness capabilities fit this
stage?* This document answers that with evidence from the installed package
and the repo's own history.

## Why

- FR-101 needs 4 stages; constitution is the only fully-greenfield one
  (quality_gate is built, research is scaffolded, requirements is a scope
  question of its own).
- Principles drafted *from the repo* (its AGENTS.md chain, its skills, its
  code) are grounded in what the project already enforces, instead of
  hand-written in a config file that drifts.
- The harness dep (`pydantic-ai-harness[codemode,exa]`) is pinned with one
  production use today — `CodeMode` on the research/exa provider path
  (`agents/research/agent.py:8`). This stage is its first `FileSystem` /
  `RepoContext` use, on the seam the repo already trusts (activity-side
  agents with loader-supplied capabilities first, role's own after).

## Goals

1. `Constitution` artifact: versioned, content-addressed (digest), memoizable.
2. A drafter agent that reads the target repo read-only and proposes
   principles with per-principle source references.
3. Deterministic validation ("the freeze"): schema + normative-statement
   checks; a principle without a source reference in brownfield is rejected.
4. Off by default; flag-off runs are byte-identical to today (default graph
   untouched, no new commands, memo keys unchanged).
5. Downstream: constitution digest joins `content_key` of
   clarify/architect/planner; principles render into their prompts below the
   idea, above recall.
6. Same-diff docs: stage contract `constitution.md`, slice `AGENTS.md`,
   PRD amendment, SDLC-spec-v2 row, ROADMAP rows (artifact boundary rule).

## Non-goals

- No human gate on the constitution (spec table row 1 has none; the draft is
  machine-validated, not negotiated). Revisit only if drafts prove noisy.
- No fan-out, no refine rounds (research's machinery is not warranted for one
  small artifact).
- No editing flow — the stage drafts once per run; amendment flows
  (constitution-as-code) are future scope.
- Requirements stage (stage 3) — separate effort, not pulled in here.

## Anti-goals

- The drafter must never write to the target repo (read-only tools only).
- No network egress from this stage (keeps FR-703's posture: research and
  OSV remain the only declared outbound egress).
- Default-graph replay divergence: adding the node to `default.graph.yaml`
  (flag off) must not change any command stream or memo key.

## Constraints

- Stage slice shape (`src/sdlc/stages/<stage>/`, `step(ctx: StageContext)`,
  `ACTIVITIES` export, `<stage>.md` contract, slice `AGENTS.md`).
- Cross-stage calls banned; the producer owns its artifacts (constitution
  lives in `stages/constitution/models.py`; `core/` gets only the config
  flag + role plumbing).
- Temporal: model calls happen activity-side (research precedent,
  `stage.py`); workflow code stays deterministic.
- File ceiling 1000 lines; prompts are versioned assets (FR-806).
- Roles load from `agents/<role>/agent.yaml` + `instructions.md`
  (loader.py; registry dir name IS the role name).

## Approaches considered

1. **Hand-written config file** (`policy/constitution.yaml`, zero LLM) —
   spec-literal, cheapest, but principles aren't grounded in the repo, drift
   from actual conventions, and the human partner wanted the harness used
   where it shines. Dropped.
2. **Agent-drafted, off by default (FR-107 pattern)** — chosen. Grounded in
   the target repo; the freeze stays deterministic so the spec's intent
   ("governing principles fixed") holds; opt-in keeps default runs identical.
3. **Config first, agent amends later** — defers everything but pays the
   config-file authoring cost twice. Dropped.

## Capability pick (pydantic-ai-harness)

| Capability | Verdict | Reason |
|---|---|---|
| `FileSystem` | **use** (read-only) | Bounded, pattern-filtered file tools (`read_file`, `search_files`, `find_files`, `list_directory`) rooted at the target repo; containment + secret-denial built in; **explicitly supported under Temporal durable execution** (filesystem README, "Durable execution"). `read_only=True` + `denied_patterns` for secrets/.git. |
| `RepoContext` | **use** | Walk-up autoload of the target repo's `AGENTS.md`/`CLAUDE.md` chain (ancestor-first, deduped) + optional asset inventory (`.claude`/`.agents`/`.codex`/`.grok`) — exactly "principles from the repo's own governing documents". |
| `CodeMode` | **exclude** | The repo already spiked it for research and dropped it: "untestable via TestModel under durable execution" (research `deps.py` docstring, task-6-brief-amended.md). Plain sequential tools won there; same verdict here. |
| `Shell` | exclude | Write/command posture violates the read-only stage; FR-703 spirit. |
| `SubAgents`, `Planning`, `DynamicWorkflow` | exclude | One small single-agent artifact; no decomposition or orchestration. |
| compaction family, `OverflowingToolOutput` | exclude | Short run, small prompt budget (`context_budget_tokens` already bounds assembly). |
| `StepPersistence`, `ManagedPrompt`, media | exclude | No cross-run state here; prompts are versioned assets (FR-806), not logfire-managed. |

Composition note: capabilities compose on the *activity-side* agent
(`Agent(..., capabilities=[single_retry_layer(), LocalWorkspace(repo),
FileSystem(read_only=True, ...), RepoContext(...)])`) — same seam research
already uses, so the CodeMode durable-testing lesson is respected (tools stay
individually TestModel-callable).

## Design

### 1. Artifact — `stages/constitution/models.py`

```python
class Principle(BaseModel):
    id: str                      # "CP-1", assigned by code not the model
    statement: str               # one normative sentence
    normative: Literal["MUST", "SHOULD"]
    rationale: str               # why it exists, one sentence
    source_ref: str | None       # "AGENTS.md#L17" / "pyproject.toml" — required in brownfield

class Constitution(BaseModel):
    principles: list[Principle]  # ≥1, unique ids, enforced by verify
    digest: str                  # sha256 over sorted (id, statement) pairs — memo seam
    drafted_by: Literal["agent", "empty"]  # "empty" = flag-off / greenfield-empty skip
```

### 2. Slice layout (mirrors research, smaller)

```
src/sdlc/stages/constitution/
  __init__.py
  models.py      # Principle, Constitution, _DraftOutput (agent output_type)
  deps.py        # serializable: repo_path, model, run_id (crosses the activity boundary)
  stage.py       # draft_constitution activity: runs the REGISTRY agent, hands usage → RoleUsage
  verify.py      # deterministic freeze: schema + normative checks + source refs (pure)
  prompts.py     # user-prompt assembly (idea brief render); system prompt lives in instructions.md
  step.py        # workflow-side: flag check → activity → verify → emit; exports step, ACTIVITIES
  constitution.md# stage contract (numbered clauses)
  AGENTS.md      # slice rules (invariants, passthrough set, gotchas)
```

**Agent seam (settled — builder-check finding 1).** The drafter is the
**registry role**, not an ad-hoc `Agent(...)` in `stage.py` — the loader
contract makes this the only coherent choice for a stage's proposer:
`agents/constitution/agent.py` must export `build()` anyway (boot fails
otherwise), so an ad-hoc agent would leave a dead registry role behind in a
repo that fails closed on dead config. Wiring mirrors `research_agent`:

- `agents/constitution/agent.yaml`: `kind: constitution` role name, but
  `RoleConfig.kind` is the closed `Literal["proposer","harness","research"]`
  → **`proposer`**.
- `agent.py build()` attaches the capabilities:
  `[single_retry_layer(), FileSystem(read_only=True, ...), RepoContext(...)]`
  (workspace is per-run: `workspace=LocalWorkspace(repo_path)` on the run
  call, activity-side — the FileSystem README's sanctioned pattern).
- Role added to `OPTIONAL_ROLES` (unknown role dirs fail boot);
  `"constitution"` is already in `CANONICAL_STAGES`.
- The system prompt is `agents/constitution/instructions.md` — governed by
  `PROMPT_SHAS`/the E-82 prompt-eval gate. No separate `DRAFTER_SYSTEM`.
- The durable activity name this registers is a wire contract: never rename
  after deploy.
- FS/RepoContext capabilities attach **brownfield-only** (greenfield
  `repo_path` is the `/var/sdlc/repo` fallback; the agent drafts from the
  idea alone).

### 3. Flag & config — `core/models.py`

- `class ConstitutionConfig(BaseModel)`: `enabled: bool = False`,
  `max_principles: int = 12`, `max_requests: int = 6` (inner-run bound,
  ResearchDeps.max_requests precedent).
- `constitution_enabled: bool = False` on PipelineConfig beside
  `research_enabled` (models.py:391), same comment style (FR number).

### 4. Graph wiring

- Register node type `constitution` in `graph/node_types.py`: `IdeaBrief`
  arrives the research way — a `trigger` **signal** in-port (IdeaBrief is
  not in `PAYLOAD_TYPES`; intake's out-ports are signal ports) read from
  `nc.facts.idea`; output `Constitution`; ordering-only deps (like
  research's `requires` note at node_types.py:128).
- **Do not touch `default.graph.yaml`.** New
  `graphs/default-constitution.graph.yaml` = default + constitution node
  between intake and context/clarify (FR-107 file precedent). Two in-edges
  from `intake.ok` and `intake.brownfield` into the one optional trigger
  port is legal (`ONE_PORT_MULTIPLE_SOURCES` bans multiple source nodes,
  not multiple edges). Flag-off + default graph ⇒ byte-identical replays.
- Graph catalog picks it up as a new selectable graph; `project_cfg` sets
  `constitution_enabled` from graph presence, as it does for research.
- Downstream delivery (E-74's only input mechanism): optional
  `constitution` in-ports on the clarify / architect / plan node types +
  edges from the constitution node in the new graph.

### 5. Step semantics (`step.py`)

- Flag off → return the empty constitution (`drafted_by="empty"`,
  principles `[]`, digest `""` — the research ungrounded sentinel, not a
  non-empty constant) without scheduling any activity — zero commands,
  downstream memo keys unchanged.
- Flag on → `draft_constitution` activity → `verify` (a pure function, runs
  in workflow code — no activity needed) → emit `STAGE_ENDED`, retain via
  `ctx.retain`.
- Greenfield → agent drafts from idea alone; `source_ref` not required.

**Freeze semantics — RESOLVED (human): partial freeze.** Verify drops the
offending principles and freezes the rest, emitting a warning event; if
nothing survives validation, the stage degrades to the empty constitution
with FAIL recorded (research's fail-soft floor). The node has no reject
port — the opt-in flag can never kill a run.

### 6. Role registry

- `agents/constitution/agent.yaml`: `kind: constitution`, model pinned by
  registry (boot validation FR-201/204 applies — different family from
  downstream consumers comes free).
- `agents/constitution/instructions.md`: drafter charter (propose, never
  edit; every principle cites a file).

### 7. Downstream seams (minimal, in this PR)

- `content_key`: `constitution_digest` joins the memo inputs of
  clarify/architect/planner (brief_digest precedent, FR-103).
- Prompt render: `render_constitution(c, limit)` — bounded block, ordered
  idea → constitution → codebase map → recall (spec §5 hierarchy).

### 8. Usage & budget

- `RoleUsage(role="constitution", ...)` handed back activity-side
  (research `_role_usage` precedent; priced by the workflow).
- No tool budget: local reads cost nothing; the global `run_budget_usd`
  gate (FR-701) already bounds spend; `max_requests` bounds the single run.

### 9. Docs amendments (same diff)

- PRD: **FR-112** "(new scope) constitution drafter — off by default" row in
  the FR-100 table. (FR-109/110/111 are taken — capture-always sessions
  among them; FR-112 is the next free id, verified across PRD, ROADMAP,
  docs/roadmap, src and tests.)
- SDLC-spec-v2 §1 row 1: `(deterministic)` → `(deterministic + optional
  drafter)` (retro-row style), artifact column unchanged.
- ROADMAP §1 stage-1 line: from "no model, no stage" to landed-pointer;
  FR-101 note gains "constitution live"; new FR-112 row; Last verified per
  convention.
- README roles table: +1 proposer role.

## Test strategy

- Unit (fast tier): model schema; verify rules (unique ids, ≥1 principle,
  normative literal, brownfield source-ref enforcement, digest stability);
  flag-off → constant empty artifact + zero scheduled commands (golden
  command projection unchanged); prompt render bounds; node-type
  registration; graph yaml loads + topology valid.
- TestModel agent test: fake workspace fixture repo; tools callable
  directly (CodeMode lesson); output_type validates; usage handed back.
- Temporal tier (`pytest -m temporal`): default-constitution graph runs
  flag-on end-to-end with fake model; constitution digest present in
  clarify's memo key.
- No live/prompt-eval tier in this PR (prompt quality gate can follow the
  E-82 pattern later).

## What's left to the builder

- Exact prompt wording (DRAFTER_SYSTEM) and principle-count sweet spot.
- `source_ref` grammar (file#anchor vs path-only) — pick and pin by test.
- Whether `RepoContext` asset inventory (`expose_inventory_tool`) is worth
  its tokens for v1 — default off, flip only if drafts lack grounding.
- Graph-file composition story if a run wants research AND constitution
  (out of scope; note in graph catalog).

## Open questions (for the human)

None remaining — freeze semantics resolved to **partial freeze**; both
settled calls confirmed.

## Calls already made (settled by me, from the codebase)

- **Agent seam: registry role** (builder-check finding 1) — not an ad-hoc
  stage-local agent; mirrors `research_agent`; capabilities attach in
  `agent.py build()`, workspace per-run; system prompt = `instructions.md`
  under PROMPT_SHAS governance; durable activity name = wire contract.
- **FR id: FR-112** (builder-check finding 3) — next free in the 100
  series; verified nothing references FR-112 today.
- Empty constitution digests to `""` (research ungrounded sentinel) so
  flag-off downstream memo keys are byte-identical.

