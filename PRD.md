# PRD — Agentic SDLC Factory

| | |
|---|---|
| Status | Draft v1.0 |
| Date | 2026-07-02 |
| Related | `ARCHITECTURE.md`, `SDLC-spec.md` (v2 + v2.1 addendum) |

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

## 4. Goals / Non-goals

**Goals**
- G1: Idea → deployed feature for greenfield projects and brownfield features
  with configurable human involvement per decision point.
- G2: Durable execution — runs survive crashes, deploys, and multi-day waits.
- G3: Structural quality enforcement — deterministic gates, cross-harness
  review, contract validation.
- G4: Cross-run learning via shared memory.
- G5: Post-deploy maintenance loop (detect → repair through the factory).

**Non-goals (v1)**
- NG1: Replacing human product judgment — the factory executes decided work.
- NG2: Multi-repo / monorepo-wide refactors spanning many services per run.
- NG3: A spec-authoring UI (Spec Kit / OpenSpec conventions are consumed,
  not reimplemented).
- NG4: Self-modification — the factory does not change its own prompts,
  validators, or gates autonomously.

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
  and model usage records.
- FR-702: Payloads through workflow history SHALL stay under 2MB via
  claim-check `ArtifactRef`s.
- FR-703: Harness containment SHALL be tiered: at P1 a restricted OS user +
  filesystem ACLs (writes scoped to the worktree) + an egress policy
  (model API and git remote only); at fleet scale a container per run. The
  harness environment SHALL be an **allowlist** (curated toolchain vars +
  injected repo-scoped, short-TTL credentials), never the worker's full
  environment. Destructive-action denial (out-of-worktree writes, `rm -rf`,
  non-allowlisted network) SHALL be enforced in the `pre_tool` hook, with
  native config (`--allowedTools` / `opencode.json`) as the inner layer — a
  worktree is not a sandbox.
- FR-704: An observability export SHALL render run history to
  `events.jsonl` + `report.html`.

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

## 9. Rollout

| Phase | Scope | Exit criteria |
|---|---|---|
| P1 | Greenfield pipeline, CLI only, hard gates everywhere, no memory | one project shipped end-to-end |
| P2 | Brownfield mode, dashboard + notifications, fix loops, cross-harness review | first brownfield feature merged via PR |
| P3 | Hindsight memory + confidence-gated soft gates | SC-4 and SC-6 measurable |
| P4 | MCP surface, maintenance loop (DAPER), fleet scale | SC-1..3 at target |

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
- OQ-4: Multi-tenant isolation (namespace per team?) — defer to fleet scale.
