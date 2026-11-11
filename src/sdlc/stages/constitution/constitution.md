# Constitution Stage

The constitution stage (Stage 1, FR-112) drafts the run's governing principles
and freezes them into the `Constitution` artifact the post-constitution
proposer stages (clarify, architect, planner) consume. It is off by default:
a run opts in by carrying a constitution node in its graph
(`default-constitution.graph.yaml` ships as the reference such graph).

The split is the house rule (the model proposes, code validates): a registry
drafter agent proposes a raw `DraftOutput` over a read-only workspace, and a
deterministic `freeze` assigns the ids and the digest workflow-side. Freeze is
partial — offending principles are dropped, never retried or repaired — and
the stage holds no gate, so the opt-in flag can never kill a run: a degraded
draft fails soft into the empty artifact.

## Requirements

### CONSTITUTION-1.1
The constitution step receives a `StageContext` protocol and required
collaborators as keyword arguments, never the workflow instance, and never
calls `ctx.gate`: partial freeze means the opt-in flag can never kill a run,
so a degraded constitution fails soft into the empty artifact. [FR-101, FR-112]

### CONSTITUTION-1.2
The flag is `PipelineConfig.constitution_enabled` (bounds on
`PipelineConfig.constitution`: `ConstitutionConfig(enabled=False,
max_principles=12, max_requests=6)`), overlaid from graph presence at the
single `project_cfg` call site — never set by project config alone. Flag off
returns the empty artifact (`drafted_by="empty"`, `principles=[]`,
`digest=""`) with zero activities scheduled: byte-identical to a graph
without the node. [FR-112, FR-010]

### CONSTITUTION-1.3
Flag on, the step schedules exactly one draft activity
(`draft_constitution`), freezes the raw draft workflow-side via
`freeze(result.draft, mode=inp.deps.mode)` — ids and digest are assigned by
code, never by the model — prices the returned usage through `price_usage`,
and emits `STAGE_ENDED` directly via `ctx.emit`: no benchmark row and no
`duration_s` are recorded for this stage, and its cost reaches the run's
tracking through the `MODEL_USAGE` event. A freeze that dropped principles
carries a `warning` naming the count; a degraded freeze carries
`outcome=fail` plus `warning="no principle survived freeze"` and retains
nothing; a non-degraded freeze retains one `STAGE_SUMMARY` whose text is the
frozen principles and whose metadata carries `stage`, `digest` and `run_id`.
[FR-112]

### CONSTITUTION-1.4
`freeze` is a deterministic partial freeze over the raw draft: ids `CP-1`,
`CP-2`, … are code-assigned in surviving order (the model never names the
artifact's ids); in brownfield mode items with an empty `source_ref` (`None`
or `""`) are dropped (greenfield is exempt — an idea-alone draft has nothing
to cite); exact-duplicate statements (verbatim, case-sensitive; whitespace
variants are distinct) collapse to the first occurrence; statements that are
empty or whitespace-only are dropped; zero survivors degrade the stage
(`drafted_by="empty"`, `digest=""`, `degraded=True` — verify never raises).
[FR-112]

### CONSTITUTION-1.5
`constitution_digest` is sha256 over the sorted `(statement, normative)`
pairs — prose, ordering and ids drop out, content remains, so the same
principles hash the same everywhere. `""` for an empty list is the
wire-level sentinel (research's ungrounded-brief convention): a flag-off or
fully-dropped constitution digests, keys and renders identically to no
constitution stage at all. [FR-112, FR-010]

### CONSTITUTION-1.6
The activity resolves its workspace through one predicate: the repo
checkout when `repo_path` names an existing directory, else an empty scratch
workspace at `$SDLC_RUNS_ROOT/<run_id>/constitution/` (default root
CWD-relative `runs/`), created before the run. The prompt's mode line
derives from that resolved workspace, not from `deps.mode` — which remains
the freeze contract — so the prompt can never instruct repo citation over a
tree the agent cannot read. `UsageLimitExceeded` degrades once to an empty
draft and is never re-raised (the bound is config; a retry hits the same
exhausted cap); any other exception propagates to the activity retry policy.
[FR-112]

### CONSTITUTION-1.7
The drafter is the optional registry role `constitution` (kind proposer,
Temporal wire name `constitution_agent` — never renamed; `output_type` is
`DraftOutput` with `retries={"output": 3}`) carrying a read-only
`FileSystem` capability exposing exactly `read_file`, `search_files`,
`find_files`, `list_directory`, plus `RepoContext` with no walk-up past the
workspace. The activity hands its spend back as
`RoleUsage(role="constitution", cost_usd=None)`; dollars are priced
workflow-side because pricing must stay replay-safe and never fail a stage.
[FR-112]

### CONSTITUTION-1.8
The graph node type `constitution` has an optional `trigger` in-port, a
`constitution` out-port carrying the `Constitution` payload (whose `digest`
field is the memo seam — object and key always move together), no reject
port (partial freeze never rejects), and `budget_after="continuing"`.
`Constitution` is registered in `PAYLOAD_TYPES`;
`default-constitution.graph.yaml` is the default graph plus one node and
five edges (two triggers from intake, three artifact edges to
clarify/architect/planner), leaving the default graph's content sha
untouched. [FR-112]

### CONSTITUTION-1.9
The downstream seam is `render_constitution(c, *, max_chars=2000)`: the
bounded prompt block (a header plus one line per principle), `""` for a
constitution with no principles, truncated deterministically to whole lines.
Clarify, architect and plan take the `constitution` object plus
`constitution_digest` read from the same payload, and both the memo key and
the prompt insert the constitution between the idea and the codebase
map/recall (idea → constitution → map → recall). [FR-112, FR-010]

### CONSTITUTION-1.10
The slice exports `step` (on its submodule — the package attribute is
shadowed by the submodule of the same name) and
`ACTIVITIES = [draft_constitution]`. [FR-112]

## Failure modes

- **Usage limit exhausted**: Degrades once to an empty draft, never re-raised; the spend up to the abort is still priced, a run refused before its first request reports zero spend.
- **Partial freeze**: Offending principles are dropped and listed in `dropped`; the stage continues with the survivors and a `warning` on `STAGE_ENDED`.
- **Degraded (zero survivors)**: `outcome=fail` on `STAGE_ENDED`, nothing retained, the pipeline continues with the empty artifact — the opt-in flag can never kill a run.
- **Worker without the role**: The node handler raises (a graph carrying a constitution node requires `agents/constitution/`); flag-off runs schedule nothing and never reach the handler's model path.
