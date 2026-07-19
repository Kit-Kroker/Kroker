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
- [ ] ⚠️ **12 · quality_gate** — `DeterministicQualityGate` mechanism ✅; 6 checks built (`build_integration_green`, `lint_clean`, `security_no_critical` absolute; `review_severity`, `traceability`, `coverage` advisory). Absolute security floor now wired ✅; traceability enforced ✅; coverage via deterministic Cobertura seam (`measured=False` ⇒ no-op — blocked not just on a project emitting `coverage.xml` + setting `coverage_threshold`, but on the test suite actually running in the *integration* worktree the seam reads from: stage 5a only runs `run_lint`/`security_scan` there, `run_test_suite` runs per-task in task worktrees, so `coverage.xml` never lands where `measure_coverage` looks unless the artifact is carried across the merge).
- [ ] ⚠️ **13 · deploy** — single hardcoded `make deploy ENV=staging`; no `DeployPlan`/`DeployReport` split, no smoke-test vs PR-merge distinction.
- [ ] **14 · retro** — `reflect()` activity exists and is registered but **never called**; no `RunSummary`, no export.

---

## 2. Functional requirements (PRD §6)

### Pipeline (FR-100)
- [ ] ⚠️ **FR-101** 15-stage durable DAG — 7/15 stages (see §1).
- [ ] **FR-102** greenfield/brownfield classify + `CodebaseMap` + delta.
- [x] **FR-103** memoization, per-run watermark, audit-record-always-kept (`memoization/cache.py`, `content_key`, `_cached_stage`) — each stage's memo key now carries *its own* role's model (`STAGE_MODELS`), so a per-role model change invalidates exactly that stage. `brief_digest` keeps memoization alive once a non-memoized stage (research) feeds memoized ones: the brief contributes only a canonical (source_url, claim) digest to `content_key`, so identical facts hit and new facts invalidate clarify/architect/planner.
- [x] **FR-104** integration branch, per-task worktree, own-branch-point diff (ADR-14 fully wired).
- [ ] ⚠️ **FR-105** fix loops — QA loop ✅, review findings now fold into it ✅; loop-count defaults drift from spec (2 vs 3).
- [ ] ⚠️ **FR-106** deterministic absolute/advisory gate — classification ✅ and load-bearing; security absolute-floor check now wired ✅ (`security_no_critical`); traceability enforced ✅; coverage wired as a deterministic diff-scoped seam ✅ (real instrumentation future work).
- [ ] **FR-107 (new scope)** grounded research stage — `ResearchBrief`, quote-verified against bytes fetched this run, off by default (`research_enabled`). Landed behind the PRD amendment adding FR-107; `2026-07-17-research-agent-grounded-briefs`.

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
- [ ] ⚠️ **FR-404** nightly reflect — **project half live**: `schedules/nightly-reflect.yaml` → `ReflectWorkflow` → `reflect()`, applied via `sdlc schedules apply` (E-12/E-13). **Org half unmet**: nothing retains to `org_bank`, so `reflect(org)` would consolidate an empty bank (E-25). Not `[x]` until org has writers.

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
- [ ] **FR-701** run-level budgets — research ships the FIRST run-level counters (`max_searches`/`max_fetches`/`max_cost_usd`), stage-scoped and enforced inside the tools; E-19 remains the general version.
- [ ] ⚠️ **FR-702** claim-check `ArtifactRef` / 2MB discipline — `ArtifactRef` model exists but diffs travel inline; no `CodeArtifact` union; no size guard.
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
3. ~~**retro/reflect wiring** (FR-404) — starts accumulating the SC-4/SC-6 calibration signal. Tasks: **E-12, E-13** (§9.3).~~ **Partially done** — schedule mechanism + nightly project reflect ship (E-12/E-13); plan `docs/superpowers/plans/2026-07-16-schedules-as-files-and-nightly-reflect.md`. Signal only accrues on runs with `memory.enabled=true` (defaults `False`). Org half blocked on **E-25**; the retro *stage* (§1 item 13, `RunSummary`) is still unbuilt.
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
- [x] **E-27** Cat café monitoring golden case + `qa`/`research` rubric judging. The suite's two cases are both "sized for a single short factory run", so **planner decomposition — the load-bearing variable in real work — is unexercised**. The kata is large enough to require decomposition and small enough to specify completely. Authoring it surfaced that only 3 rubric keys reach the judge (`clarifier`/`architect`/`planner`, `feature.py:773`/`:840`/`:879`): `qa` (`:539`) emits a judgeable artifact that only feeds the deterministic `code` record, and `research` (`:730`) hardcoded `judge="contract"` with no `_judge` call, so **no cell had ever run the stage**. Added `CaseSpec.research_enabled` (default `False`) with a per-case injected `provider: tavily` (registry stays `fake` so CI needs no key), both `_judge` calls, and five rubrics. Spec: `docs/superpowers/specs/2026-07-19-cat-cafe-monitoring-benchmark-design.md`; plan: `docs/superpowers/plans/2026-07-19-cat-cafe-monitoring-benchmark.md`. *Smoke run reached the research stage live (real Tavily+glm) and grounded the exact risk threshold the research rubric targets (>35 bpm at rest), but ends at `rejected:research.grounding` — the fail-closed verifier (`research/verify.py`) requires byte-exact contiguous quotes and glm-5.2 cannot reliably reproduce special chars/tabular data (violations improved 8→3 across two prompt fixes, then plateaued). So live judge scoring of `research`/`qa` records is unit-tested but unproven end-to-end; it unblocks when E-29 or E-30 lands. Two robustness defects surfaced by the run and fixed inline: `read_repo` infinite-retry (see E-28) and the research quoting prompt.*
- [ ] **E-28** Research tool-call activities retry a **deterministic** failure with no attempt cap. E-27's smoke run hung when `read_repo` raised `ValueError` on an out-of-cwd path: the pydantic-ai temporal tool-call wrapper retried it forever (attempt 11+). Fixed the immediate trigger (`read_repo` now returns a refusal string, matching its own missing-file branch), but the underlying hazard remains — **any** research tool that raises a non-transient error loops the whole run. Needs a bounded/`non_retryable` retry policy on `agent__research_agent__toolset__*__call_tool`, or a rule that research tools return errors as strings rather than raise.
- [ ] **E-29** Research grounding is unreachable for a mid-tier author model. `verify_brief` (`research/verify.py`) fails closed unless every `grounded_finding.quote` is a **byte-exact contiguous substring** (whitespace-normalized only) of a page fetched this run. glm-5.2 reliably violates this on special characters (en-dash `–`, curly quotes) and tabular content — E-27's run plateaued at 3 violations after two prompt fixes cut it from 8. Options: (a) normalize more aggressively in the verifier (dash/quote folding — but "every loosening is a hole", per the module's own warning, so each needs a test proving the false-failure it fixes); (b) a per-case research-model override to a higher-fidelity family (interacts with ADR-6 + E-26); (c) accept research as advisory (`inferred_findings`) rather than a hard gate for benchmark cells. **Blocks live proof of E-27's research-stage judging.**
- [ ] **E-26** Make `cfg.roles` genuinely per-project (US-4) without reintroducing drift. `PipelineConfig.roles` is a hardcoded mirror of `agents.yaml`'s harness roles because `PipelineConfig()` is constructed *inside* the workflow (`feature.py:602`), so its default cannot read the file without breaking sandbox purity. The boot mirror-check makes drift fail closed, but it also means a per-project override must resolve at the boundary (`cli.py`, `benchmarks/workflow.py`) and satisfy ADR-6 *per run*, not just at boot. **Nothing populates `cfg.roles` today**, which is the only reason the mirror can be a static assertion.

### 9.4 `pre_tool` unifies containment with gates → FR-703, NFR-5, FR-301

Eve marks individual tools `needsApproval`. FR-703 wants a `pre_tool` hook and has none. These are the same hook — a denial is a policy decision, an approval request is a gate. Building `pre_tool` as an escalation into the *existing* gate machinery gets both, instead of growing containment and human-in-the-loop as two separate subsystems.

- [ ] **E-15** `pre_tool` hook seam in `harness/adapters.py`, called for every harness tool invocation.
- [ ] **E-16** Policy denial path — deny by rule, no human involved (FR-703).
- [ ] **E-17** Approval escalation: a `needsApproval`-class tool call raises a gate through existing FR-301/FR-302 machinery rather than a parallel mechanism.
- [ ] **E-18** harness/egress containment — **re-ranked up.** §8 item 4 ranked it fourth on the strength of `pre_tool`; an unpoliced outbound egress (research, FR-703) is a second, independent argument. The research stage fetches arbitrary URLs through a provider with only an env allowlist between it and the worker's network.

### 9.5 Sandbox / Connect / Gateway → NFR-5, FR-701, FR-703

Reference designs for gaps already named in §2/§3, not new scope.

- [ ] **E-19** Single model egress point yielding run-level token/cost counters (FR-701). Today cost bookkeeping "exists in benchmarks only"; one egress point is how to get run counters without touching every call site. *Prerequisite for the run-budget escalation half of FR-701.*
- [ ] **E-20** Short-lived, task-scoped credential injection with an audit trail binding each action to a user (Connect's model) — the "scoped-cred injection absent" gap in NFR-5.
- [ ] **E-21** OS-user / container isolation tier (Sandbox's model) — the missing tier in FR-703.

### 9.6 Observability — the lesson eve teaches by failing → FR-704, NFR-4

Independent reviews of eve converge on observability as its weak point: silent delivery failures with no diagnostic ("no 404, no failed-delivery banner — silence"), debugging by manual diff, dependency drift breaking tool loops mid-execution. That is precisely our unimplemented FR-704. This is outside evidence that the missing piece is what makes such a system painful in production — an argument for ranking FR-704 above "nice to have".

- [ ] **E-22** `observability/` module emitting `events.jsonl` (FR-704, NFR-4).
- [ ] **E-23** `report.html` export from the event stream (FR-704).
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
