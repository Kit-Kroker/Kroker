# Requirements Stage

The requirements stage (Stage 3, FR-113) drafts the run's user stories from
the idea (and, brownfield, the repo's own product intent) and freezes them
into the `Requirements` artifact clarify consumes. It is off by default: a
run opts in by carrying a requirements node in its graph
(`default-requirements.graph.yaml` ships as the reference such graph).

The split is the house rule (the model proposes, code validates): a
registry drafter agent (the `product` role) proposes a raw `DraftOutput`
of story-shaped drafts over a read-only workspace, and a deterministic
`freeze` assigns the ids and the digest workflow-side. Freeze is partial —
offending stories and texts are dropped, never retried or repaired — and
the stage holds no gate, so the opt-in flag can never kill a run: a
degraded draft fails soft into the empty artifact.

## Requirements

### REQUIREMENTS-1.1
The requirements step receives a `StageContext` protocol and required
collaborators as keyword arguments, never the workflow instance, and never
calls `ctx.gate`: partial freeze means the opt-in flag can never kill a
run, so a degraded requirements draft fails soft into the empty artifact.
[FR-113]

### REQUIREMENTS-1.2
The flag is `PipelineConfig.requirements_enabled` (bounds on
`PipelineConfig.requirements`: `RequirementsConfig(enabled=False,
max_stories=8, max_requests=6)`), overlaid from graph presence at the
single `project_cfg` call site — never set by project config alone, and
the `requirements_in_graph` kwarg is REQUIRED there (mirroring research:
a defaulted bridge fails silently instead of loudly). Flag off returns
the empty artifact (`drafted_by="empty"`, `stories=[]`, `digest=""`) with
zero activities scheduled: byte-identical to a graph without the node.
[FR-113, FR-010]

### REQUIREMENTS-1.3
Flag on, the step schedules exactly one draft activity
(`draft_requirements`), freezes the raw draft workflow-side via
`freeze(result.draft, mode=inp.deps.mode,
max_stories=cfg.requirements.max_stories)` — `deps.mode` is exactly
greenfield|brownfield, derived from `idea.mode`, and ids and digest are
assigned by code, never by the model — prices the returned usage through
`price_usage` (fail-open: a pricing failure prices nothing), and emits
`STAGE_ENDED` directly via `ctx.emit`: no benchmark row and no
`duration_s` are recorded for this stage, and its cost reaches the run's
tracking through the `MODEL_USAGE` event. A freeze that dropped items or
capped the stories carries a `warning` naming the counts; a degraded
freeze carries `outcome=fail` plus `warning="no story survived freeze"`
and retains nothing; a non-degraded freeze retains one `STAGE_SUMMARY`
whose text is the frozen story lines and whose metadata carries `stage`,
`digest` and `run_id`. [FR-113]

### REQUIREMENTS-1.4
`freeze` is a deterministic partial freeze over the raw draft, applying
its rules in this OPERATIONAL order (the brownfield drop runs BEFORE the
text rules): a story whose narrative is empty or whitespace-only drops
whole; a brownfield story with a missing `source_ref`
(`not (ref or "").strip()` — `None`, `""` and whitespace all count as
missing; greenfield is exempt — an idea-alone draft has nothing to cite)
drops before its texts are examined, so a rejected story's texts never
enter the keyspace and never block the same text in a story freeze keeps;
per surviving story, FR/SC texts that are empty or whitespace-only drop,
and exact-duplicate texts (verbatim, case-sensitive) collapse to the
first occurrence across one artifact-wide keyspace each for FR texts and
SC texts, committed only when the story survives; a story left with zero
surviving `functional` entries drops (zero surviving criteria is NOT a
drop — the artifact-level "≥1 SC" pin is a caller concern, never
freeze's); ids `US-1…` (per story) and `FR-1…` / `SC-1…` (global across
the artifact, never reset per story) are code-assigned in surviving order
(the model never names the artifact's ids); more survivors than
`max_stories` cap to the first `max_stories` with `capped=True` (ids stay
dense; capped stories are recorded by the flag, not re-listed in
`dropped`); zero survivors degrade the stage (`drafted_by="empty"`,
`digest=""`, `degraded=True` — freeze never raises). [FR-113]

### REQUIREMENTS-1.5
The artifact is story-shaped: each `Story` carries a narrative
("As a …, I want …, so that …"), its `functional` requirements and
`success_criteria`, and an optional repo-relative `source_ref`; the
drafter's `DraftStory`/`DraftOutput` carry the same shape with NO ids.
`requirements_digest` is sha256 over the JSON of the sorted
`(narrative, sorted FR texts, sorted SC texts)` tuples — story order,
text order and ids drop out, content remains, so the same stories hash
the same everywhere. `""` for an empty list is the wire-level sentinel
(the constitution convention): a flag-off or fully-dropped requirements
artifact digests, keys and renders identically to no requirements stage
at all. [FR-113, FR-010]

### REQUIREMENTS-1.6
The activity resolves its workspace through one predicate
(`_repo_workspace`): the repo checkout when `repo_path` names an existing
directory, else an empty scratch workspace at
`$SDLC_RUNS_ROOT/<run_id>/requirements/` (default root CWD-relative
`runs/`), created before the run. The prompt's mode line derives from
that resolved workspace, not from `deps.mode` — which remains the freeze
contract — so the prompt can never instruct repo citation over a tree the
agent cannot read. `UsageLimitExceeded` degrades once to an empty draft
and is never re-raised (the bound is config; a retry hits the same
exhausted cap); any other exception propagates to the activity retry
policy. The usage is always handed back, including a zero-spend
`RoleUsage` (calls=0) when the run was refused before its first request.
[FR-113]

### REQUIREMENTS-1.7
The drafter is the optional registry role `product` (kind proposer,
Temporal wire name `product_agent` — never renamed; `output_type` is
`DraftOutput` with `retries={"output": 3}`) carrying a read-only
`FileSystem` capability exposing exactly `read_file`, `search_files`,
`find_files`, `list_directory`, plus `RepoContext` with no walk-up past
the workspace. `STAGE_ROLES["requirements"] = "product"` is the one place
the stage↔role divergence reconciles, and `PROMPT_SHAS` carries the
role's auto-derived prompt sha. The activity hands its spend back as
`RoleUsage(role="product", cost_usd=None)`; dollars are priced
workflow-side because pricing must stay replay-safe and never fail a
stage. [FR-113]

### REQUIREMENTS-1.8
The graph node type `requirements` has optional `trigger`, `constitution`
and `codebase_map` in-ports, a `requirements` out-port carrying the
`Requirements` payload (whose `digest` field is the memo seam — object
and key always move together), no reject port (partial freeze never
rejects), and `budget_after="continuing"`. A port's identity is
`(direction, name)` (E-72), so clarify legally carries an in-port and an
out-port both named `requirements`. `Requirements` is registered in
`PAYLOAD_TYPES`; `default-requirements.graph.yaml` is the default graph
plus one node and three edges (two triggers from intake, one artifact
edge to clarify's `requirements` in-port), leaving the default graph's
content sha untouched. `select_graph` picks that graph only when
`cfg.requirements_enabled` is set and the registry ships the `product`
role — precedence research > constitution > requirements (no shipped
graph carries more than one of the three nodes, and there is no
explicit-pin mechanism, so another combination needs a graph that
carries it). [FR-113]

### REQUIREMENTS-1.9
The downstream seam is clarify ONLY. Clarify takes the `requirements`
object plus `requirements_digest` read from the same payload, both
omitted at the default, so a run that never saw a requirements draft
keys byte-identically to today (FR-010). The bounded block is
`render_requirements(c, *, max_chars=2000)`: a header plus one US line
per story (id, narrative, `[source_ref]` when present) with its FR and
SC lines nested beneath, `""` for an artifact with no stories,
truncated deterministically to whole lines. `clarify_prompt` composes it
through its third parameter `blocks` — the constitution block, then the
requirements block — placing the requirements between the idea and the
codebase map/recall (idea → constitution → requirements → map → recall),
with the map reaching the fan-out's probes as grounding rather than a
prompt block. [FR-113, FR-010]

### REQUIREMENTS-1.10
The slice exports `step` (on its submodule — the package attribute is
shadowed by the submodule of the same name) and
`ACTIVITIES = [draft_requirements]`. [FR-113]

## Failure modes

- **Usage limit exhausted**: Degrades once to an empty draft, never re-raised; the spend up to the abort is still priced, a run refused before its first request reports zero spend.
- **Partial freeze**: Offending stories and texts are dropped and listed in `dropped`; the stage continues with the survivors and a `warning` on `STAGE_ENDED`.
- **Cap exceeded**: The first `max_stories` survivors are kept with dense ids and a `warning` on `STAGE_ENDED`; capped stories are recorded by the flag, not re-listed as drops.
- **Degraded (zero survivors)**: `outcome=fail` on `STAGE_ENDED`, nothing retained, the pipeline continues with the empty artifact — the opt-in flag can never kill a run.
- **Worker without the role**: The node handler raises (a graph carrying a requirements node requires `agents/product/`); flag-off runs schedule nothing and never reach the handler's model path.
