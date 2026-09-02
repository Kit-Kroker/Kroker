# Filesystem-first work items (`E-`) — design input from `vercel/eve`

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
- [x] **E-10** FastAPI dashboard backend as a channel adapter, replacing the Vue frontend's mock API (FR-601, US-6, ADR-8). *Landed 2026-08-18.* `run_state()` — one query over state the run already held — plus `sdlc/dashboard/{fleet,api,channel}.py`: a lazy shared poller fanning out `run_state()` + `pending_decisions()` across open runs and `run_summary()` across the 20 most recent closed ones, served as REST reads plus an SSE stream. Three write routes, not five: `pending.py`'s four variants already collapse to two FR-302 signals. Spec `docs/superpowers/specs/2026-08-18-dashboard-backend-design.md`.
- [ ] **E-11** MCP server as a channel adapter — list/detail/inbox/answer/decide/start (FR-602, US-7). *Re-exports `sdlc/operator/tools.py` (E-86) rather than reimplementing the verbs.*
- [x] **E-86** Operator chat surface — a Pydantic AI agent over the same tool layer, served by `pydantic_ai.ui.create_web_app` and mounted at `/chat` beside the board and dashboard routers. Twelve verbs in `src/sdlc/operator/` (nine reads, three approval-gated writes), a run-scoped bounded `follow`, and a 32 KB paged `read_artifact`. Shipped behind `SDLC_CHAT_ENABLED`, default off. Closes the chat half of US-7; FR-602 stays open until E-11's MCP server ships. Spec `docs/superpowers/specs/2026-08-20-operator-chat-surface-design.md`, plan `docs/superpowers/plans/2026-08-20-operator-chat-surface.md`.

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

- [x] **E-79 (new scope)** External benchmark corpus — import the DevEval
  Python repositories (COLING 2025; code Apache-2.0, **dataset CC BY 4.0**) as
  benchmark cases, delivering BENCHMARK.md §5's "public anchors (external
  validity)". *Landed 2026-08-09:* `benchmarks/importers/deveval.py` converts
  each repo's `repo_config.json` manifest into a case dir — PRD → description
  with the reference architecture inlined as a **frozen contract** (the
  cat-café pattern; DevEval oracles bind to exact module and function names,
  so a free-form architect scores ~0), reference suites → `oracle/`, plus
  three new sibling dirs `reference/`, `reference_artifacts/`, `reference_env/`
  that **E-80** and **E-81** consume. `CaseSpec.network_required` quarantines
  egress-needing cases at matrix expansion until **E-21**. Gate: every
  imported case's oracle must score 1.0 against its own `reference/`
  (`sdlc benchmark verify-case`), which caught four conversion defects the
  synthetic fixture could not — see
  `docs/reports/deveval-import-report-2026-08-09.md`. **Six of ten repos committed;
  corpus 3 → 9 cases (answers OQ-B1's first data point and OQ-B8).** Spec:
  `docs/superpowers/specs/2026-08-09-benchmark-corpus-and-stage-isolation-design.md`.
- [ ] **E-80 (new scope)** Stage isolation via pinned reference artifacts —
  pre-seed the memo cache (`_cached_stage`) from `reference_artifacts/` so a
  proposer stage is skipped and its output *is* the reference. DevEval's
  modular evaluation protocol, expressed as configuration rather than a fork.
  Turns the error heatmap from "where failure surfaced" into "which stage is
  weak"; partial pinning measures cascade sensitivity. Fails closed.
- [ ] **E-81 (new scope)** Completeness and test-quality metrics — functional
  completeness (requirement-weighted, aggregated over the `TaskGrade`s
  `tasks.yaml` already produces), stub density (deterministic placeholder scan,
  reported never gated), and **Oracle Test** (run the QA stage's own generated
  tests against `reference/`: a test that fails on gold code is a wrong test).
  Measures BENCHMARK.md §4.1's traceability gap directly rather than by proxy.
