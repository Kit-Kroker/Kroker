# FR-205 Validators Library — Design

| | |
|---|---|
| Date | 2026-11-14 |
| Status | Proposed (awaiting approval) |
| Closes | FR-205 (PRD §6, Agents); AP-2.3's library half |
| Related | ADR-24 (out of scope), AP-2.1 (out of scope), AP-4.1/4.2 (partially served), FR-113 (composes), E-74 (`stages/plan/validation.py` origin), 017 (`workflow.patched` precedent) |

## 1. Intent and why

FR-205: *"Proposer decision boundaries (MAY / MUST NOT per SDLC-spec §2)
SHALL be enforced by validators where expressible."* SDLC-spec-v2 §2 keeps
those boundaries "enforced structurally — schema validators, contract checks,
deterministic gate — not prompt prose."

The principle is already the house style, but every instance is a one-off
living inside its stage (`validate_task_graph`, the freeze rules, research's
`verify_brief`, `untraced_criteria`). What FR-205's letter asks for — and what
AP-2.3 names — is a **shared validators library** plus **evidence schemas**, so
boundaries are systematically expressible instead of accidentally built.

This round closes FR-205 **without** the AP-2.1 `make_agent` factory and
**without** ADR-24 verdict functions: stage steps and graph nodes call the
library directly. (Chosen in conversation over honoring full AP-plan phasing;
the FR's letter does not require the factory.)

## 2. Goals

1. `src/sdlc/validators/` — a horizontal package (the `memoization/`,
   `memory/`, `vcs/` seam) with pure, workflow-safe validators.
2. Migrate plan-graph validation into it; fix the live hole it hides:
   duplicate task ids silently collapse (`{t.id: t}` dict build) instead of
   failing.
3. Convert the expressible-today prose-only boundaries:
   - **plan**: duplicate ids, requirement coverage, task size →
     `failed:plan-validation:…` halts;
   - **clarify**: probe evidence that cites a *path* must cite an existing
     path → discard inside the existing merge filter.
4. Evidence schemas (`Finding`, `AssertionEvidence`, `Coverage`),
   evidence-fields-before-status-fields, zero consumers this round, marked as
   the ADR-24 handoff point.
5. Flip the tracking: ROADMAP FR-205 → `[x]`, AP-2.3 checkbox, ARCHITECTURE.md
   target block → as-built.

## 3. Non-goals / anti-goals

- **No verdict functions** (`review_verdict`, `plan_verdict`, `task_verdict`)
  — ADR-24 / AP-3. Anti-goal: this round must not grow evidence *consumers*.
- **No `make_agent` / `RoleSpec`** — AP-2.1.
- **No contract dry-run** — AP-4.2 (Tier 3, explicitly declined).
- **No migration of freeze rules or `verify_brief`** into the library — they
  stay stage-local; the library's README points at them. Moving working,
  tested code with no reuse gain is churn.
- **No new gates.** Halts and discards only; gate semantics (FR-301) untouched.
- Anti-goal: false kills. Every new halt must have a written false-kill story
  (§7) and a golden-case pass requirement (§9).

## 4. Constraints

- **Seams** (root AGENTS.md, docs/framework.md): validators/ is a horizontal
  package; it may import stage *types* (`DevTask`) — "importing a type
  another stage produces is not a call" — and nothing else from stages.
  `core/` is ruled out by its layering invariant (imports nothing from
  stages or horizontal packages).
- **Temporal**: workflow code is deterministic; tree-reading validators run
  as activities (ARCHITECTURE.md:275-279). New activity calls behind a
  `workflow.patched` marker so in-flight histories replay (017
  `_DRIFT_V2` precedent).
- **Replay invariants** (slice AGENTS.md files): clarify's step finishes at
  `ctx.record`; `merge_clarification` stays pure — activity results arrive as
  arguments.
- **Prompts**: `src/sdlc/prompts.py` is byte-pinned by
  `tests/test_prompts_characterization.py`; adding a block follows the FR-112
  `constitution_block` precedent ("" default = byte-identical old form).
- **File size**: 1000-line ceiling; the library starts far below.
- **Artifact boundary**: stage-contract clauses updated in the same diff as
  behavior.

## 5. Approaches (decided in conversation)

**Placement** — picked: horizontal `src/sdlc/validators/` package.
Rejected: `agents/validators.py` (real callers today are stage steps and
graph nodes, not agent loops — premature `make_agent` home) and
`core/validators.py` (erodes core's config/envelope charter; core may not
import stage types).

**Requirement coverage** — picked: add `DevTask.covers: list[str]` (default
empty) and bind `covers_all` only when the id-addressable FR-113
`Requirements` artifact exists. Rejected: deferring to AP-4.2 (leaves FR-205
open) and text-overlap heuristics (not deterministic; false-kill factory).

**Semantics by host** — decided: plan extends the existing
`failed:plan-validation:` halt family (consistent, legible, immediate);
clarify extends the existing DISCARD filter (a question citing a missing path
was "never a real candidate" — exactly merge.py's existing DISCARD meaning,
so it is not recorded on `dropped`).

## 6. Design

### 6.1 Package layout

```
src/sdlc/validators/
├── __init__.py     # facade: re-exports the public names
├── pure.py         # workflow-safe, no I/O, no Temporal imports
├── activities.py   # tree-reading validators; exports ACTIVITIES
└── evidence.py     # ADR-24 handoff schemas, no consumers yet
```

### 6.2 Pure validators (`pure.py`)

All return `str | None` (None = pass) except `covers_all`; all take typed
models; all unit-tested with the `tests/plan/test_plan_graph_validation.py`
style.

- `ids_unique(tasks: list[DevTask]) -> str | None` — duplicate ids named.
  Fixes the silent `{t.id: t}` collapse; runs **before** the DAG checks.
- `deps_resolve(tasks) -> str | None` and `dag_acyclic(tasks) -> str | None`
  — `validate_task_graph`'s two halves, split but behavior-identical
  (same messages) so existing tests pin the migration.
- `covers_all(tasks, requirement_ids: list[str]) -> list[str]` — uncovered
  FR ids, empty list = pass. Called only when a `Requirements` artifact with
  ids exists; vacuous otherwise (today's common run). Covers citing ids
  *not* in the artifact pass (a `US-*`-prefixed cover is legal) — only an
  uncovered *requirement id* fails.
- `task_size(tasks, limits: PlanLimits) -> str | None` — first breach named:
  `files_hint` count or `acceptance_criteria` count over their limits.

### 6.3 Plan wiring

- `DevTask.covers: list[str] = Field(default_factory=list)` — additive,
  old plans deserialize unchanged (E-1 defaulted-field precedent).
- `planner_prompt(..., requirements_block: str = "")` — FR-112
  `constitution_block` pattern; renders US/FR ids + statements when the
  artifact exists, "" default keeps bytes identical. The block instructs:
  populate each task's `covers` with the FR ids it implements.
- **Delivery route (builder-check Q1): through the graph, not host state.**
  Two new edges in `graphs/default-requirements.graph.yaml` onto a NEW
  port — `requirements → planner(requirements_doc)` and
  `requirements → plan_check(requirements_doc)`; the planner's existing
  `requirements` slot is `ClarifiedRequirements` and stays that way. That
  graph's content sha changes (E-72) — accepted: it is off by default, the
  default graph's pinned sha stays untouched (FR-112/113 precedent), and a
  run pins its graph for its lifetime. The requirements slice's "clarify is
  the artifact's ONLY downstream consumer" invariant is rewritten in the
  same diff (artifact-boundary rule). Both edges are load-bearing: ids must
  reach the *prompt* or `covers` stays empty and `covers_all` halts every
  requirements-enabled run.
- **Memoization (builder-check Q4):** plan's cache key gains a
  `requirements_digest` term (the FR-113 digest; `""` sentinel when the
  artifact is absent) — exactly the term clarify already joins. Flag-off
  runs stay byte-identical; one-time misses on in-flight requirements-
  enabled runs are the accepted ADR-5 cost.
- `PlanLimits` on `PipelineConfig` as `plan: PlanConfig` (the nested-config
  pattern of `constitution`/`requirements`), defaults generous:
  `max_files_hint: int = 24`, `max_criteria: int = 12`.
- `graph_nodes/postplan.py::plan_check_node` order:
  `ids_unique` → `deps_resolve`/`dag_acyclic` → `covers_all` (requirements
  ids arrive via the node's input models — type import, no stage call) →
  `task_size`; each failure returns
  `NodeResult(port="halt", result=f"failed:plan-validation:{reason}")`.
- `stages/plan/validation.py` is deleted; `validate_task_graph`'s import
  sites (`postplan.py`, both plan test files, chaos test) repoint to the
  library. No compatibility alias — 020's alias was a cutover crutch, not a
  pattern.

### 6.4 Clarify wiring (evidence paths)

- New `activities.py::paths_exist(repo_path: str, paths: list[str]) ->
  dict[str, bool]` — batched, one call per merge; joins
  `get_worker_activities()`'s horizontal list; clarify keeps
  `ACTIVITIES = []`.
- Path-like token extraction from `OpenQuestion.evidence`: tokens containing
  `/` or matching `[\w.-]+\.(py|ts|tsx|go|rs|js|md|yaml|yml|json|toml|…)`,
  normalized by `plan/models.py::_norm_path` semantics (move that helper or
  duplicate it — builder's call). Symbol citations (`module.attr`) are **not**
  path-like: they pass, unchecked — the check grounds *paths only*.
- `merge_clarification(..., missing_paths: frozenset[str] = frozenset())` —
  stays pure; a question whose evidence cites a path in `missing_paths` is
  DISCARDed (not recorded), extending the line-99 filter.
- The activity call sits in clarify's `step` before merge, behind a
  `workflow.patched("<round>-clarify-evidence-paths")` marker (exact id
  assigned in the plan); unpatched (in-flight) replays skip the call and the
  discard — identical to today's behavior.
- **Mode gate (builder-check Q3): brownfield only.** The check runs only
  when `idea.mode` is brownfield (FR-102's `classify()` fact, already
  first-class) — the grounded dimensions are repo-grounded by definition,
  so greenfield and seeded runs never call the activity and no
  tree-emptiness probe is needed. `repo_path` is plumbed from `RunFacts`
  at the node layer into the call site (the step keeps no repo state); the
  activity's wire signature stays `paths_exist(repo_path, paths)`.
- **Fan-out only (builder-check Q2).** The discard lives in
  `merge_clarification`, which runs only on the probe path
  (`clarify_probes_enabled`, off by default). That is not dead code by
  accident: the route agent owns only ungrounded C1/C2 dimensions
  (merge.py:84), so path-citing evidence exists only where probes ran.
  Single mode has no subjects for the rule; enforcing it there would be
  vacuous. Default runs are unchanged by the clarify half of this round —
  by construction, not by omission.

### 6.5 Evidence schemas (`evidence.py`)

`Finding`, `AssertionEvidence`, `Coverage` — minimal Pydantic, evidence
fields before status fields (AP-1.4 ordering). Module docstring states
plainly: no consumers yet; they exist so ADR-24's verdict functions have a
fixed shape to consume, and so artifact models adopt them incrementally.

### 6.6 What deliberately stays

`stages/constitution|requirements/verify.py::freeze`, research's
`verify_brief`, `untraced_criteria`, `gate.py`, `payload_guard` — stage-local,
already tested; the library's README maps them as "instances of the
principle" so the surface is discoverable without churn.

## 7. False-kill stories

- **Duplicate ids**: no legitimate plan has them; today they corrupt
  silently (`by_id` keeps the last, the scheduler drops the first).
- **Coverage**: binds only when id-addressable requirements exist; a plan
  that misses an FR is exactly the defect FR-106's `untraced_criteria`
  catches late — this catches it before code exists. Requirements-artifact
  runs are off by default, so no existing run changes behavior.
- **Task size**: limits config-gated, defaults set above every golden-case
  plan's real tasks (verified in tests against `benchmarks/cases` fixtures);
  breach halts legibly, not silently.
- **Evidence paths**: discards only when a token *looks* like a path, was
  checked, and is missing — and only in brownfield runs. Symbols pass.

## 8. Docs & close-out (same diff as code)

- `stages/plan/plan.md` + slice AGENTS.md: new clauses (covers, limits,
  halt family extension, validation.py removal, `requirements_digest` memo
  term).
- `stages/requirements/requirements.md` + slice AGENTS.md: the consumer
  list grows from "clarify only" to "clarify, planner, plan_check".
- `graphs/default-requirements.graph.yaml`: the two new edges (§6.3).
- `stages/clarify/clarify.md` + slice AGENTS.md: evidence-path discard
  clause, patch marker note.
- ROADMAP: FR-205 → `[x]` with evidence; "Last verified" one-liner + full
  entry in `docs/roadmap/last-verified-log.md`; fix the stale
  "only inline dependency-cycle check" text.
- `docs/roadmap/agent-architecture-plan.md`: AP-2.3 → `[x]` (library +
  schemas + activity/inline split all delivered; factory integration remains
  AP-2.1's).
- ARCHITECTURE.md: validators move from the "Target (plan, not built)" block
  to as-built (§4 table, §14 tree).
- PRD untouched — the requirement already reads as delivered.

## 9. Tests

- Unit: every validator, both pass and fail shapes; token extraction;
  `_norm_path` equivalence.
- Migration pin: existing `validate_task_graph` tests repointed, messages
  unchanged.
- Wiring: `plan_check_node` halt strings per check; clarify discard with a
  faked `paths_exist`; greenfield skip; patch-marker replay test (017
  pattern).
- Defaults pin: `PlanConfig()` wire values locked by test (the false-kill guard is
  the generous default, not a sweep — the golden cases hold oracle task ids,
  not `DevTask` plans, so there is nothing in-repo to sweep; confirmed
  2026-11-14).
- Characterization: `tests/test_prompts_characterization.py` extended for the
  new default-"" block.

## 10. Left to the builder

- Patch-marker id (follows the round number this work ships under).
- Whether `_norm_path` moves to the library or is duplicated (one caller
  today; move is cleaner, duplicate is lower-risk — builder's call).
- `PlanConfig` field placement details in `core/models.py` (nested pattern,
  fail-closed parse if any).
