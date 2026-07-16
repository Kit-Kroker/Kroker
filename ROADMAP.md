# Implementation Roadmap — Agentic SDLC Factory

| | |
|---|---|
| Status | Living tracker |
| Last verified | 2026-07-16 (against `src/sdlc/`, `interfaces/`, `tests/`, `config/`) |
| Source of truth for scope | `PRD.md`, `ARCHITECTURE.md`, `SDLC-spec.md` |
| Method | Every FR / NFR / SC / US / ADR and the 14-stage DAG checked against actual code, not against prior audit claims |

**Legend**
- `[x]` — implemented and wired into the live path
- `[ ]` ⚠️ — partial: mechanism exists but incomplete or not fully wired (see note)
- `[ ]` — not started
- `—` — not falsifiable from code alone (needs runtime measurement)

> Since the 2026-07-05 audit, the **reviewer stage (ADR-6/FR-204)** and **agent registry (FR-201)** landed (merged `b9455c3`), plus a **coding-harness adapter layer** and **harness observability logging**. Those items are now checked. The audit's `docs/feature-coverage-audit-2026-07-05.md` is superseded by this tracker.

---

## 0. Phase summary (PRD §9)

- [x] **P1** — Greenfield pipeline, CLI, hard gates, no memory → *one project shipped end-to-end*
  Exit criterion **demonstrated**: `tests/test_e2e_greenfield.py` drives the real `FeatureWorkflow` greenfield `IdeaBrief` → `deployed:` end-to-end in CI, and the `security_no_critical` absolute floor now bites (SC-5). Delivered on `feat/p1-consolidation` (`3cfbe62`…`41c9185`).
- [ ] ⚠️ **P2** — Brownfield, dashboard + notifications, fix loops, cross-harness review → *first brownfield feature merged via PR*
  Cross-harness review ✅ and fix loops ✅ landed early; brownfield mode, dashboard backend, and notifications not started.
- [ ] ⚠️ **P3** — Hindsight memory + confidence-gated soft gates → *SC-4 and SC-6 measurable*
  Memory (recall/retain/watermark) ✅ and soft gates ✅ done; SC-4/SC-6 not yet measurable (need retro/reflect wiring + real runs).
- [ ] **P4** — MCP surface, maintenance loop (DAPER), fleet scale → *SC-1..3 at target*
  Not started.

---

## 1. Pipeline — 14-stage DAG (SDLC-spec v2 §1)

**8 of 14 stages live.**

- [ ] **0 · intake** — routing greenfield/brownfield/repair. `IdeaBrief.mode` is a field only; no branch logic in `feature.py`.
- [ ] **1 · constitution** — no `Constitution` model, no stage.
- [ ] **2 · context (Cartographer)** — no `CodebaseMap`, no `cartography.py`, no brownfield delta.
- [ ] **3 · requirements (Product)** — conflated into clarify; no standalone Product proposer / `Requirements` artifact.
- [x] **4 · clarify** — Clarifier + gate; open-question wait on `answer_question`; recall/retain/memoization wired.
- [x] **5 · architecture** — Architect + gate, with REVISE loop (`_revisable_stage`).
- [x] **6 · planning** — Planner + gate, with REVISE loop.
- [x] **7 · code** — Developer, per-task, ADR-14 integration branch (`_dev_task`).
- [x] **8 · review** — clean-context `reviewer_agent` (`t_reviewer`) run in `_dev_task`; blocking findings fold into the fix loop. **(new)**
- [x] **9 · analyze (Analyst)** — Analyst clean-context proposer (`t_analyst`) emits `AnalysisReport`; workflow enforces criterion→test traceability against the plan's authoritative criteria (FR-106).
- [x] **10 · qa (+ Resolver)** — clean-context `t_qa` + bounded fix loop (folded into stage 7). *Note: default `max_fix_attempts=2`, PRD says QA loop 3 — numeric drift.*
- [ ] ⚠️ **11 · quality_gate** — `DeterministicQualityGate` mechanism ✅; 6 checks built (`build_integration_green`, `lint_clean`, `security_no_critical` absolute; `review_severity`, `traceability`, `coverage` advisory). Absolute security floor now wired ✅; traceability enforced ✅; coverage via deterministic Cobertura seam (`measured=False` ⇒ no-op until a project emits coverage + sets `coverage_threshold`).
- [ ] ⚠️ **12 · deploy** — single hardcoded `make deploy ENV=staging`; no `DeployPlan`/`DeployReport` split, no smoke-test vs PR-merge distinction.
- [ ] **13 · retro** — `reflect()` activity exists and is registered but **never called**; no `RunSummary`, no export.

---

## 2. Functional requirements (PRD §6)

### Pipeline (FR-100)
- [ ] ⚠️ **FR-101** 14-stage durable DAG — 8/14 stages (see §1).
- [ ] **FR-102** greenfield/brownfield classify + `CodebaseMap` + delta.
- [x] **FR-103** memoization, per-run watermark, audit-record-always-kept (`memoization/cache.py`, `content_key`, `_cached_stage`).
- [x] **FR-104** integration branch, per-task worktree, own-branch-point diff (ADR-14 fully wired).
- [ ] ⚠️ **FR-105** fix loops — QA loop ✅, review findings now fold into it ✅; loop-count defaults drift from spec (2 vs 3).
- [ ] ⚠️ **FR-106** deterministic absolute/advisory gate — classification ✅ and load-bearing; security absolute-floor check now wired ✅ (`security_no_critical`); traceability enforced ✅; coverage wired as a deterministic diff-scoped seam ✅ (real instrumentation future work).

### Agents (FR-200)
- [x] **FR-201** versioned `config/agents.yaml` registry (role/kind/model). **(new)**
- [ ] ⚠️ **FR-202** schema-validated artifacts + re-prompt — Pydantic `output_type` gives validation; configurable `validation_retries` knob not surfaced.
- [x] **FR-203** `claude -p` / `opencode run` adapters, harness-agnostic workflow (`harness/adapters.py`, `HARNESSES`).
- [x] **FR-204** reviewer clean-context, model-family inequality enforced by boot-time `validate_registry`, no session resume. **(new)**
- [ ] ⚠️ **FR-205** proposer MAY/MUST NOT validators — only inline dependency-cycle check; no dedicated `validators.py`.

### Human-in-the-loop (FR-300)
- [ ] ⚠️ **FR-301** hard/soft/off + threshold + revise + `MAX_GATE_ROUNDS` — wired for architecture/plan/merge; soft still confidence-only (no deterministic-check AND-clause); no calibration monitoring.
- [x] **FR-302** idempotent signals, `(gate, round)` identity, first-decision-wins.
- [ ] ⚠️ **FR-303** notifications + durable timers — timeout→auto-reject only; no notify activity, no reminder timer, no fallback-approver.
- [ ] ⚠️ **FR-304** decisions recorded/queryable — fields captured + retained as text; no structured queryable decision log.
- [ ] **FR-305** cross-run decision inbox — no surface lists everything awaiting a human.

### Memory (FR-400)
- [x] **FR-401** retain stage summaries / fix-loop gotchas / gate decisions (no "incidents" — needs maintenance loop).
- [ ] ⚠️ **FR-402** `RecallSnapshot` persisted/hashed/declared input — `query_hash` exists; snapshots not a separately content-addressed artifact; watermark is the working piece.
- [x] **FR-403** non-blocking retain, fire-and-forget with retries, PII/secret scrub hook (`memory/scrub.py`).
- [ ] **FR-404** nightly reflect (project + org) — activity exists, never invoked; no Temporal `Schedule`.

### Maintenance (FR-500)
- [ ] **FR-501** DAPER proactive workflow (timer + nudge).
- [ ] **FR-502** repair `code_fix` as brownfield child runs; risk-classed ops actions.
- [ ] **FR-503** confidence-gated repair approval; timeout = inaction.

### Interfaces (FR-600)
- [ ] ⚠️ **FR-601** dashboard fleet/spine/inbox — Vue 3 frontend exists (mock API); **no FastAPI backend** wired to Temporal.
- [ ] **FR-602** MCP server (list/detail/inbox/answer/decide/start) — no `interfaces/mcp/`.
- [ ] ⚠️ **FR-603** CLI — `start/status/answer/approve/reject/benchmark` ✅; missing cross-run `inbox` (FR-305).
- [x] **FR-604** stateless shells, no interface DB — true for CLI.

### Governance & ops (FR-700)
- [ ] **FR-701** run budgets (wall-clock/steps/cost) + escalation — only *context* budget exists; no run-level counters. Cost bookkeeping exists in benchmarks only.
- [ ] ⚠️ **FR-702** claim-check `ArtifactRef` / 2MB discipline — `ArtifactRef` model exists but diffs travel inline; no `CodeArtifact` union; no size guard.
- [ ] ⚠️ **FR-703** tiered harness containment — env allowlist ✅ only; **no `pre_tool` hook, no OS-user/container tier, no egress policy**.
- [ ] **FR-704** observability export (`events.jsonl` + `report.html`) — no `observability/` module.

---

## 3. Non-functional requirements (PRD §7)

- [x] **NFR-1** Durability — Temporal-native.
- [ ] **NFR-2** Scale / two pools — single task queue `"ai-sdlc"`; contra ADR-9.
- [ ] — **NFR-3** Latency (5s/2s) — untested, not falsifiable from code.
- [ ] ⚠️ **NFR-4** Auditability — Temporal history reconstructs runs; no `events.jsonl`/`report.html` export.
- [ ] ⚠️ **NFR-5** Security — env allowlist done; OS user, container, `pre_tool` hook, egress, scoped-cred injection absent.
- [x] **NFR-6** Reproducibility vs memoization — watermark-pinned recall + content-addressed cache.
- [x] **NFR-7** Portability — `MemoryConfig.backend` defaults to `fake`; real Hindsight client for self-hosting.

---

## 4. Success criteria (PRD §8)

- [ ] — **SC-1** ≥80% runs reach merge gate unattended — not measurable (no fleet runs).
- [ ] — **SC-2** ≤15 min operator time — not measurable.
- [ ] — **SC-3** fix-loop success ≥70% — mechanism exists; no aggregate metric captured.
- [ ] — **SC-4** repeat-clarification <10% by run 10 — needs reflect wiring (FR-404) + runs.
- [x] **SC-5** zero deploys past a failed **absolute** check — empty/vacuous-task bypass fixed, absolute failure is terminal, and the `security_no_critical` floor is now emitted by the `security_scan` activity and wired as an absolute merge-gate check (`feature.py:807,818`). `tests/test_security_floor.py` asserts a critical finding blocks deploy.
- [ ] — **SC-6** soft-gate override <5% — mechanism exists; not measurable without runs + reflect.

---

## 5. User stories (PRD §5)

- [ ] ⚠️ **US-1** clarify + one-click suggested answers — CLI clarify + suggested-answer auto-accept ✅; no dashboard/Slack/MCP delivery.
- [x] **US-2** approve/revise architecture spec — REVISE loop with recorded identity.
- [x] **US-3** task escalation → retry-with-guidance/quarantine — guidance reaches same harness session.
- [x] **US-4** per-project gate config (hard/soft + threshold) — `GateConfig`, no code change.
- [x] **US-5** dev/reviewer different model family; registry rejects same-family — enforced at boot. **(new)**
- [ ] **US-6** stakeholder one-screen fleet view — no dashboard backend.
- [ ] **US-7** MCP conversational gate approval — no MCP server.

---

## 6. Architecture decision records (ARCHITECTURE.md §12)

- [x] **ADR-1** Temporal owns state
- [x] **ADR-2** Pydantic AI proposers + harness CLIs
- [ ] **ADR-3** `CodeArtifact` union (files|diff_ref) — model doesn't exist; diff handling ad hoc.
- [x] **ADR-4** Gates as policy-driven durable signal waits (revision loop included)
- [x] **ADR-5** Memoization + watermark; auditability/memoization split
- [x] **ADR-6** Anti-collusion review (model-family inequality, clean-context reviewer) **(new)**
- [ ] **ADR-7** Repairs execute through the factory — maintenance loop absent.
- [ ] ⚠️ **ADR-8** Interfaces as stateless shells — true for CLI; dashboard backend absent.
- [ ] **ADR-9** Two worker pools by capability — single queue.
- [ ] ⚠️ **ADR-10** Claim-check for large payloads — `ArtifactRef` exists but not load-bearing.
- [ ] ⚠️ **ADR-11** Deterministic DAG — holds for the 8 live stages; 6 stages absent.
- [x] **ADR-12** Contract-first, clean-context validators — QA ✅ and review ✅ both clean-context. **(now complete)**
- [x] **ADR-13** Serial-by-default; resume-bounded; context by reference (`near_context_ceiling` wired).
- [x] **ADR-14** Integration by running branch (fully wired).

---

## 7. Structural / repo-hardening items (ARCHITECTURE.md §14)

- [ ] ⚠️ Layered `src/factory/` tree — code still lives in the flattened `src/sdlc/` skeleton; §14 tree is aspirational (documented "P1 hardening", not silent drift).
- [ ] `prompts/` as versioned assets — prompts are inline Python constants (`REVIEWER_PROMPT`, etc.), hashed into `PROMPT_SHAS`, but not standalone files with an eval loop.
- [x] Deterministic CI stand-in for the e2e proof — `tests/fakes/` provides same-named `TemporalAgent` `TestModel` stubs + fake git/subprocess activities (P1 orchestration test). (A `fake_harness.py`-style adapter for real-git fidelity remains future work.)
- [ ] Cosmetic: workflow class is `FeatureWorkflow`; docs call it `FactoryWorkflow`.

---

## 8. Recommended next increments (ranked by invariant undercut, not effort)

1. ~~**Close P1 honestly** — CI-runnable end-to-end run through `FeatureWorkflow` + wire the `security_no_critical` absolute check.~~ **Done** on `feat/p1-consolidation` (`3cfbe62`…`41c9185`); plan `docs/superpowers/plans/2026-07-15-p1-consolidation.md`.
2. ~~**Analyze/Analyst stage** — unlocks coverage + criterion→test traceability advisory checks (FR-106).~~ **Done** on `feat/analyst-stage`; plan `docs/superpowers/plans/2026-07-16-analyst-stage.md`, spec `docs/superpowers/specs/2026-07-16-analyst-stage-traceability-coverage-design.md`.
3. **retro/reflect wiring** (FR-404) — starts accumulating the SC-4/SC-6 calibration signal.
4. **Harness containment** beyond env allowlist — `pre_tool` hook + egress (FR-703/NFR-5).
5. **Operability** — dashboard FastAPI backend + MCP + cross-run inbox (FR-305/601/602).
6. **Post-P1 roadmap** — MaintenanceWorkflow/DAPER, two worker pools, run budgets, observability export, brownfield mode, claim-check.
