# PRD — Agentic SDLC Factory

| | |
|---|---|
| Status | Draft v1.1 |
| Date | 2026-07-02 (amended 2026-07-25) |
| Related | `ARCHITECTURE.md`, `SDLC-spec.md` (v2 + v2.1 addendum), `docs/superpowers/specs/2026-07-25-brownfield-assessment-and-outcome-measurement-design.md` |

> **2026-07-25 amendment.** Adds two user groups and four requirement families:
> **FR-900** (Tier 0 repository triage), **FR-910** (Tier 2 capability & risk
> audit, porting the EDCR methodology from
> [`BrownKit`](https://github.com/MaksimShevtsov/BrownKit)), **FR-1000**
> (service platform: tenancy, untrusted-code isolation, repository connection,
> identity), and **FR-1100** (product outcome: pre-registered hypotheses,
> deploy contract, durable observation). Also documents the pre-existing
> **FR-800** context & continuity family, which was live in code but absent
> here. Rationale, alternatives, and the BrownKit gap analysis are in the design
> doc linked above.

---

## 1. Vision

A software factory that takes a feature idea to a deployed, observed feature
through a governed pipeline of specialized AI agents — with humans making
decisions, not doing labor. The operator decides *what* and approves *whether*;
agents handle *how*. The factory learns from every run, so run N+1 is cheaper
and better than run N.

## 2. Problem

Teams adopting coding agents today face four gaps:

1. **No orchestration.** Coding agents (Claude Code, OpenCode) are powerful
   per-task but have no durable, resumable process around them. A crash, a
   deploy, or an overnight wait for approval loses state.
2. **All-or-nothing autonomy.** Existing tools are either fully interactive
   (human babysits every step) or fully autonomous (human reviews a giant PR
   at the end). There is no per-decision autonomy dial.
3. **No structural governance.** Prompt-based rules drift; agents review
   their own work; quality is asserted, not enforced.
4. **No learning.** Every run starts from zero. Clarifications answered last
   week get asked again; gotchas rediscovered every task.

## 3. Users

| Persona | Needs |
|---|---|
| **Operator** (tech lead / senior eng) | start runs, answer clarifications, approve architecture/merge/deploy, handle escalations — from dashboard, chat, or CLI, in minutes/day |
| **Platform engineer** | deploy/scale the factory, configure agents/gates per project, add harnesses, monitor cost |
| **Stakeholder** (PM / EM) | visibility into run status, cost, and what shipped; audit trail of who approved what |
| **Client / auditee** (owns an existing codebase) | connect a repository, get a readiness + risk picture whose evidence they can independently check, approve a remediation backlog, see a provable before/after |
| **Assessor** (consultant / operator assessing a repo they did not write) | run triage and audit on unfamiliar code, bound cost per repository, hand over a defensible evidence bundle |
| **Product owner** | state a hypothesis with a decision rule, ship a PoC or feature behind a flag, and get an honest verdict against the rule they pre-registered |

## 4. Goals / Non-goals

**Goals**
- G1: Idea → deployed feature for greenfield projects and brownfield features
  with configurable human involvement per decision point.
- G2: Durable execution — runs survive crashes, deploys, and multi-day waits.
- G3: Structural quality enforcement — deterministic gates, cross-harness
  review, contract validation.
- G4: Cross-run learning via shared memory.
- G5: Post-deploy maintenance loop (detect → repair through the factory).
- G6: Assessment-first brownfield entry — an existing repository (from a
  days-old vibe-coded app to an enterprise monolith) → deterministic triage →
  optional capability + risk audit → approved remediation backlog → governed
  fix runs → measured risk delta.
- G7: Outcome measurement — a product hypothesis carrying a decision rule
  fixed *before* the build, shipped, then decided against that same rule by
  durable observation.

**Non-goals (v1)**
- NG1: Replacing human product judgment — the factory executes decided work.
- NG2: Multi-repo / monorepo-wide refactors spanning many services per run.
- NG3: A spec-authoring UI (Spec Kit / OpenSpec conventions are consumed,
  not reimplemented).
- NG4: Self-modification — the factory does not change its own prompts,
  validators, or gates autonomously.
- NG5: Assessment never patches a repository directly. Every fix is a governed
  factory run — the same discipline FR-502 already imposes on repair actions.
- NG6: The factory is not a substitute for human security audit or penetration
  testing and issues **no compliance certification**. It produces evidence a
  human auditor can independently verify, not an attestation.
- NG7: The factory does not build deployment or product-analytics substrate.
  Hosting targets and analytics sources are **adapters** over what the customer
  already runs (cf. FR-108's toolchain adapters), never reimplementations.

## 5. User stories

- US-1: As an operator, I submit "Add SSO to our app" with a repo URL and
  receive clarifying questions with suggested answers I can accept in one
  click. *(AC: questions arrive in dashboard + Slack/MCP within one pipeline
  cycle; accept-suggestion is a single action.)*
- US-2: As an operator, I approve an architecture spec before any code is
  written, or send it back with comments for revision. *(AC: a `revise`
  outcome re-runs the architect with the feedback as input, bounded by
  `MAX_GATE_ROUNDS`; `reject` abandons the branch; approval is recorded with
  identity + timestamp.)*
- US-3: As an operator, when a task fails its fix loop, I receive an
  escalation with the resolver's analysis and choose retry-with-guidance or
  quarantine. *(AC: guidance text reaches the same harness session.)*
- US-4: As a platform engineer, I set the merge gate to `soft` with a 0.95
  confidence threshold for a low-risk repo, and `hard` for the billing repo.
  *(AC: per-project YAML config; no code change.)*
- US-5: As a platform engineer, I run the developer role on Claude Code and
  the reviewer on OpenCode with a different model family. *(AC: registry
  validator rejects same-family dev/reviewer configs.)*
- US-6: As a stakeholder, I see every run's stage, cost to date, and pending
  blockers in one screen. *(AC: fleet view + per-run spine.)*
- US-7: As an operator, I ask my chat assistant "what's blocked in the
  factory?" and approve a gate conversationally. *(AC: MCP tools expose
  inbox + decisions.)*
- US-8: As a client, I connect a repository and receive a readiness verdict plus
  a prioritized hygiene list in which every item names a file and line I can
  open myself. *(AC: each finding's quote matches the file byte-exact at the
  assessed commit; a repository that does not build yields a finding, not an
  error; no capability model is required to get this.)*
- US-9: As a client, I approve a tidy-up backlog and get one pull request per
  accepted item plus a before/after triage delta. *(AC: no direct push to a
  protected branch; the delta is a recorded artifact, not prose.)*
- US-10: As an assessor, I run a full audit on a repository I did not write and
  hand the client a bundle in which every claim resolves to evidence. *(AC:
  cross-reference integrity is an absolute check; the bundle regenerates
  identically from the same commit.)*
- US-11: As a product owner, I state a hypothesis with a decision rule, have
  that rule frozen when I approve it, and later see the verdict computed against
  it. *(AC: a post-hoc rule change requires a new audited gate round with both
  versions retained; insufficient data returns `inconclusive`.)*
- US-12: As a platform engineer, I onboard a tenant whose repositories execute in
  isolation with no path to another tenant's artifacts or memory. *(AC: the
  adversarial cross-tenant read/recall test passes; harness execution is
  containerised and non-root.)*

## 6. Functional requirements

### Pipeline (FR-100)
- FR-101: The pipeline SHALL execute the 15-stage DAG defined in SDLC-spec v2
  §1 (intake → … → deploy → retro) as a durable workflow.
- FR-102: Intake SHALL classify runs as greenfield or brownfield; brownfield
  runs SHALL produce a `CodebaseMap` and a delta `Architecture`.
- FR-103: Each stage SHALL be a pure function of hashed, declared inputs;
  unchanged inputs SHALL be served from a content-addressed cache. Memory
  SHALL be pinned per run by a watermark so memoization is deterministic and a
  memory refresh is a deliberate watermark bump. Memoization (skipping
  recompute) SHALL never elide an audit *record* — full history is retained
  regardless of cache hits.
- FR-104: Dev tasks SHALL execute in dependency-ordered parallel waves, each
  in an isolated git worktree cut from the **running integration head**
  (ADR-14), with a dedicated branch merged back into integration on gate
  approval; a task's diff SHALL be measured against its own branch point, not
  the run's base.
- FR-105: Review/analyze failures SHALL trigger a bounded Developer repair
  loop (default 2) resuming the same harness session; QA failures a bounded
  Resolver loop (default 3); exhaustion SHALL escalate to a human gate.
- FR-106: The quality gate SHALL be deterministic and classify each check as
  **absolute** or **advisory**. Absolute checks (lint clean, no critical
  security finding, build/integration green) SHALL block the merge
  unconditionally — no policy or human override. Advisory checks (coverage,
  criterion→test traceability completeness, review/analysis severity — config:
  `high`) SHALL block only until an audited human `GateDecision` override is
  recorded. Coverage SHALL be **diff-scoped**, not a repo-wide ratio. The
  Analyst SHALL *propose* the criterion→test mapping; the gate SHALL *enforce*
  that every acceptance criterion traces to ≥ 1 test. The LLM `MergeVerdict`
  SHALL be advisory input to the gate, never the decider.
- **FR-107 — Grounded research.** The pipeline MAY run a research stage before
  clarification that produces a `ResearchBrief` grounding downstream stages in
  fetched evidence. Every claim presented as grounded MUST carry a source URL
  and a verbatim quote verified against bytes fetched during that run; claims
  that cannot be so verified MUST be presented as inferred, or not at all.
  Research findings retained to memory are leads, not grounded claims: recall
  MUST NOT restore grounded status without re-verification. The stage MUST be
  bounded by explicit per-run limits and is off by default.
- **FR-108 — Language-agnostic toolchain.** The deterministic quality gate's
  stack-specific verification steps — build, test, lint, coverage, and the
  security scan (FR-106) — SHALL be performed by a **toolchain adapter**
  resolved from the produced repository's marker file (e.g. `pyproject.toml`,
  `package.json`, `go.mod`, `Cargo.toml`), so the gate grades whatever language
  was actually built rather than an assumed stack. Adapters SHALL normalize
  their output into the gate's canonical, language-neutral evidence formats
  (one coverage schema, one security-finding schema), so the deterministic gate
  reader is identical across languages and **adding a language SHALL NOT change
  workflow or gate code** (cf. FR-203). Diff-scoped coverage (FR-106) SHALL be
  measured against the running integration head (FR-104): the coverage artifact
  produced by the test step SHALL be available in the integration worktree the
  gate reads. The factory SHALL ship at least one reference adapter exercised
  end-to-end; further language adapters are additive and off the critical path.
- **FR-109 (new scope; ADR-16)** Capture-always harness sessions: every
  harness run emits a canonical, scrubbed `HarnessSession` transcript as a
  claim-checked `ArtifactRef{kind: harness_session}` plus an inline
  `SessionDigest` (waste aggregates + decision-skeleton, always kept).
  Scrub is fail-closed before storage; retention downgrades clean-green
  non-benchmark runs to digest-only (full-transcript TTL remains open,
  OQ-B7).

### Agents (FR-200)
- FR-201: Agents SHALL be declared in a versioned registry (`agents.yaml`):
  role, kind (proposer|harness), model, prompt file, memory policy.
- FR-202: Proposer agents SHALL emit schema-validated Pydantic artifacts;
  validation failure SHALL re-prompt up to a configured retry count.
- FR-203: Harness roles SHALL support `claude -p` and `opencode run` behind a
  common adapter; adding a harness SHALL not change workflow code.
- FR-204: The reviewer SHALL default to a clean-context proposer whose model
  family differs from the developer's author-model family; the registry SHALL
  reject configurations that violate this. When an optional harness
  deep-review tier is configured, it SHALL run a different harness than the
  developer's. The reviewer SHALL NOT resume the developer's harness session.
- FR-205: Proposer decision boundaries (MAY / MUST NOT per SDLC-spec §2)
  SHALL be enforced by validators where expressible.

### Human-in-the-loop (FR-300)
- FR-301: Gates (clarify, architecture, plan, merge, deploy, task
  escalation, repair) SHALL each be configurable hard | soft | off per
  project, with a confidence threshold for soft. A gate SHALL resolve to one
  of `approve | reject | revise`; `revise` SHALL re-enter the producing stage
  with the comments as input, bounded by `MAX_GATE_ROUNDS` (default 2) before
  escalating to a hard human gate.
- FR-302: Decisions SHALL arrive as idempotent signals from any surface (CLI,
  dashboard, MCP, Slack); gate identity SHALL be `(gate, round)` so the first
  decision per round wins and a signal for a superseded round is ignored.
- FR-303: Open gates SHALL push notifications (activity-based, retried) with
  deep links; durable timers SHALL drive reminder, escalation-to-fallback,
  and timeout policies.
- FR-304: Every decision SHALL be recorded with outcome (approve|reject|
  revise), decider (human|policy|timeout), identity `(gate, round)`, comments,
  timestamp — queryable per run. Advisory-check overrides SHALL be recorded as
  audited decisions.
- FR-305: A cross-run decision inbox SHALL list everything awaiting a human.

### Memory (FR-400)
- FR-401: The factory SHALL retain to Hindsight: stage summaries, fix-loop
  experiences, human gate decisions, incidents; and recall per the agent's
  configured banks/filters.
- FR-402: Recall results SHALL be persisted as hashed `RecallSnapshot`
  artifacts and treated as declared stage inputs.
- FR-403: Memory writes SHALL be non-blocking (fire-and-forget with retries)
  and pass a PII/secret scrub hook.
- FR-404: A scheduled reflect job SHALL consolidate learnings nightly
  (project) and cross-project (org).

### Maintenance (FR-500)
- FR-501: A per-project proactive workflow SHALL run the DAPER cycle on a
  timer and on demand (nudge signal).
- FR-502: Repair `code_fix` actions SHALL execute as brownfield factory runs
  (children), never as direct patches; ops actions SHALL be risk-classed.
- FR-503: Repair execution below the confidence threshold SHALL require
  human approval via the standard gate contract; timeout SHALL mean inaction.

### Interfaces (FR-600)
- FR-601: Dashboard: fleet list, per-run stage spine, decision inbox with
  one-click accept-suggestion, approve/reject with comments.
- FR-602: MCP server exposing list/detail/inbox/answer/decide/start tools.
- FR-603: CLI covering the same operations.
- FR-604: All surfaces SHALL be stateless shells over Temporal queries and
  signals (no interface-owned database).

### Governance & ops (FR-700)
- FR-701: Budgets (wall-clock, steps, LLM cost) per run; exhaustion SHALL
  escalate, not silently stop. Cost SHALL aggregate harness JSON cost output
  and model usage records. *(Landed 2026-07-23, E-33: run-level token/cost
  counters in `RunSummary.roles` aggregate both the harness JSON cost output
  and model usage records; a `run_budget_usd` gate escalates through the
  FR-301/302 gate machinery on crossing. Stage-scoped research budgets under
  FR-107 are unchanged.)*
- FR-702: Payloads through workflow history SHALL stay under 2MB via
  claim-check `ArtifactRef`s.
- FR-703: Harness containment SHALL be tiered: at P1 a restricted OS user +
  filesystem ACLs (writes scoped to the worktree) + an egress policy
  (model API and git remote only); at fleet scale a container per run. The
  harness environment SHALL be an **allowlist** (curated toolchain vars +
  injected repo-scoped, short-TTL credentials), never the worker's full
  environment.   Destructive-action denial (out-of-worktree writes, `rm -rf`,
  non-allowlisted network) SHALL be enforced in the `pre_tool` hook, with
  native config (`--allowedTools` / `opencode.json`) as the inner layer — a
  worktree is not a sandbox.
  *(Partially landed 2026-07-24, E-15/E-16: `policy/containment.yaml` +
  a `PreToolUse` hook enforce out-of-worktree writes, recursive deletes,
  agent-config rewrites, and a host allowlist, with denials recorded as
  `ToolDenial` on `HarnessRunResult`. Egress is **tool-level only** — a
  socket opened from inside an allowed `Bash` call is not visible to it.
  Network-level egress and the restricted-OS-user/container tier remain
  open under E-21.)*
- FR-704: An observability export SHALL render run history to
  `events.jsonl` + `report.html`.
- **FR-110 (new scope) — Rubric-judge calibration.** Before a rubric's
  LLM-judge score is trusted in a phase-exit decision, the factory SHALL
  support calibrating that rubric against a sample of human-scored fixtures
  and SHALL report judge-human agreement (a within-epsilon agreement rate,
  mean absolute error, and rank correlation) per rubric. A rubric's
  calibration verdict and agreement rate SHALL be surfaced alongside every
  score derived from it, so a rubric score is never read without its trust
  level. Calibration is an offline measurement tool; it SHALL NOT modify
  scores or gate outcomes automatically -- low agreement is a rubric defect
  to be fixed, not an automatic adjustment.
- **FR-111 (new scope)** opt-in `deep_review` transcript lens -- an advisory
  proposer that reads the *scrubbed* `HarnessSession` (FR-109) as data, once
  per task, ADR-6 family-independent of `dev`. It records an anti-cheat signal
  (oracle peeking / hardcoded answers / test gaming / backtracking) and a
  richer verdict for observability and benchmark aggregation; it NEVER gates
  the merge. Off by default (`deep_review_enabled=False`). The clean-context
  reviewer (FR-204) remains the sole blocking lens.

### Context & continuity (FR-800) — *documented retroactively 2026-07-25*

This family has been live in `src/sdlc/` and `ARCHITECTURE.md` since P1 but was
never written down here. Recorded now so the numbers are not silently reused;
no new scope.

- FR-801: Role prompt assembly SHALL respect a per-role
  `context_budget_tokens`, enforced at assembly rather than by truncation
  downstream.
- FR-802: Harness sessions SHALL resume across fix attempts up to
  `max_session_resumes`, past which a fresh session starts; a detected stack
  mismatch SHALL override toward a fresh session.
- FR-803: `ValidationContract` SHALL express machine-checkable "done", frozen
  at planning before any code is written.
- FR-804: Clean-context validators SHALL see a materialized diff anchored to
  the task's own branch point, plus the contract and test output — nothing else.
- FR-805: `HandoffSummary` SHALL carry structured task→task continuity within
  a run.
- FR-806: Prompts are versioned assets — edit → offline eval → deploy — and the
  prompt hash SHALL participate in the memoization key.

### Assessment, Tier 0 — triage (FR-900) *(new scope)*

Tier 0 answers *"what state is this repository actually in?"* for any
repository, with no preconditions. It is deliberately cheap and mostly
deterministic, because the repositories that most need it are the ones least
able to support expensive analysis.

- **FR-901 — Triage stage.** A durable triage stage SHALL run over a connected
  repository pinned at a commit and produce a `RepoTriage` artifact plus a
  `readiness` verdict covering at minimum: buildable, runnable, tests present,
  and structure discernible. Triage SHALL NOT require a capability model, a
  test suite, a lockfile, or a working build to complete — an unbuildable
  repository is a *finding*, not a failure. Every LLM-derived element of triage
  SHALL be optional; the readiness verdict itself SHALL be computable from
  deterministic signals alone.
- **FR-902 — Hygiene signal set.** Triage SHALL collect, via FR-108 toolchain
  adapters: a build and run probe; a secret scan including **credentials
  reachable from client-side bundles**; dependency health (unpinned, known-
  vulnerable, unused, duplicated); dead and generator-scaffold code;
  framework-default misconfiguration (unauthenticated routes, permissive CORS,
  world-readable storage); size and duplication outliers; and missing baseline
  practice (tests, CI, `.gitignore` hygiene, environment handling). Each signal
  SHALL have exactly one implementation.
- **FR-903 — Readiness gate.** The Tier 2 audit (FR-910) SHALL be gated on the
  triage readiness verdict. A repository that does not build or whose structure
  is not discernible SHALL NOT be capability-mapped; the factory SHALL report
  that precondition as unmet rather than emit a low-confidence capability model.
  The gate SHALL resolve through the standard FR-301/302 machinery, so an
  operator MAY override with an audited decision.
- **FR-904 — Mechanical remediation.** Triage findings SHALL carry a
  `mechanically_fixable` classification. Accepted mechanically-fixable findings
  SHALL execute as brownfield factory runs (NG5), and the factory SHALL re-run
  triage afterwards so the delta between before and after is recorded evidence
  rather than a claim.

### Assessment, Tier 2 — capability & risk audit (FR-910) *(new scope)*

Tier 2 is the EDCR methodology (`BrownKit`: evidence → discovery → capability →
risk) executed as durable, typed, gated stages.

- **FR-911 — Assessment workflow.** A durable `AssessmentWorkflow` SHALL
  execute the EDCR DAG — init → scan → discover → assess → **report** →
  generate → finish — over a repository pinned at a commit. Phase state SHALL
  live in workflow history; a tracked phase-status file is NOT part of this
  design. `report` SHALL run *after* `assess`, because reports render risk
  scores that only `assess` produces. Context injection (`enrich`) and
  pre-implementation risk checks (`gate`) are NOT phases: the former is a
  declared stage input to a brownfield feature run (FR-402 pattern), the latter
  is a set of deterministic gate checks (FR-917).
- **FR-912 — Deterministic scan.** Signal extraction SHALL be deterministic
  activities with exactly one implementation per signal, resolved through
  FR-108 adapters, and memoized on `(repository tree hash, signal version)` per
  FR-103, so re-scanning an unchanged repository is a cache hit. Candidate
  confidence SHALL derive from cross-source corroboration (three or more
  independent sources = high, two = medium, one = low), never from the depth of
  a single source.
- **FR-913 — Capability model.** `discover` SHALL produce a `CapabilityMap`:
  L1 capabilities with **content-derived** stable `BC-NNN` identifiers, L2
  operations, entity ownership resolving to exactly one owner or a surfaced
  conflict, and file→capability coverage at or above a configurable floor
  (default 0.90) with every orphan explicitly classified as attached,
  infrastructure, or dead. Delivery channels and deployment boundaries SHALL
  NOT be treated as capabilities. Identifier stability SHALL be a property of
  content, not of iteration order — two runs over the same commit SHALL produce
  the same identifiers. **This artifact satisfies FR-102's `CodebaseMap`.**
- **FR-914 — Verified grounding.** Every assessment finding presented as
  grounded MUST carry a path, a line span, and a verbatim quote verified
  **byte-exact against the pinned commit during that run**. Verification SHALL
  be fail-closed: a claim that cannot be so verified MUST be presented as
  inferred, or not at all. Findings recalled from memory are leads, not
  grounded claims; recall MUST NOT restore grounded status without
  re-verification. (The FR-107 invariant, applied to code instead of fetched
  bytes, and sharing its verifier.)
- **FR-915 — Measurement honesty.** Every measurement in the assessment
  contract set SHALL distinguish a measured value from `not_collected` (with a
  recorded reason) and from `unknown`. A missing measurement SHALL NEVER
  default to zero. Composite scores MAY be `partial` or `unknown` with
  justification. This requirement applies to the **existing** gate and QA
  contracts as well: a coverage figure that was never measured SHALL be
  distinguishable from a measured zero.
- **FR-916 — Risk model.** `assess` SHALL produce, per capability: a STRIDE
  threat model in which a category with no applicable threat carries an
  explicit rationale rather than being omitted; vulnerabilities classified
  `confirmed | probable | potential` with location and threat linkage; control
  coverage across authentication, authorization, validation, monitoring, and
  encryption; a security composite over likelihood, impact, and exposure; a QA
  composite over coverage gap, testability, defect density, and change
  velocity; and a unified composite in [0,1] or a `partial`/`unknown`
  sentinel, carrying **one to three specific drivers** — a generic label is not
  a driver. Cross-capability analysis SHALL identify shared vulnerabilities,
  cascading failures, weak trust boundaries, and privilege-escalation chains.
- **FR-917 — Assessment gate.** Risk thresholds SHALL be deterministic gate
  checks under FR-106: BLOCK on a confirmed unaccepted vulnerability, on a
  testability blocker in a high-criticality capability, or on a unified
  composite ≥ 0.8; WARN between 0.6 and 0.79; otherwise PASS. False-positive
  dispositions (`false_positive | mitigated_elsewhere | accepted_risk`) SHALL
  be recorded as audited human decisions per FR-304 and SHALL persist across
  re-runs.
- **FR-918 — Acceptance criteria as code.** Per-phase exit criteria and the
  terminal acceptance criteria SHALL be evaluated as `CheckResult`s computed by
  pure code from typed artifacts — never asserted by the agent that produced
  those artifacts. Cross-reference integrity (every capability, threat,
  vulnerability, and testability identifier cited anywhere resolves to a real
  record) SHALL be an **absolute** check.
- **FR-919 — Remediation backlog.** `generate` SHALL emit capability-scoped
  specification seeds naming only files that exist. Each accepted seed SHALL
  start a brownfield `FeatureWorkflow` child run (NG5). The seed's validation
  criteria SHALL become that run's acceptance criteria, so a fix is graded
  against the assessment that motivated it.
- **FR-920 — Re-assessment and delta.** An assessment SHALL be re-runnable at a
  later commit, SHALL re-scan only capabilities whose files changed, and SHALL
  compute a per-capability risk delta. The delta is the evidence of value and
  SHALL be first-class output, not a derived report.
- **FR-921 — Evidence bundle.** The factory SHALL produce a reproducible
  bundle: a machine-readable manifest, role-scoped reports (architect,
  developer, SDET, security, stakeholder), every finding with its verification
  status, all gate results with their overrides, and the `HarnessSession`
  transcripts (FR-109) of any fix runs. This bundle is simultaneously the
  customer deliverable and the audit trail (NFR-4).
- **FR-922 — Assessment budgets.** Assessment input size is chosen by the
  customer, not the factory, so each phase SHALL carry wall-clock, token, and
  cost ceilings. Exhaustion SHALL escalate per FR-701; partial results SHALL be
  marked partial and SHALL NEVER be presented as complete (FR-915).

### Service platform (FR-1000) *(new scope)*

- **FR-1001 — Tenancy by construction.** Every workflow, artifact, and memory
  bank SHALL be scoped to a tenant by namespace, store prefix, and bank
  namespace — not by a query filter. Memory recall SHALL NOT cross a tenant
  boundary under any configuration. (Resolves OQ-4.)
- **FR-1002 — Untrusted-code isolation.** A connected repository is untrusted
  input. Harness execution and all build, test, and lint execution over
  customer code SHALL run in a per-run container as a non-root user, with no
  host mount beyond the worktree and a **network-level** egress allowlist.
  FR-703's tool-level containment is the inner layer, not the boundary — a
  `pre_tool` hook cannot see a socket opened inside an allowed command. This is
  a **precondition** for admitting any external tenant.
- **FR-1003 — Repository connection.** Tenants SHALL connect repositories by
  installing a VCS app, not by surrendering a personal token. Credentials SHALL
  be short-TTL, repository-scoped, minted per run, and never persisted
  (satisfying FR-703's credential clause). Delivery SHALL be by pull request
  only — the factory SHALL NOT push to a protected branch.
- **FR-1004 — Identity and authorization.** Every surface SHALL authenticate,
  and every `GateDecision` SHALL record a real principal, closing FR-304's
  identity gap. Per-tenant roles SHALL distinguish at minimum owner, approver,
  and viewer.
- **FR-1005 — Metered cost attribution.** Per-tenant, per-run cost SHALL derive
  from the FR-701 counters and be exportable for billing, with per-tenant
  ceilings enforced through the same gate machinery.
- **FR-1006 — Deployment topologies.** The same artifact SHALL be deployable
  single-tenant on-premises or multi-tenant hosted, with the model provider
  endpoint configurable so a customer MAY use their own credentials or gateway.
  No mandatory SaaS dependency (NFR-7).
- **FR-1007 — Retention and deletion.** Evidence, transcripts, and memory SHALL
  carry a per-tenant retention policy. A tenant deletion request SHALL purge
  artifacts, banks, and transcripts, and the purge itself SHALL be audited.

### Product outcome (FR-1100) *(new scope)*

Where FR-100…FR-700 govern whether the factory built the thing correctly,
FR-1100 governs whether the thing was worth building — and holds that judgment
to the same evidentiary standard.

- **FR-1101 — Hypothesis at intake.** A run MAY carry a `Hypothesis`: the
  metric, the expected direction, the minimum effect worth shipping, the
  decision rule, the kill condition, and the observation window. It SHALL be
  gated before any code is written.
- **FR-1102 — Pre-registration.** On approval, the decision rule SHALL be
  frozen and hashed, exactly as `ValidationContract` freezes at planning
  (FR-803). A post-hoc change SHALL be a new, audited gate round with both
  versions retained — never a silent rewrite. The factory's contribution here
  is that the rule cannot be edited after the data arrives.
- **FR-1103 — Metric traceability.** Every hypothesis metric SHALL trace to at
  least one instrumentation task and at least one emitted event, enforced by
  the same deterministic gate mechanism as criterion→test traceability
  (FR-106). An uninstrumented hypothesis SHALL NOT reach deploy.
- **FR-1104 — Deploy contract.** The deploy stage SHALL split into a
  `DeployPlan` and a `DeployReport` covering environment, feature flag and
  cohort, rollback procedure, and the distinction between a smoke-tested
  deployment and a pull-request merge. (This replaces the hardcoded single
  deploy command and closes DAG stage 13 for *all* runs, not only experiments.)
- **FR-1105 — Substrate adapters.** Hosting target and product-analytics source
  SHALL be adapters resolved from configuration, following FR-108's pattern.
  The factory SHALL ship one reference adapter for each and SHALL NOT
  reimplement hosting, feature flagging, or analytics (NG7).
- **FR-1106 — Durable observation.** A durable timer SHALL span the observation
  window. On expiry the factory SHALL collect the metric, evaluate the
  pre-registered rule, and open a keep / kill / extend gate through the
  standard FR-301/302 machinery.
- **FR-1107 — PoC mode.** A run MAY be marked a proof of concept: bounded
  budget, explicitly disposable output, a preview deployment, and a recorded
  decision. PoC output SHALL be marked so it never silently accrues as
  production debt.
- **FR-1108 — Honest verdicts.** Insufficient data SHALL yield `inconclusive`.
  A verdict SHALL NEVER be reported as favourable on data that does not meet
  the pre-registered rule's requirements — FR-915's measurement honesty applied
  to product metrics.

## 7. Non-functional requirements

- NFR-1 **Durability:** no run state lost on worker/server restart; waits of
  ≥ 7 days supported.
- NFR-2 **Scale (v1 targets):** 50 concurrent runs, 200 concurrent harness
  tasks across pooled workers; harness and proposer pools scale
  independently.
- NFR-3 **Latency:** operator surfaces reflect state within 5 s; decision
  signals take effect within 2 s.
- NFR-4 **Auditability:** every artifact, decision, retry, and cost item
  reconstructible from history + artifact store.
- NFR-5 **Security:** tiered harness containment (restricted OS user + FS
  ACLs + egress policy now, container at scale — a worktree is not a sandbox);
  environment allowlist, not passthrough; repo-scoped, short-TTL credentials
  only (never org-wide); least-privilege harness tools with destructive-action
  denial in the `pre_tool` hook; secrets never in prompts, history, or memory
  (scrub hook); operator surfaces authenticated.
- NFR-6 **Reproducibility & auditability (distinct concerns):** identical
  inputs + prompts + model + watermarked memories = cache hit; any variation
  is an explicit, hashed input change. Auditability is independent of
  memoization — every artifact, decision, and cost item stays reconstructible
  from history even when recompute was skipped.
- NFR-7 **Portability:** self-hostable (Temporal OSS, Hindsight OSS,
  Postgres, object store); no mandatory SaaS.
- NFR-8 **Tenant isolation:** no data path SHALL exist between tenants.
  Isolation is proven by an adversarial test that attempts cross-tenant artifact
  reads and memory recall, not asserted by configuration review.
- NFR-9 **Hostile input:** every connected repository SHALL be treated as
  attacker-controlled. Build scripts, test code, configuration, and dependency
  manifests are attacker-controlled surfaces; executing any of them is an
  execution of untrusted code (FR-1002).
- NFR-10 **Assessment reproducibility:** the same repository at the same commit
  SHALL yield identical deterministic signals and an identical grounded-finding
  set. Fused, LLM-derived layers SHALL carry confidence rather than present
  false precision, and their variance SHALL be observable across runs.

## 8. Success criteria

- SC-1: ≥ 80% of runs reach the merge gate without human intervention beyond
  configured gates (no unplanned escalations).
- SC-2: Median operator time per shipped feature ≤ 15 minutes of decisions.
- SC-3: Fix-loop success (no escalation) ≥ 70% of failing tasks.
- SC-4: Repeat-clarification rate (same question re-asked on same project)
  trends to < 10% by run 10 — the memory efficacy metric.
- SC-5: Zero deploys past a failed **absolute** gate check; zero *unattended*
  deploys past any failed check (a failed advisory check requires an audited
  human override) — the hard invariant.
- SC-6: Soft-gate auto-approvals overridden by humans < 5% when sampled —
  the confidence calibration metric.
- SC-7: **Grounding integrity** — 100% of findings labelled grounded re-verify
  byte-exact on independent re-check, and a sampled audit finds zero fabricated
  path or line references. This is the assessment product's hard invariant, and
  it plays the role SC-5 plays for the pipeline: a single violation is a defect,
  not a percentage to improve.
- SC-8: **Capability coverage** — ≥ 90% of source files map to a capability
  with every orphan explicitly classified, on ≥ 80% of assessed repositories
  that pass the readiness gate.
- SC-9: **Remediation efficacy** — for accepted backlog items, the post-fix
  re-assessment shows a reduced unified composite for the targeted capability in
  ≥ 80% of cases, with no new critical finding introduced.
- SC-10: **Assessment economics** — median cost and wall-clock per assessed
  repository reported per repository-size band, so the work can be priced.
- SC-11: **Pre-registration adherence** — ≥ 95% of experiments are decided by
  the rule pre-registered at the hypothesis gate, with no post-hoc modification.
  A modification is not a failure if audited; an *unaudited* one is.
- SC-12: **Instrumentation completeness** — 100% of hypothesis metrics trace to
  an emitted event before the deploy gate opens.

## 9. Rollout

| Phase | Scope | Exit criteria |
|---|---|---|
| P1 | Greenfield pipeline, CLI only, hard gates everywhere, no memory | one project shipped end-to-end |
| P2 | Brownfield mode, dashboard + notifications, fix loops, cross-harness review | first brownfield feature merged via PR |
| P3 | Hindsight memory + confidence-gated soft gates | SC-4 and SC-6 measurable |
| P4 | MCP surface, maintenance loop (DAPER), fleet scale | SC-1..3 at target |
| P5 | Triage + tidy-up (Tier 0/1), operator-run, single tenant | one unfamiliar repository triaged, a mechanical backlog fixed through governed runs, before/after delta recorded |
| P6 | Capability & risk audit (Tier 2) + evidence bundle | one repository audited end-to-end with SC-7 held and a bundle handed over |
| P7 | Hosted multi-tenant service | NFR-8 adversarial test green; FR-1002 container tier live; a tenant onboards without operator assistance |
| P8 | Product outcome loop | one hypothesis pre-registered, shipped, and decided by its own rule (SC-11/SC-12) |

**Phase independence.** P5/P6 do not depend on P7: assessment delivered by an
operator on repositories they are authorised to run needs neither tenancy nor
self-serve onboarding. P7 is what converts operator-delivered work into a
product strangers can use, and FR-1002 is its gating item. FR-913 lands *inside*
P2, since it is how FR-102's `CodebaseMap` gets built.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Agent confidence miscalibrated → bad auto-approvals | start all gates hard; calibration report in retro (SC-6) before enabling soft |
| Coverage/tests gamed by same-factory authorship | criterion→test traceability check; cross-harness review; mutation testing later |
| Harness CLI breaking changes (`claude`, `opencode`) | adapter layer + contract tests against pinned versions; fake harness in CI |
| Memory poisoning (bad learnings compound) | validators outrank memory; retain scrubbing; reflect review; bank-level reset |
| Cost runaway on fix loops | per-run budgets (FR-701), bounded loops, cost surfaced per run |
| Temporal history bloat on long runs | claim-check discipline (FR-702), continue-as-new policies |

## 11. Open questions

- OQ-1: Clarifier confidence — numeric self-score vs. separate judge call?
- OQ-2: **Resolved (ADR-14):** parallel task branches integrate onto a
  **running integration branch** — each task's worktree is cut from the
  current integration head and merged back on gate approval, so later tasks
  build on earlier merged work rather than a stale base. (Conflict-handling
  policy on merge-back remains to be tuned in P2.)
- OQ-3: Per-run working-memory banks (`run:<id>`) vs. project-bank metadata
  only — defer until P3 data exists.
- OQ-4: **Resolved (FR-1001):** multi-tenant isolation is by construction —
  namespace, store prefix, and memory-bank namespace per tenant, proven by the
  NFR-8 adversarial test. It stopped being deferrable the moment an external
  repository became an input.
- OQ-5: Is there a repository class for which Tier 0 triage *is* the whole
  product and Tier 2 never pays for itself? A packaging question, answerable
  only against real repositories — do not guess it in advance.
- OQ-6: **Blocking FR-913.** What canonical key makes a `BC-NNN` identifier
  content-derived *and* stable across refactoring? A key over file paths breaks
  when files move; a key over entity names breaks on rename. Without an answer,
  "stable identifiers" is aspiration and every cross-reference in the evidence
  bundle is fragile.
- OQ-7: Does FR-914 quote verification run inline per finding or as a batch
  gate before storage? Per-finding is simpler and fail-closed by default; batch
  is cheaper on an assessment producing thousands of findings.
- OQ-8: Given NG6, what exactly does the FR-921 evidence bundle assert, in what
  words? This needs review by someone qualified in liability before the first
  external hand-off, not after.
- OQ-9: FR-1106 reads a metric from a **customer-controlled** analytics source
  to decide keep/kill. What prevents a mis-instrumented or manipulated metric
  from driving the verdict? This is FR-914's grounding problem inside a system
  the factory does not control, and it has no obvious answer yet.
