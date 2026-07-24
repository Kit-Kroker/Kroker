# Implementation Roadmap — Agentic SDLC Factory

| | |
|---|---|
| Status | Living tracker |
| Last verified | 2026-07-19 (against `src/sdlc/`, `interfaces/`, `tests/`, `config/`, `agents/`) |
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

---

## 0. Phase summary (PRD §9)

- [x] **P1** — Greenfield pipeline, CLI, hard gates, no memory → *one project shipped end-to-end*
  Exit criterion **demonstrated**: `tests/test_e2e_greenfield.py` drives the real `FeatureWorkflow` greenfield `IdeaBrief` → `deployed:` end-to-end in CI, and the `security_no_critical` absolute floor now bites (SC-5). Delivered on `feat/p1-consolidation` (`3cfbe62`…`41c9185`).
- [ ] ⚠️ **P2** — Brownfield, dashboard + notifications, fix loops, cross-harness review → *first brownfield feature merged via PR*
  Cross-harness review ✅ and fix loops ✅ landed early; brownfield mode, dashboard backend, and notifications not started.
- [ ] ⚠️ **P3** — Hindsight memory + confidence-gated soft gates → *SC-4 and SC-6 measurable*
  Memory (recall/retain/watermark) ✅ and soft gates ✅ done; SC-4/SC-6 not yet measurable (need retro/reflect wiring + real runs). **The retro stage that makes them measurable is E-32** (§9.8); the on/off memory delta is the measurement E-31/E-33 exist to run.
- [ ] **P4** — MCP surface, maintenance loop (DAPER), fleet scale → *SC-1..3 at target*
  Not started.

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
- [ ] ⚠️ **12 · quality_gate** — `DeterministicQualityGate` mechanism ✅; 6 checks built (`build_integration_green`, `lint_clean`, `security_no_critical` absolute; `review_severity`, `traceability`, `coverage` advisory). Absolute security floor now wired ✅; traceability enforced ✅; coverage via deterministic Cobertura seam — **E-30 closes the FR-106 crossing gap**: `run_integration_checks` now runs coverage-instrumented tests against the merged integration head, landing `coverage.xml` where `measure_coverage` reads (Python adapter end-to-end; Go/TS/Rust via E-30a/b/c). Still an advisory no-op unless `coverage_threshold` is set.
- [ ] ⚠️ **13 · deploy** — single hardcoded `make deploy ENV=staging`; no `DeployPlan`/`DeployReport` split, no smoke-test vs PR-merge distinction.
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
- [ ] ⚠️ **FR-301** hard/soft/off + threshold + revise + `MAX_GATE_ROUNDS` — wired for architecture/plan/merge; soft still confidence-only (no deterministic-check AND-clause); no calibration monitoring.
- [x] **FR-302** idempotent signals, `(gate, round)` identity, first-decision-wins.
- [ ] ⚠️ **FR-303** notifications + durable timers — timeout→auto-reject only; no notify activity, no reminder timer, no fallback-approver.
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
- [ ] ⚠️ **FR-703** egress policy — **research is the pipeline's first outbound egress, and it arrives before the egress policy.** Still env-allowlist only; no `pre_tool` hook, no egress tier. This spec is E-18's first consumer, not its implementation.
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

- [ ] — **SC-1** ≥80% runs reach merge gate unattended — not measurable (no fleet runs). Vehicle: the benchmark matrix (§9.8, E-34) is where unattended-reach rate is aggregated; cases can now carry a held-out grade (E-31 landed), so the gate is the next load-bearing piece.
- [ ] — **SC-2** ≤15 min operator time — not measurable.
- [ ] — **SC-3** fix-loop success ≥70% — mechanism exists; no aggregate metric captured. Captured per run as a coordination metric by the benchmark (§9.8, E-36 heatmap): fix-loop attempts vs resolution, per stage.
- [ ] — **SC-4** repeat-clarification <10% by run 10 — needs reflect wiring (FR-404) + runs. **The per-run signal now accrues:** the retro stage (E-32) emits a `RunSummary` carrying `clarifications[].answered_by` (`human`/`suggested`/`unanswered`) on every terminal path. The cross-run *aggregation* into a repeat-clarification rate remains the benchmark's job (§9.8), via the memory-on cells that generate the run-10 series.
- [x] **SC-5** zero deploys past a failed **absolute** check — empty/vacuous-task bypass fixed, absolute failure is terminal, and the `security_no_critical` floor is now emitted by the `security_scan` activity and wired as an absolute merge-gate check (`feature.py:807,818`). `tests/test_security_floor.py` asserts a critical finding blocks deploy.
- [ ] — **SC-6** soft-gate override <5% — mechanism exists; not measurable without runs + reflect. **The per-run signal now accrues:** the retro stage (E-32) emits `RunSummary.gates[]` with `policy`/`decided_by`/`confidence`/`overrides` (ARCHITECTURE §10 calibration compare). The cross-run *aggregation* into an override rate remains the benchmark's job (§9.8).

---

## 5. User stories (PRD §5)

- [ ] ⚠️ **US-1** clarify + one-click suggested answers — CLI clarify + suggested-answer auto-accept ✅; no dashboard/Slack/MCP delivery.
- [x] **US-2** approve/revise architecture spec — REVISE loop with recorded identity.
- [x] **US-3** task escalation → retry-with-guidance/quarantine — guidance reaches same harness session.
- [x] **US-4** per-project gate config (hard/soft + threshold) — `GateConfig`, no code change.
- [x] **US-5** dev/reviewer different model family; registry rejects same-family — enforced at boot, against `dev` (the role that actually codes) since `2026-07-16-registry-drives-every-role`.
- [ ] **US-6** stakeholder one-screen fleet view — no dashboard backend.
- [ ] **US-7** MCP conversational gate approval — no MCP server.

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
4. **Harness containment** beyond env allowlist — `pre_tool` hook + egress (FR-703/NFR-5). Tasks: **E-15…E-18** (§9.4) — note the hook and the gate are one mechanism, not two.
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
- [ ] **E-8** Cross-run inbox as a query over pending gates (FR-305, FR-603's missing verb) — the first capability the contract buys that we don't already have.
- [ ] **E-9** Notify activity + reminder timer + fallback approver (FR-303). Today: timeout→auto-reject only.
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
- [ ] **E-26** Make `cfg.roles` genuinely per-project (US-4) without reintroducing drift. `PipelineConfig.roles` is a hardcoded mirror of `agents.yaml`'s harness roles because `PipelineConfig()` is constructed *inside* the workflow (`feature.py:602`), so its default cannot read the file without breaking sandbox purity. The boot mirror-check makes drift fail closed, but it also means a per-project override must resolve at the boundary (`cli.py`, `benchmarks/workflow.py`) and satisfy ADR-6 *per run*, not just at boot. **Nothing populates `cfg.roles` today**, which is the only reason the mirror can be a static assertion.

### 9.4 `pre_tool` unifies containment with gates → FR-703, NFR-5, FR-301

Eve marks individual tools `needsApproval`. FR-703 wants a `pre_tool` hook and has none. These are the same hook — a denial is a policy decision, an approval request is a gate. Building `pre_tool` as an escalation into the *existing* gate machinery gets both, instead of growing containment and human-in-the-loop as two separate subsystems.

- [ ] **E-15** `pre_tool` hook seam in `harness/adapters.py`, called for every harness tool invocation.
- [ ] **E-16** Policy denial path — deny by rule, no human involved (FR-703).
- [ ] **E-17** Approval escalation: a `needsApproval`-class tool call raises a gate through existing FR-301/FR-302 machinery rather than a parallel mechanism.
- [ ] **E-18** harness/egress containment — **re-ranked up.** §8 item 4 ranked it fourth on the strength of `pre_tool`; an unpoliced outbound egress (research, FR-703) is a second, independent argument. The research stage fetches arbitrary URLs through a provider with only an env allowlist between it and the worker's network.

### 9.5 Sandbox / Connect / Gateway → NFR-5, FR-701, FR-703

Reference designs for gaps already named in §2/§3, not new scope.

- [x] **E-19** Single model egress point yielding run-level token/cost counters (FR-701). Today cost bookkeeping "exists in benchmarks only"; one egress point is how to get run counters without touching every call site. *Prerequisite for the run-budget escalation half of FR-701.* *Folded into E-33:* `_run_role` is the single egress point; run-level counters live in `RunSummary.roles`.
- [ ] **E-20** Short-lived, task-scoped credential injection with an audit trail binding each action to a user (Connect's model) — the "scoped-cred injection absent" gap in NFR-5.
- [ ] **E-21** OS-user / container isolation tier (Sandbox's model) — the missing tier in FR-703.

### 9.6 Observability — the lesson eve teaches by failing → FR-704, NFR-4

Independent reviews of eve converge on observability as its weak point: silent delivery failures with no diagnostic ("no 404, no failed-delivery banner — silence"), debugging by manual diff, dependency drift breaking tool loops mid-execution. That is precisely our unimplemented FR-704. This is outside evidence that the missing piece is what makes such a system painful in production — an argument for ranking FR-704 above "nice to have".

- [x] **E-22** `observability/` module emitting `events.jsonl` (FR-704, NFR-4). *Folded into E-32:* `observability/trace.py` (`RunEvent`) + `observability/export.py::render_events_jsonl` render the in-workflow trace to `events.jsonl`; written by the `export_run_artifacts` activity.
- [x] **E-23** `report.html` export from the event stream (FR-704). *Folded into E-32:* `observability/export.py::render_report_html` renders a self-contained `report.html` from the `RunSummary`.
- [ ] **E-24** Pin harness/adapter versions and assert them at boot — eve's dependency-drift failure mode applies directly to `HARNESSES` (FR-203).

### 9.7 Suggested ordering

Not a commitment, and deliberately not "by section":

1. **E-12, E-13** — smallest, and the only items that start the SC-4/SC-6 signal (§8 item 3).
2. ~~**E-1 → E-2 → E-3**~~ — landed. E-1/E-2 landed as `agents/<role>/` directories (`feat/agents-as-folders`); E-3 was subsumed by the registry increment (`2026-07-16-registry-drives-every-role`), which already closed the model-half gap.
3. ~~**E-6**~~ landed (`feat/channel-contract`) → ~~**E-7**~~ landed
   (`feat/cli-channel-refit`) → **E-8** — the CLI refit proved the contract;
   E-8 is the first *new* capability it buys.
4. **E-15 → E-17** — the hook seam, then gate reuse.
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
- [ ] **E-35** `cursor` harness adapter — third point on the harness axis,
  normalised into `HarnessRunResult` (tokens, cost, `context_window`,
  `compacted`, resume handle) and version-pinned at boot (FR-203; folds the
  intent of **E-24**). Value is not "cursor vs claude in the abstract" — it is
  measuring `claude -p` vs `opencode` vs `cursor` **through the
  DeterministicQualityGate on the held-out oracles**, a comparison no external
  leaderboard provides. Ordered *after* E-33 so the economics fields exist to
  receive it; until the adapter fills them, cursor cells are quality-only.
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
  derived waste (E-38) as a heatmap input and calibration-as-CI-gate (OQ-B4)
  deliberately deferred. Spec
  `docs/superpowers/specs/2026-07-24-error-heatmap-and-rubric-calibration-design.md`,
  plan `docs/superpowers/plans/2026-07-24-error-heatmap-and-rubric-calibration.md`.
- [ ] **E-37** Per-role model sweep at the benchmark boundary. Resolve
  `cfg.roles` per cell (folds **E-26**) so each cell overrides role→model and
  satisfies ADR-6 *per run*, not just at boot — the full model×role matrix
  (US-4). Deferred last: the harness (E-35) and memory (E-32) axes deliver most
  of the insight without it, and E-26 is real work. Ties to **OQ-B2** (the
  judge family must move per cell to stay ADR-6-independent of the swept
  producer family) and **OQ-E2**.

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
- [ ] **E-39 (new scope)** `deep_review` — an optional, opt-in review tier that
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
**Open questions (tracked in `docs/BENCHMARK.md §7`):** OQ-B1 minimum trustworthy
corpus size; OQ-B2 judge independence under model sweep (→ E-37); OQ-B3 **answered** (E-29 closed: grounding failure = recorded stage `FAIL`, run continues); OQ-B4 the regression-gate half of E-4 as a CI gate (→ OQ-E2); OQ-B7
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
