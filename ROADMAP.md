# Implementation Roadmap — Agentic SDLC Factory

| | |
|---|---|
| Status | Living tracker |
| Last verified | 2026-08-06 (E-40/E-43 against `src/sdlc/`; the rest 2026-08-05, against `src/sdlc/`, `interfaces/`, `tests/`, `config/`, `agents/`) |
| Source of truth for scope | `PRD.md`, `ARCHITECTURE.md`, `SDLC-spec.md` |
| Method | Every FR / NFR / SC / US / ADR and the 15-stage DAG checked against actual code, not against prior audit claims |

**Legend**
- `[x]` — implemented and wired into the live path
- `[ ]` ⚠️ — partial: mechanism exists but incomplete or not fully wired (see note)
- `[ ]` — not started
- `—` — not falsifiable from code alone (needs runtime measurement)

> Since the 2026-07-05 audit, the **reviewer stage (ADR-6/FR-204)** and **agent registry (FR-201)** landed (merged `b9455c3`), plus a **coding-harness adapter layer** and **harness observability logging**. Those items are now checked. The audit's `docs/feature-coverage-audit-2026-07-05.md` is superseded by this tracker.

> **2026-07-16 — ADR-6 correction.** The anti-collusion check was validating `config/agents.yaml`'s `developer` role, which nothing ever ran; `cfg.roles["dev"]` (a second, hardcoded registry in `models.py`) selected the coding model. The invariant held only while two hardcoded lists agreed. `agents.yaml` is now the single registry, the check compares `reviewer` against `dev`, and `PipelineConfig.roles` is asserted at boot to mirror it. Prior `[x]` marks on ADR-6/US-5 were true of the mechanism, not of the pairing it constrained.

> **2026-07-17 — research stage (FR-107).** A grounded research stage lands
> before clarify, off by default. `grounded` means quote-verified against bytes
> fetched this run; unverified claims are inferred or dropped; recall yields
> leads, not truth. It is the pipeline's first outbound egress (raising E-18)
> and the first role a folder genuinely describes. Memoization is preserved by a
> canonical `brief_digest`, not by caching the brief (a cached brief was never
> fetched). `2026-07-17-research-agent-grounded-briefs`.

> **2026-07-19 — benchmark & evaluation design input.** A measurement
> design (`docs/BENCHMARK.md`) folds the existing benchmark harness (E-27)
> and prompt eval loop (E-4) into an instrument for the success criteria.
> It adds **no scope**: each item anchors to an FR/NFR/SC already open, and
> the capabilities that would (held-out oracles, anti-cheat assertions,
> rubric-calibration tracking) are marked **(new scope)** and need a PRD
> line. New work lands as **E-30…E-39** (§9.8), with a language-agnostic
> `ToolchainAdapter` (ADR-15) under E-30 so the grade holds across Python /
> TS / Go / Rust, and canonical claim-checked harness **sessions** (ADR-16,
> E-38) captured on every run so *how* a diff was reached is measurable, not
> just the diff. The framing: three of four
> phase exits are gated on measurement that does not run yet — P3's exit is
> literally *"SC-4 and SC-6 measurable"*, and SC-1/2/3 are all `—`.

> **2026-07-25 — two new user groups, four new requirement families.** PRD v1.1
> adds repository **triage** (FR-900), the **capability & risk audit** (FR-910,
> porting the EDCR methodology from
> [`BrownKit`](https://github.com/MaksimShevtsov/BrownKit)), the **service
> platform** (FR-1000), and the **product-outcome loop** (FR-1100). New work
> lands as **E-40…E-71** (§§10–13). Three framings worth keeping in view:
> (a) **triage is a separate, cheaper tier than the audit, and gates it** — EDCR
> is enterprise-brownfield machinery (BIAN/TM Forum/ACORD/HL7 blueprints,
> Java/Maven sample) and pointing it at a three-week-old vibe-coded repo
> produces a capability model over structure that does not exist; (b) the port's
> real value is **enforceability** — BrownKit's gates and 14 acceptance criteria
> are prose graded by the model that produced the artifacts, and here they
> become `CheckResult`s computed by pure code; (c) **BrownKit's `not-collected`
> discipline flows back into the existing contracts** (FR-915) — the factory's
> `QAReport.coverage_pct: float | None` conflates a measured zero with a
> never-measured value, which is a defect in a product that sells measurement.
> Spec `docs/superpowers/specs/2026-07-25-brownfield-assessment-and-outcome-measurement-design.md`.

> **2026-08-06 — E-40/E-43 designed and planned, not yet implemented.** The two
> §15 invariants now have an approved design
> (`docs/superpowers/specs/2026-08-06-measurement-and-shared-grounding-verifier-design.md`)
> and a task-by-task plan
> (`docs/superpowers/plans/2026-08-06-measurement-and-shared-grounding-verifier.md`).
> No code has landed: `src/sdlc/measurement.py` and `src/sdlc/grounding.py` do
> not exist, so both items stay `[ ]`. Reading the code before designing against
> it produced **three corrections to this tracker's own framing**, recorded here
> because the roadmap was wrong, not merely incomplete:
> (a) **E-40's stated defect is stale** — the merge gate reads `CoverageReport`,
> which E-30 already gave a `measured: bool` + `detail` discipline;
> `QAReport.coverage_pct` is an LLM-asserted field that *nothing reads* (it is
> deleted, not retyped);
> (b) **the sharper FR-915 instance is on the absolute floor** — `report_from_sarif`
> returns `SecurityReport(critical=0, findings=[])` for a malformed or partial
> SARIF, byte-identical to a clean scan, and `security_no_critical` is the
> **absolute** SC-5 check, so a broken scanner reads as a passing security floor.
> Latent today (nothing shells semgrep; the regex scan always collects) — which
> is exactly when the guard is cheap to install. The check splits into
> `security_scan_collected` + `security_no_critical`, both in `ABSOLUTE_FLOOR`;
> (c) **E-43 is not an invariant awaiting a consumer** — `HandoffClaim.evidence`
> and `IntegrityFlag.evidence` are *two live consumers* carrying unverified
> model-asserted quotes into downstream prompts and anti-cheat accusations
> today. The verifier ships with two normalization profiles that must never be
> merged (`EXTRACTED_TEXT` for third-party extractor output, `VERBATIM_BYTES`
> for code and stored transcripts), and it never decides consequences — research
> fails its stage, the two lenses drop the item.

---

## 0. Phase summary (PRD §9)

- [x] **P1** — Greenfield pipeline, CLI, hard gates, no memory → *one project shipped end-to-end*
  Exit criterion **demonstrated**: `tests/test_e2e_greenfield.py` drives the real `FeatureWorkflow` greenfield `IdeaBrief` → `deployed:` end-to-end in CI, and the `security_no_critical` absolute floor now bites (SC-5). Delivered on `feat/p1-consolidation` (`3cfbe62`…`41c9185`).
- [ ] ⚠️ **P2** — Brownfield, dashboard + notifications, fix loops, cross-harness review → *first brownfield feature merged via PR*
  Cross-harness review ✅, fix loops ✅, and notifications ✅ (E-9) landed early; brownfield mode and dashboard backend remain. The backend is **E-75** (§14) — `api/http.ts:4` still rejects every call and the dashboard runs entirely on `api/mock`.
- [ ] ⚠️ **P3** — Hindsight memory + confidence-gated soft gates → *SC-4 and SC-6 measurable*
  Memory (recall/retain/watermark) ✅ and soft gates ✅ done; SC-4/SC-6 not yet measurable (need retro/reflect wiring + real runs). **The retro stage that makes them measurable is E-32** (§9.8); the on/off memory delta is the measurement E-31/E-33 exist to run.
- [ ] **P4** — MCP surface, maintenance loop (DAPER), fleet scale → *SC-1..3 at target*
  Not started.
- [ ] **P5** — Triage + tidy-up (Tier 0/1), operator-run, single tenant → *one unfamiliar repository triaged, a mechanical backlog fixed through governed runs, before/after delta recorded*
  Not started (§10, E-40…E-44). **Does not depend on P7** — operator-run delivery on repositories you are authorised to run needs neither tenancy nor self-serve onboarding.
- [ ] **P6** — Capability & risk audit (Tier 2) + evidence bundle → *one repository audited end-to-end with SC-7 held and a bundle handed over*
  Not started (§11, E-45…E-56). Gated on P5's readiness verdict (FR-903), not merely sequenced after it.
- [ ] **P7** — Hosted multi-tenant service → *NFR-8 adversarial test green; FR-1002 container tier live; a tenant onboards unassisted*
  Not started (§12, E-57…E-63). **FR-1002 is the gating item for admitting any external tenant**, not a hardening task: today a customer's `npm install` executes as the worker user with the worker's toolchain and unrestricted network egress.
- [ ] **P8** — Product outcome loop → *one hypothesis pre-registered, shipped, and decided by its own rule (SC-11/SC-12)*
  Not started (§13, E-64…E-71). E-67 (`DeployPlan`/`DeployReport`) delivered the deploy contract; the outcome loop still needs the observation/keep-kill half (E-70).

---

## 1. Pipeline — 15-stage DAG (SDLC-spec v2 §1)

**7 of 15 stages live.**

- [ ] **0 · intake** — routing greenfield/brownfield/repair. `IdeaBrief.mode` is a field only; no branch logic in `feature.py`.
- [ ] **1 · constitution** — no `Constitution` model, no stage.
- [ ] **2 · context (Cartographer)** — no `CodebaseMap`, no `cartography.py`, no brownfield delta.
- [ ] **3 · requirements (Product)** — conflated into clarify; no standalone Product proposer / `Requirements` artifact.
- [ ] **4 · research** (FR-107) — grounded brief before clarify. The DAG is now 15
  stages; **7 of 15 stages live** (research is scaffolded, off by default).
- [x] **5 · clarify** — Clarifier + gate; open-question wait on `answer_question`; recall/retain/memoization wired.
- [x] **6 · architecture** — Architect + gate, with REVISE loop (`_revisable_stage`).
- [x] **7 · planning** — Planner + gate, with REVISE loop.
- [x] **8 · code** — Developer, per-task, ADR-14 integration branch (`_dev_task`).
- [x] **9 · review** — clean-context `reviewer_agent` (`t_reviewer`) run in `_dev_task`; blocking findings fold into the fix loop. **(new)**
- [x] **10 · analyze (Analyst)** — Analyst clean-context proposer (`t_analyst`) emits `AnalysisReport`; workflow enforces criterion→test traceability against the plan's authoritative criteria (FR-106).
- [x] **11 · qa (+ Resolver)** — clean-context `t_qa` + bounded fix loop (folded into stage 7). *Note: default `max_fix_attempts=2`, PRD says QA loop 3 — numeric drift.*
- [ ] ⚠️ **12 · quality_gate** — `DeterministicQualityGate` mechanism ✅; 7 checks built (`build_integration_green`, `lint_clean`, `security_no_critical`, `security_scan_collected` absolute; `review_severity`, `traceability`, `coverage` advisory). Absolute security floor now wired ✅ — the floor now carries `security_scan_collected` beside `security_no_critical`, so a scan that never collected (e.g. a malformed SARIF) can no longer read as a clean absolute floor (FR-915, 2026-08-06); traceability enforced ✅; coverage via deterministic Cobertura seam — **E-30 closes the FR-106 crossing gap**: `run_integration_checks` now runs coverage-instrumented tests against the merged integration head, landing `coverage.xml` where `measure_coverage` reads (Python adapter end-to-end; Go/TS/Rust via E-30a/b/c). Still an advisory no-op unless `coverage_threshold` is set.
- [x] ✅ **13 · deploy** — `DeployPlan`/`DeployReport` split (E-67), deterministic `DeploymentWorkflow` child owning apply → smoke → rollback, `deploy_failed` gate in the parent. Off by default (`PipelineConfig.deploy.enabled`). *Remaining: `devops_planner` does not yet author the plan — `FeatureWorkflow._deploy_plan` builds a single-liveness-check plan (see its docstring).*
- [x] **14 · retro** — on every terminal path the workflow builds a `RunSummary` from an in-workflow `RunEvent` trace, retains it + fires-and-forgets `reflect(project_bank)` (gated on `memory.enabled`), and exports `events.jsonl` + `report.html` via the `export_run_artifacts` activity (E-32). The `org_bank`-writer half stays unbuilt (E-25); retro is project scope only.

---

## 2. Functional requirements (PRD §6)

### Pipeline (FR-100)
- [ ] ⚠️ **FR-101** 15-stage durable DAG — 7/15 stages (see §1).
- [ ] **FR-102** greenfield/brownfield classify + `CodebaseMap` + delta.
- [x] **FR-103** memoization, per-run watermark, audit-record-always-kept (`memoization/cache.py`, `content_key`, `_cached_stage`) — each stage's memo key now carries *its own* role's model (`STAGE_MODELS`), so a per-role model change invalidates exactly that stage. `brief_digest` keeps memoization alive once a non-memoized stage (research) feeds memoized ones: the brief contributes only a canonical (source_url, claim) digest to `content_key`, so identical facts hit and new facts invalidate clarify/architect/planner.
- [x] **FR-104** integration branch, per-task worktree, own-branch-point diff (ADR-14 fully wired).
- [ ] ⚠️ **FR-105** fix loops — QA loop ✅, review findings now fold into it ✅; loop-count defaults drift from spec (2 vs 3).
- [ ] ⚠️ **FR-106** deterministic absolute/advisory gate — classification ✅ and load-bearing; security absolute-floor check now wired ✅ (`security_no_critical`); traceability enforced ✅; coverage wired as a deterministic diff-scoped seam ✅ (Python instrumentation landed via E-30; Go/TS/Rust via E-30a/b/c).
- [ ] **FR-107 (new scope)** grounded research stage — `ResearchBrief`, quote-verified against bytes fetched this run, off by default (`research_enabled`). Landed behind the PRD amendment adding FR-107; `2026-07-17-research-agent-grounded-briefs`.
- [x] **FR-108 (new scope; ADR-15)** language-agnostic toolchain adapter — `ToolchainAdapter`/`TOOLCHAINS` resolved by marker file, canonical Cobertura + SARIF, Python reference end-to-end; `run_integration_checks` closes the FR-106 coverage-crossing gap. Go/TS/Rust = E-30a/b/c.

### Agents (FR-200)
- [x] **FR-201** versioned `config/agents.yaml` registry (role/kind/model) — governs all eleven roles (3 harness + 8 proposer); `PipelineConfig.roles` is a purity-mandated mirror asserted at boot.
- [ ] ⚠️ **FR-202** schema-validated artifacts + re-prompt — Pydantic `output_type` gives validation; configurable `validation_retries` knob not surfaced.
- [x] **FR-203** `claude -p` / `opencode run` adapters, harness-agnostic workflow (`harness/adapters.py`, `HARNESSES`).
- [x] **FR-204** reviewer clean-context, model-family inequality enforced by boot-time `validate_registry`, no session resume. **(new)**
- [ ] ⚠️ **FR-205** proposer MAY/MUST NOT validators — only inline dependency-cycle check; no dedicated `validators.py`.

### Human-in-the-loop (FR-300)
- [ ] ⚠️ **FR-301** hard/soft/off + threshold + revise + `MAX_GATE_ROUNDS` — wired for architecture/plan/merge; soft still confidence-only (no deterministic-check AND-clause); no calibration monitoring. Tool-call approval now escalates into this same machinery (E-17), so a `pre_tool` denial and a human gate are one mechanism.
- [x] **FR-302** idempotent signals, `(gate, round)` identity, first-decision-wins.
- [x] **FR-303** notifications + durable timers — notify activity (`log`/`webhook` adapters), reminder + escalation + expiry timers, `on_timeout` per gate (E-9).
- [ ] ⚠️ **FR-304** decisions recorded/queryable — fields captured + retained as text; no structured queryable decision log.
- [ ] **FR-305** cross-run decision inbox — no surface lists everything awaiting a human.

### Memory (FR-400)
- [x] **FR-401** retain stage summaries / fix-loop gotchas / gate decisions (no "incidents" — needs maintenance loop).
- [ ] ⚠️ **FR-402** `RecallSnapshot` persisted/hashed/declared input — `query_hash` exists; snapshots not a separately content-addressed artifact; watermark is the working piece.
- [x] **FR-403** non-blocking retain, fire-and-forget with retries, PII/secret scrub hook (`memory/scrub.py`).
- [ ] ⚠️ **FR-404** nightly reflect — **project half live**: `schedules/nightly-reflect.yaml` → `ReflectWorkflow` → `reflect()`, applied via `sdlc schedules apply` (E-12/E-13); the retro stage (E-32) now also calls `reflect(project_bank)` per run (best-effort, gated on `memory.enabled`). **Org half unmet**: nothing retains to `org_bank`, so `reflect(org)` would consolidate an empty bank (E-25). Not `[x]` until org has writers.

### Maintenance (FR-500)
- [ ] **FR-501** DAPER proactive workflow (timer + nudge).
- [ ] **FR-502** repair `code_fix` as brownfield child runs; risk-classed ops actions.
- [ ] **FR-503** confidence-gated repair approval; timeout = inaction.

### Interfaces (FR-600)
- [ ] ⚠️ **FR-601** dashboard fleet/spine/inbox — Vue 3 frontend exists (mock API); **no FastAPI backend** wired to Temporal.
- [ ] **FR-602** MCP server (list/detail/inbox/answer/decide/start) — no `interfaces/mcp/`.
- [ ] ⚠️ **FR-603** CLI — `start/status/answer/approve/revise/reject/benchmark` ✅
  (`revise` landed with E-7; gate rounds are now derived from the pending item,
  not typed by the operator); missing cross-run `inbox` (FR-305).
- [x] **FR-604** stateless shells, no interface DB — true for CLI.

### Governance & ops (FR-700)
- [x] **FR-701** run-level budgets — research ships the FIRST run-level counters (`max_searches`/`max_fetches`/`max_cost_usd`), stage-scoped and enforced inside the tools; E-19 remains the general version. *Landed (E-33):* run-level token/cost counters in `RunSummary.roles` + a `run_budget_usd` budget gate that escalates through the FR-301/302 gate machinery on crossing (approve = one more increment, reject = `rejected:budget`). Stage-scoped research budgets (FR-107) unchanged.
- [ ] ⚠️ **FR-702** claim-check `ArtifactRef` / 2MB discipline — `ArtifactRef` model exists but diffs travel inline; no `CodeArtifact` union; no size guard. Sessions are now a real claim-check consumer (`ArtifactStore` / `harness_session`, E-38), but diffs still travel inline, so FR-702 stays open.
- [ ] ⚠️ **FR-703** egress policy — **research is the pipeline's first outbound egress, and it arrives before the egress policy.** *Partially landed (2026-07-24, E-15/E-16):* the `pre_tool` hook now exists and denies out-of-worktree writes, recursive deletes, agent-config rewrites, and non-allowlisted hosts (tool-level); approval escalation for `action: escalate` rules lands via the same hook (E-17). Egress is still env-allowlist + tool-level only — network-level egress and the OS/container tier remain open (E-21).
- [ ] **FR-704** observability export (`events.jsonl` + `report.html`) — no `observability/` module.

### Context & continuity (FR-800) — *documented in PRD 2026-07-25, no new scope*

Live since P1, never written into the PRD until now. Listed so the family reads
as tracked rather than accidental.

- [x] **FR-801** per-role `context_budget_tokens` enforced at prompt assembly (`models.py:496`).
- [x] **FR-802** `max_session_resumes` with stack-mismatch override (`feature.py:211,695`).
- [x] **FR-803** `ValidationContract` frozen at planning (`models.py:184`).
- [x] **FR-804** materialized diff for clean-context validators (`activities.py:502`).
- [x] **FR-805** `HandoffSummary` task→task continuity (`models.py:202,275`).
- [ ] ⚠️ **FR-806** prompts as versioned assets in the memo hash — prompt bytes are hashed into `content_key` ✅; the edit → offline eval → deploy loop is E-4.

### Assessment, Tier 0 — triage (FR-900) *(new scope; PRD v1.1)*

- [ ] **FR-901** triage stage → `RepoTriage` + readiness verdict; completes on repos that do not build (E-42). *Artifact landed with E-41 (2026-08-06); the stage and the readiness gate are E-42.*
- [ ] ⚠️ **FR-902** hygiene signal set via FR-108 adapters, one implementation
  per signal — three of seven landed (build probe, secrets incl. client-bundle
  reachability, baseline practice); dependency health, dead/scaffold code,
  framework misconfig and size/duplication outliers are E-41a–d.
- [ ] **FR-903** readiness gate blocking Tier 2, overridable by audited decision (E-42).
- [ ] **FR-904** `mechanically_fixable` → brownfield child runs + before/after re-triage (E-44).

### Assessment, Tier 2 — capability & risk audit (FR-910) *(new scope; PRD v1.1)*

- [ ] **FR-911** `AssessmentWorkflow` EDCR DAG, report-after-assess, no phase-status file (E-45); `/enrich` as a declared stage input rather than a phase (E-56).
- [ ] **FR-912** deterministic scan memoized on `(tree hash, signal version)`; cross-source confidence (E-46).
- [ ] **FR-913** `CapabilityMap` with content-derived stable ids + coverage floor + orphan classification — **also satisfies FR-102** (E-47/E-48). Blocked on **OQ-6** (what canonical key survives refactoring).
- [ ] **FR-914** byte-exact quote verification against the pinned commit, fail-closed — shares FR-107's verifier (E-43). *Partially landed 2026-08-06 (`grounding.py`: one substring invariant, two normalization profiles, verdict-only) — see spec `docs/superpowers/specs/2026-08-06-measurement-and-shared-grounding-verifier-design.md`. The verifier + research/handoff/deep-review consumers landed; the commit source gained its first consumer with E-41's secrets signal (2026-08-06), which re-verifies every emitted evidence quote against the pinned commit; stays open until an LLM-proposing assessment stage cites the same way, which is where the check stops being a drift guard.*
- [ ] **FR-915** `not_collected` / `unknown` vs measured value (E-40). *Contract half landed 2026-08-06 (`measurement.py`, retrofitted onto `CoverageReport`/`SecurityReport`/`claim_survival_score`; `QAReport.coverage_pct` deleted) — see spec `docs/superpowers/specs/2026-08-06-measurement-and-shared-grounding-verifier-design.md`. The `RepoTriage`/triage half is deferred to E-41; the load-bearing case was the SARIF-malformed-reads-as-clean hole on the absolute floor.*
- [ ] **FR-916** STRIDE + vuln classification + control coverage + composites with 1–3 specific drivers (E-49).
- [ ] **FR-917** risk thresholds as deterministic gate checks; FP dispositions as audited overrides (E-50).
- [ ] **FR-918** acceptance criteria computed by code, not self-asserted; cross-reference integrity **absolute** (E-51).
- [ ] **FR-919** spec seeds → brownfield child runs; seed criteria become run acceptance criteria (E-53).
- [ ] **FR-920** re-assessment, incremental re-scan, per-capability risk delta as first-class output (E-54).
- [ ] **FR-921** evidence bundle: manifest + five role reports + verification status + gates + fix-run sessions (E-52).
- [ ] **FR-922** per-phase budgets; exhaustion escalates, partials marked partial (E-55).

### Service platform (FR-1000) *(new scope; PRD v1.1)*

- [ ] **FR-1001** tenancy by construction — namespace + store prefix + bank namespace; resolves OQ-4 (E-58).
- [ ] **FR-1002** untrusted-code isolation — per-run container, non-root, network-level egress allowlist. **Precondition for any external tenant** (E-21 + E-57).
- [ ] **FR-1003** repo connection — app install, short-TTL repo-scoped tokens, PR-only delivery, webhooks (E-59).
- [ ] **FR-1004** identity/authz; real principal in `GateDecision` — closes FR-304's identity gap (E-60).
- [ ] **FR-1005** metered per-tenant cost from FR-701 counters (E-61).
- [ ] **FR-1006** on-prem single-tenant *or* hosted; configurable model provider (E-62).
- [ ] **FR-1007** per-tenant retention + audited purge (E-63).

### Product outcome (FR-1100) *(new scope; PRD v1.1)*

- [ ] **FR-1101** `Hypothesis` at intake, gated before any code (E-64).
- [ ] **FR-1102** pre-registration freeze + hash, reusing FR-803 semantics (E-65).
- [ ] **FR-1103** metric → instrumentation → emitted-event traceability via the FR-106 mechanism (E-66).
- [x] **FR-1104** `DeployPlan`/`DeployReport` — **closes DAG stage 13 for all runs** (E-67). Delivered on `feat/deploy-contract`; spec `docs/superpowers/specs/2026-08-06-deploy-contract-design.md`.
- [ ] **FR-1105** hosting + analytics adapters, one reference each; no substrate reimplementation (E-68/E-69).
- [ ] **FR-1106** durable observation window → collect → evaluate → keep/kill/extend gate (E-70). See **OQ-9**.
- [ ] **FR-1107** PoC mode: bounded, disposable, marked so it never accrues as debt (E-71).
- [ ] **FR-1108** `inconclusive` is a valid verdict; never a favourable read on insufficient data (E-70).

---

## 3. Non-functional requirements (PRD §7)

- [x] **NFR-1** Durability — Temporal-native.
- [ ] **NFR-2** Scale / two pools — single task queue `"ai-sdlc"`; contra ADR-9.
- [ ] — **NFR-3** Latency (5s/2s) — untested, not falsifiable from code.
- [ ] ⚠️ **NFR-4** Auditability — Temporal history reconstructs runs; no `events.jsonl`/`report.html` export.
- [ ] ⚠️ **NFR-5** Security — env allowlist done; `pre_tool` hook landed (2026-07-24, E-15/E-16, tool-level destructive-action + egress denial); OS user, container, network-level egress, scoped-cred injection still absent (E-20/E-21).
- [x] **NFR-6** Reproducibility vs memoization — watermark-pinned recall + content-addressed cache. *Pinning is exact on `fake` (entry-count cutoff) and a `mentioned_at` cutoff on `hindsight`, which has no point-in-time read: memories retained after the freeze cannot enter a stage input, but ranking is still contaminated by them and post-freeze consolidation can mint observations carrying pre-freeze timestamps. `2026-08-02-hindsight-real-integration-design` §2.1.*
- [x] **NFR-7** Portability — `MemoryConfig.backend` defaults to `fake`; real Hindsight client for self-hosting, verified against a live container by `tests/test_hindsight_live.py` (the client shipped before 2026-08-02 implemented an invented API and could not have worked).
- [ ] **NFR-8** Tenant isolation proven by adversarial cross-tenant read/recall test — no tenant concept exists yet (E-58).
- [ ] **NFR-9** Hostile input — the factory currently assumes repositories are its own. Build scripts, test code, and manifests of a connected repo are attacker-controlled and executed (E-57). **E-41's build probe is the first stage that knowingly executes a foreign repository's code** (bounded, in a throwaway clone, as the worker user with network access). Operator-run only until E-57/E-21.
- [ ] — **NFR-10** Assessment reproducibility — not falsifiable until the assessment exists; the deterministic half is E-41/E-46, the fused-layer variance half needs runs.

---

## 4. Success criteria (PRD §8)

- [ ] — **SC-1** ≥80% runs reach merge gate unattended — not measurable (no fleet runs). Vehicle: the benchmark matrix (§9.8, E-34) is where unattended-reach rate is aggregated; cases can now carry a held-out grade (E-31 landed), so the gate is the next load-bearing piece.
  **Aggregation landed** (`benchmarks/sc_rollup.py`, `sdlc benchmark score`);
  the number is n/a until 5+ runs exist.
- [ ] — **SC-2** ≤15 min operator time — not measurable.
- [ ] — **SC-3** fix-loop success ≥70% — mechanism exists; no aggregate metric captured. Captured per run as a coordination metric by the benchmark (§9.8, E-36 heatmap): fix-loop attempts vs resolution, per stage.
  **Aggregation landed** (`benchmarks/sc_rollup.py`, `sdlc benchmark score`);
  the number is n/a until 5+ runs exist.
- [ ] — **SC-4** repeat-clarification <10% by run 10 — needs reflect wiring (FR-404) + runs. **The per-run signal now accrues:** the retro stage (E-32) emits a `RunSummary` carrying `clarifications[].answered_by` (`human`/`suggested`/`unanswered`) on every terminal path. The cross-run *aggregation* into a repeat-clarification rate remains the benchmark's job (§9.8), via the memory-on cells that generate the run-10 series.
  **Aggregation landed** (`benchmarks/sc_rollup.py`, `sdlc benchmark score`);
  the number is n/a until 5+ runs exist.
- [x] **SC-5** zero deploys past a failed **absolute** check — empty/vacuous-task bypass fixed, absolute failure is terminal, and the `security_no_critical` floor is now emitted by the `security_scan` activity and wired as an absolute merge-gate check (`feature.py:807,818`). `tests/test_security_floor.py` asserts a critical finding blocks deploy.
- [ ] — **SC-6** soft-gate override <5% — mechanism exists; not measurable without runs + reflect. **The per-run signal now accrues:** the retro stage (E-32) emits `RunSummary.gates[]` with `policy`/`decided_by`/`confidence`/`overrides` (ARCHITECTURE §10 calibration compare). The cross-run *aggregation* into an override rate remains the benchmark's job (§9.8).
  **Aggregation landed** (`benchmarks/sc_rollup.py`, `sdlc benchmark score`);
  the number is n/a until 5+ runs exist.
- [ ] — **SC-7** grounding integrity: 100% of `grounded` findings re-verify byte-exact, zero fabricated path/line refs when sampled — **the assessment product's SC-5**: one violation is a defect, not a percentage. Mechanism is E-43 (designed 2026-08-06, not implemented); the sampled audit needs real assessments.
- [ ] — **SC-8** capability coverage ≥90% with classified orphans on ≥80% of readiness-passing repos — needs E-47 + a corpus.
- [ ] — **SC-9** remediation efficacy: reduced composite for the targeted capability in ≥80% of accepted items, no new critical — needs E-54's delta.
- [ ] — **SC-10** assessment economics per repo-size band — needs E-55 budgets + runs; without this the work cannot be priced.
- [ ] — **SC-11** ≥95% of experiments decided by the pre-registered rule with no *unaudited* post-hoc change — needs E-65.
- [ ] — **SC-12** 100% of hypothesis metrics traced to an emitted event before the deploy gate — needs E-66.

---

## 5. User stories (PRD §5)

- [ ] ⚠️ **US-1** clarify + one-click suggested answers — CLI clarify + suggested-answer auto-accept ✅; no dashboard/Slack/MCP delivery.
- [x] **US-2** approve/revise architecture spec — REVISE loop with recorded identity.
- [x] **US-3** task escalation → retry-with-guidance/quarantine — guidance reaches same harness session.
- [x] **US-4** per-project gate config (hard/soft + threshold) — `GateConfig`, no code change.
- [x] **US-5** dev/reviewer different model family; registry rejects same-family — enforced at boot, against `dev` (the role that actually codes) since `2026-07-16-registry-drives-every-role`.
- [ ] **US-6** stakeholder one-screen fleet view — no dashboard backend.
- [ ] **US-7** MCP conversational gate approval — no MCP server.
- [ ] **US-8** client connects a repo → readiness verdict + checkable hygiene list (E-41/E-42/E-43).
- [ ] **US-9** client approves a tidy-up backlog → PR per item + before/after delta (E-44).
- [ ] **US-10** assessor hands over a bundle whose every claim resolves to evidence (E-51/E-52).
- [ ] **US-11** product owner's decision rule frozen at approval, verdict computed against it (E-64/E-65/E-70).
- [ ] **US-12** platform engineer onboards an isolated tenant (E-57/E-58).

---

## 6. Architecture decision records (ARCHITECTURE.md §12)

- [x] **ADR-1** Temporal owns state
- [x] **ADR-2** Pydantic AI proposers + harness CLIs
- [ ] **ADR-3** `CodeArtifact` union (files|diff_ref) — model doesn't exist; diff handling ad hoc.
- [x] **ADR-4** Gates as policy-driven durable signal waits (revision loop included)
- [x] **ADR-5** Memoization + watermark; auditability/memoization split
- [x] **ADR-6** Anti-collusion review (model-family inequality, clean-context reviewer) — *the boot check validated `agents.yaml`'s `developer` entry, which nothing ran; `cfg.roles["dev"]` did the coding. Re-aimed at `dev` and the two registries mirror-checked at boot (`2026-07-16-registry-drives-every-role`).*
- [ ] **ADR-7** Repairs execute through the factory — maintenance loop absent.
- [ ] ⚠️ **ADR-8** Interfaces as stateless shells — true for CLI; dashboard backend absent.
- [ ] **ADR-9** Two worker pools by capability — single queue.
- [ ] ⚠️ **ADR-10** Claim-check for large payloads — `ArtifactRef` exists but not load-bearing.
- [ ] ⚠️ **ADR-11** Deterministic DAG — holds for the 8 live stages; 6 stages absent.
- [x] **ADR-12** Contract-first, clean-context validators — QA ✅ and review ✅ both clean-context. **(now complete)**
- [x] **ADR-13** Serial-by-default; resume-bounded; context by reference (`near_context_ceiling` wired).
- [x] **ADR-14** Integration by running branch (fully wired).
- [x] **ADR-15** Language-agnostic toolchain by marker file (`src/sdlc/toolchain/`) — Python reference adapter end-to-end; Go/TS/Rust are E-30a/b/c.
- [x] **ADR-16** Harness sessions as first-class, claim-checked artifacts (E-38).
- [x] **ADR-17** Containment as a declared harness capability — native inner, hook outer, fail closed (E-15/E-16).
- [ ] **ADR-18** Triage precedes capability modelling — an unbuildable or structurally-illegible repo is reported as a precondition failure, never capability-mapped (FR-903, E-42).
- [ ] ⚠️ **ADR-19** Deployment targets and analytics sources are adapters, not substrate (FR-1105, NG7, E-68/E-69). **Deployment half done** (E-67/E-68: `src/sdlc/deploy/adapters.py`, compose + script). Analytics half open (E-69). Unresolved consequence: **OQ-9**.
- [ ] **ADR-20** Pre-registration reuses `ValidationContract` freeze semantics (FR-1102, FR-803, E-65).

---

## 7. Structural / repo-hardening items (ARCHITECTURE.md §14)

- [ ] ⚠️ Layered `src/factory/` tree — code still lives in the flattened `src/sdlc/` skeleton; §14 tree is aspirational (documented "P1 hardening", not silent drift).
- [x] `prompts/` as versioned assets **with an eval loop** — prompts live in
  `agents/<role>/instructions.md` and hash into `PROMPT_SHAS` from file content (E-2 ✅); a prompt
  edit is now measurable via `sdlc eval <role>` (E-4 ✅).
- [x] Deterministic CI stand-in for the e2e proof — `tests/fakes/` provides same-named `TemporalAgent` `TestModel` stubs + fake git/subprocess activities (P1 orchestration test). (A `fake_harness.py`-style adapter for real-git fidelity remains future work.)
- [ ] Cosmetic: workflow class is `FeatureWorkflow`; docs call it `FactoryWorkflow`.
- **ReviewReport / MergeVerdict SGR ordering (found in the research spec).**
  `ReviewReport` is `approve → findings → confidence` — the reviewer commits to a
  verdict before writing a finding, contradicting `REVIEWER_PROMPT`'s "set
  approve to false if ANY finding is critical/high". `MergeVerdict` rates its own
  confidence two fields before listing concerns. `AnalysisReport`/`ArchitectureSpec`
  are already evidence-first. A one-line-per-contract fix; its own change and its
  own benchmark run (out of scope for the research increment).

---

## 8. Recommended next increments (ranked by invariant undercut, not effort)

1. ~~**Close P1 honestly** — CI-runnable end-to-end run through `FeatureWorkflow` + wire the `security_no_critical` absolute check.~~ **Done** on `feat/p1-consolidation` (`3cfbe62`…`41c9185`); plan `docs/superpowers/plans/2026-07-15-p1-consolidation.md`.
2. ~~**Analyze/Analyst stage** — unlocks coverage + criterion→test traceability advisory checks (FR-106).~~ **Done** on `feat/analyst-stage`; plan `docs/superpowers/plans/2026-07-16-analyst-stage.md`, spec `docs/superpowers/specs/2026-07-16-analyst-stage-traceability-coverage-design.md`.
3. ~~**retro/reflect wiring** (FR-404) — starts accumulating the SC-4/SC-6 calibration signal. Tasks: **E-12, E-13** (§9.3).~~ **Partially done** — schedule mechanism + nightly project reflect ship (E-12/E-13); plan `docs/superpowers/plans/2026-07-16-schedules-as-files-and-nightly-reflect.md`. Signal only accrues on runs with `memory.enabled=true` (defaults `False`). Org half blocked on **E-25**; the retro *stage* (§1 item 13, `RunSummary`) is still unbuilt (**E-32**). *Follow-on:* the benchmark instrument (§9.8) is what turns the accruing signal into the SC-1..6 numbers — held-out grade (**E-30/E-31**) and per-role economics (**E-33**) are the load-bearing measurement work, ranked there by invariant undercut.
4. ~~**Harness containment**~~ — `pre_tool` hook ✅ (E-15/E-16) + approval escalation ✅ (E-17); egress beyond tool-level remains **E-21**. Tasks: **E-15…E-18** (§9.4) — note the hook and the gate are one mechanism, not two.
5. **Operability** — dashboard FastAPI backend + MCP + cross-run inbox (FR-305/601/602). Tasks: **E-6…E-11** (§9.2) — these four items are one contract plus thin adapters, so E-6/E-7 land before any surface.
6. **Post-P1 roadmap** — MaintenanceWorkflow/DAPER (**E-14**), two worker pools, run budgets (**E-19**), observability export (**E-22, E-23**), brownfield mode, claim-check.
7. **Repo hardening via agents-as-folders** — closes §7's prompts-as-assets drift. Tasks: **E-1, E-2, E-4** (§9.1). *Re-ranked down*: the memoization payoff that justified it was already banked (see §9.1), and the ADR-6 hole it sat next to is closed. Cheapest self-contained item on this list, but now purely reorganisation.

---

## 9. Filesystem-first work items (`E-`) — design input from `vercel/eve`

**Tracked work, not an idea list.** The `[x]`/`[ ]` legend applies here as it does in §§1–7, with one difference: §§1–7 record what *is*, while §9 records what we've *decided to build*. Nothing here is started, so every item is `[ ]` until code says otherwise.

**Scope discipline:** `PRD.md` / `ARCHITECTURE.md` / `SDLC-spec.md` remain the source of truth for *scope*. [`vercel/eve`](https://github.com/vercel/eve) and the [Vercel agent stack](https://vercel.com/blog/agent-stack) supply an *approach*. Every `E-` task therefore anchors to an FR/NFR already open in this tracker — an `E-` task is how we satisfy that requirement, not a new requirement. `E-` items that would add genuine scope are marked **(new scope)** and need a PRD change before they're real.

Eve's thesis is *"the filesystem is the authoring interface"*: an agent is a directory (`instructions.md`, `agent.ts`, `tools/`, `skills/`, `channels/`, `schedules/`), the framework reads and validates that directory, and the filename is the API — nothing registers because the directory **is** the registry. The reported payoff is that an agent change becomes a reviewable file diff, and one agent runs across terminal / HTTP / Slack without rewriting.

### 9.1 Agents-as-folders → §7 "prompts as versioned assets", FR-201, FR-103

Today a role's definition is split: `config/agents.yaml` carries `kind`/`model`/`harness`,
while prompts are inline Python constants hashed into `PROMPT_SHAS`. §7 records this as known
drift.

**The memoization argument for consolidating has been withdrawn.** E-3 was written on the
theory that prompt files would *become* content-addressed memo inputs. They already are:
`content_key` takes a `prompt_sha` and `PROMPT_SHAS` hashes the prompt text, so editing a
prompt already invalidates exactly its stage. Moving that text into `instructions.md` hashes
the same bytes. E-1/E-2 remain justified by §7's prompts-as-assets drift and by E-4's eval
loop — but they are filing, which is what E-3's own note warned against.

The real gap E-3 pointed at was the *model*, not the prompt, and it turned out to sit on top
of an ADR-6 hole. Closed by `docs/superpowers/specs/2026-07-16-registry-drives-every-role-design.md`.

- [x] **E-1** `agents/<role>/` directory loader — `load_registry()` walks a directory
  (`agent.yaml` + `instructions.md` + `agent.py`) instead of parsing one file. ADR-6's
  family-inequality check keeps biting at boot, unchanged: `validate_registry` is re-fed the
  same dict, not re-implemented. Also deleted the `parents[3]` walk, which made the
  containerised worker unbootable (the editable install masked it). Spec:
  `docs/superpowers/specs/2026-07-17-agents-as-folders-design.md`.
- [x] **E-2** Prompts moved to `agents/<role>/instructions.md`; `PROMPT_SHAS` derives from file
  content. Every hash byte-identical, pinned. *Revived not by the memoization argument E-3's
  note made — finding 1 checked that and it was wrong — but because the research role is the
  first role a folder describes rather than decorates, and a folder for it beside eleven YAML
  entries would reopen the two-registry hole.*
- [x] **E-3** ~~Wire prompt-file content into `content_key`~~ — **the prompt half was already wired before the item was written** (`content_key(prompt_sha=...)` + `PROMPT_SHAS`). The *model* half was the real gap: every stage passed one hardcoded `MODEL` constant as `content_key`'s `model_id`, so per-role models would have served stale-model cache hits. Closed together with the ADR-6 hole (§9.1 preamble); `STAGE_MODELS` now resolves each stage's real model.
- [x] **E-4** Prompt eval loop over the `agents/` assets — `sdlc eval <role>` A/B-scores a
  working-tree `instructions.md` against a committed one on a captured fixture, judged by the
  existing cross-family `judge_artifact` + the case rubric; `sdlc eval capture` harvests fixtures
  from a run's history. Stage-isolated and on-demand (an exploration tool). Six pure proposers;
  architect/research refused (carry deps). Closes §7's "with an eval loop" clause. The
  regression-gate half (a committed baseline + a CI check) is a named future increment (OQ-E2).
  Spec: `docs/superpowers/specs/2026-07-18-prompt-eval-loop-design.md`.
- [ ] **E-5** *(speculative — do not schedule)* Factory takes its own `agents/` folders as brownfield input to itself (ADR-7's endpoint). Recorded because it's a pleasing closure of ADR-7, flagged because that's exactly why it deserves suspicion. Needs E-1 and brownfield mode (FR-102) first.
- Research is the first role a folder *describes* rather than decorates
  (instructions + four tools + a provider + a corpus + a budget), which is the
  argument that reopened E-1/E-2 (agents-as-folders finding 6). The memoization
  argument the registry spec's finding 1 killed stays dead — this is not it.

### 9.2 Channels as one abstraction → FR-303, FR-305, FR-601, FR-602, US-1, US-7

We track notifications, cross-run inbox, dashboard backend, and MCP server as four independent unbuilt items. Eve treats them as one primitive wearing four hats: *render the pending decision, deliver it, translate the reply into a signal.* We already own the hard half — FR-302 (idempotent signals, `(gate, round)` identity, first-decision-wins) makes two channels racing the same gate safe by construction.

- [x] **E-6** Channel contract over the FR-302 signal substrate: a structured `pending_decisions()` workflow query (Layer A, `sdlc/pending.py`) feeding a pure `render`/`translate` adapter (Layer B, `sdlc/channels/contract.py`), with `deliver` an opt-in `PushChannel`. All four render variants (clarify / stage gate / task escalation / merge gate) collapse to the two FR-302 signals on reply. Contract only — no new surface; E-7 refits the CLI as the proof. *Layer B landed under `sdlc/channels/` not `interfaces/channels/`: `pyproject` packages only `src/`. Spec: `docs/superpowers/specs/2026-07-18-channel-contract-over-fr302-design.md`.*
- [x] **E-7** Refit the existing CLI (`answer`/`approve`/`reject`) onto the contract.
  *Ordered first deliberately: it validates the contract against a known-good
  surface before any new surface depends on it.* **The contract held; the CLI and
  the query did not.** Three defects fell out: `--round` defaulted to 1, so a
  post-REVISE approve was silently deduped under a success message; `revise` had
  no verb despite `GateOutcome.REVISE` and US-2 marked done; and
  `pending_decisions()` over-reported answered clarify questions because
  `answer_question` never popped `_pending` (an E-6 bug, fixed here before E-8
  could inherit it). Adds `channels/transport.py` — query/match/signal/verify —
  so E-8/E-10/E-11 do not each reimplement it. Spec:
  `docs/superpowers/specs/2026-07-19-cli-refit-onto-channel-contract-design.md`.
- [x] **E-8** Cross-run inbox as a query over pending gates (FR-305, FR-603's missing verb) — the first capability the contract buys that we don't already have. *Landed:* `sdlc/channels/inbox.py` (`fetch_inbox`) plus the CLI inbox verb over the existing Layer A/B contract. Plan `docs/superpowers/plans/2026-07-22-cross-run-inbox.md`.
- [x] **E-9** Notify activity + reminder timer + fallback approver (FR-303). *Landed:* `src/sdlc/notify/` (schedule + routes asset + log/webhook transports + activity), deadline-walking wait in `_gate`, `GATE_NOTIFIED` traced with delivery outcome. `on_timeout` per gate; `merge` holds rather than discarding a green run. Spec `docs/superpowers/specs/2026-07-26-gate-notifications-and-reminder-timers-design.md`, plan `docs/superpowers/plans/2026-07-26-gate-notifications-and-reminder-timers.md`.
- [ ] **E-10** FastAPI dashboard backend as a channel adapter, replacing the Vue frontend's mock API (FR-601, US-6, ADR-8).
- [ ] **E-11** MCP server as a channel adapter — list/detail/inbox/answer/decide/start (FR-602, US-7).

### 9.3 Schedules as files → FR-404, FR-501

FR-404 records that `reflect()` exists and is registered but is **never called**, with no Temporal `Schedule`. We have Schedules natively, so this is small work that starts the SC-4/SC-6 calibration signal accruing — which nothing else currently does. Same mechanism later carries the DAPER timer.

- [x] **E-12** `schedules/*.yaml` assets reconciled into Temporal Schedules via `sdlc schedules apply` (`--dry-run` shows the diff; drift is reported, `--prune` deletes). *Not worker boot as originally written: schedules are server-side mutable state, so a restart must not silently rewrite production scheduling. Spec: `docs/superpowers/specs/2026-07-16-schedules-as-files-and-nightly-reflect-design.md`.*
- [x] **E-13** `schedules/nightly-reflect.yaml` → `ReflectWorkflow` → the existing `reflect()` activity, **project banks only** (FR-404, partial). *Corrected from "invoking the existing `reflect()` activity": Temporal Schedules start workflows, not activities, hence the wrapper. Corrected from "project + org scope": see E-25.*
- [ ] **E-14** DAPER maintenance timer + nudge as a schedule asset (FR-501). Blocked on MaintenanceWorkflow existing at all.
- [ ] **E-25** Nothing retains to `org_bank` — `MemoryConfig` defines it (`models.py:376`) but every `_retain` call site in `feature.py` passes `project_bank`. Cross-project consolidation (`reflect(org)`, SDLC-spec §279) therefore has no writers, and the nightly schedule deliberately omits it. **This, not scheduling, is the remaining blocker on FR-404's org half.** Needs a decision on what belongs in an org bank — likely **(new scope)**.
- [x] **E-27** Cat café monitoring golden case + `qa`/`research` rubric judging. The suite's two cases are both "sized for a single short factory run", so **planner decomposition — the load-bearing variable in real work — is unexercised**. The kata is large enough to require decomposition and small enough to specify completely. Authoring it surfaced that only 3 rubric keys reach the judge (`clarifier`/`architect`/`planner`, `feature.py:773`/`:840`/`:879`): `qa` (`:539`) emits a judgeable artifact that only feeds the deterministic `code` record, and `research` (`:730`) hardcoded `judge="contract"` with no `_judge` call, so **no cell had ever run the stage**. Added `CaseSpec.research_enabled` (default `False`) with a per-case injected `provider: tavily` (registry stays `fake` so CI needs no key), both `_judge` calls, and five rubrics. Spec: `docs/superpowers/specs/2026-07-19-cat-cafe-monitoring-benchmark-design.md`; plan: `docs/superpowers/plans/2026-07-19-cat-cafe-monitoring-benchmark.md`. *Smoke run reached the research stage live (real Tavily+glm) and grounded the exact risk threshold the research rubric targets (>35 bpm at rest), but ends at `rejected:research.grounding` — the fail-closed verifier (`research/verify.py`) requires byte-exact contiguous quotes and glm-5.2 cannot reliably reproduce special chars/tabular data (violations improved 8→3 across two prompt fixes, then plateaued). So live judge scoring of `research`/`qa` records is unit-tested but unproven end-to-end; E-29's closure (fail-and-continue, 2026-07-20) unblocks the run itself — a live re-run is still pending. Two robustness defects surfaced by the run and fixed inline: `read_repo` infinite-retry (see E-28) and the research quoting prompt.*
- [ ] **E-28** Research tool-call activities retry a **deterministic** failure with no attempt cap. E-27's smoke run hung when `read_repo` raised `ValueError` on an out-of-cwd path: the pydantic-ai temporal tool-call wrapper retried it forever (attempt 11+). Fixed the immediate trigger (`read_repo` now returns a refusal string, matching its own missing-file branch), but the underlying hazard remains — **any** research tool that raises a non-transient error loops the whole run. Needs a bounded/`non_retryable` retry policy on `agent__research_agent__toolset__*__call_tool`, or a rule that research tools return errors as strings rather than raise.
- [x] **E-29** Research grounding was unreachable for a mid-tier author
  model (byte-exact quote verification; glm-5.2 plateaued at 3
  violations). **Closed by the 2026-07-20 fail-and-continue decision**
  (`feature.py:987`): a grounding violation now fails the research *stage*
  (recorded `FAIL`, retain + digest skipped) and the run proceeds on the
  idea alone — of the three options this is (c) advisory, implemented as
  fail-and-continue rather than demote-to-inferred. Rubric judging of the
  brief happens only when grounding passes, so a cell's research grade is
  earnable but not guaranteed. The demote-to-inferred + still-judge
  variant was considered for E-34 and deliberately not built
  (`2026-07-23-cat-cafe-tier-a-oracle-design.md` §2). OQ-B3 answered
  accordingly. The verifier itself is unchanged — no loosening.
- [x] **E-26** Make `cfg.roles` genuinely per-project (US-4) without reintroducing drift. `PipelineConfig.roles` is a hardcoded mirror of `agents.yaml`'s harness roles because `PipelineConfig()` is constructed *inside* the workflow (`feature.py:602`), so its default cannot read the file without breaking sandbox purity. The boot mirror-check makes drift fail closed, but it also means a per-project override must resolve at the boundary (`cli.py`, `benchmarks/workflow.py`) and satisfy ADR-6 *per run*, not just at boot. **Nothing populates `cfg.roles` today**, which is the only reason the mirror can be a static assertion.
  *Landed by E-37:* `cfg.roles` is now resolved per run at both boundaries —
  the benchmark cell (per-arm `role_models`) and the CLI (`--role-model`) —
  with per-run ADR-6 enforced via `validate_run_roles`. The static boot
  mirror-check is unchanged; the default `PipelineConfig()` still mirrors the
  harness roles, and overrides are applied at the boundary, not inside the
  sandbox.

### 9.4 `pre_tool` unifies containment with gates → FR-703, NFR-5, FR-301

Eve marks individual tools `needsApproval`. FR-703 wants a `pre_tool` hook and has none. These are the same hook — a denial is a policy decision, an approval request is a gate. Both halves now exist: E-16 denies by rule, E-17 escalates by rule into the FR-301/302 gate. The remaining gap in §9.4 is E-18's network-level tier, which is E-21.

- [x] **E-15** `pre_tool` hook seam in `harness/adapters.py`, called for every harness tool invocation. *Landed (2026-07-24):* a declared `containment` capability per `CodingHarness` + a fail-closed `PreToolUse` hook (`python -m sdlc.harness.hook`); spec `docs/superpowers/specs/2026-07-24-harness-containment-pre-tool-hook-design.md`, plan `docs/superpowers/plans/2026-07-24-harness-containment-pre-tool-hook.md`, ADR-17.
- [x] **E-16** Policy denial path — deny by rule, no human involved (FR-703). *Landed (2026-07-24):* one versioned asset `policy/containment.yaml` + four predicates + `ToolDenial` records on `HarnessRunResult`/`SessionDigest`; verified live against claude 2.1.219.
- [x] **E-17** Approval escalation: a `needsApproval`-class tool call raises a
  gate through existing FR-301/FR-302 machinery rather than a parallel
  mechanism. *Landed (2026-07-25):* `action: escalate` on a containment rule
  → the hook emits claude's `defer` → the run ends with
  `stop_reason: tool_deferred` → the **workflow** owns the durable wait
  (`tool_approval` gate) → the session resumes with a **single-use** grant
  bound to `tool_use_id` + input digest. `defer` is **solo-only**: the hook
  counts sibling `tool_use` blocks via `transcript_path` and denies rather
  than emitting a defer the CLI would discard (a discarded defer would fall
  through to `acceptEdits` and be ALLOWED). Every non-approve path — reject,
  timeout, cap, batched — resumes with a rejecting grant and the task
  continues, so a refusal never throws away a session. Spec
  `docs/superpowers/specs/2026-07-25-tool-approval-escalation-design.md`,
  plan `docs/superpowers/plans/2026-07-25-tool-approval-escalation.md`.
- [ ] ⚠️ **E-18** harness/egress containment — **re-ranked up.** §8 item 4 ranked it fourth on the strength of `pre_tool`; an unpoliced outbound egress (research, FR-703) is a second, independent argument. The research stage fetches arbitrary URLs through a provider with only an env allowlist between it and the worker's network. *Partially landed (2026-07-24, E-15/E-16):* tool-level egress denial (`WebFetch`/`WebSearch`/`Bash` host allowlist) now exists via the hook; network-level egress (a socket opened inside an allowed `Bash` call) remains open and is E-21's OS/container tier.

### 9.5 Sandbox / Connect / Gateway → NFR-5, FR-701, FR-703

Reference designs for gaps already named in §2/§3, not new scope.

- [x] **E-19** Single model egress point yielding run-level token/cost counters (FR-701). Today cost bookkeeping "exists in benchmarks only"; one egress point is how to get run counters without touching every call site. *Prerequisite for the run-budget escalation half of FR-701.* *Folded into E-33:* `_run_role` is the single egress point; run-level counters live in `RunSummary.roles`.
- [ ] **E-20** Short-lived, task-scoped credential injection with an audit trail binding each action to a user (Connect's model) — the "scoped-cred injection absent" gap in NFR-5.
- [ ] **E-21** OS-user / container isolation tier (Sandbox's model) — the missing tier in FR-703.

### 9.6 Observability — the lesson eve teaches by failing → FR-704, NFR-4

Independent reviews of eve converge on observability as its weak point: silent delivery failures with no diagnostic ("no 404, no failed-delivery banner — silence"), debugging by manual diff, dependency drift breaking tool loops mid-execution. That is precisely our unimplemented FR-704. This is outside evidence that the missing piece is what makes such a system painful in production — an argument for ranking FR-704 above "nice to have".

- [x] **E-22** `observability/` module emitting `events.jsonl` (FR-704, NFR-4). *Folded into E-32:* `observability/trace.py` (`RunEvent`) + `observability/export.py::render_events_jsonl` render the in-workflow trace to `events.jsonl`; written by the `export_run_artifacts` activity.
- [x] **E-23** `report.html` export from the event stream (FR-704). *Folded into E-32:* `observability/export.py::render_report_html` renders a self-contained `report.html` from the `RunSummary`.
- [ ] **E-24** Pin harness/adapter versions and assert them at boot — eve's dependency-drift failure mode applies directly to `HARNESSES` (FR-203). *Note (2026-07-24):* version drift confirmed live — `ClaudeCodeHarness.expected_version` pins `2.1.218`; installed is `2.1.220` (E-17 verified `defer` against it). `check_harness_versions` will flag this once it runs.

### 9.7 Suggested ordering

Not a commitment, and deliberately not "by section":

1. **E-12, E-13** — smallest, and the only items that start the SC-4/SC-6 signal (§8 item 3).
2. ~~**E-1 → E-2 → E-3**~~ — landed. E-1/E-2 landed as `agents/<role>/` directories (`feat/agents-as-folders`); E-3 was subsumed by the registry increment (`2026-07-16-registry-drives-every-role`), which already closed the model-half gap.
3. ~~**E-6**~~ landed (`feat/channel-contract`) → ~~**E-7**~~ landed
   (`feat/cli-channel-refit`) → **E-8** — the CLI refit proved the contract;
   E-8 is the first *new* capability it buys.
4. ~~**E-15 → E-17**~~ — landed.
5. **E-22** — before the surfaces in E-9/E-10/E-11 multiply the ways delivery can fail silently.

E-19/E-20/E-21 and E-14 are post-P1. E-5 is not scheduled.

### 9.8 Benchmark & evaluation → SC-1..6, FR-106, FR-404, FR-701, FR-702, FR-704, ADR-15, ADR-16

Design: `docs/BENCHMARK.md`. The factory already has the *pieces* of a
measurement system — the E-27 benchmark harness (golden cases + cross-family
rubric judging), the E-4 prompt eval loop, eval-aware memoization (FR-103/NFR-6),
and cost bookkeeping that "exists in benchmarks only" (§9.5). What it lacks is a
measurement *design*: a held-out grade, metrics per success criterion, and the
wiring that turns SC-1..SC-6 from `—` into numbers. These items build that.
Ranked, as everywhere in §8/§9.7, by which measurement invariant is undercut —
not by effort. Anchors are existing FR/NFR/SC; genuinely new measurement scope
is marked **(new scope)** and needs a PRD line before it is real.

- [x] **E-30 (new scope; ADR-15)** `ToolchainAdapter` + the coverage seam,
  language-agnostic. **This is a pipeline capability, not a benchmark fix** —
  `run_test_suite`/`run_lint`/`security_scan`/`measure_coverage` are stage 11/12
  *production* activities the benchmark merely exercises, and generated projects
  can be Python, TS, Go, Rust, … so the grade cannot be language-agnostic unless
  those stages are. Structurally identical to the harness adapter (ADR-2/3): a
  `TOOLCHAINS` registry beside `HARNESSES`, resolving **by marker file in the
  produced repo** (`pyproject.toml`/`package.json`/`go.mod`/`Cargo.toml` — detect
  what was *built*, not what was intended, matching E-31's anti-cheat stance),
  normalising `build()/test()/lint()/coverage()` into the existing `TestReport`.
  Two format decisions keep the gate untouched and language-agnostic: **(a)
  canonical coverage = Cobertura XML** — `measure_coverage` already reads
  `coverage.xml`, so each adapter only *translates into* it (coverage.py / c8 /
  gocover-cobertura / cargo-llvm-cov), and E-30 adds **no change to the gate
  reader**; **(b) absolute security floor = semgrep → SARIF** — one multi-language
  tool keeps `security_no_critical` (SC-5) a single language-agnostic check
  rather than bandit/gosec/clippy sprawl. E-30 proper delivers: the interface +
  registry + marker detection + canonical formats + **the Python adapter
  end-to-end as the reference** + the artifact crossing the merge into the
  integration worktree where the seam reads (the original FR-106 gap). **Highest-
  leverage item on this list — without it there is no objective, test-based grade
  and every benchmark number rests on rubric-only judging.**
  *Landed:* PRD FR-108 + ADR-15; `src/sdlc/toolchain/` (adapter + Python
  reference + SARIF seam) and the `run_integration_checks` activity close the
  FR-106 gap (coverage.xml now crosses into the integration worktree) and make
  `build_integration_green` a real integration run. Spec
  `docs/superpowers/specs/2026-07-22-toolchain-adapter-coverage-seam-design.md`,
  plan `docs/superpowers/plans/2026-07-22-toolchain-adapter-coverage-seam.md`.
  Go/TS/Rust adapters (E-30a/b/c) remain open; the held-out oracle (E-31) is landed.
- [ ] **E-30a** Go `ToolchainAdapter` — the second adapter (`go test -cover` →
  Cobertura via gocover-cobertura; `go vet`/golangci-lint; semgrep). Incremental,
  same shape as the Python reference; validates the abstraction on a
  non-Python language.
- [ ] **E-30b** TypeScript/JS `ToolchainAdapter` — vitest/jest + c8/nyc →
  Cobertura; eslint; semgrep.
- [ ] **E-30c** Rust `ToolchainAdapter` — cargo-llvm-cov → Cobertura; clippy;
  semgrep. *E-30a/b/c are deliberately sub-numbered: each is the N-th adapter,
  identical in shape, added on demand as the corpus (E-34) needs that language —
  not a fork, exactly like adding a harness. Order by which languages the case
  corpus actually exercises.*
- [x] **E-31 (new scope)** Tier-A held-out oracle in benchmark cases:
  `benchmarks/cases/<case>/oracle/` — a suite + fixtures held out of the
  workflow's context (never in a worktree, prompt, or recall), run against the
  produced code **through the case's `ToolchainAdapter` (E-30)**, graded as
  fraction passing. Each case manifest declares `language:`; the runner
  dispatches to the matching adapter, and **manifest-language vs marker-detected
  language is itself a mismatch signal** (the toolchain analogue of the
  criterion→test traceability gap). Adds the Cursor anti-cheat as a routine
  assertion (oracle-is-held-out check + a diff-coverage "built evenly, not to the
  test" check). Extends E-27, which judges rubrics only. Depends on E-30. The
  factory's own criterion→test discipline (FR-106) makes the author side natural:
  the case ships acceptance criteria + a hidden oracle; the gap between the
  factory's self-proposed mapping and the oracle is itself a signal.
  *Landed:* `BenchmarkScope.ORACLE` + `CaseSpec.language` + the pure grading
  logic + the benchmark-only `grade_oracle` activity
  (`src/sdlc/benchmarks/oracle.py`), invoked by `BenchmarkWorkflow` strictly
  after each child (held out by construction). Ships the fraction-passing grade
  via JUnit XML (`ToolchainAdapter.oracle_test_cmd`) + manifest `language:`
  adapter dispatch + manifest-vs-marker mismatch signal + oracle-is-held-out
  assertion; the "built evenly" overfit check is deferred to **E-31a**. todo-api
  is the Python reference oracle (ASGI `app:app` contract). Spec
  `docs/superpowers/specs/2026-07-23-held-out-oracle-design.md`, plan
  `docs/superpowers/plans/2026-07-23-held-out-oracle.md`.
- [ ] **E-31a** Anti-cheat B: diff-coverage "built evenly, not to the test"
  check. The oracle-is-held-out assertion (E-31) catches the model writing into
  the oracle dir; E-31a closes the second half of the Cursor anti-cheat — that
  produced code wasn't overfit to the visible criterion→test mapping vs the
  hidden oracle. Reuses the E-30 coverage seam; adds a per-file diff-coverage
  gate signal alongside the fraction-passing grade.
- [x] **E-32** Retro stage 14: emit `RunSummary`, call the already-registered
  `reflect()`, export trace + metrics (§1 stage 14; FR-404; NFR-4; SDLC-spec
  §1/§6). Closes the learning loop. **Three payoffs from one stage:** unblocks
  SC-4/SC-6 (P3's exit), turns on the memory benchmark axis (on/off delta,
  §9.8 economics), and opens the loop-B intake where production runs become
  eval cases. The `org_bank`-writer half stays **E-25** (needs the "what
  belongs in an org bank" decision); E-32 is the stage itself, project scope.
  *Landed:* spec `docs/superpowers/specs/2026-07-22-retro-stage-run-summary-design.md`,
  plan `docs/superpowers/plans/2026-07-22-retro-stage-run-summary.md`. E-22/E-23
  (events.jsonl + report.html) folded in here.
- [x] **E-33** Per-role cost attribution: promote cost from benchmarks-only
  (§9.5) to run-level counters (folds **E-19**) and attribute **dollars per
  role**, not per token (FR-701). The Cursor economics result restated for this
  registry: the expensive roles are the deciding proposers (architect on
  `opus-4-8`), the volume is in the executing harness roles — so per-role $ is
  the number that moves ($1,339 vs $10,565 on the same task, in their run).
  `HarnessRunResult` already carries the token/context/`compacted` fields; this
  is the aggregation + the proposer-side TemporalAgent usage join.
  *Landed:* single workflow egress (`_run_role`) + `MODEL_USAGE` events + `price_usage` activity (genai-prices, replay-safe) + `RunSummary.roles` rollup + report.html role table + proposer CostBag fill, **and FR-701's run-level budget gate** (`run_budget_usd`, hard gate via FR-301/302, approve = one more increment, reject = `rejected:budget` with retro intact). Research provider spend stays stage-scoped. Spec `docs/superpowers/specs/2026-07-23-per-role-cost-attribution-design.md`, plan `docs/superpowers/plans/2026-07-23-per-role-cost-attribution.md`.
- [x] **E-34 (new scope)** A decomposition-forcing benchmark case. *Landed
  via cat-café (E-27), not a new case* — the "both current cases" text
  predated E-27 landing the kata; the real gap was that the decomposition
  case had no objective grade. Cat-café now freezes an interface contract
  (ASGI `app:app`, `/telemetry` injection, `/floorplan`, `/cats`) and
  ships a held-out `oracle/` graded through the E-31 machinery
  (`language: python`). Assertions are unambiguous extremes crafted
  against the app's **own** floorplan, so the kata's "rules are up to you"
  freedom is intact. Oracle validated in CI against a reference
  implementation (`tests/fixtures/cat_cafe_ref/`): green on the reference,
  red when risk detection is stubbed out. Spec
  `docs/superpowers/specs/2026-07-23-cat-cafe-tier-a-oracle-design.md`,
  plan `docs/superpowers/plans/2026-07-23-cat-cafe-tier-a-oracle.md`.
- [x] **E-35** `cursor` harness adapter — third point on the harness axis,
  normalised into `HarnessRunResult` (tokens, cost, `context_window`,
  `compacted`, resume handle) and version-pinned at boot (FR-203; folds the
  intent of **E-24**). Value is not "cursor vs claude in the abstract" — it is
  measuring `claude -p` vs `opencode` vs `cursor` **through the
  DeterministicQualityGate on the held-out oracles**, a comparison no external
  leaderboard provides. Ordered *after* E-33 so the economics fields exist to
  receive it; until the adapter fills them, cursor cells are quality-only.
  *Landed:* `CursorHarness` + `check_harness_versions` in
  `harness/adapters.py`, registered in `worker.py`. Plan
  `docs/superpowers/plans/2026-07-23-cursor-harness-adapter.md`.
- [x] **E-36 (new scope)** Error heatmap (`case × stage`) + rubric-calibration
  tracking. The heatmap aggregates gate rejections, fix-loop iterations, and
  oracle failures per stage per case (FR-704 export is the data source, NFR-4) —
  Abdullin's prioritisation instrument, answering "which stage on which case
  class costs most, so what do I fix next." Calibration tracking attaches a
  judge-agreement rate to every rubric score (hand-score 20–30 fixtures per
  rubric) so a Tier-B number is never read without its trust level.
  *Landed:* `src/sdlc/benchmarks/heatmap.py` (case x stage rework-density
  grid) written by `finalize_benchmark_report` as `heatmap.{html,json}`;
  `src/sdlc/benchmarks/calibration.py` + `sdlc calibrate <rubric>` report
  within-epsilon agreement + MAE + Spearman over human-scored fixtures,
  surfaced as a trust level beside every rubric score (PRD FR-110). Session-
  derived waste (E-38) as a heatmap input **landed 2026-08-03** via
  `WasteBag` on `BenchmarkRecord` + `benchmarks/waste_matrix.py` (task x arm,
  six metrics); calibration-as-CI-gate (OQ-B4) still deferred. Spec
  `docs/superpowers/specs/2026-08-03-completing-the-measurement-instrument-design.md`,
  plan `docs/superpowers/plans/2026-08-03-completing-the-measurement-instrument.md`. Spec
  `docs/superpowers/specs/2026-07-24-error-heatmap-and-rubric-calibration-design.md`,
  plan `docs/superpowers/plans/2026-07-24-error-heatmap-and-rubric-calibration.md`.
- [x] **E-37** Per-role model sweep at the benchmark boundary. Resolve
  `cfg.roles` per cell (folds **E-26**) so each cell overrides role→model and
  satisfies ADR-6 *per run*, not just at boot — the full model×role matrix
  (US-4). Deferred last: the harness (E-35) and memory (E-32) axes deliver most
  of the insight without it, and E-26 is real work. Ties to **OQ-B2** (the
  judge family must move per cell to stay ADR-6-independent of the swept
  producer family) and **OQ-E2**.
  *Landed:* per-run `resolve_role_model` (proposers + memo key) + shared
  `check_adr6_families`/`validate_run_roles` + named `Arm`s on `CaseSpec`
  (harness `models` desugared for back-compat) + fixed-judge-validated-at-
  expansion (answers OQ-B2) + `--role-model` CLI surface (folds E-26, US-4).
  Spec `docs/superpowers/specs/2026-07-24-per-role-model-sweep-design.md`,
  plan `docs/superpowers/plans/2026-07-24-per-role-model-sweep.md`.

- [x] **E-38 (new scope; ADR-16)** Capture-always harness sessions. Every
  harness run emits a **canonical `HarnessSession`** (normalised transcript:
  tool-calls, file reads/writes, commands + exit status, model turns) as a
  claim-checked `ArtifactRef{kind: harness_session}` on `HarnessRunResult`
  (ADR-3/§4). **Because it is captured on every run, three things are hot-path
  invariants, not options:** (a) claim-check is unconditional — the transcript
  is megabytes and never touches workflow state, which is the second, independent
  reason to finally close **FR-702** (diffs *and* sessions both force it); (b)
  the memory scrub (`pre_retain`) runs over the session **before** it is stored,
  **fail-closed like the SC-5 security floor** — an injected credential in a
  transcript stored by default is a leak by default; (c) retention follows a
  **decided policy**: full transcript on fail / benchmark / any run with >0
  fix-loop attempts (the diagnostic cases), a structured **`SessionDigest`**
  on clean-green (first-pass green) runs — never a blind byte-truncation. The
  §4.3 waste aggregates and a decision-skeleton are computed **pre-truncation**
  in the scrub activity and always kept, so the heatmap sees waste on green
  runs too and P5 harvesting keeps successful-trajectory shape. Ordering is
  strict — capture → scrub (fail-closed) → *then* branch full-vs-digest — so a
  scrub failure stores nothing regardless of outcome. Full-transcript TTL is
  the one open sub-point (OQ-B7). Normalising the transcript is the **harness adapter's** job,
  beside the resume-handle it already owns (`claude --resume` / `opencode -s`) —
  same registry, same pattern as `HarnessRunResult` and `ToolchainAdapter`.
  **This is the concrete P5 trajectory-harvesting seam** (ARCHITECTURE §10): the
  session is most of what `events.jsonl`/`report.html` should render (**E-22/E-23**)
  and the extraction point for trajectory eval + small-model distillation.
  *Invariant it must preserve:* capturing the developer's session does **not**
  let the default reviewer read it — see E-39.
  *Landed:* `HarnessSession`/`SessionDigest` + per-adapter normalisers
  (claude via `--output-format stream-json --verbose`; opencode from its
  event stream), `ArtifactStore` seam with `file://` backend
  (`src/sdlc/artifacts/`), fail-closed capture in `run_coding_task`,
  retro-time OQ-B7 retention, env-gated Logfire slice. PRD line: FR-109.
  Diff claim-check (FR-702 proper) and report rendering deliberately not
  here; TTL still open. Spec
  `docs/superpowers/specs/2026-07-23-capture-always-harness-sessions-design.md`,
  plan `docs/superpowers/plans/2026-07-23-capture-always-harness-sessions.md`.
- [x] **E-39 (new scope)** `deep_review` — an optional, opt-in review tier that
  reads the scrubbed `HarnessSession` (E-38) as **data**. This is Cursor's
  full-transcript lens, and it deliberately does what the default reviewer must
  not: see *how* the diff was reached (backtracking, oracle peeking, hardcoded
  answers), feeding both the anti-cheat check (§2/§4.4) and a richer verdict.
  **Three guardrails, all load-bearing:** it reads the **scrubbed** artifact,
  never the raw session and never via resume-handle (else it drags authoring
  context + secrets back in); its model stays **ADR-6 family-independent** of the
  developer (else the lens correlates with authoring); and it is an **additional**
  lens, not a replacement — the clean-context `review` (ADR-6/ADR-12) remains the
  default, because Cursor's value is *decorrelated lenses stacking*, not swapping
  one for another. Requires the ADR-6 boundary to be restated precisely (E-38's
  ADR-16 note does this): *default review starts clean and never resumes the
  developer's session; `deep_review` reads the scrubbed session as data.*
  *Landed:* `DeepReviewReport`/`IntegrityFlag` + optional `agents/deep_review/`
  role (ADR-6 family clause vs `dev`) + `load_session` claim-check read +
  advisory `_run_deep_review` in `_dev_task` (once per task, records a
  `deep_review` stage record for the E-36 heatmap, retains integrity flags,
  never gates). Off by default (`deep_review_enabled`). PRD line: FR-111.
  Deferred follow-ons: a blocking/harness-based deep-review tier and
  report.html rendering of the verdict. Spec
  `docs/superpowers/specs/2026-07-24-deep-review-transcript-lens-design.md`,
  plan `docs/superpowers/plans/2026-07-24-deep-review-transcript-lens.md`.
**Open questions (tracked in `docs/BENCHMARK.md §7`):** OQ-B1 minimum trustworthy
corpus size; OQ-B2 judge independence under model sweep **answered** (E-37: judge fixed per case, family validated at expansion against every arm); OQ-B3 **answered** (E-29 closed: grounding failure = recorded stage `FAIL`, run continues); OQ-B4 the regression-gate half of E-4 as a CI gate (→ OQ-E2); OQ-B7
session-retention policy **decided** (full on fail/benchmark/attempts>0,
`SessionDigest` on clean-green, aggregates kept pre-truncation, scrub
fail-closed before the branch — E-38); **only the full-transcript TTL is
still open**; OQ-B5 when an external eval platform (Braintrust, ARCHITECTURE §10) earns its keep.

**Suggested ordering within §9.8:** E-30 (interface + **Python reference**, the
grade) ✓ → E-31 (held-out oracle on that one language) ✓ → E-32 (the loop, also
unblocks P3) → **E-38 (capture-always sessions — observability + anti-cheat
foundation, feeds E-22/E-23/P5) ✓** → E-33 ✓ + E-34 (economics + the
decomposition case) → E-30a/b/c (add languages as the corpus needs them) →
E-35 (the cursor point) → E-36 (heatmap + calibration, sliceable by
language) → E-39 (deep-review lens, reads the session) → E-37 (per-role
sweep). E-38 is ranked high on purpose: it is the observability substrate
every later analysis (heatmap, anti-cheat, harvesting) reads from.
**Deliberate:** the pipeline goes multi-language *incrementally* — E-30 proves
one language end-to-end so the first SC signal isn't blocked on N adapters;
E-30a/b/c follow the corpus, not precede it. E-30/E-32 unblock the most: the
first gives an objective grade, the second closes P3 and three capabilities.

---

## 10. Tier 0 — repository triage & tidy-up (`E-40`…`E-44`) → FR-900, FR-102, FR-108, NG5

**Why a separate tier.** The EDCR methodology (§11) is enterprise-brownfield
machinery: its blueprints are BIAN, TM Forum, ACORD, HL7, ARTS, APQC, and its
worked example is Java/Maven/Jenkins/JaCoCo. It decomposes a system that *has*
structure. A vibe-coded repository has none — it may not build, has no tests, has
`.env` committed and the service key in the client bundle, and half its files are
untouched generator scaffolding. Point EDCR at it and file→capability coverage
has nothing to map to, every QA composite degenerates to `unknown`, and you pay
for per-capability STRIDE reasoning about a structure that does not exist.

Tier 0 answers the question that actually comes first — *what state is this repo
in?* — deterministically and cheaply, and **gates** Tier 2 on the answer
(FR-903). It is also the tier whose findings are mostly *mechanically* fixable,
which makes it the shortest path to a demonstrable assess → fix → prove loop.

- [ ] ⚠️ **E-40 — `Measurement` type + `RepoTriage` contracts** → FR-915, FR-901.
  *`Measurement` landed (2026-08-06)*: `src/sdlc/measurement.py`, retrofitted
  onto `CoverageReport`, `SecurityReport` and `claim_survival_score`, with
  `QAReport.coverage_pct` deleted as a second registry for a measured fact.
  The roadmap's original framing of the defect was stale — the merge gate
  reads `CoverageReport` (which E-30 had already given a `measured` flag), and
  the live conflation worth fixing was on the **absolute** floor:
  `report_from_sarif` returned `critical=0` for a malformed document. That is
  now `not_collected`, and `security_no_critical` split into
  `security_scan_collected` + `security_no_critical` so an unmeasurable floor
  cannot be silently satisfied. **`RepoTriage` landed with E-41** (2026-08-06),
  where the signals that populate it are designed. FR-915's triage half is
  therefore closed.
- [ ] ⚠️ **E-41 — deterministic hygiene signals** → FR-902, FR-108.
  *Contracts + seam + three signals landed (2026-08-06):* `src/sdlc/triage/`
  ships `RepoTriage`/`TriageFinding`/`Readiness` (closing the half **E-40**
  deferred here), a one-activity-per-signal seam, and **build probe**,
  **secret scan** (including client-bundle-reachable credentials) and
  **baseline practice**. Readiness is three-valued: any dimension that is not
  MEASURED forces `INDETERMINATE`, so an unmeasured repository can never read
  as ready for the FR-903 gate. The build probe **executes the triaged
  repository's own code** in a throwaway clone at the pinned commit — an
  operator-authorization trust boundary, not a solved one (see NFR-9; removed
  by E-57/E-21). Remaining four families are **E-41a–d**. Spec
  `docs/superpowers/specs/2026-08-06-repository-triage-hygiene-signals-design.md`,
  plan `docs/superpowers/plans/2026-08-06-repository-triage-hygiene-signals.md`.
- [ ] **E-41a** dependency health — unpinned / known-vulnerable / unused /
  duplicated, behind the FR-108 adapter.
- [ ] **E-41b** dead and generator-scaffold code. Also sharpens
  `structure_discernible`, which E-41 ships as a deliberate floor (a repository
  that is entirely untouched scaffolding currently passes it).
- [ ] **E-41c** framework-default misconfiguration — unauthenticated routes,
  permissive CORS, world-readable storage.
- [ ] **E-41d** size and duplication outliers.
- [ ] **E-42 — `TriageWorkflow` + readiness verdict + readiness gate** → FR-901,
  FR-903. Readiness (buildable / runnable / tests present / structure
  discernible) computed from deterministic signals **only**, so triage completes
  on a repository where an LLM would have nothing to reason about. An
  unbuildable repo is a finding, not an error. The gate resolves through the
  FR-301/302 machinery, so an operator can override with an audited decision.
- [x] **E-43 — grounding verifier** → FR-914, shares FR-107's implementation.
  *Landed (2026-08-06):* `src/sdlc/grounding.py` owns the one substring
  invariant with **two normalization profiles** — `EXTRACTED_TEXT` (research's
  two documented Tavily loosenings) and `VERBATIM_BYTES` (code and
  transcripts, where `**` and quote glyphs are meaningful). Sharing the
  implementation without sharing the profile is the load-bearing decision.
  Three byte-sources: fetched pages (research, unchanged semantics), stored
  sessions (**two live holes closed** — `HandoffClaim.evidence` and
  `IntegrityFlag.evidence` were model-asserted and unverified), and
  `read_committed_bytes` for `path@sha` (tested, registered, no caller until
  E-41). Also closed a live hole in the shipped research check: an empty quote
  grounded trivially, since `"" in haystack` is True. FR-914 stays open until
  an assessment stage consumes the commit source. **OQ-7 untouched.**
- [ ] **E-44 — tidy-up fix runs + re-triage** → FR-904, NG5.
  `mechanically_fixable` findings become brownfield `FeatureWorkflow` child runs
  (one PR per accepted item, never a direct patch), then triage re-runs and the
  before/after delta is recorded. This is the first end-to-end proof of the
  assess → fix → prove loop, on the cheapest and lowest-risk class of fix.

## 11. Tier 2 — the EDCR port (`E-45`…`E-56`) → FR-910

**What the port is actually for.** BrownKit's methodology is sound and its
artifact set is well specified; what it cannot do is *enforce itself*. `/gate`
writes no files and explicitly permits continuation when `/assess` never ran.
`/finish`'s 14 acceptance criteria are graded by the same model that produced the
artifacts being graded. `*Source: ...*` cross-references are audited by an LLM
asked to check its own citations. Ported here, each of those becomes a
`CheckResult` computed by pure code from typed artifacts, with the
absolute/advisory split of FR-106 — which is the entire reason to do this inside
the factory rather than as prompts.

- [ ] **E-45 — `AssessmentWorkflow` EDCR DAG shell** → FR-911.
  init → scan → discover → assess → **report** → generate → finish.
  Two deliberate deviations from the source methodology: **(a)** `report` runs
  *after* `assess` — the methodology numbers report 4th and assess 5th, but
  reports render risk scores only `assess` produces, and `/finish` requires all
  five reports complete; **(b)** `workflow.json` is **not ported** — its
  `phases[].status/started_at/completed_at/artifacts` is a hand-rolled durable
  state machine, which is exactly what Temporal history already is.
  `/enrich`, `/gate` and `/validate` are not stages (→ E-56, E-50, E-53).
- [ ] **E-46 — scan phase** → FR-912. S1–S5 capability signals, SS1–SS4
  security, QS1–QS4 QA. Cross-source confidence: three or more independent
  sources = high, two = medium, one = low — never the depth of one source. Memo
  key `(repository tree hash, signal version)` per FR-103, so re-assessing an
  unchanged repo is a cache hit and editing one signal's logic invalidates
  exactly that signal.
- [ ] **E-47 — `CapabilityMap`** → FR-913, **FR-102**. L1 with content-derived
  stable `BC-NNN`, L2 operations, entity ownership (exactly one owner or a
  surfaced conflict), file→capability coverage floor (default 0.90), orphans
  classified attached | infrastructure | dead. **This is where the assessment
  product and the core pipeline converge**: it satisfies FR-102's `CodebaseMap`,
  so building it for the audit also unblocks P2 brownfield feature runs.
  **Blocked on OQ-6** — a content key over file paths breaks when files move, one
  over entity names breaks on rename, and until that is settled "stable
  identifiers" is aspiration and every cross-reference in the bundle is fragile.
- [ ] **E-48 — discover proposers** → FR-913. D1 cohesion/coupling/boundary
  clarity; D2 action per candidate (`CONFIRM | SPLIT | MERGE | DE-SCOPE |
  FLAG`); D3 coverage verification with orphan disposition; D4 lock; D5 L2
  decomposition with entity ownership (`OWNS / CREATES / MANAGES / TRACKS /
  READS`); D6 security context; D6a QA context using E-40's `not_collected`;
  D7 consolidated domain model; D8 industry-blueprint comparison where `MISSING`
  is context, not failure. Guardrail worth porting verbatim: *delivery channels
  and deployment boundaries are not capabilities*.
- [ ] **E-49 — `UnifiedRiskMap` + risk proposers** → FR-916. Conforms to the
  `unified-risk-map` v1.0 schema: composite in [0,1] or an `unknown`/`partial`
  sentinel; drivers `minItems: 1, maxItems: 3` with a real minimum length, so a
  generic label cannot pass as a driver. STRIDE per capability with explicit
  rationale for inapplicable categories; vulnerabilities `confirmed | probable |
  potential`; five control families; cross-capability shared vulnerabilities,
  cascading failures, weak trust boundaries, privilege-escalation chains.
- [ ] **E-50 — assessment gate checks** → FR-917, FR-106, FR-304.
  BLOCK on a confirmed unaccepted vulnerability, a testability blocker in a
  high-criticality capability, or composite ≥ 0.8; WARN 0.6–0.79; else PASS.
  False-positive dispositions (`false_positive | mitigated_elsewhere |
  accepted_risk`) become audited overrides that persist across re-runs.
- [ ] **E-51 — acceptance criteria as code** → FR-918. The 14 terminal criteria
  and every per-phase exit criterion as `CheckResult`s computed from typed
  artifacts. Cross-reference integrity — every capability, threat, vulnerability
  and testability id cited anywhere resolves to a real record — is an
  **absolute** check, because a bundle with a dangling reference is not a
  weaker audit, it is an unverifiable one.
- [ ] **E-52 — role reports + evidence bundle** → FR-921, FR-704.
  Architect / developer / SDET / security / stakeholder reports plus a
  machine-readable manifest, every finding carrying its verification status, all
  gate results with overrides, and the `HarnessSession` transcripts of fix runs.
  Folds into the FR-704 export rather than opening a second reporting path.
- [ ] **E-53 — spec seeds → brownfield child runs** → FR-919, NG5.
  Capability-scoped seeds naming only files that exist; each accepted seed starts
  a brownfield `FeatureWorkflow` child. `/validate`'s criteria (D1–D4 boundary
  and ownership, A1–A3 vulnerability regression / control presence / data
  sensitivity, G1–G3 coverage / testability seams / non-functional constraints)
  become that run's acceptance criteria, so **the fix is graded against the
  assessment that motivated it**. This is the join BrownKit cannot close on its
  own, and it is the product's central claim.
- [ ] **E-54 — re-assessment + per-capability delta** → FR-920. Incremental
  re-scan of capabilities whose files changed; composite delta as a first-class
  artifact. Feeds SC-9.
- [ ] **E-55 — per-phase assessment budgets** → FR-922, FR-701. Assessment input
  size is the customer's choice, not the factory's — the only stage family where
  that is true. Exhaustion escalates; partial results are marked partial.
- [ ] **E-56 — `/enrich` as a declared stage input** → FR-911, FR-402 pattern.
  The capability slice (structure, entity contracts, blast radius, QA
  constraints, threats, external dependencies) as a hashed declared input to a
  brownfield feature run — not a command, and not something an agent fetches
  ad hoc.

## 12. Service platform (`E-57`…`E-63`) → FR-1000, NFR-8, NFR-9

**E-57 and E-58 are preconditions for admitting an external tenant, not
hardening.** Everything in §§10–11 can be delivered by an operator on
repositories they are authorised to run; none of it can be offered self-serve
until these land.

- [ ] **E-57 — untrusted-input threat model + adversarial tests** → FR-1002,
  NFR-9; extends **E-21**. E-21 covers the container / restricted-OS-user tier;
  E-57 is the threat model and the tests that prove it — a repository whose test
  suite exfiltrates the environment, whose build script writes outside the
  worktree, whose `postinstall` opens a socket. FR-703's own note concedes the
  gap: egress enforcement is tool-level, so *"a socket opened from inside an
  allowed `Bash` call is not visible to it"*. Running a stranger's
  `npm install` today is arbitrary code execution as the worker user with the
  worker's toolchain and unrestricted network.
- [ ] **E-58 — tenancy by construction** → FR-1001, NFR-8; **resolves OQ-4**.
  Temporal namespace + artifact-store prefix + memory-bank namespace per tenant,
  with an adversarial test that attempts a cross-tenant artifact read and a
  cross-tenant recall. Memory is the sharpest edge: cross-run learning is the
  factory's differentiator and, without a tenant boundary, its first
  data-breach path — client A's gotchas recalled into client B's run.
- [ ] **E-59 — repository connection** → FR-1003, FR-703. VCS app install per
  tenant; short-TTL, repo-scoped tokens minted per run and never persisted
  (FR-703 specifies these and nothing implements them); PR-only delivery;
  webhooks for commit and PR events.
- [ ] **E-60 — identity & authorization** → FR-1004; closes FR-304's gap.
  Authenticated principals on every surface and a real principal recorded in
  every `GateDecision`. FR-304 already records *who approved what* — there is
  simply no principal to record, which is fine for one operator at a CLI and
  void as an audit trail you hand to a client.
- [ ] **E-61 — metered per-tenant cost** → FR-1005, FR-701. The FR-701 counters
  already aggregate harness JSON cost and model usage per run; this attributes
  and exports them per tenant with enforceable ceilings.
- [ ] **E-62 — on-prem packaging + configurable model provider** → FR-1006,
  NFR-7. One artifact, single-tenant on-prem or multi-tenant hosted; the
  customer may supply their own model credentials or gateway.
- [ ] **E-63 — retention & audited purge** → FR-1007. Per-tenant retention for
  evidence, transcripts and memory; a deletion request purges artifacts, banks
  and transcripts, and the purge itself is audited.

## 13. Product outcome (`E-64`…`E-71`) → FR-1100

**The framing.** The factory measures *itself* very well — SC-1..6, the
benchmark matrix, rubric calibration (FR-110), capture-always transcripts
(FR-109). It measures **the product it ships: nothing**. FR-1100 closes that,
and the reason it is tractable rather than a second company is NG7: hosting,
feature flagging and analytics are *adapters over what the customer already
runs*, following FR-108's pattern. What remains is squarely this codebase's
competence — a frozen contract, a traceability check, a durable timer, and a gate.

- [ ] **E-64 — `Hypothesis` contracts + intake gate** → FR-1101. Metric,
  expected direction, minimum effect worth shipping, decision rule, kill
  condition, observation window — gated before any code is written.
- [ ] **E-65 — pre-registration freeze** → FR-1102. The decision rule is frozen
  and hashed at approval, reusing `ValidationContract.frozen` semantics
  (FR-803). A post-hoc change is a new audited gate round with both versions
  retained. **This is the differentiating mechanic**: the owner commits to how
  they will decide before they see the data, and the factory is what makes that
  commitment structural rather than cultural.
- [ ] **E-66 — metric traceability** → FR-1103, FR-106. Every hypothesis metric
  must trace to ≥1 instrumentation task and ≥1 emitted event, enforced by the
  same deterministic mechanism as criterion→test traceability. An
  uninstrumented hypothesis cannot reach deploy — which is the single most
  common way a "measured" feature ships unmeasurable.
- [x] **E-67 — `DeployPlan` / `DeployReport`** → FR-1104. Environment, flag and
  cohort, rollback, smoke-tested deployment vs. PR merge. **Closes DAG stage 13
  for all runs**, not only experiments: previously the stage was a single
  hardcoded `make deploy` shell-out with no plan/report split. Delivered on
  `feat/deploy-contract`; spec `docs/superpowers/specs/2026-08-06-deploy-contract-design.md`.
- [x] **E-68 — deployment target adapters** → FR-1105, NG7. Resolved from
  config, one reference adapter, no hosting substrate of our own. Delivered on `feat/deploy-contract` (`src/sdlc/deploy/adapters.py`, compose + script).
- [ ] **E-69 — analytics source adapters** → FR-1105, NG7. One reference
  adapter. See **OQ-9**: the factory would read a metric from a
  customer-controlled source to decide keep/kill, which is FR-914's grounding
  problem inside a system we do not control and currently has no good answer.
- [ ] **E-70 — durable observation + verdict gate** → FR-1106, FR-1108. A
  Temporal timer spans the observation window — the one thing Temporal is
  uniquely suited to here, since a 14-day wait is exactly what NFR-1 already
  guarantees. On expiry: collect, evaluate the pre-registered rule, open a
  keep / kill / extend gate. Insufficient data yields `inconclusive`, never a
  favourable read (FR-915 applied to product metrics).
- [ ] **E-71 — PoC mode** → FR-1107. Bounded budget, explicitly disposable
  output, preview deployment, recorded decision, and marked so it never silently
  accrues as production debt.

## 14. Pipeline as data — graph interpreter + canvas (`E-72`…`E-77`) → FR-1200

**The framing.** The 15-stage DAG is not data — it is imperative Python.
`feature.py::_pipeline` (line 1625, in a 2,329-line file) hardcodes stage order,
the typed handoffs between stages, the fix loops, the gate awaits and the signal
handling. Every pipeline shape the factory can run is a shape someone wrote by
hand. FR-1200 makes the pipeline a user-authored `PipelineGraph` executed by a
generic interpreter, with a canvas to edit it — n8n's model, applied to the SDLC
DAG.

**Decided 2026-08-06** (brainstorm, no spec written): ports carry control flow
(n8n-style branching, not a strict DAG of composite nodes), and the interpreter
**replaces** `_pipeline` big-bang rather than running beside it. Three objections
were raised and answered rather than dismissed:

- (a) **Temporal determinism.** The graph is workflow *input*, pinned for the
  run's lifetime. A canvas edit never mutates a running workflow — it writes a
  new `content_sha` that the next run picks up. No per-edit `workflow.patched()`.
- (b) **Typed contracts.** Ports declare payload types by existing model name
  (`ArchitectureSpec`, `ImplementationPlan`, `TaskResult`…); edge validation
  rejects incompatible connections. Freedom is real but type-bounded.
- (c) **The benchmark axis.** Node types declare a `canonical_stage`, mapping any
  graph onto the fixed `CANONICAL_STAGES` list (`benchmarks/heatmap.py:24`), so
  the heatmap and SC rollups survive arbitrary graphs. Unmapped types record as
  `unknown`, which `heatmap.py:96` already handles.

**Cheaper than it looks.** The node handlers already exist as methods —
`_run_clarify` (:1836), `_run_architect` (:1900), `_fan_out_research` (:803),
`_dev_task` (:1218), `_gate` (:1105), `_run_deep_review` (:876), `_run_adversary`
(:942), `_run_handoff` (:994), `_merge_task` (:1193), `_retro` (:1559). The work
is replacing the *wiring*, not the stage bodies. `_revisable_stage` (:1166)
disappears entirely: wrapping a stage in a gate-and-retry loop becomes topology.

**The quiet win.** Four boolean flags (`research_enabled`, `deep_review_enabled`,
`adversarial_review_enabled`, `handoff_enabled`) and their scattered
`if cfg.X_enabled and t_X is not None` guards collapse into *is there a node*.

- [ ] **E-72 — `PipelineGraph` model + node-type registry** → FR-1201.
  `GraphNode` / `GraphEdge` / `NodePort` in `sdlc/graph/model.py`; nodes carry
  `RoleConfig` (`models.py:717`) and `GateConfig` (`models.py:53`) **verbatim**
  rather than a forked `params["model"]` string, so the registry loader's
  validation, the ADR-6 model-inequality checks and `PROMPT_SHAS` memo
  invalidation keep working unchanged. `content_sha()` excludes `position` and
  `label` so tidying the canvas never invalidates a memo. Registry declares each
  node type's ports, payload types and `canonical_stage`.
- [ ] **E-73 — `GraphRouter` + `validate.py`** → FR-1202. **The bug budget lives
  here.** A pure, synchronous routing state machine — no Temporal, no I/O — so
  the hard part is table-testable in milliseconds. Owns: one-output-port-per-
  activation branching; **round-based stale-input invalidation** (a backward edge
  increments `round` and invalidates buffered inputs at lower rounds, or a revise
  loop re-runs `architect` while `planner` still holds last round's spec);
  per-edge `max_traversals` with exhaustion terminating `ESCALATED` (reproducing
  `feature.py:1464`); fan-out/collect. Rounds are not new — `gate_key(gate,
  round)` (`models.py`) already carries this semantics for gates; the router
  generalises it to the whole graph. `validate.py` is the **single** source of
  truth for legality (port compatibility, reachability, every cycle bounded,
  one entry node) and is never reimplemented in TypeScript.
- [ ] **E-74 — `GraphWorkflow` replaces `_pipeline`** → FR-1203. Thin Temporal
  layer over E-73: dispatch table from `node.type` to the existing handlers,
  which converge on `(Activation, PipelineConfig) -> Emission`; exceptions become
  `fail` emissions so error routing is topology. `PipelineConfig` splits by scope
  — run-scoped settings stay, per-stage settings move onto nodes,
  `max_fix_attempts` becomes `GraphEdge.max_traversals`. Determinism rules
  (sorted iteration, no bare `set`/`dict` walks, fixed-order `gather`) enforced
  by a lint test, since the router is new code where they break silently.
  `default.graph.yaml` expresses today's pipeline and is asserted to reproduce
  its stage sequence. **Big-bang was chosen over strangler-with-parity** — run
  the benchmark before/after anyway as a regression check; the choice was to not
  *gate* on dual-running, not to discard free evidence.
- [ ] **E-75 — dashboard backend** → FR-1204. **Closes the "dashboard backend
  remains" half of P2.** There is no backend today: `api/http.ts:4` rejects every
  call with *"Dashboard http provider not wired"* and the whole dashboard runs on
  `api/mock`. Thinner than it looks — live run state needs no database, only two
  new queries on `GraphWorkflow` (`graph_state()`, `graph()`) beside the existing
  `status` / `pending_decisions` / `run_summary` (`feature.py:739`–:753). The only
  storage is content-addressed `graphs/<sha>.yaml`. Gates and answers are the
  existing signals. **This is the project's first network surface** — see OQ-11.
- [ ] **E-76 — canvas** → FR-1205. `@vue-flow/core` (React Flow's Vue port, what
  n8n itself uses; fits the existing Vue 3 + Pinia + Vite stack) plus `dagre` for
  auto-layout of YAML-authored graphs. **One renderer, two modes**: `runState`
  present ⇒ status rings, cost, durations, traversal counters on loop edges, live
  gate approve/reject; `editable` ⇒ palette + inspector. Editing a *running*
  graph is disabled by design (see (a) above). Backward edges render curved with
  a `2/3` counter, so a post-mortem shows **why** a run looped, not merely that it
  did. `Run.stageIdx` (`api/types.ts:20`) is a linear index that cannot express
  graph position and becomes `currentNodes: string[]`; `StageDots.vue` survives by
  mapping active nodes through `canonical_stage` back onto the fixed 15-stage
  strip, so the fleet table keeps its glanceable row and cannot disagree with the
  benchmark.
- [ ] **E-77 — graph store + custom-graph benchmark mapping** → FR-1206. Runs
  record their `graph_sha`, so a post-mortem always renders the graph that
  *actually ran* rather than what the graph looks like now. Benchmark records
  derive `fix_attempts` from inbound-fail-edge traversal counts and `round` from
  the router, keeping the §9 measurement axes intact across hand-authored graphs.

**Open questions.**

- **OQ-10 — in-flight runs at cutover.** Big-bang means `FeatureWorkflow`
  disappears. Drain first (block new runs, wait out current ones) or accept that
  in-flight runs fail and are restarted? Unresolved; blocks E-74's landing, not
  its design.
- **OQ-11 — dashboard auth.** E-75 is the first server in the project, and
  *"start a run"* and *"approve a merge gate"* are not endpoints to leave
  unauthenticated once anything but localhost can reach them. Localhost-bind with
  no auth is the assumed near-term answer; **E-60** (identity & authorization,
  FR-1004) is where it stops being acceptable.

## 15. Suggested ordering across §§10–14

Not a commitment. Ranked by what each item unblocks and by which invariants get
harder to install later:

1. **E-40 + E-43** — the two invariants. **Designed and planned 2026-08-06; next
   to implement.** Both are small, both land in *existing* code paths, and both
   improve the current pipeline on their own (`Measurement` closes the
   malformed-SARIF-reads-as-clean hole on the absolute floor; the verifier is
   shared with FR-107's research stage and with two live consumers — handoff
   claims and deep-review integrity flags — that carry unverified quotes today).
   Installing "no unverified claim may be labelled grounded" before any
   finding-producing stage exists is far cheaper than retrofitting it across
   four of them.
2. **E-41 → E-42 → E-44** — triage and tidy-up. The cheapest shippable product,
   almost entirely deterministic, and it needs neither tenancy nor containment
   because it can be operator-run. E-44 is the first item that proves the whole
   assess → fix → prove claim end to end.
3. **E-47 (with E-46)** — `CapabilityMap`. Unblocks P2 brownfield whether or not
   the audit ships, which makes it the highest-leverage item in §11. **Settle
   OQ-6 first** — it is genuinely blocking, not a detail.
4. **E-67** — `DeployPlan`/`DeployReport`. Closes stage 13 for ordinary feature
   runs; the outcome loop needs it, but so does P1's own deploy stage.
5. **E-57 + E-58** — the moment an external, self-serve tenant is on the table
   these stop being optional. Not required for operator-run delivery, so their
   position depends entirely on whether P7 is the near-term goal.
6. Then audit depth (**E-48 → E-49 → E-50 → E-51 → E-52 → E-53 → E-54 → E-55 →
   E-56**), service (**E-59…E-63**), and the outcome loop (**E-64 → E-65 →
   E-66 → E-68/E-69 → E-70 → E-71**).
7. **§14 (E-72…E-77) is deliberately unsequenced.** It is the only tier that
   rewrites a core code path rather than extending one, and it competes with
   nothing above it for invariants — the factory ships fine without it. Two
   things argue for pulling it earlier anyway: **E-75 closes P2's outstanding
   dashboard-backend half** regardless of whether the interpreter lands, and the
   longer `_pipeline` accretes stages (§1 has 8 unbuilt ones), the more imperative
   wiring the big-bang rewrite has to absorb. If §14 is wanted at all, **E-72 →
   E-73 before §1 grows** is the cheap moment; E-75 can be lifted out and shipped
   on its own.

**Deliberate:** §10 ships before §11 even though §11 is the more impressive
product. Triage is what tells you whether the audit is worth running (FR-903),
its findings are the ones that are mechanically fixable, and it is the only tier
that works on the repositories most likely to arrive first.
