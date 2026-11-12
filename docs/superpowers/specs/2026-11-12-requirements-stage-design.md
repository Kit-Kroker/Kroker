# Requirements stage (stage 3) — design

Date: 2026-11-12
Status: draft — awaiting human approval (builder check pending)
Owner: brainstorming session (superpowers), picked approach: **feed-it — Product drafts, clarify fuses (opt-in, FR-107/112 pattern)**

## Intent

Close FR-101's last gap: stage 3 · requirements. ROADMAP §1:283 records
the conflation — *"conflated into clarify; no standalone Product proposer /
`Requirements` artifact."* Today clarify's supervisor call both authors the
requirements body (plain strings, no story shape, no numbering) and asks the
open questions. The spec (SDLC-spec-v2 §1 row 3) reserves slot 3 for a
**Product** owner emitting a `Requirements` artifact with success criteria
"≥1 story; FR-### + SC-###", sitting after context (slot 2) and before
research (slot 4) and clarify (slot 5).

The human partner picked the **feed-it** approach (the FR-107/112 pattern):
a Product proposer drafts `Requirements`; clarify takes it as an **optional
input** and still fuses everything into `ClarifiedRequirements`; the stage
is off by default, so default runs change nothing. The full split (clarify
shrinks to disambiguation-only, downstream consumes numbered requirements
directly) is the tracked end-state follow-up, not this PR.

The human partner asked for **pydantic-ai-harness capabilities** on the
drafter; this document picks the set.

## Why

- FR-101 goes 15/15 — the last `[ ]` in ROADMAP §1.
- Stories with numbered FR/SC give the pipeline an addressable requirements
  vocabulary: clarify questions can cite "FR-3", and a future FR-106
  re-rooting (criterion→test traced to FR-### instead of plan-authored
  criteria) gets an earlier authoritative anchor.
- The FR-112 playbook is two stages proven (research FR-107, constitution
  FR-112): registry proposer + read-only harness capabilities + opt-in
  graph + deterministic freeze + digest seam. This stage is that pattern
  applied once more, with the one difference that its consumer is clarify
  alone (the fusion point), not the three proposer stages.

## Goals

1. `Requirements` artifact: story-shaped, code-numbered (`US-n`/`FR-n`/
   `SC-n`), content-addressed (digest), memoizable.
2. A Product drafter role (`agents/product/`) that reads the target repo
   read-only and proposes stories grounded in what the repo (brownfield)
   or the idea alone (greenfield) offers.
3. Deterministic partial freeze: code assigns ids, drops noise, dedupes;
   zero surviving stories degrades to the empty artifact — never kills a
   run.
4. Off by default (`requirements_enabled`, overlaid from graph presence);
   flag-off runs byte-identical (default graph untouched, zero new
   commands, memo keys unchanged).
5. Downstream seam: clarify gains optional `requirements` +
   `requirements_digest` inputs (memo key + prompt, omitted at default).
6. Same-diff docs: stage contract `requirements.md`, slice `AGENTS.md`,
   PRD FR-113 row, SDLC-spec-v2 §1 row-3 annotation, ROADMAP (stage-3
   line, FR-101 15/15, FR-113 row, Last verified), README roles table.
7. Graph selection wired at birth: `default-requirements` in
   `SHIPPED_NAMES` + a `select_graph` branch + flag-on E2E temporal test —
   the FR-112 final-review gap, not repeated.

## Non-goals

- **No clarify restructure** — clarify keeps authoring
  `ClarifiedRequirements` (now informed by the draft) and keeps the human
  gate. The split is the tracked follow-up (approach 2 below).
- No NFRs, no `out_of_scope` in this artifact — spec pins "≥1 story;
  FR-### + SC-###"; clarify continues to own NFRs in the fused artifact.
- No gate on this stage (spec row 3 names no gate; the draft is
  machine-frozen, not negotiated).
- No repo-aligned numbering continuation (the model may *read* the target
  repo's PRD and continue its intent; number continuity is not promised —
  per-run code-assigned numbering only).
- No fan-out, no refine rounds; one bounded single-pass drafter.
- No combined opt-in graph (research+constitution+requirements); ships
  single-purpose like the other two. Composition is a later catalog story.
- No FR-106 re-rooting in this PR — the artifact makes it possible;
  switching analyze's enforcement root is separate scope.

## Anti-goals

- The drafter must never write to the target repo (read-only tools only).
- No network egress from this stage (FR-703 posture: research and OSV stay
  the only declared outbound egress).
- Default-graph replay divergence: `default.graph.yaml` stays byte-identical;
  flag-off ⇒ no new commands, no memo-key drift.

## Constraints

- Stage slice shape (`src/sdlc/stages/requirements/`, `step(ctx,
  StageContext)`, `ACTIVITIES` export, `requirements.md` contract, slice
  `AGENTS.md`).
- Cross-stage calls banned; the producer owns its artifacts (`Requirements`
  lives in `stages/requirements/models.py`; `core/` gets only the config
  flag + role plumbing; clarify importing the *type* + render helper is
  legal).
- Temporal: model calls activity-side; workflow code deterministic; wire
  names (`product_agent`, `draft_requirements`, node type `requirements`)
  never renamed after deploy.
- File ceiling 1000 lines; prompts are versioned assets (FR-806,
  PROMPT_SHAS).
- Registry: `agents/product/` dir name IS the role name; loader
  `OPTIONAL_ROLES` grows `"product"`; `"requirements"` is already in
  `CANONICAL_STAGES` (benchmarks/heatmap.py:36) — free, like constitution.

## Approaches considered

1. **Feed it** (constitution pattern) — **chosen**. Product drafts
   `Requirements`; clarify consumes it as optional input and still emits
   `ClarifiedRequirements`. Downstream (architect/plan) untouched; flag-off
   byte-identical; cheapest; two-stage precedent. Trade-off: the conflation
   survives while the flag is off — accepted, and the split follows.
2. **Split clarify now** — Product owns authoring; clarify shrinks to
   disambiguation + gate over numbered requirements; architect consumes
   `Requirements` directly. This is the spec's end-state, but it rewires
   clarify's core supervisor call, every downstream memo key, and the
   E-85 probe fan-out in one PR. Deferred: the risk concentrates exactly
   where the pipeline's most-touched stage lives.
3. **Requirements-as-config** (hand-written `requirements.yaml`, zero LLM)
   — spec-literal but ungrounded, drifts, and the human partner asked for
   the harness drafter. Dropped (same verdict as constitution's approach 1).

## Capability pick (pydantic-ai-harness)

| Capability | Verdict | Reason |
|---|---|---|
| `FileSystem` | **use** (read-only) | Same 4 tools as constitution (`read_file`, `search_files`, `find_files`, `list_directory`), rooted at the target repo; containment + secret-denial built in; supported under Temporal durable execution. Brownfield: the drafter reads the repo's own PRD/README/docs to continue intent. |
| `RepoContext` | **use** | AGENTS.md/CLAUDE.md chain walk-up — the repo's own governing context for what it values; same defaults as constitution (no `home_dir` walk-up surprises). |
| `CodeMode` | exclude | Repo's own spike verdict stands: untestable via TestModel under durable execution (research `deps.py` docstring). |
| `Shell` | exclude | Write/command posture violates read-only; FR-703 spirit. |
| `docs`, `smart_search`, `web_search`/`exa` | exclude | Web grounding is research's job (FR-107), a different stage with its own budget and verification; this stage is repo- and idea-grounded. |
| `SubAgents`, `Planning`, `DynamicWorkflow` | exclude | One small single-agent artifact; no decomposition or orchestration. |
| compaction family, `StepPersistence`, media, guardrails extras | exclude | Short bounded run; no cross-run state; prompts are versioned assets. |

Composition: activity-side agent, loader-supplied capabilities first,
role's own after (`agents/research/agent.py` 003 contract) — the exact
constitution composition, second production use of `FileSystem` +
`RepoContext`.

## Design

### 1. Artifact — `stages/requirements/models.py`

```python
class FunctionalRequirement(BaseModel):
    id: str          # "FR-1", assigned by code not the model; GLOBAL across the artifact (PRD convention)
    text: str

class SuccessCriterion(BaseModel):
    id: str          # "SC-1", code-assigned, global across the artifact
    text: str

class Story(BaseModel):
    id: str                              # "US-1", code-assigned
    narrative: str                       # "As a …, I want …, so that …"
    functional: list[FunctionalRequirement]   # ≥1 (freeze enforces)
    success_criteria: list[SuccessCriterion]  # ≥0 at freeze; spec's SC pin is artifact-level: ≥1 SC overall or a warning
    source_ref: str | None               # brownfield grounding: one repo-relative path (e.g. the PRD/README a story continues)

class Requirements(BaseModel):
    stories: list[Story]
    digest: str                           # "" when empty (flag-off sentinel)
    drafted_by: Literal["agent", "empty"]

class DraftStory(BaseModel):              # agent output carries NO ids (constitution DraftOutput precedent)
    narrative: str
    functional: list[str]
    success_criteria: list[str]
    source_ref: str | None = None

class DraftOutput(BaseModel):
    stories: list[DraftStory]
```

**Digest.** sha256 over the JSON-serialized, sorted list of per-story
canonical tuples `(narrative, sorted(functional texts), sorted(sc texts))`;
`""` for an empty story list. Ids are code-assigned and excluded, so the
digest is drop-order-stable — identical to constitution's
`(statement, normative)` design philosophy: same digest ⇒ same memo key,
reordered drops don't churn keys.

**Namespace note (pinned by test):** node *type* string `requirements` and
clarify's existing out-*port* name `requirements`
(`node_types.py:160`) live in different namespaces — no collision, but a
test pins both to keep it that way.

### 2. Slice layout (mirrors constitution exactly)

```
src/sdlc/stages/requirements/
  __init__.py
  models.py      # Story/FR/SC/Requirements + Draft* (no ids) + digest
  deps.py        # RequirementsDeps: run_id, mode, max_stories, max_requests (serializable, FR-010 omit-when-default)
  stage.py       # draft_requirements activity: registry agent run, usage → RoleUsage
  verify.py      # freeze(draft, *, mode) -> FreezeResult — pure
  prompts.py     # user-prompt assembly + render_requirements(c, *, max_chars=2000) for clarify
  step.py        # flag check → activity → freeze (workflow-side) → emit/retain; exports step, ACTIVITIES
  requirements.md# stage contract (numbered clauses)
  AGENTS.md      # slice rules
```

### 3. Freeze rules (`verify.py`, pure, never raises)

1. Drop stories with empty/whitespace-only `narrative`.
2. Drop empty/whitespace-only texts from `functional`/`success_criteria`.
3. Dedup exact-duplicate texts: globally across the artifact for FR texts
   and for SC texts (a requirement stated twice is one requirement — PRD
   convention).
4. Drop stories left with zero surviving `functional` entries (a story
   with nothing functional isn't a story).
5. Assign ids in surviving order: `US-1…`, `FR-1…` **global across the
   artifact**, `SC-1…` global.
6. Brownfield: stories with an empty or whitespace-only `source_ref`
   (`not (source_ref or "").strip()`) are **dropped with a warning**
   (constitution's ungrounded-drop rule, with its parked whitespace gotcha
   fixed by using strip-semantics here); greenfield exempt.
7. `degraded=True` iff zero stories survive →
   `Requirements(drafted_by="empty", stories=[], digest="")` + FAIL-path
   STAGE_ENDED, nothing retained. Artifact-level "≥1 SC" miss (stories but
   zero SCs) is a **warning**, not a drop — spec's "≥1 story; FR-### +
   SC-###" pins the shape, and a usable draft with missing SCs shouldn't
   be discarded.
8. Cap: if more than `max_stories` survive, keep the first `max_stories`
   and warn (bounded artifact, honest record).

### 4. Activity (`stage.py`)

- `DraftInput(idea_json, repo_path, deps: RequirementsDeps, model)`;
  `@activity.defn async def draft_requirements(...) -> _DraftResult(draft:
  DraftOutput, usage: RoleUsage)` — raw draft, freeze is workflow-side.
- Workspace resolution = constitution's, **with its T6 fix baked in from
  the start**: one predicate (`_repo_workspace`) decides both the
  workspace and the prompt's mode line; `deps.mode` is consumed only by
  the freeze. Brownfield-mode + missing repo ⇒ greenfield prompt over the
  scratch tree, never "cite the repo" over an empty workspace.
- Scratch workspace: `$SDLC_RUNS_ROOT/<run_id>/requirements/`.
- `UsageLimitExceeded` → empty `DraftOutput` (degrade, never raise);
  everything else propagates.
- Usage: `RoleUsage(role="product", model=..., cost_usd=None)` (workflow
  prices) — the registry role name, matching `resolve_role_model(cfg,
  "product")`.
- Model forwarding D7a (pass `model=` only when it differs from registry).

### 5. Role registry

- `agents/product/agent.yaml` — `kind: proposer`, model in research's
  family (`zai:glm-5.3`) subject to boot `validate_registry`.
- `agents/product/instructions.md` — charter: propose ≤ `max_stories`
  user stories for THIS idea; brownfield stories continue the repo's
  product intent and each cites exactly one repo-relative `source_ref`;
  never quote file contents; FR/SC texts are single-sentence testable
  statements; do not invent numbering (output carries no ids).
- `agent.py build()`: `name="product_agent"` (wire contract),
  `deps_type=RequirementsDeps`, `output_type=DraftOutput`,
  `retries={"output": 3}`; own capabilities appended after loader's:
  `FileSystem(read_only=True, tools=[read_file, search_files, find_files,
  list_directory])`, `RepoContext()` — explicit `home_dir=None`.
- Loader `OPTIONAL_ROLES` += `"product"`; `roles.py` `t_product` joins
  `ALL_TEMPORAL_AGENTS` conditionally (t_research pattern).
- **Stage→role mapping (builder-check finding 1):** `resolve_role_model`
  is keyed by *stage* keys via `STAGE_ROLES` (roles.py:236-245), so the
  build adds `STAGE_ROLES["requirements"] = "product"` and calls
  `resolve_role_model(cfg, "requirements")` — which also puts
  `agents/product/instructions.md` under `PROMPT_SHAS["requirements"]`,
  matching the node-types "type names equal STAGE_ROLES keys" convention.
  (The §4 activity text says the role name "product"; the *call* is keyed
  by the stage name "requirements".)

### 6. Config & flag

- `RequirementsConfig(BaseModel)`: `enabled: bool = False`,
  `max_stories: int = 8`, `max_requests: int = 6`.
- `PipelineConfig.requirements: RequirementsConfig` (default factory,
  FR-010 omit-when-default discipline) +
  `requirements_enabled: bool = False` beside `research_enabled`/
  `constitution_enabled`.
- `project_cfg` overlay: `requirements_in_graph` → `requirements_enabled`,
  **required kwarg this time** (constitution's defaulted-False bridge was
  a parked footgun; research's required shape is the pattern), wired at
  the single `project_cfg` call site in `graph_dispatch.py`.

### 7. Graph wiring

- Node type `requirements` (`kind="stage"`, `role="product"`,
  `canonical_stage="requirements"`, `budget_after="continuing"`):
  `_in("trigger", None, required=False)`,
  `_in("constitution", "Constitution", required=False)`,
  `_in("codebase_map", "CodebaseMap", required=False)`,
  `_out("requirements", "Requirements")`, `_fail()` — no reject port.
  Optional constitution/map in-ports exist so future composed graphs can
  wire them; the shipped graph doesn't.
- `graphs/default-requirements.graph.yaml` = default ⊕ node ⊕ edges:
  `intake.ok → requirements.trigger`, `intake.brownfield →
  requirements.trigger`, `requirements.requirements →
  clarify.requirements`. (`default.graph.yaml` byte-identical — sha-pinned
  by the existing test.)
- New optional in-port `_in("requirements", "Requirements", required=False)`
  on the **clarify** node type only (architect/plan stay untouched —
  approach 1's whole point).
- `PAYLOAD_TYPES` += `"Requirements"`.
- **Selection wired at birth** (FR-112 final-review lesson):
  `SHIPPED_NAMES` += `"default-requirements"`; `select_graph` branch
  mirroring research/constitution (`cfg.requirements_enabled and
  "product" in roles_map`); documented precedence if multiple flags are on
  (research > constitution > requirements — stable, commented, test-pinned;
  and the comment/AGENTS.md line must NOT claim a nonexistent explicit-pin
  mechanism).

### 8. Step semantics (`step.py`)

- Flag off → `Requirements(drafted_by="empty", stories=[], digest="")`,
  zero activities scheduled, no `ctx.gate`.
- Flag on → `draft_requirements` activity → `freeze(draft,
  mode=deps.mode)` in workflow code → price usage → STAGE_ENDED emitted
  directly via `ctx.emit` (no benchmark row / `duration_s`; cost on
  MODEL_USAGE — constitution's ruled shape) + warning when anything was
  dropped/capped + FAIL-path event when degraded (nothing retained) →
  else `ctx.retain`.
- Inputs: `idea` (nc.facts.idea), `repo_path`, and the optional
  constitution/codebase_map payloads **rendered into the drafter's user
  prompt** (idea → constitution principles → map digest-bounded render →
  draft instruction) — graph presence makes them available; the prompt
  uses what arrived. (Builder-check note: the optional renders are dead in
  the shipped graph — neither port is wired there; they exist for composed
  graphs. Covered by the delegated port-shipping choice.)

### 9. Downstream seam (clarify only)

- `clarify/step.py`: `requirements: Requirements | None = None` +
  `requirements_digest: str = ""`, threaded beside `constitution_digest`
  into the memo/`content_key` inputs; omitted while at default (FR-010 —
  flag-off byte-identity, test-pinned the T8 way).
- Prompt render via `render_requirements(c, *, max_chars=2000)` from
  `stages/requirements/prompts.py` (producer owns the render). Order:
  idea → constitution → **requirements** → codebase map → recall.
- Handler (`precode.py`): requirements object + digest from the SAME
  payload (T8 carry — prompt and key move together).

### 10. Docs amendments (same diff)

- PRD §6: **FR-113** (verified next-free in the 100 series across
  PRD/ROADMAP/src/tests) — "(new scope) requirements drafter — Product
  proposer drafts story-shaped `Requirements` (US/FR/SC code-numbered),
  read-only FileSystem+RepoContext, deterministic partial freeze, off by
  default; feeds clarify."
- SDLC-spec-v2 §1 row 3: owner column annotation "(optional; off by
  default — FR-113)" in research row-4's style.
- ROADMAP §1: stage-3 line → `[x]` (deploy-row off-by-default precedent),
  **15 of 15**, FR-101 row → `[x]`, FR-113 row, Last verified per
  convention (one-sentence cell; full entry prepends to
  `docs/roadmap/last-verified-log.md`).
- README roles table: +1 proposer. Count check is mandated — note the
  README header prose says "3+8+5=16" (excludes assessment roles) while
  the roles-table count includes them (18 today, 19 after); update the
  table's count and reconcile the prose if the diff touches it (builder
  check finding 4).
- Follow-up tracked (not this PR): approach-2 clarify split; FR-106
  re-rooting onto FR-### ids.

## Test strategy

- Unit (fast tier): model schema (no ids on Draft*); freeze rule table
  (each rule + interaction: dedup-after-empty-drop, brownfield drop
  ordering, cap-with-warning, degraded); digest stability + `""` sentinel;
  flag-off zero-commands (golden command projection unchanged); render
  bounds + `""` for empty; node-type registration + port shape; graph
  loads + topology; sha pin of `default.graph.yaml`; clarify memo-key
  byte-identity at defaults + flip on digest change; namespace pin
  (type string vs clarify out-port); `RoleUsage(role="product")`.
- TestModel agent test: fake workspace fixture repo; tools individually
  callable; `output_type` validates; usage handed back;
  brownfield-mode-without-repo never prompts for source_refs (T6 lesson
  pinned from birth).
- Temporal tier: `default-requirements` graph runs flag-on end-to-end;
  Requirements produced/retained; digest-salted clarify memo key present,
  digest-less key absent (constitution E2E pattern); selection precedence
  test when research+requirements flags both on.
- No live/prompt-eval tier in this PR (E-82 pattern can follow; the
  charter is PROMPT_SHAS-governed from day one).

## What's left to the builder

- Exact charter wording in `instructions.md` (structure pinned above).
- `render_requirements` block format (one line per story: `US-1 <narrative>`
  + nested `FR-1 …` lines; truncation at `max_chars` whole-line-first).
- Whether the optional `constitution`/`codebase_map` in-ports on the node
  type ship unused in v1 (design says yes — future composed graphs) or are
  deferred until a graph wires them (cheaper catalog); builder picks,
  contract records the choice.
- Test file names/locations following the constitution suite layout.

## Open questions (for the human)

None remaining — approach (feed-it), artifact shape, capability set, and
degradation semantics were all settled in the conversation; everything
else above is marked as a call.

## Calls already made (settled by me, from the codebase + FR-112 lessons)

- **FR-113** — next free id in the 100 series (verified).
- **Role name `product`** (dir/registry), stage/type name `requirements`.
  Registry role names follow the owner (analyst→Analyst, dev→Developer);
  the owner here is Product → role `product`. `RoleUsage` carries
  `"product"`; node type and payload carry `"requirements"`.
- **FR/SC ids are global across the artifact** (PRD §6/§8 convention),
  not per-story restarts.
- **`requirements_in_graph` is a required `project_cfg` kwarg** — no
  defaulted-False bridge (constitution's parked footgun not repeated).
- **Selection wiring + E2E in scope at birth** — the FR-112 final-review
  gap is designed in, not patched in.
- Prompt mode line derives from the resolved workspace (T6 fix baked in);
  `deps.mode` is the freeze contract.
- STAGE_ENDED direct (no benchmark row/duration_s), cost on MODEL_USAGE —
  constitution's ruled shape, kept for symmetry.
