# Implementation Roadmap — Agentic SDLC Factory

| | |
|---|---|
| Status | Living tracker |
| Last verified | 2026-09-02 (E-50 against `src/sdlc/{assessment/gates,dispositions}` + `workflows/assessment.py`, full unit suite + temporal e2e green, four final-review defects fixed and re-verified); 2026-08-17 (E-49 plan 3 against `src/sdlc/assessment/risk/crosscap.py` + unit suite and Temporal e2e green); 2026-08-16 (E-49 plan 2 against `src/sdlc/assessment/risk/`, `agents/risk/`, `src/sdlc/assessment/verification.py`, Temporal e2e green); 2026-08-16 (E-49 plan 1 against `src/sdlc/assessment/risk/` + unit suite green); 2026-08-14 (E-47c against `src/sdlc/assessment/discover/` + `src/sdlc/assessment/scan/naming.py` + unit suite green); 2026-08-13 (E-47b against `src/sdlc/assessment/discover/` + `src/sdlc/assessment/scan/configpaths.py` + unit suite green); 2026-08-13 (E-46 plan 3 + review fixes against `src/sdlc/assessment/scan/`, unit + temporal e2e green); 2026-08-13 (E-46 plan 3 against `src/sdlc/assessment/scan/` + unit suite green); 2026-08-13 (E-46 plan 2 against `src/sdlc/assessment/scan/` + unit suite green); 2026-08-10 (E-45 against `src/sdlc/{assessment,workflows/assessment.py,triage/admission.py}` + unit/e2e tests green); 2026-08-09 (E-44 against `src/sdlc/{tidyup,workflows/tidyup.py,triage/delta.py}` + unit/component tests green; E-42 against `src/sdlc/workflows/{gates,triage}.py` + `pytest -m temporal`, with three review defects fixed; E-47a 2026-08-08 against `src/sdlc/capability/`; E-78 2026-08-07 against `src/sdlc/board/`; E-40/E-43 2026-08-06; the rest 2026-08-05, against `src/sdlc/`, `interfaces/`, `tests/`, `config/`, `agents/`) |
| Source of truth for scope | `PRD.md`, `ARCHITECTURE.md`, `SDLC-spec.md` |
| Method | Every FR / NFR / SC / US / ADR and the 15-stage DAG checked against actual code, not against prior audit claims |

**Legend**
- `[x]` — implemented and wired into the live path
- `[ ]` ⚠️ — partial: mechanism exists but incomplete or not fully wired (see note)
- `[ ]` — not started
- `—` — not falsifiable from code alone (needs runtime measurement)

> Since the 2026-07-05 audit, the **reviewer stage (ADR-6/FR-204)** and **agent registry (FR-201)** landed (merged `b9455c3`), plus a **coding-harness adapter layer** and **harness observability logging**. Those items are now checked. The audit's `docs/reports/feature-coverage-audit-2026-07-05.md` is superseded by this tracker.

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
  Cross-harness review ✅, fix loops ✅, notifications ✅ (E-9), and brownfield ✅ (E-84, 2026-08-15; `CapabilityMap` via E-47a/b/c) all landed. The dashboard backend landed 2026-08-18 (**E-10**, §9.2) — `interfaces/dashboard/api/main.py` now composes the board and dashboard routers, and the frontend's `http` provider serves live Temporal state. **Correction 2026-08-18 — "every part is built" was wrong, and the part that was missing was the *via PR* clause itself.** `open_pull_request` had never executed outside fakes: its only appearance under `tests/` was `fake_open_pull_request`, every e2e reached `deployed:` through `GIT_FAKES`, and benchmark runs short-circuit it by design (`"skipped:benchmark-run-has-no-remote"`), so nothing had ever forced the real branch. Three things were absent, each of which would have killed the demonstration after every gate had already passed: **`gh` was not in the worker image** (the `Dockerfile` apt line installed `git`, `nodejs`, `npm`); **no GitHub credential reached the worker** (`.env` had no `GH_TOKEN`, and `git push` needs one too, not just `gh`); and **the activity reported none of this** — a missing binary raised `FileNotFoundError` that `ACT` retried six times, and `check=True` raised a `CalledProcessError` whose `str()` drops gh's own diagnostic crossing Temporal, the hazard `_git`'s docstring documents one seam over. *Closed 2026-08-18:* pinned `gh` 2.97.0 plus a `!gh auth git-credential` helper in the image, `GH_TOKEN` documented in `.env.example`, non-retryable `gh`/`origin` preconditions checked **before** the push (so a misconfigured worker cannot leave a pushed branch with no PR pointing at it), and the activity's first real-git coverage — `tests/test_open_pull_request.py` and the `docker`-marked `tests/test_worker_image.py`. **The exit criterion — *first brownfield feature merged via PR* — is still a demonstration that has not been run**; what changed is that it can now fail for interesting reasons. One thing to settle before judging it: the pipeline **opens** the PR and never merges it (`activities.py` says so outright), so the `merged-not-deployed:<pr_url>` terminal status means merged *into the integration branch* — the criterion's final merge is an operator action.

  **2026-08-19 — the demonstration was run twice, against this repository, and
  did not reach the PR step either time. The blocker is no longer plumbing; it
  is the merge gate's own design.** Both runs built the feature successfully
  (E-30a, a `GoToolchain` adapter: `src/sdlc/toolchain/adapters.py` +93 and
  `tests/test_toolchain_go.py` +232, 36 tests, verified passing). Run 1 died at
  a task gate; run 2 reached the merge gate and was rejected
  `absolute-gate-failed:build_integration_green,lint_clean,security_no_critical`.

  **The finding that matters: the absolute floor measures the repository, not
  the change.** `security_scan` takes the whole `integration_worktree`,
  `lint_cmd()` is `ruff check .`, and the integration test run is the entire
  suite; only `measure_coverage` is scoped to `changed_files`. On this
  repository all three fail on `main` itself, before any feature is added:
  `ruff check .` reports **1142 errors**; the security scan reports **4
  criticals**, all in pre-existing files, including `tests/test_security_floor.py`
  — the security floor's *own fixtures*, which contain deliberate fake secrets
  and `eval()` so that detection can be tested (added by `4805c45`, the commit
  that built the floor); and two tests fail (see below). Absolute checks are
  never overridable by design (`gate.py:86`), so **no operator can pass this
  gate, and no brownfield change can ship into a repository carrying any lint
  debt or scanner false positive** — which is every real brownfield repository.
  For greenfield this is correct, because the repo *is* the change. P2 inherits
  a floor built for P1. Scoping lint and security to the diff, the way
  `measure_coverage` already is, changes what SC-5's security floor *means* and
  needs its own spec — it is not a patch.

  Five further defects, each of which needed a real repository, a real worker
  image, or a real operator decision to appear — none was reachable by the
  existing suite:

  - **The per-task gate could not honour REVISE** — *fixed*, `477635e`, with
    `tests/test_task_gate_revise_loop.py` (the first coverage this path has
    ever had). `_dev_task` branched on `decision.approved`, which is False for
    both reject and revise — the exact confusion `GateDecision.approved`'s
    docstring warns callers about — so guidance was recorded in
    `TaskResult.notes` and the task quarantined anyway. Since any quarantined
    task fails the run, APPROVE was the only outcome a run could survive, from
    a gate whose comment promised "accept, retry, or quarantine". This killed
    run 1 after 4h09m. Now bounded by `max_gate_rounds` exactly as
    `_revisable_stage` bounds the stage gates, and exercised live in run 2:
    three revisions were issued across three tasks and every one was honoured.
  - **A task's own tests never ran, and the gate reported on them anyway** —
    the planner authored `pytest tests/ -x -q`; `-x` aborted at an unrelated
    failing test sorting alphabetically *before* the task's own file, so across
    four attempts the Go adapter's tests executed **zero times**. `QAReport`
    cannot express this: it says `tests_passed: false`, true of the suite and
    silent about the task. **This is E-30's `CoverageReport` problem one layer
    up** — that contract already separates `measured: bool` from a zero;
    `QAReport` has no way to distinguish "failed" from "never ran". The reviewer
    caught it unprompted, on a diff it was otherwise approving.
  - **The retry prompt carries no diagnostic.** `QAReport.issues` keeps the last
    2000 characters of output, which on this repository is entirely PydanticAI
    deprecation warnings, so the traceback is truncated away and every retry
    prompt contains the failing test's *name* and nothing else. Four consecutive
    tasks — documentation, adapter, tests, CI — none touching the relevant code,
    responded by attacking the named test file, each widening further: editing
    the test, rewriting git handling in `activities.py`, then adding an
    `OSError`-swallowing retry helper that would have masked real defects in the
    checkpoint path. That is one broken signal reproducing the same failure four
    times, not four agents behaving badly. Nothing tells an agent its diff has
    left its assigned files; the reviewer says so only after every attempt is
    spent. **Cheapest high-value fix on this list.**
  - **A contract authored from a false premise cannot be retired.** The planner
    asserted that CI existed and must include the new test paths; there is no
    `.github/workflows` on `main`, and `scan_ci` had already established that.
    The task was then unsatisfiable by construction: the agent invented a CI
    workflow (reverted for scope), and the correct empty diff cannot satisfy
    assertions about a file that should not exist. Only an operator override or
    quarantine — which fails the run — can clear it. The adapters' degrading
    defaults solve exactly this problem one layer down; contracts have no way to
    mark an assertion *inapplicable* rather than unmet.
  - **`project()` runs in the workflow thread and can trip Temporal's deadlock
    detector.** `_context` projects thirteen scan signals inside the workflow;
    on this repository's ~300KB payload that exceeded the 2s no-yield bound and
    raised `TMPRL1101`. It is load-*order* dependent: run 1 failed when two large
    results landed in one activation, run 2 passed on identical data because they
    arrived spread out. It self-heals via retry, so **a green run is not evidence
    it is absent**. The fix is a seam move — `project()` is pure and belongs
    behind an activity like the signals it consumes.

  Also observed: `pytest-cov` is **not installed in the worker image**, so
  `test_cmd(coverage=True)` always raises a usage error and
  `run_integration_checks` always falls back to the uninstrumented command —
  E-30's coverage instrumentation cannot function as deployed (it degrades
  honestly, naming the reason, rather than reporting a false zero). The planner
  emitted one task with an empty description, and authored contract commands
  using `pip install -e .`, which `PythonToolchain.install_cmd` rejects in terms
  ("writes `*.egg-info` into the tree under audit") and which duly left
  `src/ai_sdlc_temporal.egg-info` in the worktree. No mechanism tracks which task
  owns which file, so one task delivered a later task's deliverable under a
  different filename and the branch carried duplicate coverage of one class until
  an operator caught it. And `tests/test_coding_task_checkpoint.py::test_checkpoint_survives_dubious_ownership`
  is **flaky inside pipeline runs specifically** — 5/5 failures in runs, 7/7
  passes on direct re-runs including under the exact contract command on pristine
  code. Five hypotheses were tested and eliminated (environmental, pre-existing,
  concurrent `pip install -e .`, the contract command, ambient `GIT_*` differing
  between the worker process and an exec shell — verified byte-identical). It
  remains unexplained.

  **What the two runs cost and bought:** roughly nine hours and two full runs,
  no PR. One defect fixed, six recorded with evidence, and the reason P2 has
  never been demonstrated is now understood and is architectural rather than
  incidental. A proposed `_git_env()` fix from one of the agents — stripping
  ambient `GIT_*` from git subprocesses, a real silent-hijack hazard — was
  reverted for scope and timing and is worth its own branch and tests; it does
  **not** explain the flake (tested).
- [ ] ⚠️ **P3** — Hindsight memory + confidence-gated soft gates → *SC-4 and SC-6 measurable*
  Memory (recall/retain/watermark) ✅ and soft gates ✅ done; SC-4/SC-6 not yet measurable (need retro/reflect wiring + real runs). **The retro stage that makes them measurable is E-32** (§9.8); the on/off memory delta is the measurement E-31/E-33 exist to run.
- [ ] **P4** — MCP surface, maintenance loop (DAPER), fleet scale → *SC-1..3 at target*
  Not started.
- [ ] ⚠️ **P5** — Triage + tidy-up (Tier 0/1), operator-run, single tenant → *one unfamiliar repository triaged, a mechanical backlog fixed through governed runs, before/after delta recorded*
  E-40/E-41/E-42/E-43/E-44 all landed in code. `[x]` here means "exit criterion **demonstrated**" (see P1 above), and no `TidyUpWorkflow` has run end-to-end yet: the four-scenario temporal e2e the plan specifies is deferred — its multi-workflow fan-out (a `TriageWorkflow` child whose readiness gate must be serviced plus N `FeatureWorkflow` fix children) is heavier than this Windows host's temporal dev-server can run contended. The components are each green under their own `pytest -m temporal` e2e (`test_triage_workflow_e2e`, `test_seeded_work`'s seeded run, `test_verification_branch`), the full unit suite is green, and `.run()` sequencing is unit-tested and follows the verified `GateHost`/`TriageWorkflow` pattern. Held at ⚠️ until the `TidyUpWorkflow` e2e runs (a CI host that can run the fan-out, or the env contention resolved). Operator-run only; **does not depend on P7**.
- [ ] ⚠️ **P6** — Capability & risk audit (Tier 2) + evidence bundle → *one repository audited end-to-end with SC-7 held and a bundle handed over*
  **Opened 2026-08-10** with E-45's DAG shell. Gated on P5's readiness verdict (FR-903), not merely sequenced after it — and the gate now requires a **human** approval to admit a tree that is not READY. Three of seven phase bodies are now live and measured end-to-end: scan (E-46), discover (E-48), and assess (E-49, all three plans).
- [ ] **P7** — Hosted multi-tenant service → *NFR-8 adversarial test green; FR-1002 container tier live; a tenant onboards unassisted*
  Not started (§12, E-57…E-63). **FR-1002 is the gating item for admitting any external tenant**, not a hardening task: today a customer's `npm install` executes as the worker user with the worker's toolchain and unrestricted network egress.
- [ ] **P8** — Product outcome loop → *one hypothesis pre-registered, shipped, and decided by its own rule (SC-11/SC-12)*
  Not started (§13, E-64…E-71). E-67 (`DeployPlan`/`DeployReport`) delivered the deploy contract; the outcome loop still needs the observation/keep-kill half (E-70).

---

## 1. Pipeline — 15-stage DAG (SDLC-spec v2 §1)

**11 of 15 stages live.**

- [x] **0 · intake** — routing greenfield/brownfield/repair. Verified by `classify_repo` activity against git tree (E-84 D3); fails closed when brownfield has nothing to map.
- [ ] **1 · constitution** — no `Constitution` model, no stage.
- [x] **2 · context (Cartographer)** — `CodebaseMap` projected from scan tree, bounded prompt rendering (`render_for_prompt`), and `check_brownfield_delta` grounding check with 1 retry before failing closed (E-84).
- [ ] **3 · requirements (Product)** — conflated into clarify; no standalone Product proposer / `Requirements` artifact.
- [ ] **4 · research** (FR-107) — grounded brief before clarify. The DAG is now 15
  stages; **11 of 15 stages live** (research is scaffolded, off by default).
- [x] **5 · clarify** — Clarifier + gate; open-question wait on `answer_question`; recall/retain/memoization wired.
- [x] **6 · architecture** — Architect + gate, with REVISE loop (`_revisable_stage`).
- [x] **7 · planning** — Planner + gate, with REVISE loop.
- [x] **8 · code** — Developer, per-task, ADR-14 integration branch (`_dev_task`). A task may instead run as a **crew** of roles in a `CrewTaskWorkflow` child (E-88, §17) — opt-in per role config, `agents/dev` still ships one opencode session.
- [x] **9 · review** — clean-context `reviewer_agent` (`t_reviewer`) run in `_dev_task`; blocking findings fold into the fix loop. **(new)**
- [x] **10 · analyze (Analyst)** — Analyst clean-context proposer (`t_analyst`) emits `AnalysisReport`; workflow enforces criterion→test traceability against the plan's authoritative criteria (FR-106).
- [x] **11 · qa (+ Resolver)** — clean-context `t_qa` + bounded fix loop (folded into stage 7). *Note: default `max_fix_attempts=2`, PRD says QA loop 3 — numeric drift.*
- [ ] ⚠️ **12 · quality_gate** — `DeterministicQualityGate` mechanism ✅; 7 checks built (`build_integration_green`, `lint_clean`, `security_no_critical`, `security_scan_collected` absolute; `review_severity`, `traceability`, `coverage` advisory). Absolute security floor now wired ✅ — the floor now carries `security_scan_collected` beside `security_no_critical`, so a scan that never collected (e.g. a malformed SARIF) can no longer read as a clean absolute floor (FR-915, 2026-08-06); traceability enforced ✅; coverage via deterministic Cobertura seam — **E-30 closes the FR-106 crossing gap**: `run_integration_checks` now runs coverage-instrumented tests against the merged integration head, landing `coverage.xml` where `measure_coverage` reads (Python adapter end-to-end; Go/TS/Rust via E-30a/b/c). Still an advisory no-op unless `coverage_threshold` is set.
- [x] ✅ **13 · deploy** — `DeployPlan`/`DeployReport` split (E-67), deterministic `DeploymentWorkflow` child owning apply → smoke → rollback, `deploy_failed` gate in the parent. Off by default (`PipelineConfig.deploy.enabled`). *Remaining: `devops_planner` does not yet author the plan — `FeatureWorkflow._deploy_plan` builds a single-liveness-check plan (see its docstring).*
- [x] **14 · retro** — on every terminal path the workflow builds a `RunSummary` from an in-workflow `RunEvent` trace, retains it + fires-and-forgets `reflect(project_bank)` (gated on `memory.enabled`), and exports `events.jsonl` + `report.html` via the `export_run_artifacts` activity (E-32). The `org_bank`-writer half stays unbuilt (E-25); retro is project scope only.

---

## 2. Functional requirements (PRD §6)

### Pipeline (FR-100)
- [ ] ⚠️ **FR-101** 15-stage durable DAG — 11/15 stages (see §1).
- [x] **FR-102** greenfield/brownfield classify + `CodebaseMap` + delta. **Landed 2026-08-15 (E-84)**: `classify()` pure rule + `classify_repo` activity; `CodebaseMap` projection from 13 Tier 2 scan signals; bounded prompt rendering; typed `BrownfieldDelta` (added/modified/removed) with activity-side git grounding check in architecture stage.
- [x] **FR-103** memoization, per-run watermark, audit-record-always-kept (`memoization/cache.py`, `content_key`, `_cached_stage`) — each stage's memo key now carries *its own* role's model (`STAGE_MODELS`), so a per-role model change invalidates exactly that stage. `brief_digest` keeps memoization alive once a non-memoized stage (research) feeds memoized ones: the brief contributes only a canonical (source_url, claim) digest to `content_key`, so identical facts hit and new facts invalidate clarify/architect/planner. ⚠️ **Amendment pending (E-47a, 2026-08-08):** E-46's `(tree hash, signal version)` key gains a third term, `identity_registry_version` — the `CapabilityMap` is a function of the tree *and* the identity registry, so re-assessing an unchanged tree is no longer unconditionally a cache hit. Deliberately coarse (any identity write invalidates the whole map for that project); the map is a single artifact with no per-capability memoization to preserve. **Clarified (E-46 D10, 2026-08-12):** E-47a's `identity_registry_version` term applies to the `CapabilityMap`, not to E-46's signal keys — E-46 is a pure function of the tree, keyed on `(tree_hash, signal_version, rules_sha)`.
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
- [x] **FR-601** dashboard fleet/spine/inbox — Vue 3 frontend over a FastAPI backend serving live Temporal state (E-10, 2026-08-18). Closed runs render from `run_summary()` within Temporal's retention window; older history would need a store (OQ-13).
- [ ] **FR-602** MCP server (list/detail/inbox/answer/decide/start) — no `interfaces/mcp/`.
- [ ] ⚠️ **FR-603** CLI — `start/status/answer/approve/revise/reject/benchmark` ✅
  (`revise` landed with E-7; gate rounds are now derived from the pending item,
  not typed by the operator); missing cross-run `inbox` (FR-305).
- [x] **FR-604** stateless shells, no interface DB — true for CLI.

### Governance & ops (FR-700)
- [x] **FR-701** run-level budgets — research ships the FIRST run-level counters (`max_searches`/`max_fetches`/`max_cost_usd`), stage-scoped and enforced inside the tools; E-19 remains the general version. *Landed (E-33):* run-level token/cost counters in `RunSummary.roles` + a `run_budget_usd` budget gate that escalates through the FR-301/302 gate machinery on crossing (approve = one more increment, reject = `rejected:budget`). Stage-scoped research budgets (FR-107) unchanged.
- [ ] ⚠️ **FR-702** claim-check `ArtifactRef` / 2MB discipline — `ArtifactRef` model exists but diffs travel inline; no `CodeArtifact` union; no size guard. Sessions are now a real claim-check consumer (`ArtifactStore` / `harness_session`, E-38), but diffs still travel inline, so FR-702 stays open.
- [ ] ⚠️ **FR-703** egress policy — **research is the pipeline's first outbound egress, and it arrives before the egress policy.** *Partially landed (2026-07-24, E-15/E-16):* the `pre_tool` hook now exists and denies out-of-worktree writes, recursive deletes, agent-config rewrites, and non-allowlisted hosts (tool-level); approval escalation for `action: escalate` rules lands via the same hook (E-17). Egress is still env-allowlist + tool-level only — network-level egress and the OS/container tier remain open (E-21).
  *2026-08-08 (E-41a):* `OsvAdvisorySource` adds the pipeline's **second** declared outbound egress after research (FR-107) — declared, opt-in, and off by default. It is still env/tool-level only; E-21 remains the network tier.
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

- [x] **FR-901** triage stage → `RepoTriage` + readiness verdict; completes on repos that do not build (E-42). *The `RepoTriage` artifact landed with E-41 (2026-08-06); the stage and the readiness gate landed with E-42 (2026-08-08) — `TriageWorkflow` pins a commit, fans out the seven deterministic signals, and `compute_readiness` produces the verdict. Completes on repositories that do not build: the build probe reports `not_ready` dimensions, not an error.*
- [x] **FR-902** hygiene signal set via FR-108 adapters, one implementation
  per signal — **seven of seven landed**: build probe, secrets (incl.
  client-bundle reachability), baseline practice (E-41), plus dependency
  health, generator-scaffold/dead code, framework-default misconfig, and
  size/duplication outliers (E-41a–d, 2026-08-08). **Extended cross-tier by E-46 D2 (2026-08-12):** an assessment signal that duplicates a triage signal **cites** it by `finding_identity` and copies nothing. Two follow-ups from E-49 RD5: an SS1 v2 separating `authn_authz` into distinct authentication and authorization signals, and a monitoring-presence signal so the observability control family has a deterministic source.
- [x] **FR-903** readiness gate blocking Tier 2, overridable by audited decision (E-42). *The gate resolves through the existing FR-301/302 machinery (now in `GateHost`); a verdict that is not READY opens a `readiness` gate, and an APPROVE records a `ReadinessOverride` on the artifact. E-42's admission rule was `verdict is READY or override is not None` (tightened by E-45 — see below).*
  *2026-08-10 (E-45):* the rule is now one function at two strictnesses
  (`triage/admission.py`). Tier 2 requires `approved_by == "human"`, so a
  `policy` (gate OFF) or `timeout` approval no longer admits an audit; Tier 0
  keeps the broader rule for the build-economics reason `backlog.admitted`
  documents.
- [x] **FR-904** `mechanically_fixable` → brownfield child runs + before/after re-triage (E-44). Landed: `TidyUpWorkflow` turns accepted MECHANICAL findings into seeded `FeatureWorkflow` child runs (one PR each), then re-runs triage against `build_verification_branch`'s composite tree and records `compute_delta`.

### Assessment, Tier 2 — capability & risk audit (FR-910) *(new scope; PRD v1.1)*

- [ ] ⚠️ **FR-911** `AssessmentWorkflow` EDCR DAG, report-after-assess, no
  phase-status file (E-45) — **the DAG and both deviations landed 2026-08-10**;
  six of seven phase bodies were stubs reporting `not_collected` with the E-item
  that owes them, so an assessment that assessed nothing says so (FR-915).
  `/enrich` as a declared stage input remains E-56. **2026-08-12 (E-46 plan 1):**
  the stub count dropped from six to five and `PHASE_OWNER` lost its `SCAN` entry
  — scan is now built, so the scan phase row is measured and `terminal_status`
  derives `assessed:partial` on an admitted run. **2026-08-13 (E-46 plan 3):**
  the scan phase's own thirteen signals all report. **2026-08-15 (E-48 plan 2/3):**
  the stub count dropped from five to four and `PHASE_OWNER` lost its `DISCOVER` entry
  — discover is now built and runs measured end-to-end. **2026-08-16 (E-49 plan 1/2):**
  the stub count dropped from four to three and `PHASE_OWNER` lost its `ASSESS` entry
  — assess is now built and the phase is measured with deterministic score + judged proposer layer.
  **2026-08-17 (E-49 plan 3):** the assess phase is complete; the stub count is unchanged at three (report, generate, finish).
- [x] **FR-912** deterministic scan memoized on `(tree hash, signal version)`; cross-source confidence (E-46). **All three plans landed (2026-08-12, 2026-08-13).** The memo key is `(tree_hash, signal_version, rules_sha)` — `rules_sha` beyond the specified two terms, hashed transitively over shared rule modules and consumed signals, because a hand-maintained version int misses a real input (spec D10). All thirteen signal rows report and every body computes or inherits; `OWED_BY` is empty. Cross-source confidence is live and derived (D8), and now reaches HIGH: S2 and S4 produce, so S5 can merge three or more distinct sources.
- [x] **FR-913** `CapabilityMap` with stable ids + coverage floor + orphan classification — **also satisfies FR-102** (E-47a/E-47b/E-47c/E-48). **All three plans of E-48 landed 2026-08-15**, wiring the complete discover phase into `AssessmentWorkflow`: context building, baseline dispositions, identity lock, finalize with attribution/decomposition/ownership, proposer judgment, quote/ref verification, citation guard, blueprint comparison, and derived domain model. **Identity half landed 2026-08-08 (E-47a):** surrogate `BC-NNN` ids, weighted-Jaccard re-attachment, audited `IdentityCorrection` (`src/sdlc/capability/`). **Coverage floor + orphans landed 2026-08-13 (E-47b):** attribution and orphan classification in `src/sdlc/assessment/discover/`. **L2 + entity ownership landed 2026-08-14 (E-47c):** `decompose()` and `assign()` in `src/sdlc/assessment/discover/`.
- [x] **FR-914** byte-exact quote verification against the pinned commit, fail-closed — shares FR-107's verifier (E-43). **Landed 2026-08-06 (E-43) and fully closed 2026-08-15 (E-48 plan 3):** `verify_discover_refs` byte-verifies every evidence path and quote against the pinned commit using `Profile.VERBATIM_BYTES` before dispositions are applied, and a citation guard fails closed if the fabrication rate exceeds 0.10.
- [ ] **FR-915** `not_collected` / `unknown` vs measured value (E-40). *Contract half landed 2026-08-06 (`measurement.py`, retrofitted onto `CoverageReport`/`SecurityReport`/`claim_survival_score`; `QAReport.coverage_pct` deleted) — see spec `docs/superpowers/specs/2026-08-06-measurement-and-shared-grounding-verifier-design.md`. The `RepoTriage`/triage half is deferred to E-41; the load-bearing case was the SARIF-malformed-reads-as-clean hole on the absolute floor. **E-44 adds a second consumer:** `compute_delta` reads `SignalResult.collected.state` and emits `UNVERIFIABLE` whenever a side did not collect, so a triage that timed out on the after side cannot read as "all findings fixed".*
- [x] **FR-916** STRIDE + vuln classification + control coverage + composites with 1–3 specific drivers (E-49). **Per-capability half landed 2026-08-16 (Plans 1 and 2):** deterministic baseline composites, severity, factors, rules_sha, memo caching, lifted quote verifier to `assessment/verification.py` (RD6), proposer models and contracts, `render_risk_prompt`, `apply_judgment` with layer-scoped degradation (RD7), `risk` role, memo seam and cache key extension (P2-D3), and `verify_risk_refs` activity. **Plan 3 landed 2026-08-17 (the system view):** the capability→capability projection over `attribution.graph.edges`, shared vulnerabilities keyed on the path-excluded weakness class, bounded cascades from high-security-composite origins, and trust-boundary and privilege-escalation candidates enumerated by code and dispositioned by the proposer. Known limit, stated and tested: escalation chains are authentication-gated, not authorization-gated, because RD5 leaves Authorization with no scan source.
- [ ] ⚠️ **FR-917** risk thresholds as deterministic gate checks; FP dispositions as audited overrides (E-50). *Landed 2026-09-02 (E-50):* the two live clauses — unaccepted confirmed vulnerability and high-criticality testability blocker — are computed by pure code (`assessment/gates/`) into a `RiskGateReport` that gates the workflow on BLOCK, and dispositions persist across re-runs as audited FR-304 decisions (`src/sdlc/dispositions/` + `sdlc risk dispose`). ⚠️ remains: the composite-threshold clauses (BLOCK ≥ 0.8, WARN 0.6–0.79) are implemented per-capability but carried in `deferred` until E-56 — the roadmap's own RD3 note, now enforced in code rather than merely documented.
- [ ] **FR-918** acceptance criteria computed by code, not self-asserted; cross-reference integrity **absolute** (E-51).
- [ ] **FR-919** spec seeds → brownfield child runs; seed criteria become run acceptance criteria (E-53).
- [ ] **FR-920** re-assessment, incremental re-scan, per-capability risk delta as first-class output (E-54).
- [ ] **FR-921** evidence bundle: manifest + five role reports + verification status + gates + fix-run sessions (E-52).
- [ ] **FR-922** per-phase budgets; exhaustion escalates, partials marked partial (E-55).

### Service platform (FR-1000) *(new scope; PRD v1.1)*

- [ ] **FR-1001** tenancy by construction — namespace + store prefix + bank namespace; resolves OQ-4 (E-58).
- [ ] **FR-1002** untrusted-code isolation — per-run container, non-root, network-level egress allowlist. **Precondition for any external tenant** (E-21 + E-57).
- [ ] **FR-1003** token vault — envelope encryption, per-tenant keys, zero plaintext persistence (E-59).
- [ ] **FR-1004** metering + billing — per-run token / compute / wall-time tracking; per-tenant quota enforcement (E-60).
- [ ] **FR-1005** audit log — append-only, tamper-evident hash chain for all customer actions (E-61).
- [ ] **FR-1006** customer dashboard backend — tenant-isolated query APIs over assessments, runs, and gates (E-62).
- [ ] **FR-1007** customer webhook delivery — guaranteed at-least-once with HMAC signing and exponential backoff (E-63).

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
- [ ] **NFR-9** Hostile input — the factory currently assumes repositories are its own. Build scripts, test code, and manifests of a connected repo are attacker-controlled and executed (E-57). **E-41's build probe is the first stage that knowingly executes a foreign repository's code** (bounded, in a throwaway clone, as the worker user with network access). **E-44 widens the exposure:** the tidy-up fix runs execute the triaged repository's own build and test commands (not just the probe), as governed `FeatureWorkflow` children. Still operator-run only until E-57/E-21. **E-46 (2026-08-12)** adds no new execution of repository code: every scan signal is a blob read at the pinned commit. **E-46 plan 3 (2026-08-13)** adds no execution either: QS2 parses a committed Cobertura report rather than running the suite, and QS4 parses pipeline files rather than running them. **E-47b (2026-08-13)** adds no execution of repository code: every input is a parameter and the graph is built from blobs already read. **E-47c (2026-08-14)** adds no execution of repository code: every input is a parameter, as E-47b. **E-48 (2026-08-15)** adds no execution of repository code: `verify_discover_refs` reads committed blobs via `git show` at the pinned commit, and `load_blueprint` reads a factory-shipped reference file. **E-49 plan 1 (2026-08-16)** adds no execution of repository code and no tree read at all: every input is projected from the `CapabilityMap`. **E-49 plan 2 (2026-08-16)** adds no execution of repository code: `verify_risk_refs` reads committed blobs via `git show` at the pinned commit (RD6). **E-49 plan 3 (2026-08-17)** adds no execution of repository code and no tree read: the projection is a re-index of `member_paths` against a graph discover already built.
- [ ] — **NFR-10** Assessment reproducibility — not falsifiable until the assessment exists; the deterministic half is E-41/E-46, the fused-layer variance half needs runs. **E-46 plan 3 (2026-08-13):** the deterministic half is now asserted for every pure signal module (`test_every_pure_signal_module_is_order_independent`), not only the capability chain. **E-47b (2026-08-13):** two more pure modules (`discover/refgraph.py`, `discover/attribution.py`) carry their own byte-identical-across-input-order assertions in their own test files. **E-47c (2026-08-14):** two more pure modules (`discover/operations.py`, `discover/ownership.py`) carry their own byte-identical-across-input-order assertions. **E-48 plan 3 (2026-08-15):** three more pure modules (`discover/verify.py`, `discover/blueprint.py`, `discover/domain.py`) carry their own order-independence assertions in their own test files. **E-49 plan 1 (2026-08-16):** five more pure modules (`risk/severity.py`, `risk/controls.py`, `risk/factors.py`, `risk/composites.py`, `risk/build.py`) carry their own order-independence assertions in their own test files. **E-49 plan 2 (2026-08-16):** three more pure modules (`risk/prompt.py`, `risk/apply.py`, `assessment/verification.py`) carry their own order-independence assertions. **E-49 plan 3 (2026-08-17):** one more pure module (`risk/crosscap.py`) carries its own order-independence assertions, and `build()`'s own byte-identical assertion now covers the system view.

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
- [ ] — **SC-7** grounding integrity: 100% of `grounded` findings re-verify byte-exact, zero fabricated path/line refs — **the assessment product's SC-5**: one violation is a defect, not a percentage. Mechanism is E-43 / E-48 (2026-08-15): zero fabricated references is now computed and enforced on every run via the citation guard in `verify_discover_refs`, not only sampled.
- [ ] — **SC-8** capability coverage ≥90% with classified orphans on ≥80% of readiness-passing repos — needs **E-47a + E-47b** (the coverage floor and orphan classification are E-47b; it needs E-47a's identified capability set to classify against) + a corpus. Not E-47c. **(2026-08-14):** E-47a/b/c are all done; the blocker narrows to a corpus of readiness-passing repos.
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
- [ ] ⚠️ **US-7** conversational gate approval — chat agent shipped (E-86, 2026-08-20); MCP server pending (E-11).

- [x] **US-9** client approves a tidy-up backlog → PR per item + before/after delta (E-44). `TidyUpWorkflow` opens a `tidy_up` gate with the backlog rendered, `select_items` narrows it, each accepted item becomes one governed fix run, and `compute_delta` records the before/after.
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
- [ ] ⚠️ **ADR-8** Interfaces as stateless shells — true for CLI. **Two documented exceptions, both deliberate:** the agent board API (E-78) serves durable cross-run state no live workflow holds (ADR-21); and the dashboard backend (E-10) holds an in-process fleet poller and subscriber set — not durable state, but not a stateless shell either. The poller exists because a per-request fan-out costs `N_clients × N_runs` while one shared poller costs `N_runs`. ARCHITECTURE.md §8 scopes the claim accordingly.
- [ ] **ADR-9** Two worker pools by capability — single queue.
- [ ] ⚠️ **ADR-10** Claim-check for large payloads — `ArtifactRef` exists but not load-bearing.
- [ ] ⚠️ **ADR-11** Deterministic DAG — holds for the 8 live stages; 6 stages absent.
- [x] **ADR-12** Contract-first, clean-context validators — QA ✅ and review ✅ both clean-context. **(now complete)**
- [x] **ADR-13** Serial-by-default; resume-bounded; context by reference (`near_context_ceiling` wired).
- [x] **ADR-14** Integration by running branch (fully wired).
- [x] **ADR-15** Language-agnostic toolchain by marker file (`src/sdlc/toolchain/`) — Python reference adapter end-to-end; Go/TS/Rust are E-30a/b/c.
- [x] **ADR-16** Harness sessions as first-class, claim-checked artifacts (E-38).
- [x] **ADR-17** Containment as a declared harness capability — native inner, hook outer, fail closed (E-15/E-16).
- [x] **ADR-18** Triage precedes capability modelling — an unbuildable or structurally-illegible repo is reported as a precondition failure, never capability-mapped (FR-903, E-42). *The readiness gate enforces it; E-45's Tier 2 admission rule (`triage/admission.py`, `require_human=True`) refuses a non-human override, so a `policy`/`timeout` approval no longer admits an audit.*
- [ ] ⚠️ **ADR-19** Deployment targets and analytics sources are adapters, not substrate (FR-1105, NG7, E-68/E-69). **Deployment half done** (E-67/E-68: `src/sdlc/deploy/adapters.py`, compose + script). Analytics half open (E-69). Unresolved consequence: **OQ-9**.
- [ ] **ADR-20** Pre-registration reuses `ValidationContract` freeze semantics (FR-1102, FR-803, E-65).
- [x] **ADR-21** Agent board as a durable projection; `authoritative_status` (workflow-written) vs `status` (agent-writable) keeps replay the source of truth (E-78).

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

## 9. Epics, by group

The per-epic detail lives in `docs/roadmap/`. This file keeps what is read
end-to-end — phase summary, requirements, criteria, ADR index, and the
ranked next increments above. Each file below tracks what is true on `main`;
in-flight work lives in its design doc until merge.

| Group | File |
|---|---|
| Filesystem-first work items (`E-`) | [`filesystem-first.md`](docs/roadmap/filesystem-first.md) |
| Tier 0 — repository triage & tidy-up (`E-40`…`E-44`) | [`tier-0-triage.md`](docs/roadmap/tier-0-triage.md) |
| Tier 2 — the EDCR port (`E-45`…`E-56`) | [`tier-2-edcr.md`](docs/roadmap/tier-2-edcr.md) |
| Service platform (`E-57`…`E-63`) | [`service-platform.md`](docs/roadmap/service-platform.md) |
| Product outcome (`E-64`…`E-71`) | [`product-outcome.md`](docs/roadmap/product-outcome.md) |
| Pipeline as data (`E-72`…`E-77`) | [`pipeline-as-data.md`](docs/roadmap/pipeline-as-data.md) |
| Suggested ordering across the groups | [`ordering.md`](docs/roadmap/ordering.md) |
| Agent board (`E-78`) | [`agent-board.md`](docs/roadmap/agent-board.md) |
| The crew (`E-88`) | [`crew.md`](docs/roadmap/crew.md) |
