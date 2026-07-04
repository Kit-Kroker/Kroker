# Architecture Pressure-Test — Review & Decisions

| | |
|---|---|
| Status | Decisions recorded 2026-07-03 |
| Scope | Critical review of `PRD.md`, `ARCHITECTURE.md`, `SDLC-spec-v2.md`, cross-checked against the `src/sdlc/` skeleton |
| Method | Findings ranked worst-first; each deep-dived to a resolution and applied back into the three specs |

---

## Spine

The resolutions all rest on one principle, which the docs imply but never state cleanly:

> **LLMs emit typed evidence; deterministic code decides; humans override only audited *advisory* checks; task code integrates on a run branch; memory is pinned per run and refreshed on purpose; harnesses run contained with least-privilege; and everything is auditable by construction.**

Recurring root cause: the docs are strongest on **orchestration and governance** and weakest on (a) **code integration** — how task branches compose — and (b) **where the deterministic/LLM boundary actually sits** (reviewer, quality gate, and traceability all blur it).

---

## Finding #1 — Dependency-ordered tasks never integrate each other's code — **CRITICAL**

**Problem.** `create_worktree` branches every task from `base_branch` (activities.py:33), yet tasks carry `depends_on` edges and the waves/handoffs story (ARCH §3, FR-104/805) assumes task B builds on task A. In the current model B's worktree contains none of A's code — only a prose `HandoffSummary`. Dependency ordering buys nothing, and OQ-2 ("N branches → one PR") is the mirror image of the same missing object: an **accumulation point**.

**Decision — running integration branch (approach A).**
- Create `sdlc/<run_id>/integration` from `base` at run start; it accumulates completed task work.
- Each task branches from the **current integration head**, not from base. In wave mode, all tasks in a wave branch from the head frozen at wave start.
- On clean-context QA pass, an activity merges the task branch back into integration. The next task/wave branches from the updated head.
- The merge-gate PR is simply `integration → base`. OQ-2 dissolves: continuous integration onto a run branch — neither sequential-rebase nor octopus.
- **Validator diffs anchor to the branch point**, not base, so a dependent task's diff shows only its own change (preserves clean-context validation).
- Wave-mode merge conflict = a **falsified `overlaps` declaration** (now detectable) → serialize the loser (re-run from updated head) or escalate. Makes `overlaps` verifiable rather than trusted.

**Caveat.** Integration fixes **visibility, not divergence**. It guarantees B can *see* A's code; it does not stop parallel agents making inconsistent design choices — that remains serial-by-default's job (ADR-13).

**Implied edits.**
- Docs: PRD FR-104 + OQ-2 (resolved); ARCH §3 + new ADR-14; SDLC §1 code stage note.
- Code (to-do): `create_worktree` takes `from_ref` (integration head SHA); new activity `merge_into_integration(task_branch, integration_branch) → conflict?`; `get_task_diff` anchors to the branch-point SHA, not `base_branch...HEAD`; run-scoped paths `runs/<run_id>/worktrees/<task>/`; `TaskResult`/worktree record the branch-point SHA.

---

## Finding #2 / #3 — Memoization: conflates auditability with caching, and has no owner — **HIGH**

**Problem.** NFR-6 states memoization as an *invariant* ("identical inputs + prompts + model + memories = cache hit") and implies bit-identical reproducibility — false for LLM/harness stages regardless of caching. Separately, the nightly org `reflect` (FR-404) mutates the org bank → every recall snapshot changes → agent stages cache-miss every run once memory is on (ADR-5 concedes this). And Temporal provides no cross-run activity memoization: the cache referenced ~4× (FR-103, §3, ADR-5, ARCH §3) has no owner or mechanism.

**Decision — separate the two concepts; build a watermark cache first-class.**
- **Auditability** = the standing invariant (persisted artifacts + RecallSnapshots + Temporal history reconstruct everything). This is real and always on.
- **Memoization** = a best-effort *dev-loop* optimization (skip unchanged upstream stages when re-running a fixed idea after a prompt/config edit). ROI is bounded: it saves stages *upstream* of the edit; the expensive code stage is almost always downstream and re-runs anyway.
- **Mechanism (the missing owner):** a content-addressed activity cache — `key = hash(activity_name + inputs + prompt_content + model_id + upstream_recall_snapshot_ref)` — backed by the existing artifact store (hash-named keys, no new infra). A `memoization` module wraps activity dispatch.
- **Per-run memory watermark** dissolves the churn conflict: recall is itself a cached activity keyed on `hash(agent + banks + filters + query + watermark)`. Reusing the *persisted* RecallSnapshot **is** the freeze — nightly `reflect` mutates the live bank, not the frozen snapshot. Default re-run reuses the watermark (reproducible, cache-warm); an explicit "refresh memory" advances it (picks up new learnings, intentionally busts downstream caches).
- De-risks the Hindsight dependency (#10): no point-in-time read support needed — the snapshot store provides the freeze.

**Implied edits.** PRD NFR-6 (auditability-invariant vs memoization-best-effort) + FR-103 caveat; ARCH §3 (watermark + cache + owner) + ADR-5 (controlled refresh); ARCH §14 (`memoization` module). Code (to-do): cache wrapper; watermark capture at run start; `HarnessRunResult`/recall wiring.

---

## Finding #4 — Reviewer specified as both proposer and harness — **HIGH**

**Problem.** SDLC §1 row 8 = "TemporalAgent activity"; SDLC §2 `agents.yaml` = `kind: harness`; ARCH §4 lists it under long-running harness runs. Three-way inconsistency. It matters because ADR-6's registry validator (`reviewer.harness ≠ developer.harness`) is only load-bearing if the reviewer *is* a harness.

**Decision — clean-context proposer by default (A) + optional harness deep-review tier (C).**
- Reviewer = `TemporalAgent → ReviewReport`, no tools, no repo, no worker session. Inputs are orchestrator-assembled: materialized diff + frozen contract + test output + scoped `CodebaseMap` extracts / affected call sites (ARCH §3 "handles, not walls"). It *physically cannot* wander or be polluted — ADR-12's clean-context ideal enforced structurally.
- Clean structural split: **the doer (developer) has tools; the judge (reviewer) does not** — a stronger anti-collusion story than "two harnesses reviewing each other," and cheaper + typed.
- ADR-6's real invariant is **model-family inequality**, not harness inequality. Default validator: `reviewer.model family ≠ developer authoring-model family`.
- **Optional deep-review tier (C):** a harness reviewer, configurable per project/task for high-risk work. When enabled, the harness-inequality clause re-applies to *that path*.

**Implied edits.** SDLC §1 row 8 (canonical) + §2 `agents.yaml` (`reviewer: kind: proposer, output_model: ReviewReport`, note deep-review tier); ARCH §4 (move reviewer to automation table; model-tiering) + ADR-6 (model-family default, harness clause conditional); PRD FR-204.

---

## Finding #5 — Two different things called "the quality gate"; SC-5 rides on the confusion — **HIGH**

**Problem.** A *deterministic* quality gate (stage 11; SC-5: un-overridable) and an *LLM* "quality-gate verdict" (`quality_gate_agent → GateDecision`, roles.py:85) that auto-approves the *soft merge* gate both wear the name. The skeleton implements only the LLM one and has **no deterministic gate at all** — the SC-5 failure mode made literal.

**Decision — rename, strict precedence, per-check classification.**
- **`DeterministicQualityGate`** (pure code) consumes *typed evidence* (proposer `ReviewReport`, `AnalysisReport`, coverage number, lint, traceability) and emits pass/fail. **`MergeVerdict`** (advisory LLM proposer) is consulted only under `soft` merge policy, and only after the deterministic gate passes.
- **Precedence:** the deterministic gate is a hard precondition under every merge policy (hard/soft/off). `MergeVerdict` can only ever approve an already-clean build — it structurally cannot bypass the gate.
- **Per-check classification** (per-project config, with a floor):

  | Check | Class |
  |---|---|
  | Lint / syntax clean | **Absolute** |
  | No critical security finding | **Absolute** (floor — never demotable) |
  | Builds / no unresolved integration conflict | **Absolute** |
  | Coverage threshold | **Advisory** — diff-scoped on brownfield |
  | Criterion→test traceability completeness | **Advisory** |
  | Non-critical review/analysis issues at configured severity | **Advisory** |

  Human override allowed only on **advisory** checks, recorded (identity + reason + check) and retained as calibration signal.
- **SC-5 reword:** "zero deploys past a failed *absolute* check, and zero *unattended* deploys past any failed check."
- **Traceability boundary (folds in #10):** the **Analyst (LLM) proposes** the criterion→test mapping; the **deterministic gate enforces** completeness. Traceability stays a genuine deterministic invariant rather than an LLM judgment masquerading as one.
- **Coverage (folds in #9):** diff-scoped for brownfield (global coverage false-blocks on untested legacy) and advisory, not an un-overridable invariant on a gameable metric.

**Implied edits.** SDLC §1 row 11 (rename) + §5 (merge precedence) + §7 (coverage diff-scoped, per-check classification, traceability propose/enforce); ARCH §4 (`MergeVerdict` naming) + §5/§10 (classification) ; PRD SC-5 + FR-106.

---

## Finding #6 — Gate revisions are impossible under "first-decision-wins" — **MEDIUM**

**Problem.** `GateDecision.approved` is a boolean, so "reject" is forced terminal; the skeleton returns `"rejected:architecture"` and exits (feature.py:216). US-2 (reject-with-comments → re-run architect → re-review) is unimplementable, and same-name idempotency would drop the second decision.

**Decision — outcome enum + round-scoped identity + bounded revision loop.**
- `GateDecision.outcome ∈ {approve, reject, revise}` (replaces `approved: bool`) with optional `guidance`. `approve` proceeds; `reject` is terminal; `revise` loops back, feeding `guidance` into the agent's next-round inputs (new hash → new artifact → new round).
- Gate identity = `(gate_name, round)` (`architecture#1`, `architecture#2`, …). First-decision-wins is preserved *per round* — its actual intent.
- Bounded revision loop; exhaustion escalates to a hard accept-anyway / abandon gate.
- Collapses architecture-revise, task-retry-with-guidance (US-3), and repair-approval into one contract — the unification ADR-4 only claimed.

**Implied edits.** SDLC §4 (`GateDecision` outcome enum + round) + §5 (revision loop); ARCH §5 + ADR-4 note; PRD FR-301 + US-2. Code (to-do): revision-loop control flow; round-scoped signal keys; `pending_decisions` surfaces current round.

---

## Finding #7 — The "context ceiling" cannot be measured — **MEDIUM**

**Problem.** ADR-13 leans on "compaction is failure; past the context ceiling, start fresh," but `HarnessRunResult` carries no token data, so the workflow degrades it to a blind `max_session_resumes` counter (feature.py:165).

**Decision — capture the data that already exists; define a real threshold.**
- The harness result JSON the adapter already parses for cost (adapters.py:104) contains token usage. Extend `HarnessRunResult` with `input_tokens`, `output_tokens`, `context_window`, optional `compacted: bool`.
- Ceiling = `input_tokens > fraction × context_window` (configurable, e.g. 0.75) → next attempt gets a fresh session + handoff. A harness-signalled compaction event fails the session for continuity immediately.
- `max_session_resumes` remains a hard fallback, so unreliable/version-changed token accounting degrades to today's count-based behavior rather than breaking.

**Implied edits.** ARCH §4 (capture tokens) + ADR-13 (measured trigger); SDLC §4 (`HarnessRunResult` fields). Code (to-do): adapter token capture; threshold logic in the task loop.

---

## Finding #8 — Secrets rule undercut by full-env passthrough + Bash auto-accept — **HIGH (security)**

**Problem.** `env={**os.environ, ...}` (adapters.py:54) hands the worker's entire environment to the harness — a bigger secret channel than prompts. Default `--allowedTools …,Bash` + `--permission-mode acceptEdits` (adapters.py:86) is effectively arbitrary execution with auto-accept. A git worktree is not an isolation boundary. NFR-5/§10 ("secrets never reach the harness," "destructive denied → escalate," "sandboxed worktree") are all undercut.

**Decision — defense-in-depth; tiered containment.**
- **Env allowlist, not passthrough** (immediate biggest win): curated allowlist (PATH, HOME, toolchain vars) + deliberately-injected task-scoped creds only.
- **Scoped, short-lived credentials:** token scoped to *this repo* with short TTL (GitHub App installation token / fine-grained PAT), never org-wide.
- **Destructive-action denial in the `pre_tool` hook**, not `--allowedTools` (which is too coarse to express "reads free / writes checked / destructive denied"): inspect the concrete command, deny/escalate `rm -rf` outside the worktree, out-of-worktree writes, non-allowlisted network.
- **Egress control:** restrict harness outbound to model API + git remote (else "secrets never in memory" is moot).
- **Tiered isolation:** P1 (single project, trusted operator) — restricted OS user + FS ACLs (worktree-only) + egress policy. Fleet scale (NFR-2) — container per run (rootless, read-only base FS, worktree bind-mounted rw, egress-restricted). Doc states both tiers and when each applies.
- **Stop calling a bare worktree a "sandbox";** name the actual boundary.

**Implied edits.** ARCH §9 (isolation tiers) + §10 (env allowlist, scoped creds, hook enforcement, egress, tiered isolation, terminology); SDLC §7 (harness sandboxing delta); PRD NFR-5 + FR-703. Code (to-do): env allowlist in `HarnessRequest`/adapters; `pre_tool` hook; credential injection; container/user launch path.

---

## Folded-in items

- **#9 Coverage on brownfield** → diff-scoped + advisory (in #5).
- **#10 Hindsight single dependency** → de-risked by watermark snapshot-reuse (in #2/#3); still merits a memory-protocol seam as a later item.
- **#10 Traceability deterministic/LLM blur** → Analyst proposes mapping, gate enforces completeness (in #5).
- **Run-isolation collision** (worktrees keyed by `task_id` only) → run-scoped paths (in #1).
- **Reproducibility category-error** ("pure function of hashed inputs" for LLM/harness stages) → FR-103 caveat: cache-*keyable*, not *pure* (in #2/#3).
- **Budget enforcement reactive** (cost known only post-run) — not resolved here; flagged for a follow-up (pre-flight budget check before expensive steps).
- **Post-deploy verify/rollback unowned** (gap between deploy smoke and the timer-driven DAPER loop) — not resolved here; flagged for a follow-up.

---

## Open follow-ups (not decided this session)

1. Memory-protocol seam so Hindsight is swappable (parity with the harness protocol).
2. Pre-flight budget enforcement for single expensive steps.
3. Post-deploy verification → rollback coupling vs. the DAPER loop.

---

## Implementation status (2026-07-04)

**Plan 1 — Foundation: contract & decision alignment** (`docs/superpowers/plans/2026-07-04-foundation-contract-alignment.md`, branch `feat/foundation-contract-alignment`) implemented the **contract/activity-level** code to-dos of the findings below. 26 unit tests, green, no live Temporal/CLI required.

| Finding | Discharged at contract/activity level | Deferred to Plan 2 (workflow orchestration) |
|---|---|---|
| #1 integration branch | `create_worktree(from_ref)`→`WorktreeHandle`, `setup_integration_branch`, `merge_into_integration` (conflict vs. infra-failure distinguished via `git ls-files --unmerged`), branch-point `get_task_diff`, run-scoped paths | wiring setup/merge into `FeatureWorkflow`; wave-mode serialize-on-conflict |
| #2/#3 memoization | — | content-addressed cache + per-run watermark module |
| #4 reviewer | `MergeVerdict` advisory proposer split from `GateDecision`; `merge_verdict_agent` | clean-context reviewer stage wiring; deep-review tier |
| #5 quality gate | `DeterministicQualityGate` (absolute vs. advisory, security floor) + `evaluate_gate` activity | gate run **before** the merge gate; override capture |
| #6 gate revisions | `GateDecision.outcome {approve,reject,revise}` + `round` + `gate_key` | revision loop + round-scoped signal keys in the workflow |
| #7 context ceiling | `HarnessRunResult` token fields + `near_context_ceiling`; adapter token parse | token-threshold fresh-session trigger in the dev-task loop |
| #8 harness security | env allowlist (`build_env`, no `os.environ` passthrough) | `pre_tool` hook, credential injection, tiered isolation launch path, egress control |

**Also fixed in Plan 1:** pre-existing broken relative imports in `agents/roles.py` (`.models`→`..models`) and `workflows/feature.py` (`.`→`..`) that prevented the package from importing at all.

**Plan 2 follow-ups surfaced during Plan 1 execution:**
- `agents/roles.py` constructs all six `pydantic_ai.Agent`s at **module import**, so importing `sdlc.agents.roles`/`sdlc.workflows.feature` requires `ANTHROPIC_API_KEY` to be set. Move to lazy/deferred agent construction.
- Dev-setup gotcha: adding a new module (e.g. `sdlc.gate`) requires re-running `pip install -e .` — the setuptools strict editable wheel does not auto-discover new files. Consider a config that puts `src/` on `sys.path`.
- Test env hygiene: `tests/test_module_imports.py` sets `ANTHROPIC_API_KEY` via `os.environ.setdefault` at import; prefer a session-scoped autouse `conftest.py` fixture.
