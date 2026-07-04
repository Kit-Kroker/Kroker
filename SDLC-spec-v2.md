# Agentic SDLC Specification v2

> Supersedes v1. Keeps v1's contracts, decision boundaries, and governance.
> Changes only what conflicted with the chosen substrate: **Temporal** is the
> orchestrator and state layer, **Pydantic AI** is the agent runtime, coding
> harnesses (`claude -p`, `opencode run`) are first-class executors, and
> **Hindsight** is the shared learning memory. The Pydantic schemas in
> `factory/models.py` remain the source of truth; this document explains them.

The factory is a deterministic state machine over a fixed DAG, executed as a
Temporal workflow. Each stage's agent *proposes* a schema-validated artifact;
the orchestration layer validates, authorizes, executes, and records it.

> **Rule 1 (revised): The model never acts outside a contained, observed
> boundary.** Thinking agents propose structured artifacts and never touch
> tools. Coding harnesses may act, but only inside a risk-classed, budgeted
> *containment* — a git worktree gives the diff boundary, but isolation is
> enforced by a restricted OS user + FS ACLs + egress policy (container at
> scale), never by the worktree alone (§7). Only their *diff* is admitted as
> an artifact.

> **Rule 2 (new): Memory is I/O.** All Hindsight calls happen in Temporal
> activities. A stage never reads memory implicitly: recall produces a
> persisted, hashed `RecallSnapshot` artifact that is a declared stage input.
> This keeps every stage a pure function of hashed inputs (v1 §1 preserved).

---

## 1. Lifecycle stages

Unchanged order from v1; each row now maps to a Temporal construct. The
pipeline is one `FactoryWorkflow` execution; stages are activities or child
workflows on the `ai-sdlc` task queue.

| # | Stage | Owner | Temporal construct | Persisted artifact | Success criteria |
|---|---|---|---|---|---|
| 0 | intake | *(deterministic)* | workflow init | `IdeaBrief{mode}` | mode ∈ {greenfield, brownfield} resolved |
| 1 | constitution | *(deterministic)* | local code | `Constitution` | governing principles fixed |
| 2 | context | Cartographer *(brownfield only)* | activity (repo tools) | `CodebaseMap` | modules, contracts, hot spots extracted from repo |
| 3 | requirements | Product | TemporalAgent activity | `Requirements` | ≥1 story; FR-### + SC-### |
| 4 | clarify | Clarifier | TemporalAgent + **gate(clarify)** | `Clarifications` | ambiguities resolved; low-confidence ones routed to human |
| 5 | architecture | Architect | TemporalAgent + **gate(architecture)** | `Architecture` | greenfield: stack+tree+contracts; brownfield: **delta** (added/modified/removed) grounded in `CodebaseMap` |
| 6 | planning | Planner | TemporalAgent + **gate(plan)** | `TaskPlan` | acyclic DAG (Kahn validator, kept from v1); phased vertical slices |
| 7 | code | Developer | **long-running activity** (harness) per task, parallel waves | `CodeArtifact` | worktree cut from the **running integration head** (ADR-14); diff measured against the task's branch point; merged back into integration on gate approval; honors contracts |
| 8 | review | Reviewer | TemporalAgent activity *(clean-context proposer; optional harness deep-review tier)* | `ReviewReport` | contract conformance; blocking issues listed |
| 9 | analyze | Analyst | TemporalAgent activity | `AnalysisReport` | cross-artifact consistency; *proposes* criterion→test mapping (gate enforces) |
| 10 | qa | QA (+ Resolver) | activities (test run + repair loop) | `TestReport` | red→green within `MAX_REPAIR_ATTEMPTS` |
| 11 | quality_gate | *(deterministic)* | local code + **gate(merge)** | `GateReport` | `DeterministicQualityGate`: absolute checks (lint, no critical security, build/integration) pass, advisory checks (coverage, traceability completeness, severity) pass-or-human-overridden |
| 12 | deploy | DevOps | activity + **gate(deploy)** | `DeployPlan` → `DeployReport` | greenfield: smoke test; brownfield: PR merged + env deploy |
| 13 | retro | *(deterministic + reflect)* | activity | `RunSummary` + memory retains | trace + metrics; learnings written to Hindsight |

Kept from v1: constitution, quality gate, and summary are deterministic code —
no LLM call. The propose/persist split is kept: QA and DevOps *propose*
(test files, `DeployPlan`); the orchestration *persists* what actually
happened (`TestReport`, `DeployReport`).

**Fix loops (correction to v1, which only had the QA loop):**
- review/analyze critical issue → bounded Developer repair loop
  (`MAX_REVIEW_FIX_ATTEMPTS = 2`), resuming the same harness session
  (`claude --resume` / `opencode -s`) so context is preserved. Then escalate.
- qa failure → Test-Error-Resolver, `MAX_REPAIR_ATTEMPTS = 3` (unchanged).

---

## 2. Agent roster & configurable registry

v1's decision boundaries are kept verbatim and remain enforced structurally
(schema validators, contract checks, deterministic gate) — not prompt prose.

**Correction:** agents are no longer hardcoded `AgentSpec`s. The registry is
config, loaded at worker start:

```yaml
# agents.yaml — the "configurable agents" surface
defaults:
  model: anthropic:claude-sonnet-4-6
  validation_retries: 2          # Pydantic AI output_retries handles v1's re-prompt loop

agents:
  product:
    output_model: Requirements
    prompt: prompts/product.md
    memory:
      recall: {banks: [project], top_k: 8, filters: {kind: requirements}}
      retain: {bank: project, kind: requirements}
  clarifier:
    output_model: Clarifications
    prompt: prompts/clarifier.md
    memory:
      recall: {banks: [project, org], top_k: 10, filters: {kind: clarification}}
      retain: {bank: project, kind: clarification}
  architect:
    model: anthropic:claude-opus-4-8        # per-agent override
    output_model: Architecture
    prompt: prompts/architect.md
    memory:
      recall: {banks: [project, org], top_k: 12, filters: {kind: [adr, incident]}}
      retain: {bank: project, kind: adr}
  developer:
    kind: harness                            # acts, doesn't propose
    harness: claude_code                     # or opencode
    memory:
      recall: {banks: [project], top_k: 6, filters: {kind: [convention, gotcha]}}
  reviewer:
    kind: proposer                           # clean-context reviewer, default
    output_model: ReviewReport
    model: openai/gpt-5.2                     # different family than developer's author model
    prompt: prompts/reviewer.md
    deep_review:                             # optional escalation tier
      kind: harness                          # a harness that can read the tree, run greps
      harness: opencode                      # cross-harness: never the developer's
      trigger: {on: [large_diff, security_touch, low_confidence]}
    memory:
      recall: {banks: [project, org], top_k: 8, filters: {kind: review_finding}}
      retain: {bank: project, kind: review_finding}
  # analyst, qa, resolver, devops, cartographer ...
```

Loader semantics: `kind: proposer` (default) builds a Pydantic AI `Agent`
with the declared `output_model` and wraps it in `TemporalAgent`; `kind:
harness` routes the role through the harness activity. **Constraint carried
over from v1 activity-naming rules:** agent names and toolset ids become
Temporal activity names — adding agents is safe, renaming deployed ones is a
breaking change. The registry validator enforces the review-independence
invariant: `reviewer.model family ≠ developer author-model family` (a
clean-context proposer that shares no authoring bias), and, when the
`deep_review` tier is configured, `reviewer.deep_review.harness ≠
developer.harness` (cross-harness deep review by construction). The reviewer
never resumes the developer's harness session — review starts from a clean
context by definition.

Schema-validation retries: v1's `MAX_VALIDATION_RETRIES` re-prompt loop is
**deleted as custom code** — Pydantic AI's output validation retries provide
it natively; the count moves to `defaults.validation_retries`.

---

## 3. State, communication, and error handling

**Correction (the big one): Temporal owns state.** v1's `run_manifest.md` +
`events.jsonl` re-implemented durable execution; two sources of truth is one
too many.

| v1 mechanism | v2 replacement |
|---|---|
| `run_manifest.md` (current stage, statuses) | workflow state, exposed via **queries** (`status()`, `pending_gate()`) |
| `events.jsonl` (append-only trace) | Temporal event history is the record of truth; `events.jsonl` + `report.html` become an **export** rendered by the retro stage |
| retry counters in the harness | activity `RetryPolicy` + bounded loops in workflow code |
| loop budgets (steps, wall-clock, cost) | workflow timers + a `Budget` counter in workflow state; cost accumulated from harness `total_cost_usd` and TemporalAgent usage; exhaustion → escalate gate |
| "stop cleanly, write ESCALATION.md" | **durable signal wait** (see §5); `ESCALATION.md` is still written, as the gate's human-readable payload |
| input hashes for incremental re-runs | content-addressed activity cache keyed on `hash(inputs + prompt_file_content + model_id + recall_snapshot)`; memory is pinned per run by a **watermark** so re-runs inside a run are deterministic cache hits and a memory refresh is a deliberate watermark bump, not silent drift — *correction:* v1's hash omitted prompt and model, so prompt edits served stale artifacts. Auditability (full Temporal history, every artifact) is separate from memoization (skipping recompute): the cache never elides a *record*, only the recompute. |

The v1 `Message` envelope is kept as the logical protocol (it documents
hand-offs), but it is *derived from* Temporal history, not maintained
alongside it. `trace_id` = workflow id; `attempt` = activity attempt.

**Payload discipline (new, forced by Temporal):** history payloads are
capped (2MB). `CodeArtifact` inline files, full test logs, and recall dumps
do not travel through workflow state — they live in the artifact store /
git, referenced by `ArtifactRef{kind, uri, sha256}` (claim-check).

---

## 4. Artifact standards

All v1 contracts kept, with three changes:

1. **`CodeArtifact` becomes a union** (the change that admits real harnesses):
   ```python
   class CodeArtifact(BaseModel):
       # propose-mode (v1, kept — fine for small greenfield tasks & QA test files)
       files: list[FileSpec] | None = None
       # harness-mode (new): claude -p / opencode run acted in the sandbox
       diff_ref: ArtifactRef | None = None      # commit/patch in task worktree
       commit_sha: str | None = None
       harness_session: str | None = None        # resume handle for fix loops
       # exactly one of files / diff_ref must be set (model validator)
   ```
   Reviewer, Analyst, QA, and the gate consume the materialized diff either
   way; downstream contracts are unchanged.

2. **`Architecture` gains brownfield fields:** `mode`, and a
   `delta: {added[], modified[], removed[]}` block that must reference
   modules present in `CodebaseMap` (validator). Greenfield runs leave
   `delta` empty and populate `file_tree` as in v1.

3. **New contracts:**
   - `CodebaseMap { modules[], contracts[], entry_points[], hot_spots[] }`
   - `RecallSnapshot { agent, bank_ids[], query, memory_ids[], content_ref, sha256 }`
     — the hashed memory input (Rule 2)
   - `GateDecision { gate, round, outcome: approve|reject|revise, decided_by:
     human|policy|timeout, comments }` — *correction:* a boolean `approved`
     cannot express "send back for revision," which is the common gate
     outcome. `revise` re-enters the producing stage with the comments as
     input; identity is `(gate, round)` so a late signal for a superseded
     round is ignored (idempotency survives the revision loop). See §5.
   - `HarnessRunResult` gains observability fields the budget and
     context-ceiling logic depend on: `input_tokens, output_tokens,
     context_window, compacted` — so the workflow can measure "near the
     context ceiling" (`input_tokens > fraction × context_window`) rather
     than guess, and detect a harness that silently compacted mid-task.

Enum fix carried from review: `TaskStatus` drops the duplicate — 
`pending | running | done | blocked | failed` (no separate `in_progress`).

---

## 5. Human-in-the-loop (correction: gates, not just escalation)

v1's only human touchpoint was escalate-and-stop. v2 keeps escalation but
generalizes it: **escalation = entering a hard gate.** Under Temporal a gate
is a durable signal wait — free to hold for hours or days, idempotent
(first decision per gate wins), timeout → auto-reject + notify.

Per-gate policy, configured per project:

| Gate | Default | `hard` | `soft` | `off` |
|---|---|---|---|---|
| clarify | soft | human answers every open question | Clarifier auto-assumes above confidence threshold; below it, questions route to human with suggested answers | all auto-assumed (v1 behavior) |
| architecture | hard | human approves spec | quality signals auto-approve | skip |
| plan | soft | — | — | — |
| merge | hard | human approves | deterministic gate + quality-gate verdict auto-approve | skip |
| deploy | hard | always human for real envs | staging auto | sandbox smoke only (v1 behavior) |
| task escalation | hard (always) | fix loops exhausted → human accepts / retries / quarantines | n/a | n/a |

Human decisions arrive as Temporal signals (`submit_gate_decision`,
`answer_question`) from any surface (CLI, dashboard, Slack). Every decision
is **retained to Hindsight** (§6) — human feedback is the highest-value
learning signal the factory produces.

**Gate outcomes and the revision loop.** A gate resolves to one of
`approve | reject | revise` (§4). `approve` advances; `reject` terminates the
branch (quarantine/abandon); `revise` re-enters the producing stage with the
gate comments as an added input and increments `round`. The revision loop is
bounded (`MAX_GATE_ROUNDS`, default 2) — exhaustion escalates to a hard human
gate rather than looping forever. Because gate identity is `(gate, round)`, a
decision signal that names a stale round is dropped: no double-advance, no
lost revision.

**Merge-gate precedence (the merge row above, expanded).** The merge gate is
not a single verdict. `DeterministicQualityGate` runs first and classifies
each check as **absolute** (lint clean, no critical security finding,
build/integration green) or **advisory** (coverage, criterion→test
traceability completeness, review severity). A failed *absolute* check blocks
the merge unconditionally — no human, no `soft` policy, can wave it through.
A failed *advisory* check blocks only until a human override is recorded (an
audited `GateDecision`, retained). The LLM-produced `MergeVerdict` is
advisory input to that gate, never the decider: **models emit evidence,
deterministic code decides, humans override only audited advisory checks.**

---

## 6. Shared memory (Hindsight)

Hindsight (`vectorize-io/hindsight`, self-hosted, Postgres-backed) gives the
factory memory that *learns* across runs: world facts, experiences, and
mental models, accessed via `retain` / `recall` / `reflect`.

**Bank layout** (metadata filters give per-agent views without bank sprawl):

| Bank | Scope | Holds |
|---|---|---|
| `org` | all projects | engineering conventions, cross-project incident learnings, gate-rejection patterns |
| `project:<repo>` | one repo | ADRs, module contracts, clarified assumptions, review findings, deploy gotchas |
| `run:<id>` *(optional)* | one run | working memory for very long runs; folded into `project` at retro |

Every memory carries metadata: `{kind, agent, stage, run_id, task_id}` — the
recall filters in `agents.yaml` (§2) select on these.

**Integration points (all activities; Rule 2):**

| Point | Operation | Content |
|---|---|---|
| before each agent stage | `recall` → `RecallSnapshot` | per the agent's configured banks/filters/top_k; snapshot persisted, hashed, injected into the prompt |
| after each stage success | `retain(project)` | artifact summary (not the full artifact — the store holds that) |
| after fix loops | `retain(project, kind=gotcha)` | *experiences*: what failed, what fixed it — this is what makes attempt N+1 cheaper |
| after every `GateDecision` | `retain(project, kind=gate_feedback)` | human approve/reject + comments |
| retro stage (13) | `reflect` | consolidate the run into mental models ("this repo's migrations always break X") |
| nightly Temporal **Schedule** | `reflect(org)` | cross-project consolidation — the factory-wide learning loop |

**Governance additions (extends v1 §5):**
- Recall is read-only context; it can never override the constitution or an
  artifact contract (validators still win — "failures become validators"
  stays the primary learning channel for *hard* rules; Hindsight learns the
  *soft* ones).
- `RecallSnapshot` in the memoization key means: same inputs + same memories
  = cache hit; memory changed = legitimate re-run. Reproducibility preserved.
- Retain runs as a fire-and-forget activity with retries — memory writes
  must never block or fail the pipeline.
- PII/secret scrubbing hook on retain (`pre_retain` in the hook layer).

---

## 7. Governance & constraints (v1 kept, deltas only)

Kept unchanged: risk-classed actions, sandbox confinement (now: git worktree
per task under `runs/<id>/worktrees/<task>/`), hook layer (`pre_tool`,
`post_tool`, `stop`, + new `pre_retain`), deterministic quality gate,
hallucination control via Reviewer contract check, failures-become-validators.

Deltas:
- **Harness containment (a worktree is not a sandbox).** Isolation is
  *tiered*: at P1, a restricted OS user + filesystem ACLs scoping writes to
  the worktree + an egress policy; at fleet scale, a container per run. The
  harness environment is an **allowlist, not a passthrough** — curated
  `PATH`/`HOME`/toolchain vars plus deliberately-injected repo-scoped,
  short-TTL credentials (GitHub App installation token or fine-grained PAT,
  never org-wide), never the worker's full environment. Destructive-action
  denial lives in the **`pre_tool` hook** (deny/escalate out-of-worktree
  writes, `rm -rf`, non-allowlisted network) — not in `--allowedTools`, which
  is a capability list, not a guardrail. Egress is restricted to the model API
  and the git remote. Harness-native config (`--allowedTools` + permission
  mode; locked `opencode.json`) is the *inner* layer, not the only one.
- **Secrets never enter prompts, history, or memory.** Credentials are
  injected into the harness environment at run time and scrubbed from any
  artifact, log, or retain payload (`pre_retain`, §6).
- **Merge gate = per-check classification, not one threshold.** The
  `DeterministicQualityGate` splits checks into **absolute** (lint, no
  critical security finding, build/integration green — never overridable) and
  **advisory** (coverage, traceability completeness, review severity —
  overridable only by an audited human `GateDecision`). Blocking severity for
  the *advisory* review-finding check defaults to `critical`; projects may set
  `high`. See §5.
- **Coverage honesty (traceability is proposed, then enforced).** The Analyst
  *proposes* a criterion→test mapping; the gate *enforces* that every
  acceptance criterion traces to ≥1 test, and prefers **diff-scoped** coverage
  over a repo-wide ratio (v1's coverage ≥ 0.80 alone is gameable when the same
  factory writes code and tests, and dilutes on large repos).
- **Budgets** include LLM spend, summed from harness JSON cost output and
  TemporalAgent usage records; visible in the run summary and in Temporal
  search attributes for fleet-level queries.

---

## 8. What was deliberately NOT kept from v1

- The custom orchestrator loop, manifest, and event log as state — replaced
  by Temporal (v1's design was a hand-rolled durable-execution engine; the
  ideas survive, the plumbing doesn't).
- The custom schema-validation re-prompt loop — Pydantic AI output retries.
- "Harness acts, not the model" as an absolute — replaced by the sandbox
  boundary rule, because `claude -p` / `opencode run` are the product
  requirement and propose-only `CodeArtifact.files` cannot express iterative,
  test-driven implementation on brownfield code.
- Escalate-and-stop as the only HITL — replaced by policy gates; stop is now
  a wait.
