# Feature Coverage Audit — Spec vs. Code

| | |
|---|---|
| Date | 2026-07-05 |
| Scope | `PRD.md`, `ARCHITECTURE.md`, `SDLC-spec-v2.md` vs. `src/sdlc/`, `interfaces/`, `tests/` |
| Method | Read every FR/NFR/SC/ADR and the 14-stage DAG; verified each against actual code (file:line) and test presence, not against prior audit docs' claims |
| Prior audits | `docs/architecture-review-2026-07.md` (2026-07-03, spec-level decisions) and `docs/foundation.md` (2026-07-04, "Plan 1" contract/activity level). This audit checks what has *actually landed in the live workflow* since then — commits through `297ea9b` — including the untracked `docs/superpowers/plans/2026-07-05-*.md` wiring plans, which git history confirms were executed (`ac0d879`…`297ea9b`). |

## TL;DR

The **governance spine is solid and load-bearing**: the deterministic merge gate runs before the advisory `MergeVerdict` (SC-5), REVISE loops with round-scoped identity work, the ADR-14 integration branch is wired, and the context-ceiling trigger fires. Memory (recall/retain) and memoization (content-addressed cache + watermark) are both implemented and wired into clarify/architect/plan.

The gaps are concentrated in three places:
1. **The pipeline is 6 stages wired, not 14.** No constitution, context/Cartographer, standalone requirements, review, analyze, or retro stage. Brownfield mode is a string field with no actual delta/CodebaseMap behavior.
2. **Two structural governance invariants from the architecture review are still not implemented**, despite being "resolved" in the review doc: the reviewer's model-family independence (ADR-6 — there is no reviewer stage at all) and the config-driven agent registry (`agents.yaml`, FR-201 — agents are hardcoded Python).
3. **Everything outside the core pipeline is absent**: MaintenanceWorkflow/DAPER, MCP server, dashboard backend, budgets, observability export, harness containment beyond an env allowlist, claim-check artifact refs.

None of this contradicts the architecture docs — `ARCHITECTURE.md` §14 explicitly says the skeleton is pre-P1-hardening, and the 2026-07-05 wiring plan explicitly scoped stages 5–7 (constitution/retro, worker pools, fake harness) as "roadmap, not this plan." This audit exists to make the *current* boundary precise, since the plan docs' self-review claims are two-plus weeks stale relative to what's actually merged.

**Update 2026-07-05:** this audit's top-ranked finding — soft gates were configured but never auto-approved (FR-301) — is now fixed; see §2 FR-301 and §7 item 1 below for detail.

---

## 1. Pipeline stages (SDLC-spec v2 §1 — 14-stage DAG)

| # | Stage | Spec owner | Status | Evidence |
|---|---|---|---|---|
| 0 | intake | deterministic | ❌ Missing | `IdeaBrief.mode` is a field, not a routing stage — no branch logic distinguishes greenfield/brownfield anywhere in `feature.py`. `mode.value` is only interpolated into the architect prompt (`feature.py:544`). |
| 1 | constitution | deterministic | ❌ Missing | No `Constitution` model, no stage. |
| 2 | context (Cartographer) | brownfield only | ❌ Missing | No `CodebaseMap` model, no `cartography.py`, no brownfield delta logic. |
| 3 | requirements (Product) | Product agent | ❌ Missing as a distinct stage | `ClarifiedRequirements` conflates Requirements + Clarifications into one model/stage; no separate Product proposer or `Requirements` artifact precedes Clarifier. |
| 4 | clarify | Clarifier + gate | ✅ Implemented | `feature.py:498-534`; open questions wait on `answer_question` signal; recall/retain/memoization wired. |
| 5 | architecture | Architect + gate | ✅ Implemented, with REVISE loop | `feature.py:536-574` via `_revisable_stage` (`feature.py:295-313`). |
| 6 | planning | Planner + gate | ✅ Implemented, with REVISE loop | `feature.py:576-612`. |
| 7 | code | Developer, per-task, integration branch | ✅ Implemented | `_dev_task` (`feature.py:339-465`); ADR-14 integration wired (`feature.py:483-496`, `622-663`). |
| 8 | review (Reviewer) | clean-context proposer | ❌ Missing | No `ReviewReport` model, no reviewer agent, no review stage anywhere. See §4 below — this is the single biggest structural gap. |
| 9 | analyze (Analyst) | criterion→test traceability | ❌ Missing | No `AnalysisReport` model, no Analyst agent, no traceability mapping produced or enforced. |
| 10 | qa (+ Resolver) | bounded repair loop | ✅ Implemented (folded into stage 7) | `t_qa` clean-context validator + bounded fix loop in `_dev_task` (`feature.py:378-454`). Note: PRD says `MAX_REPAIR_ATTEMPTS=3`; code default `max_fix_attempts=2` (`models.py:304`) — a numeric drift, not a missing feature. |
| 11 | quality_gate | `DeterministicQualityGate` | ✅ Mechanism implemented; ⚠️ check set thin | `gate.py` + wired in `feature.py:668-761`. Only two checks are ever built: `build_integration_green`, `lint_clean` (`feature.py:681-687`). No "no critical security finding" check (the spec's *absolute floor*), no coverage/traceability advisory checks — `gate.py`'s `ABSOLUTE_FLOOR`/`CheckClass.ADVISORY` machinery supports them, but nothing populates them because stages 9 (analyze/traceability) and any security scanner don't exist yet. |
| 12 | deploy | DevOps + gate | ⚠️ Minimal | `feature.py:769-789`. Single hardcoded `make deploy ENV=staging` command; no `DeployPlan`/`DeployReport` propose-then-persist split, no smoke-test-vs-PR-merge distinction by mode. |
| 13 | retro | deterministic + reflect | ❌ Missing | `reflect()` activity exists (`memory/activities.py:94`) and is registered on the worker (`worker.py:34,59`) but is **never called** — grepping `feature.py` for `reflect` returns nothing. No `RunSummary` model, no `events.jsonl`/`report.html` export. |

**Net: 6 of 14 stages are live (4, 5, 6, 7/10, 11).** This matches what the 2026-07-05 wiring plan called out as in-scope; stages 0–3, 8, 9, 13 were explicitly deferred as "roadmap" items, not silently dropped.

---

## 2. Functional requirements (PRD §6)

### Pipeline (FR-100)
| FR | Status | Note |
|---|---|---|
| FR-101 (14-stage DAG) | ❌ | 6/14 stages, see §1. |
| FR-102 (greenfield/brownfield classify + CodebaseMap) | ❌ | No classification logic, no `CodebaseMap`. |
| FR-103 (memoization, watermark, audit-record-always-kept) | ✅ | `memoization/cache.py`, `content_key`, watermark capture (`feature.py:472-480`), `_cached_stage` (`feature.py:213-233`). |
| FR-104 (integration branch, per-task worktree, own branch-point diff) | ✅ | ADR-14 fully wired: `create_worktree(from_ref)`, `merge_into_integration`, `get_task_diff(branch_point)`. |
| FR-105 (review/analyze fix loop 2; QA fix loop 3; escalate) | ⚠️ Partial | QA fix loop exists (bounded by `max_fix_attempts`, default 2 not 3) and escalates (`feature.py:456-465`). Review/analyze fix loop is moot — those stages don't exist. |
| FR-106 (deterministic gate, absolute/advisory, diff-scoped coverage, traceability enforcement) | ⚠️ Partial | Absolute/advisory classification mechanism is correct and load-bearing (`gate.py`, SC-5 fix in `19b2ea2`). Coverage and traceability checks are unbuilt (depend on missing Analyst stage). |

### Agents (FR-200)
| FR | Status | Note |
|---|---|---|
| FR-201 (versioned `agents.yaml` registry) | ❌ | No `config/agents.yaml`; agents are hardcoded `Agent(...)` instances in `agents/roles.py:87-133`. There is no `config/` directory at all in this repo. |
| FR-202 (schema-validated artifacts, re-prompt on failure) | ⚠️ Partial | Pydantic AI's `output_type` gives schema validation; the configurable `validation_retries` knob from the spec's `agents.yaml` doesn't exist since there's no registry to hold it. |
| FR-203 (`claude -p` / `opencode run` adapters, swap without workflow changes) | ✅ | `harness/adapters.py`; `CodingTaskInput.harness: HarnessKind` selects the adapter — workflow code is harness-agnostic. |
| FR-204 (reviewer clean-context, model-family inequality enforced by validator) | ❌ | No reviewer stage, no registry, no validator. This was "resolved" as ADR-6/Finding #4 in the architecture review but never implemented in `agents/roles.py` or `feature.py`. Today, `t_qa` and `t_merge_verdict` both use the single hardcoded `MODEL = "anthropic:glm-5.2"` (`roles.py:30`) — there is no second model family anywhere in the live path except in benchmark judging (`_judge`, which is a separate, opt-in benchmarking concern, not the production review gate). |
| FR-205 (proposer MAY/MUST NOT enforced by validators) | ⚠️ Partial | No dedicated `validators.py` module (per `ARCHITECTURE.md` §14's target layout). The one concrete instance — Kahn-style dependency-cycle detection — exists inline (`feature.py:637-638: "failed:dependency-cycle"`) rather than as a reusable validator. |

### Human-in-the-loop (FR-300)
| FR | Status | Note |
|---|---|---|
| FR-301 (hard/soft/off, confidence threshold, approve/reject/revise, `MAX_GATE_ROUNDS`) | ✅ for architecture/plan/merge — ⚠️ still confidence-only (no deterministic-check "AND" clause) | **Update 2026-07-05:** wired via `docs/superpowers/plans/2026-07-05-soft-gate-auto-approval-wiring.md` — `GateConfig{policy,threshold}` (`models.py`), `_auto_decision_for()` (`feature.py`), and confidence fields on `ArchitectureSpec`/`ImplementationPlan`/`MergeVerdict` now make architecture, plan, and merge soft gates auto-approve when a proposer's self-scored confidence clears its gate's threshold; below threshold or missing confidence still falls through to the human wait. Architecture/plan soft-approval remains confidence-only (no deterministic-check equivalent exists at those stages — see priority recommendation #2, the missing review/Analyst stages) and self-scored confidence calibration has no active monitoring yet (needs the still-unwired retro/reflect stage, FR-404). The clarify gate's separate suggested-answer auto-accept mechanism (US-1) is untouched. |
| FR-302 (idempotent signals, `(gate, round)` identity) | ✅ | `gate_key()`, round-scoped `_gate_decisions` dict, first-decision-wins (`feature.py:237-243`). |
| FR-303 (notifications with deep links, durable timers: reminder / fallback-approver / timeout) | ⚠️ Partial | Timeout → auto-reject via `wait_condition` timeout exists (`feature.py:274-283`). No reminder timer, no fallback-approver escalation, no notification activity at all (`activities/notify.py` from the target layout doesn't exist; nothing pushes to Slack/email). |
| FR-304 (decision recorded with outcome/decider/identity/comments/timestamp, queryable) | ⚠️ Partial | All fields are captured on `GateDecision` and retained to memory as a text blob (`_gate`, `feature.py:287-293`). There's no structured, queryable decision history — `pending_gate()`/`status()` queries expose only current state, not the decision log. |
| FR-305 (cross-run decision inbox) | ❌ | No surface lists "everything awaiting a human" across runs — CLI has per-run `status`, no `inbox`; no dashboard backend; no MCP. |

### Memory (FR-400)
| FR | Status | Note |
|---|---|---|
| FR-401 (retain stage summaries, fix-loop gotchas, gate decisions, incidents; recall per agent config) | ✅ mostly | Retain calls present for `STAGE_SUMMARY` (clarify/architect/plan), `GOTCHA` (fix-loop), `GATE_FEEDBACK` (every gate). No "incidents" concept exists (maintenance loop is missing, see §FR-500). |
| FR-402 (RecallSnapshot persisted, hashed, declared stage input) | ⚠️ Partial | `RecallSnapshot` model has a `query_hash` field, but recall is called directly with a raw query string per-stage (`feature.py:501-503` etc.) — snapshots aren't yet a separately persisted, content-addressed artifact independent of the memoization cache; the watermark is the real hashed/pinned piece and that part works. |
| FR-403 (non-blocking retain, fire-and-forget with retries, PII scrub hook) | ✅ | `_retain` swallows exceptions (`feature.py:198-211`), `MEM_ACT` has `retry_policy=RetryPolicy(maximum_attempts=5)`, `memory/scrub.py` exists with tests (`test_memory_scrub.py`). |
| FR-404 (nightly reflect: project + org) | ❌ | `reflect()` activity exists and is registered but is **never invoked** — no retro stage, no Temporal `Schedule`. Confirmed via grep: zero references to `Schedule` or `reflect` anywhere in `feature.py`/`worker.py` call sites. |

### Maintenance (FR-500)
| FR | Status | Note |
|---|---|---|
| FR-501–503 (DAPER loop, code_fix as brownfield child runs, confidence-gated repair approval) | ❌ Entirely missing | No `MaintenanceWorkflow`, no `maintenance.py`, no detector/repair-planner agents, no `DetectionReport`/`RepairPlan` models. Confirmed via grep for `Maintenance|DAPER|Cartographer` across `src/` — zero hits. |

### Interfaces (FR-600)
| FR | Status | Note |
|---|---|---|
| FR-601 (dashboard: fleet list, stage spine, decision inbox) | ⚠️ Frontend only, not wired | `interfaces/dashboard/frontend/` is a Vue 3 app (per `docs/superpowers/specs/2026-07-05-dashboard-vue3-frontend-design.md`, explicitly "mocked API, pluggable for FastAPI"). No FastAPI backend exists yet — no `interfaces/dashboard/api.py`, nothing queries live Temporal state. |
| FR-602 (MCP server) | ❌ | No `interfaces/mcp/` directory at all. |
| FR-603 (CLI) | ✅ mostly | `cli.py` covers `start`, `status`, `answer`, `approve`, `reject`, `benchmark {run,drift,report}`. Missing: a cross-run `inbox` command (FR-305). |
| FR-604 (stateless shells, no interface DB) | ✅ for CLI | CLI is a thin Temporal client. Dashboard backend doesn't exist yet to evaluate. |

### Governance & ops (FR-700)
| FR | Status | Note |
|---|---|---|
| FR-701 (budgets: wall-clock/steps/cost; exhaustion escalates) | ❌ | Grep for `Budget`/`wall_clock`/`max_steps` across `src/sdlc/` hits only benchmark cost bookkeeping (`benchmarks/models.py` `CostBag`), which records cost for reporting — it does not enforce or escalate on any limit. No workflow-level budget counters exist. |
| FR-702 (claim-check `ArtifactRef`s, 2MB payload discipline) | ⚠️ Partial | `ArtifactRef` model exists (`models.py:39-43`) but is barely used — `HarnessRunResult.diff_ref` and various `*_ref` fields are declared and unpopulated; the actual task diff travels through workflow history as an inline dict (`get_task_diff` → `{stat, patch}`, consumed directly in `_dev_task`, `feature.py:391-400`) with no size guard. `CodeArtifact` (the union type ADR-3 specifies) doesn't exist as a model at all. |
| FR-703 (tiered harness containment: OS user + FS ACLs + egress; `pre_tool` hook denial; env allowlist not passthrough) | ⚠️ Partial — only the easiest piece is done | `build_env`/`ENV_ALLOWLIST` (`harness/adapters.py:54-60`, tested in `test_env_allowlist.py`) replaces full `os.environ` passthrough — real, meaningful progress. But there is **no `pre_tool` hook** (grep for `pre_tool` across `src/` — zero hits), no restricted-OS-user or container launch path, no egress policy. The harness still runs as a plain subprocess with `--allowedTools`/`--permission-mode acceptEdits` as the *only* layer — exactly the configuration the architecture review flagged as insufficient (Finding #8), now only half-remediated. |
| FR-704 (observability export: `events.jsonl` + `report.html`) | ❌ | No `observability/` module. |

---

## 3. Non-functional requirements (PRD §7)

| NFR | Status | Note |
|---|---|---|
| NFR-1 Durability | ✅ | Temporal-native; no custom state. |
| NFR-2 Scale (50 runs / 200 harness tasks, independent pools) | ❌ | Single task queue `"ai-sdlc"` for everything (`worker.py:38,50-63`) — proposer and harness activities are not split, contra ADR-9. No pooling/scaling story beyond "run more workers on the same queue." |
| NFR-3 Latency (5s reflect state, 2s signal effect) | — Untested | No load-testing artifacts found; not falsifiable from code alone. |
| NFR-4 Auditability | ⚠️ Partial | Temporal history + benchmark records give real reconstructability for what runs; no `events.jsonl`/`report.html` export (FR-704) means "reconstructible from history + artifact store" is true only via raw Temporal Web UI access, not the promised export. |
| NFR-5 Security | ⚠️ Partial | Env allowlist done; restricted OS user, container tier, `pre_tool` hook, egress policy, scoped short-TTL credential injection — all still absent (same gap as FR-703). |
| NFR-6 Reproducibility vs. memoization | ✅ | Correctly split per ADR-5: watermark-pinned recall + content-addressed cache (`memoization/cache.py`, `content_key`). |
| NFR-7 Portability (self-hostable, no mandatory SaaS) | ✅ | `MemoryConfig.backend: "fake" | "hindsight"` defaults to `fake` (no external dependency required); real Hindsight client exists (`memory/hindsight_client.py`) for self-hosting. |

---

## 4. Success criteria (PRD §8)

| SC | Status | Note |
|---|---|---|
| SC-1 (≥80% runs reach merge gate unattended) | — Not measurable | No fleet-scale execution has happened; mechanism (gates) exists to support it. |
| SC-2 (≤15 min operator time) | — Not measurable | Same. |
| SC-3 (fix-loop success ≥70%) | — Not measurable | Fix loop exists (§1, stage 10) but no aggregate metric is captured today. |
| SC-4 (repeat-clarification rate <10% by run 10) | — Not measurable | Requires the missing retro/reflect wiring (FR-404) to even start accumulating cross-run learning signal. |
| SC-5 (**zero deploys past a failed absolute check**) | ✅ Enforced structurally | This is the one hard invariant explicitly fixed in `19b2ea2` ("close SC-5 vacuous-truth bypass") — `_merge_evidence_all_green` (`feature.py:91-98`) now treats an empty/vacuous task list as failure, not a trivial pass, and absolute-check failure is unconditionally terminal (`feature.py:696-709`). |
| SC-6 (soft-gate override rate <5%) | — Not measurable yet, but the mechanism now exists | **Update 2026-07-05:** soft gates can auto-approve now (FR-301 fixed). Still not measurable — no runs have executed against it yet, and the metric itself needs the still-missing retro/reflect wiring (FR-404) to accumulate. |

---

## 5. Architecture Decision Records (ARCHITECTURE.md §12)

| ADR | Status | Note |
|---|---|---|
| ADR-1 Temporal owns state | ✅ | |
| ADR-2 Pydantic AI proposers + harness CLIs | ✅ | |
| ADR-3 `CodeArtifact` union (files\|diff_ref) | ❌ | Model doesn't exist; diff handling is ad hoc (see FR-702). |
| ADR-4 Gates as policy-driven durable signal waits | ✅ | Fully implemented, revision loop included. |
| ADR-5 Memoization + watermark, auditability/memoization split | ✅ | |
| ADR-6 Anti-collusion review (model-family inequality, clean-context reviewer) | ❌ | No reviewer stage exists at all — the invariant has nothing to apply to. |
| ADR-7 Repairs execute through the factory | — N/A | Maintenance loop doesn't exist. |
| ADR-8 Interfaces as stateless shells | ⚠️ | True for CLI; dashboard backend doesn't exist to evaluate. |
| ADR-9 Two worker pools by capability | ❌ | Single queue. |
| ADR-10 Claim-check for large payloads | ❌ | `ArtifactRef` exists but isn't load-bearing; diffs travel inline. |
| ADR-11 Deterministic DAG (contra "Bitter Lesson") | ⚠️ | True for the 6 stages that exist; 8 stages of the declared DAG aren't there to be deterministic about. |
| ADR-12 Contract-first, clean-context validators | ⚠️ | True for QA (`ValidationContract` + clean-context `t_qa`); false for review (doesn't exist). |
| ADR-13 Serial-by-default; resume-bounded; context by reference | ✅ | `ExecutionMode.SERIAL/WAVES`, `near_context_ceiling()` wired (`42de84a`). |
| ADR-14 Integration by running branch | ✅ | Fully wired (`dc66096`, hardened by `9794dd9`, `297ea9b`). |

---

## 6. Rollout phase status (PRD §9)

| Phase | Exit criterion | Status |
|---|---|---|
| **P1** Greenfield pipeline, CLI only, hard gates everywhere, no memory | one project shipped end-to-end | **Not yet met.** The core merge-gate/revision/integration-branch/context-ceiling mechanisms are done and this is close, but: (a) memory is *not* off by default in the sense the phase implies — `cfg.memory.enabled` defaults to `False` (`MemoryConfig.enabled=False`, `models.py:273`) so P1's "no memory" constraint is actually respected when using defaults, good; (b) **Update 2026-07-05:** "hard gates everywhere" is now a deliberate default, not an accidental side-effect of a bug — soft auto-approval is wired (FR-301 fixed), and `PipelineConfig`'s default `gates["plan"] = SOFT` will genuinely auto-approve if a project chooses to enable it, so P1 projects that want hard-everywhere must set that explicitly rather than relying on unwired soft gates doing nothing; (c) no observed end-to-end run artifact (fake harness / CI stand-in, Task 7 of the wiring plan) exists yet to *demonstrate* one project shipped. |
| **P2** Brownfield, dashboard + notifications, fix loops, cross-harness review | first brownfield feature merged via PR | Not started — no brownfield classification/CodebaseMap, no notifications, no cross-harness review (no review stage at all). |
| **P3** Hindsight memory + confidence-gated soft gates | SC-4/SC-6 measurable | Memory mechanism (recall/retain/watermark) is ready; confidence-gated soft gates are now wired (FR-301 fixed) for architecture/plan/merge. SC-4/SC-6 still aren't measurable — that needs real runs plus the still-missing retro/reflect wiring (FR-404) to accumulate the calibration signal. |
| **P4** MCP, maintenance loop, fleet scale | SC-1..3 at target | Not started. |

---

## 7. Priority recommendations

Ranked by how much they undercut a *stated* invariant (not by effort):

1. ~~Wire soft-gate auto-approval or remove `SOFT` from the default config.~~ **Done 2026-07-05** — see `docs/superpowers/plans/2026-07-05-soft-gate-auto-approval-wiring.md`. `GateConfig{policy,threshold}` + `_auto_decision_for()` now thread a confidence-scored `auto_decision` into `_gate()` for architecture, plan, and merge; `PipelineConfig.gates["plan"] = SOFT` genuinely auto-approves above its threshold. Remaining known limitation: architecture/plan soft-approval is confidence-only (no deterministic-check "AND" clause, since no such check exists at those stages yet — folds into #2/#4 below).
2. **Build the review stage (ADR-6/FR-204).** This is the largest gap between "resolved in the architecture review" and "implemented" — the anti-collusion invariant (different model family reviewing code) has no code to enforce because there's no reviewer.
3. **Config-driven agent registry (`agents.yaml`, FR-201).** Currently every model/prompt/harness choice is a Python constant in `roles.py`. This blocks per-project configurability (US-4, US-5) entirely — there's no registry to validate `reviewer.model family ≠ developer.model family` against even after #2 is built.
4. **Populate the deterministic gate's absolute floor and advisory checks.** `gate.py`'s classification machinery is solid, but only two checks are ever built. At minimum, wire a security-scan absolute check (the spec's floor invariant) before claiming FR-106/NFR-5 coverage.
5. **Everything else (constitution/context/retro stages, MaintenanceWorkflow, MCP, dashboard backend, budgets, observability export, tiered harness containment)** is correctly scoped as post-P1 roadmap in the existing plan docs — no surprise there, just confirming the scope is accurately described as "not yet built," not "partially built."
