# Architecture decision records

The ADR catalogue for the Agentic SDLC Factory, split out of
`ARCHITECTURE.md` §12 on 2026-10-12 for the 1000-line file-size
ceiling. Section numbering in `ARCHITECTURE.md` is unchanged, so
existing "ARCHITECTURE.md §12" references resolve to its short
pointer; the catalogue itself lives here. ADR-22, ADR-23 and ADR-24
and the 2026-10-11 amendments to ADR-2, ADR-6, ADR-9 and ADR-12 carry
the agent architecture plan's decisions (see
`docs/roadmap/agent-architecture-plan.md`; targets there are marked
per `docs/documentation-rules.md`).

## 12. Architecture decision records

- **ADR-1 Temporal owns state** (not a custom manifest/event-log
  orchestrator). Durable timers, signals, retries, visibility for free; the
  v1 hand-rolled engine's ideas survive as workflow code; `events.jsonl`
  demoted to export. *Trade-off:* determinism discipline required in
  workflow code (enforced by import-linter).
- **ADR-2 Pydantic AI for proposers, harness CLIs for doers.** Typed,
  validated artifacts where thinking happens; full agentic tool use where
  code gets written. The `TemporalDurability` capability (003; previously
  the deprecated `TemporalAgent` wrapper) gives durability without custom
  glue.
  *Trade-off:* two agent runtimes to operate.
  *Amended 2026-10-11 (plan, not built):* "proposers think, doers act"
  becomes "roles read, doers write". Proposer roles may hold read-only,
  commit-pinned repo tools inside a step budget (ADR-22); only harness
  roles write. pydantic-ai becomes one adapter behind the `RoleRunner`
  port (ADR-23), and a pydantic-ai coding agent is an allowed dev-harness
  option beside the CLIs.
- **ADR-3 `CodeArtifact` = files[] | diff_ref union.** Propose-mode for
  small/greenfield and test files; harness-mode (diff in worktree) for real
  iterative work. Downstream consumers see one materialized diff.
- **ADR-4 Gates as policy-driven durable signal waits** (hard/soft/off +
  confidence threshold). A decision's outcome is `{approve, reject, revise}`,
  and gate identity is `(gate_name, round)` so `revise` loops back
  (bounded) while idempotency holds per round. One mechanism serves
  approvals, questions, escalations, repairs, *and revisions* — one inbox
  everywhere. *Trade-off:* calibrated confidence is a prompt-engineering
  liability → monitored via SC-6.
- **ADR-5 Hindsight as advisory memory; auditability vs memoization split.**
  Auditability (persisted artifacts + snapshots + history) is the invariant;
  memoization is a best-effort dev-loop cache. A per-run memory watermark
  pins recall — reusing the persisted snapshot *is* the freeze — so memory is
  refreshed on purpose, not busted by nightly `reflect`. *Trade-off:* extra
  artifact per stage; the memoization module and watermark are real (if
  small) components Temporal does not provide.
- **ADR-6 Anti-collusion review by construction.** The real invariant is
  *different model family than the developer's authoring model*; the reviewer
  is a clean-context proposer (no tools/repo/session) by default, so the doer
  has tools and the judge does not. The registry validator enforces
  model-family inequality. **Precise boundary for sessions (ADR-16):** the
  default `review` starts from a clean context and **never resumes the
  developer's session**; the optional, opt-in `deep_review` tier (ROADMAP
  E-39) reads the **scrubbed** `HarnessSession` as *data* (never the raw
  session, never via resume-handle), stays ADR-6 family-independent of the
  developer, and is an **additional** decorrelated lens, not a replacement
  for clean-context review — so it additionally rejects same harness+family.
  Default review starts clean and never resumes the developer's session. The
  optional `deep_review` tier (FR-111/E-39) reads the *scrubbed* HarnessSession
  as data — never the raw session, never via resume-handle — is ADR-6
  family-independent of `dev`, and is advisory-only: an additional lens, never a
  replacement for the clean-context reviewer.
  Structural, not prompt-based.
  *Amended 2026-10-11 (plan, not built):* (a) the inequality is checked on
  the **model**, not the provider prefix. `main` compares prefixes
  (`check_adr6_families` → `model_family`), so `zai:glm-5.3` (reviewer) and
  `zai-coding-plan/glm-5.3` (dev) pass as different families while being
  the same weights — the invariant does not hold today. Benchmark data
  about reviewer behaviour from runs on the default arm was therefore
  produced with the reviewer on the developer's weights and is not
  evidence for or against ADR-6; the fix is a precondition for the plan's
  AP-3 gate, not part of it. It cannot land alone: once the check
  compares models, the shipped registry fails it, so the reviewer's second
  family has to be chosen first. (b) It widens from
  the reviewer to every judge: reviewer lenses, architect critic, plan
  critic. (c) "The judge has no tools" becomes "the judge has no write
  tool and no view of the developer's session"; read-only repo access is
  allowed.
- **ADR-7 Repairs execute through the factory.** MaintenanceWorkflow starts
  brownfield children for code fixes; autonomy never bypasses gates.
- **ADR-8 Interfaces are stateless signal/query shells.** No interface DB;
  Temporal is the single source of run truth; surfaces cannot drift.
- **ADR-9 Two worker pools by capability.** Proposer vs. harness queues:
  independent scaling, credential isolation, cheap fleet economics.
  *Amended 2026-10-11 (plan, not built):* five pools routed per role
  (§9), with worktree affinity and shared storage as prerequisites. `main`
  still runs one queue.
- **ADR-10 Claim-check for all large payloads.** 2MB history limit as a
  design forcing-function; `ArtifactRef{kind, uri, sha256}` everywhere.
- **ADR-11 Deterministic DAG, deliberately — contra the "Bitter Lesson."**
  Current practice argues orchestration should live in prompts/skills so
  architectures improve with each model release. We adopt that *within*
  stages (agent behavior, registry config, prompts) and reject it *between*
  stages: an SDLC needs auditability, gates that cannot be reasoned around,
  and reproducible re-runs — properties only a fixed, deterministic DAG
  provides. *Trade-off:* pipeline shape changes require code + versioning
  discipline; accepted as the price of governance.
- **ADR-12 Contract-first validation with clean-context validators.**
  Validation Contracts freeze "done" before implementation; validators never
  see the worker's narrative or session. Correctness is measured against
  requirements, not implementation bias — the structural complement to
  ADR-6's cross-harness rule. *Trade-off:* planning gets heavier; contracts
  can be wrong — which is exactly what the plan gate reviews.
  *Amended 2026-10-11 (plan, not built):* clean context means no view of
  the worker's session or narrative; read-only access to the worktree is
  allowed. Contracts stop relying on the plan gate alone to be right: code
  dry-runs every contract command before implementation starts.
- **ADR-13 Serial-by-default implementation; context by reference.**
  Worktrees prevent file collisions, not design divergence, so
  implementation defaults to serial with declared-overlap serialization in
  wave mode; agent context is handles + scoped extracts with per-role
  budgets, and sessions are resume-bounded (fresh session + structured
  handoff past the ceiling — compaction is failure). The ceiling is
  *measured*: `input_tokens > fraction × context_window` (from the harness
  result JSON), with `max_session_resumes` as a hard fallback — not a blind
  resume count. *Trade-off:* lower throughput per run and stricter
  prompt-assembly plumbing, in exchange for design consistency and sustained
  reasoning quality over long runs.
- **ADR-14 Integration by running branch.** Worktrees isolate but do not
  compose; a `sdlc/<run_id>/integration` branch accumulates completed task
  work, tasks branch from its head, and merge back on QA pass. The merge PR
  is `integration → base` (resolves the old OQ-2). Validator diffs anchor to
  the branch point; a wave-mode merge conflict is a falsified `overlaps`
  declaration → serialize or escalate. *Trade-off:* integration fixes
  visibility, not divergence (still serial-by-default's job); adds a
  merge-back activity and run-scoped worktree paths.
- **ADR-15 Toolchain adapters for language-agnostic evaluation.** Generated
  projects are not one language, so the stage-11/12 quality activities
  (`run_test_suite`, `run_lint`, `security_scan`, `measure_coverage`) cannot
  hardcode one toolchain. A `ToolchainAdapter` registry (`TOOLCHAINS`, beside
  `HARNESSES`) resolves **by marker file in the produced repo**
  (`pyproject.toml`/`package.json`/`go.mod`/`Cargo.toml` — the built artifact
  decides, not the Architect's stated stack) and normalises
  `build()/test()/lint()/coverage()` into the existing `TestReport`. Two format
  invariants keep the deterministic gate language-agnostic and *unchanged*:
  canonical coverage is **Cobertura XML** (each adapter translates into it;
  `measure_coverage` already reads `coverage.xml`), and the absolute security
  floor is **semgrep → SARIF** (one multi-language tool, so `security_no_critical`
  / SC-5 stays a single check, not per-language sprawl). This is the exact
  shape of ADR-2/3's harness adapter, applied to the evaluation toolchain:
  adding a language is adding an adapter, never a fork. Rollout is incremental
  — one reference adapter (Python) proves the seam end-to-end; further languages
  are added on demand as the benchmark corpus needs them (ROADMAP §9.8,
  E-30/E-30a-c). *Trade-off:* a new abstraction and registry to maintain, and a
  per-language translation shim, in exchange for a grade that holds across every
  language the factory can emit. **New scope** vs a Python-only pipeline —
  likely a PRD line for the multi-language capability, not only this ADR.
  *2026-08-08 (E-41a–d):* the adapter gains its first pure per-language
  **parser** member, `function_spans`, beside its command strings. It runs no
  subprocess and touches no filesystem, so ADR-15's purity rule holds; it is
  the same kind of member as `classify_test_exit` — a per-language
  interpretation rather than a command. Framework fingerprints and
  misconfiguration rules deliberately do **not** live here: one language
  serves many frameworks.
- **ADR-16 Harness sessions as first-class, claim-checked artifacts.**
  Every harness run emits a canonical `HarnessSession` — a normalised
  transcript (tool-calls, file reads/writes, commands + exit status, model
  turns) — as `session_ref: ArtifactRef{kind: harness_session}` on
  `HarnessRunResult` (§4). Normalising the transcript is the **harness
  adapter's** responsibility, beside the resume-handle it already owns
  (`claude --resume` / `opencode -s`) — same registry and pattern as the
  toolchain adapter (ADR-15). Because capture is **always-on**, three
  properties are hot-path invariants, not options: claim-check is
  unconditional (transcripts are large, never touch workflow state — the
  second reason FR-702 must close, beside diffs); the memory scrub
  (`pre_retain`) runs over the session **before** storage, **fail-closed**
  like the SC-5 security floor (an injected credential in an always-stored
  transcript is a leak by default); and retention follows a decided policy —
  full transcript on fail / benchmark / any run with >0 fix-loop attempts, a
  structured `SessionDigest` (§4.3 waste aggregates + decision-skeleton,
  computed pre-truncation and always kept) on clean-green runs, never a blind
  byte-truncation; scrub runs fail-closed **before** the full-vs-digest
  branch, so a scrub failure stores nothing either way (full-transcript TTL
  is the one open sub-point, OQ-B7). The session is the concrete **P5 trajectory
  seam** (§10): most of what `events.jsonl`/`report.html` render and the
  extraction point for trajectory eval + small-model distillation. Consumers
  are the offline benchmark/anti-cheat, the opt-in `deep_review` lens
  (ADR-6, E-39), trajectory harvesting, and retro distillation into memory —
  **never** the default clean-context reviewer (ADR-6). *Trade-off:* a
  storage + scrub cost on every run, in exchange for making agent behaviour
  (not just its output diff) a first-class, measurable signal. **New scope.**
- **ADR-17** Containment as a declared harness capability — a `CodingHarness`
  declares which layers it can enforce (`native` / `hook`); the policy is one
  versioned asset (`policy/containment.yaml`) compiled per adapter. Native
  config is the **inner** layer and the hook the outer one, which is
  structural rather than conventional: a hook's `allow` cannot bypass a
  `permissions.deny` rule (verified against claude 2.1.219). Because a native
  denial is **not** structurally reported (`permission_denials` is empty for
  it) while a hook denial is, `layer:` declares a rule's *minimum* capability
  and each adapter enforces at every layer it has. Total absence of layers
  fails closed (cursor); partial coverage is recorded in `ContainmentReport`,
  never silent; `strict` promotes partial coverage to a refusal. The hook
  (`python -m sdlc.harness.hook`) is its own import-light module — it runs
  once per tool call and must not import Temporal/pydantic_ai — and receives
  the policy path explicitly (`--policy`), because its cwd is the task
  worktree (a temp dir) where repo-root discovery would fail. **Adapter
  reality (unequal mechanisms):** claude compiles to `permissions.deny` +
  `hooks.PreToolUse` (full, observable); opencode (1.18.4) has no config flag
  and no config env var, so its native deny is written into the worktree's
  own `opencode.json` — self-protecting via the `edit` deny the same
  compilation emits for agent-config paths; cursor surfaces neither and fails
  closed. **This is a fence, not a sandbox:** egress denial is tool-level only
  (a socket opened inside an allowed `Bash` call is invisible); the
  OS-user/container tier is E-21.
- **ADR-18** Triage precedes capability modelling — a repository that does not
  build, or whose structure is not discernible, is **not** capability-mapped;
  the factory reports the precondition as unmet (FR-903) instead of emitting a
  low-confidence model. The forcing case is the repository class the assessment
  product exists for: the EDCR methodology is enterprise-brownfield machinery
  (BIAN / TM Forum / ACORD / HL7 blueprints), and against a three-week-old
  vibe-coded repo its ≥90% file→capability coverage has nothing to map to,
  every QA composite degenerates to `unknown`, and per-capability STRIDE
  reasoning is paid for over structure that does not exist. So Tier 0 triage
  (FR-900) is a distinct, cheaper, deterministic tier that **gates** Tier 2
  (FR-910) rather than a first pass of it. *Trade-off:* two artifact families
  and two workflows instead of one, in exchange for never shipping a
  confident-looking capability model derived from absent structure — a wrong
  answer here is not a weaker audit, it is a misleading one. **New scope.**
- **ADR-19** Deployment targets and product-analytics sources are **adapters,
  not substrate** — resolved from configuration exactly as toolchains are
  (ADR-15), with one reference adapter each and no hosting, feature-flagging,
  or analytics implementation of our own (NG7). This is what keeps the
  product-outcome loop (FR-1100) an adjacent capability rather than a second
  product: what remains after the substrate is excluded is a frozen contract, a
  traceability check, a durable timer, and a gate — all mechanisms this system
  already has. *Trade-off:* the factory's verdict depends on a metric read from
  a system it does not control, which is FR-914's grounding problem outside our
  trust boundary and is recorded unresolved as **OQ-9**. **New scope.**
- **ADR-20** Pre-registration reuses contract-freeze semantics — an
  experiment's decision rule is frozen and hashed at the hypothesis gate
  precisely as `ValidationContract` freezes at planning (FR-803), and a
  post-hoc change is a new audited gate round retaining both versions, never a
  silent rewrite. One freeze mechanism, one audit shape, and the property that
  carries the value (the rule cannot be edited once the data is visible) is
  inherited rather than reinvented. *Trade-off:* rigidity is the point — an
  owner who genuinely learns something mid-window must pay an audited round to
  act on it, which is the cost of the guarantee. **New scope.**

  *Extended 2026-07-25 (E-17):* the same hook carries approval, not only
  denial. claude's `permissionDecision: "defer"` suspends the call and ends
  the print-mode run, so the durable wait lives in the workflow's existing
  gate rather than in an activity awaiting a signal. `defer` is print-mode
  only and **solo-only** — a defer emitted for a batched call is discarded
  and the call falls through to `acceptEdits` — so the hook counts sibling
  tool_use blocks and denies when it cannot guarantee a solo defer.
  Degradation is always toward deny.

- **ADR-21 The agent board is a durable projection, never a second source of
  truth.** Typed stage artifacts (`ClarifiedRequirements`, `ArchitectureSpec`,
  `ImplementationPlan`, `DevTask[]`) previously existed only in Temporal
  history, so "what design did run X propose?" required a replay and nothing
  could carry a *status*. The board makes them addressable: immutable bodies in
  the claim-check store, a mutable graph in SQLite, versioned per project with
  lineage across runs. Agents may move task status; the workflow alone writes
  `authoritative_status`. **That split is the whole design.** Statistics,
  scoring, and any human reading "what happened" consume
  `authoritative_status` only, so an agent that crashes mid-claim,
  double-claims, or reports optimistically corrupts the live view and nothing
  else — Temporal history still reconstructs the run, preserving §12's
  auditability invariant. Divergence between the two columns is itself a
  surfaced signal. Storage splits on the mutable/immutable line because they
  have different needs: bodies want content addressing (sha256, already built
  for ADR-16), state wants transactions. SQLite supplies serialization from the
  standard library — `BEGIN IMMEDIATE` plus a `row_version` compare-and-swap is
  what makes two agents racing for one task yield one winner and one `409`.
  *Rejected:* a git-backed board in the target repo (most reviewable, but status
  churn becomes merge conflicts and every claim is a commit) and extending
  Hindsight (already project-scoped, but a semantic recall system has no state
  machine and no compare-and-swap). *Trade-off:* one SQLite file is correct for
  a single worker container and must become Postgres before a second one — the
  same threshold at which `server start-dev` has to go. **New scope.**

  *Idempotency is a load-bearing requirement, not a nicety.* Temporal executes
  activities at least once: an activity that commits and then loses its worker
  before reporting completion is re-run. Board writes must therefore absorb
  re-execution — a repeated terminal transition is a no-op returning the
  current row, not an `InvalidTransition`, because the latter fails identically
  on every retry and turns a transient worker blip into a permanently failed
  run.

  *Deferred, deliberately:* replacing the deterministic pipeline with an LLM
  scheduler that reads the board and dispatches. Externalizing state is what
  makes dynamic task graphs, resume, and re-entry possible, and Temporal can
  read the board and dispatch without surrendering replay. Building the
  orchestrator on top later means it can be *measured* against the workflow
  rather than adopted on faith; adopting it now would trade replay,
  gate semantics, and benchmark signal-to-noise for flexibility already
  obtained.

- **ADR-22 A deterministic workflow of bounded ReAct agents** *(decided
  2026-10-11 from the plan; not built)*. Workflow outside, agents inside:
  the orchestrator owns order, retries, budgets and gates, and no model
  decides what runs next. Inside one role step an agent may loop over
  read-only tools up to its step budget, then must return structured
  output. Of the common agentic patterns the system uses custom logic as
  its backbone plus sequential, parallel, bounded loop, review-and-critique,
  iterative refinement, ReAct inside roles and human-in-the-loop;
  **coordinator and swarm are excluded on purpose** — no LLM picks the next
  agent, and agents exchange only typed evidence, so judges stay
  independent. *Rejected:* one autonomous agent running the pipeline —
  harder to measure, and the workflow, gates and prompt-gate already give
  the skeleton. *Trade-off:* predictability over flexibility; more tool
  calls, tokens and latency per role, held by per-role budgets.
- **ADR-23 Kroker owns the role contract; the AI SDK is an adapter**
  *(decided 2026-10-11 from the plan; not built)*. A `RoleRunner` port sits
  between roles and the SDK, as `CodingHarness` already sits between tasks
  and the CLIs. Validators and verdicts run in Kroker code after the SDK
  returns, and a failed check resumes the same conversation with the error;
  SDK hooks stay an implementation detail of their adapter. Every model and
  tool call remains a Temporal activity. `RoleSpec` names the SDK beside
  the model. *Trade-off:* a port to maintain with one adapter behind it; a
  second SDK is added only for a stated reason, since each brings its own
  replay tests and durability bugs.
- **ADR-24 Evidence before verdict; code computes the verdict** *(decided
  2026-10-11 from the plan; not built)*. Every output schema lists evidence
  fields before status fields, judges run with thinking on, and no stage
  passes on a model's say-so: `approve`, `tests_passed`, `plan_valid` and
  their kin are pure, unit-tested functions over typed evidence. *Trade-off:*
  a stricter reviewer may block too much, so false-block rate is tracked on
  a seeded-mutation set and the human waiver path stays. The north-star
  metric becomes reviewer–oracle agreement beside task pass rate. Every
  prompt or model change ships with a before/after on prompt-gate or the
  benchmark, one variable at a time, behind a per-role flag.
