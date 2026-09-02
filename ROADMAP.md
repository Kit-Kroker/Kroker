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
  `docs/deveval-import-report-2026-08-09.md`. **Six of ten repos committed;
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
- [x] **E-41 — deterministic hygiene signals** → FR-902, FR-108.
  *Contracts + seam + three signals landed (2026-08-06):* `src/sdlc/triage/`
  ships `RepoTriage`/`TriageFinding`/`Readiness` (closing the half **E-40**
  deferred here), a one-activity-per-signal seam, and **build probe**,
  **secret scan** (including client-bundle-reachable credentials) and
  **baseline practice**. Readiness is three-valued: any dimension that is not
  MEASURED forces `INDETERMINATE`, so an unmeasured repository can never read
  as ready for the FR-903 gate. The build probe **executes the triaged
  repository's own code** in a throwaway clone at the pinned commit — an
  operator-authorization trust boundary, not a solved one (see NFR-9; removed
  by E-57/E-21). Spec
  `docs/superpowers/specs/2026-08-06-repository-triage-hygiene-signals-design.md`,
  plan `docs/superpowers/plans/2026-08-06-repository-triage-hygiene-signals.md`.
- [x] **E-41a** dependency health — unpinned / duplicated / known-vulnerable /
  unused direct dependencies behind the FR-108 adapter's `manifests` and
  `ecosystem`. The advisory database is an `AdvisorySource` seam whose
  default collects nothing: a lookup that did not happen reports
  `not_collected`, never zero vulnerabilities. `OsvAdvisorySource` is the one
  reference implementation, opt-in and off by default.
- [x] **E-41b** dead and generator-scaffold code, and **the new owner of
  `structure_discernible`** — `compute_readiness` admits exactly one signal
  per readiness key, so the dimension moved off `baseline` (now v2) rather
  than being reported twice. Detection is fingerprint-first with git history
  corroborating severity only: history alone misfires hardest on the
  single-initial-commit repositories Tier 0 targets. **The floor is raised,
  not removed** — a repository that is entirely untouched output of a
  generator we hold no fingerprint for still passes the dimension.
- [x] **E-41c** framework-default misconfiguration — permissive CORS, debug
  mode, wildcard `ALLOWED_HOSTS`, the Django placeholder `SECRET_KEY`, and
  world-readable storage rules. `unauthenticated_app` is whole-application
  scoped and fires once per repository; per-route auth reasoning is E-46/E-49.
  `secrets` (now v2) excludes the Django placeholder, so one line yields one
  finding from one signal.
- [x] **E-41d** size and duplication outliers — absolute adapter-supplied
  thresholds, not percentiles, so the numbers survive E-44's before/after
  delta. Both size rules are STRUCTURAL.
- [x] **E-42 — `TriageWorkflow` + readiness verdict + readiness gate** → FR-901,
  FR-903. Readiness (buildable / runnable / tests present / structure
  discernible) computed from deterministic signals **only**, so triage completes
  on a repository where an LLM would have nothing to reason about. An
  unbuildable repo is a finding, not an error. The gate resolves through the
  FR-301/302 machinery, so an operator can override with an audited decision.
  *Landed (2026-08-08).* Two sub-decisions worth recording because neither was
  in the roadmap's one-line description: **(D2)** `FeatureWorkflow`'s gate
  mechanics were extracted into a `GateHost` mixin (`src/sdlc/workflows/gates.py`)
  so a second workflow can host a gate without restating FR-302's
  first-decision-wins rule; **(D8a)** `SignalSpec.readiness_keys` declares which
  readiness dimensions each signal owes, so a skipped or failed signal reports
  `not_collected` for exactly those keys rather than leaving the dimension
  unreported. Spec
  `docs/superpowers/specs/2026-08-08-triage-workflow-and-readiness-gate-design.md`,
  plan `docs/superpowers/plans/2026-08-08-triage-workflow-and-readiness-gate.md`.
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
- [x] **E-44 — tidy-up fix runs + re-triage** → FR-904, NG5. Spec `docs/superpowers/specs/2026-08-09-tidy-up-fix-runs-and-re-triage-design.md`, plan `docs/superpowers/plans/2026-08-09-tidy-up-fix-runs-and-re-triage.md`.
  `mechanically_fixable` findings become brownfield `FeatureWorkflow` child runs
  (one PR per accepted item, never a direct patch), then triage re-runs and the
  before/after delta is recorded. This is the first end-to-end proof of the
  assess → fix → prove loop, on the cheapest and lowest-risk class of fix.
  Three sub-decisions the one-line summary did not contain: **`SeededWork`** (D1)
  — a deterministic `ArchitectureSpec` + `ImplementationPlan` that enters
  `FeatureWorkflow` at stage 4, skipping the six proposer calls stages 0–3 would
  make for a one-line fix; **`UNVERIFIABLE`** (D5) — `compute_delta` is
  deliberately not a set difference, so a signal that timed out on the after
  side cannot read as having fixed everything it found; **the verification
  branch** (D6) — `build_verification_branch` constructs the "if you merged all
  of these" tree, because `open_pull_request` opens PRs and does not merge them.
- [x] **E-84 — Brownfield intake, context, and checked delta** → FR-102. *Landed 2026-08-15.*
  Lifts `scan_tree()` fan-out to shared workflow code across audit and feature pipelines (D1/D5);
  pure `classify()` and `classify_repo` activity (D3); `CodebaseMap` projected from scan tree (D1);
  bounded prompt rendering `render_for_prompt()` (D12); typed `BrownfieldDelta` (added/modified/removed) (D7/D8/D9);
  activity-side tree listing `check_brownfield_delta` (D8); stages 0 and 2 wired in `FeatureWorkflow` (D3/D4/D6);
  and architecture stage delta grounding check with 1 retry before failing closed (D10/D11).
- [x] **E-85** MAC-style clarification fan-out (`src/sdlc/clarify/`): the clarify
  stage becomes supervisor → N dimension probes → pure merge, behind
  `clarify_probes_enabled` (default off). Ports MAC (IWSDS 2026), whose
  both-levels configuration beat no-clarification 62.3 vs 54.5 on MultiWOZ 2.4
  *while cutting* turns 6.53 → 4.86; SWE-RPG's C1–C6 taxonomy supplies the
  dimensions, since "implement a software feature" is one domain in MAC's
  terms. SWE-RPG attributed 24.5–46.0% of coding-agent failures to requirement
  clarification, with 42–54% coverage on interface specs and data semantics —
  dimensions our clarifier could not reach at all, having no repo access.
  **Phase 1 only:** inside the stage boundary, one human round-trip, no DAG
  change. Phase 2 (escalation at architect/planner/dev) is designed for and not
  built, so the taxonomy gain and the timing gain stay separately measurable.
  ⚠️ **The A/B has not been run.** MAC's gain came WITH shorter dialogues; six
  probes naturally push question volume the other way, and `clarify_question_cap`
  (default 5) plus `dropped` are the guard. Do not default the flag on before
  dimension coverage and the SC-4 human-answered rate are read together.
  Spec: `docs/superpowers/specs/2026-08-20-e85-mac-clarification-fanout-design.md`;
  plan: `docs/superpowers/plans/2026-08-20-e85-mac-clarification-fanout.md`.

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

- [x] **E-45 — `AssessmentWorkflow` EDCR DAG shell** → FR-911. *Landed
  2026-08-10.* init → scan → discover → assess → **report** → generate →
  finish, with six phase bodies deliberately unbuilt (scan E-46, discover
  E-48, assess E-49, finish E-51, report/generate E-52), each reporting
  `not_collected` naming the item that owes it. Two deliberate deviations
  from the source methodology: **(a)** `report` runs *after* `assess` —
  reports render risk scores only `assess` produces; **(b)** `workflow.json`
  is **not ported** — its `phases[].status/started_at/completed_at` is a
  hand-rolled durable state machine, which is what Temporal history already
  is. `/enrich`, `/gate` and `/validate` are not stages (→ E-56, E-50, E-53).
  Three sub-decisions the one-line description did not contain:
  **(D2)** the **admission rule is one function at two strictnesses** —
  `triage/admission.py:admits(triage, *, require_human)`, with Tier 0's
  `backlog.admitted` delegating at `False` and Tier 2 passing `True`. This
  closes the `FUTURE-CONSUMER TRAP` `workflows/tidyup.py` documented: the
  after-triage auto-approves its own OFF gate, so
  `TidyUpReport.after.override.approved_by == "policy"`, and E-42's broader
  rule would have admitted a tree nobody approved. Two copies of the rule
  would agree only by coincidence, so the strictness is a parameter.
  **(D3)** `init` runs a **`TriageWorkflow` child** and never accepts a
  `RepoTriage` as input — the rule's whole subject is `override.approved_by`,
  and a caller-supplied artifact is a caller-supplied value for exactly that
  field. **(D6)** `terminal_status` is **derived**, so E-46 landing flips
  `admitted:no-phases-implemented` → `assessed:partial` with no workflow
  edit. Spec
  `docs/superpowers/specs/2026-08-10-assessment-workflow-edcr-shell-design.md`,
  plan `docs/superpowers/plans/2026-08-10-assessment-workflow-edcr-shell.md`.
- [x] **E-46 — scan phase** → FR-912. S1–S5 capability signals, SS1–SS4
  security, QS1–QS4 QA. Cross-source confidence: three or more independent
  sources = high, two = medium, one = low — never the depth of one source. Memo
  key `(repository tree hash, signal version)` per FR-103, so re-assessing an
  unchanged repo is a cache hit and editing one signal's logic invalidates
  exactly that signal. **Plan 1 landed 2026-08-12:** contracts, `SCAN_SIGNALS`,
  the memoized activity seam, and the five inherited halves
  (`src/sdlc/assessment/scan/`). **Plan 2 landed 2026-08-13:** S1, S3, S5 and
  the shared `naming.py` rules — the capability core, so `ScanResult.candidates`
  carries real merged candidates and the memo has its first production caller
  (every plan-1 stub was refused by `store`'s not-MEASURED rule). **Plan 3
  landed 2026-08-13:** all thirteen signals compute or inherit; `OWED_BY` is
  empty. The plan-3 decisions worth carrying: **P3-D3** — SS4 declares `consumes
  (S2, S3)`, because `accessed_by` cites S3 and an undeclared read would also be
  an unhashed input; **P3-D5** — a wave-2 signal is never memoized when its
  upstream degraded (SS1 can be MEASURED while `input_validation` is
  `not_collected` because S3 timed out); **P3-D7** — env drift is CI-vs-config,
  because the declared-scope comparison BrownKit makes needs `/enrich`'s
  `qa_scope` (E-56); and **P3-D12** — SS4 owns two categories (`data_sensitivity`
  + `entity_access`) so an empty `accessed_by` cannot read as "no entry point
  touches PII". Two plan-2 decisions: **S3 fails closed** on a
  recognized-but-unfingerprinted framework (P2-D1) — `_unmeasured_carries_no_payload`
  makes a partial Contract tier unrepresentable, and D5 prefers absent to
  partial; and the **name tables live in `naming.py`**, so S1 declares it as a
  `rule_module` (P2-D2) or editing a layer word would move S1's output without
  moving its key. **Review pass (2026-08-13):** three findings, all a gap
  reported as a zero — fixed before merge. `_blobs_for` now returns
  `(blobs, skipped)` and every content signal reports `not_collected` naming
  an unread blob rather than a partial-as-complete count (spec §6, the S1
  `loc_metric` precedent); QS4 reports `ci_stages`/`env_drift` `not_collected`
  for a CI file that refused to parse, not `measured(0)`; and SS1/SS3 skip
  test paths like QS3. S3 still scans test files — same species, plan-2 scope,
  flagged for a follow-up. **E-47c (2026-08-14, D10):** `route_object` +
  `PATH_PREFIXES` moved from `entrypoints.py` into `naming.py` for E-47c's
  second consumer, which moves the memo keys of all six `_NAMING` signals
  (S1, S2, S3, S4, S5, SS4) once by the edit — `test_scan_rules_sha`
  asserts exactly this coupling.
- **E-47 — `CapabilityMap`** → FR-913, **FR-102**. **Split three ways
  2026-08-08**; the single item carried four independent clauses and was too
  large for one plan. **This is where the assessment product and the core
  pipeline converge**: together they satisfy FR-102's `CodebaseMap`, so building
  them for the audit also unblocks P2 brownfield feature runs. FR-102 needs all
  three, not E-47a alone.
  - [x] **E-47a — capability identity** → FR-913. Stable `BC-NNN` as a
    **surrogate** key: allocated once, persisted with its fingerprint,
    re-attached on later scans by weighted-Jaccard similarity over signal tiers
    ordered by cost-to-change (contract > behavioral > structural > locational).
    Greedy one-to-one assignment, not Hungarian — an id clients cite must not
    move because an unrelated capability's score changed. Board authoritative;
    `.sdlc/capabilities.json` is a hash-only export (a digest cannot drive
    similarity matching). Ambiguity is decided deterministically and reversed by
    an audited `IdentityCorrection` modelled on `gate.py`'s `GateOverride` —
    CLI-only until **OQ-11** closes, since `X-Actor` is self-asserted.
    **Resolves OQ-6.** Amends FR-103 (§2). Does not block on E-48: the
    matcher is pure and tests against synthetic fingerprints.
    Design: `docs/superpowers/specs/2026-08-08-oq6-capability-identity-design.md`.
  - [x] **E-47b — coverage floor + orphans** → FR-913. file→capability coverage
    floor (default 0.90), orphans classified attached | infrastructure | dead.
    Needs E-47a — an orphan is defined against an identified capability set.
    **Landed 2026-08-13.** Pure and unwired by design (D1): `_discover` still
    reports `not_collected` naming E-48, which calls `attribute()` when it
    lands. The two decisions worth carrying: the denominator is **strict**
    (every `SOURCE_EXTENSIONS` blob, tests and build tooling included) while
    the numerator is **accounted-for** (members + infrastructure + attached),
    so the floor means *the tree is explained* rather than *the tree is
    capability-owned*; and `dead` requires **four** clauses (parsed language,
    zero inbound edges, not framework-discovered, tree-wide resolution
    healthy), because it is the one orphan verdict a customer acts on by
    deleting code. D6 buys breadth with a shallow regex table and pays for it
    in dynamic references;
    `test_known_false_positive_a_dynamic_reference_reads_as_dead` pins that
    cost as a test rather than a caveat. Spec
    `docs/superpowers/specs/2026-08-13-e47b-coverage-floor-and-orphans-design.md`,
    plan `docs/superpowers/plans/2026-08-13-e47b-coverage-floor-and-orphans.md`.
  - [x] **E-47c — L2 operations + entity ownership** → FR-913. L2 decomposition,
    entity ownership (exactly one owner or a surfaced conflict). Needs E-47a.
    **Landed 2026-08-14.** Pure and unwired (D1): E-48 calls `decompose()` and
    `assign()`. Decisions worth carrying: operations are one-per-contract-member
    (D3) so each resolves to a byte range; `OperationVerb` and `OwnershipVerb`
    stay separate and **`TRACKS` is not emitted** (D6) because it has no
    deterministic trigger; ownership is declaration → writes → reads with ties
    surfaced (D7); and `CONFLICT`/`UNDIRECTED`/`UNCLAIMED` are three outcomes
    (D8) so a CLI-written table never reads as untouched. Spec
    `docs/superpowers/specs/2026-08-14-e47c-l2-operations-and-entity-ownership-design.md`,
    plan `docs/superpowers/plans/2026-08-14-e47c-l2-operations-and-entity-ownership.md`.
    **Review pass (2026-08-14, before merge):** eight findings, the worst
    being a fabricated non-route `object` (`head_token` on a command name
    returns the verb) that made CLI-written tables read as `UNCLAIMED`.
    Fixed via `L2Operation.entity_keys`: route kinds match strict (only they
    carry directed verbs), undirected kinds match on reduced binding tokens.
    Also: S3 now reads Flask's `methods=` kwarg (v2) so a POST route is a
    write; `claimants` carries every toucher so E-48's proposer sees the
    loser; `tied_declarers` names cross-file ties; a degraded `decompose()`
    names no zero counts; the decompose→assign seam is tested
    (`tests/test_discover_seam.py`). Corrections recorded in the spec's
    "Review corrections" section.
- [x] **E-48 — discover proposers** → FR-913. **All three plans landed (2026-08-15).**
  D1 cohesion/coupling/boundary clarity; D2 action per candidate (`CONFIRM | SPLIT | MERGE | DE-SCOPE | FLAG`); D3 coverage verification with orphan disposition; D4 lock; D5 L2 decomposition with entity ownership (`OWNS / CREATES / MANAGES / TRACKS / READS`); D6 security context; D6a QA context using E-40's `not_collected`; D7 consolidated domain model; D8 industry-blueprint comparison where `MISSING` is context, not failure. Proposer references and quotes verified against the pinned commit with fail-closed citation guard. Guardrail worth porting verbatim: *delivery channels and deployment boundaries are not capabilities*. Plan 1: models, context packet, baseline dispositions; Plan 2: lock activity, attribution/decomposition/ownership finalize activity, memo caching, deterministic map build; Plan 3: `discover` role, reference verification, citation guard, APQC PCF blueprint comparison, domain model derivation, and assessment workflow wiring.
- [x] **E-49 — `UnifiedRiskMap` + risk proposers** → FR-916. Conforms to the
  `unified-risk-map` v1.0 schema: composite in [0,1] or an `unknown`/`partial`
  sentinel; drivers `minItems: 1, maxItems: 3` with a real minimum length, so a
  generic label cannot pass as a driver. STRIDE per capability with explicit
  rationale for inapplicable categories; vulnerabilities `confirmed | probable |
  potential`; five control families; cross-capability shared vulnerabilities,
  cascading failures, weak trust boundaries, privilege-escalation chains.
  **Plan 1 landed 2026-08-16:** the deterministic score — criticality, severity from a table, control coverage, factors and composites — so `PHASE_OWNER` loses its `ASSESS` entry and the phase is measured with no model in the loop. Two decisions worth carrying: **RD3** — defect density and change velocity have no source, so the QA composite and therefore the unified composite are partial on every run, and FR-917's composite BLOCK clause waits on E-56 while its other two fire; **RD5** — SS1 collapses authn and authz and nothing collects monitoring presence, so two of five control families report `not_collected` rather than mirroring a sibling.
  **Plan 2 landed 2026-08-16 (the judgment layer):** lifted shared quote verification to `assessment/verification.py` across both discover and risk (RD6); structured proposer contracts with `UnifiedRiskMap.judgment` tracking; layer-scoped degradation where proposer or citation failures leave baseline composites measured and degrade `judgment` with distinct non-converging reasons (RD7, P2-D2); store guard refusing to cache degraded judgment under a proposer key so transient failures cost one recompute rather than freezing unjudged maps into cache (P2-D3); and fixed the worker activity registration gap with structural registration tests ensuring workflow calls cannot silently degrade (P2-D1).
  **Plan 3 landed 2026-08-17 (the system view):** the capability→capability projection over `attribution.graph.edges`, shared vulnerabilities keyed on the path-excluded weakness class, bounded cascades from high-security-composite origins, and trust-boundary and privilege-escalation candidates enumerated by code and dispositioned by the proposer. Known limit, stated and tested: escalation chains are authentication-gated, not authorization-gated, because RD5 leaves Authorization with no scan source.
- [x] **E-50 — assessment gate checks** → FR-917, FR-106, FR-304.
  BLOCK on a confirmed unaccepted vulnerability, a testability blocker in a
  high-criticality capability, or composite ≥ 0.8; WARN 0.6–0.79; else PASS.
  False-positive dispositions (`false_positive | mitigated_elsewhere |
  accepted_risk`) become audited overrides that persist across re-runs.
  *Landed 2026-09-02 on `feat/e50-assessment-gate-checks`.* Spec
  `docs/superpowers/specs/2026-09-01-e50-assessment-gate-checks-design.md`,
  plan `docs/superpowers/plans/2026-09-01-e50-assessment-gate-checks.md`
  (spec and plan each survived an independent review round before
  implementation; the finished diff a third, with four defects fixed). The
  gate opens between ASSESS and REPORT through `GateHost`, on BLOCK only
  (WARN never opens a gate, GD4): APPROVE stamps a this-run
  `RiskGateOverride`, REJECT leaves REPORT/GENERATE/FINISH `skipped()` with
  FR-917-naming reasons while `terminal_status` still derives `PARTIAL`
  (GD1/GD2 — no new DAG stage, no new status). Decisions worth carrying:
  **"unaccepted"** is defined against `FindingDisposition` — `kind:
  vulnerability | testability`, `(project, kind, key)` primary key in the
  board's SQLite, CLI-only surface per OQ-11 — so a testability blocker,
  not just a vulnerability, can be dispositioned across re-runs; **the
  composite-threshold clauses** evaluate per-capability with
  worst-instance semantics but land in `RiskGateReport.deferred` until
  E-56 gives the QA composite its source (RD3) — an unmeasured clause
  never reads as a pass (FR-915), and the confirmed-vulnerability clause
  likewise defers when `judgment` did not collect, because CONFIRMED is
  only reachable through the proposer (baseline rows are POTENTIAL).
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
- [ ] **E-75 — graph queries on the dashboard backend** → FR-1204. **Superseded in part 2026-08-18:** E-10 built the backend, so this narrows to adding `graph_state()` and `graph()` beside the existing queries once `GraphWorkflow` exists. The "dashboard backend remains" half of P2 is closed; what is left here is graph-shaped run state, which needs E-74 first. The only storage is still content-addressed `graphs/<sha>.yaml`.
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
- **OQ-11 — dashboard auth.** ⚠️ **Now live, not hypothetical (2026-08-07).**
  E-78's board API is already serving unauthenticated, and its two agent write
  routes trust a self-asserted `X-Actor` header — so the audit log's "who moved
  what" is spoofable by anything that can reach the port. Localhost-bind is the
  current containment. Was framed as: E-75 is the first server in the project, and
  *"start a run"* and *"approve a merge gate"* are not endpoints to leave
  unauthenticated once anything but localhost can reach them. Localhost-bind with
  no auth is the assumed near-term answer; **E-60** (identity & authorization,
  FR-1004) is where it stops being acceptable.
  **2026-08-18 (E-10):** a *second* unauthenticated surface now serves, and this
  one can start runs and approve merge gates. Operator identity is the
  self-asserted `X-Actor` header landing on `GateDecision.reviewer` — never on
  `decided_by`, which stays `Literal["human","policy","timeout"]` so
  `ReadinessOverride.approved_by` keeps distinguishing a machine approval from a
  human one. Localhost-bind remains the whole containment.
- **OQ-P5..P8 — prompt-gate sensitivity (E-83).** Tracked in the eval spec's §9
  (`docs/superpowers/specs/2026-08-12-judge-sensitivity-and-plan-adherence-design.md`),
  not duplicated here. **OQ-P5 answered:** the gate has teeth — `scope_dropped`
  fails absolutely via the `scope_preserved` veto (proven end-to-end through
  real promptfoo). An earlier draft mis-recorded it as PASS due to a
  veto-engine substring false negative (since fixed to word-boundary matching);
  see spec §9's correction. New: OQ-P6 (veto authorship is manual/unenforced),
  OQ-P7 (`PlanDrift` has no baseline yet), OQ-P8 (phase-1 step caching vs judge
  nondeterminism).
- **OQ-12 — S5 normalization is English-centric.** Layer-suffix stripping and
  singularization assume English identifiers, so a non-English codebase degrades
  to LOW-confidence single-source candidates. Recorded rather than solved:
  calibrating it needs the corpus SC-8 also needs.

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
2. ~~**E-41 → E-42 → E-44**~~ — triage and tidy-up. **Landed.** The chain is
   closed: E-44's `TidyUpWorkflow` is the first item that proves the whole
   assess → fix → prove claim end to end, almost entirely deterministic, needing
   neither tenancy nor containment because it is operator-run. (Verification
   debt: the `TidyUpWorkflow` temporal e2e is deferred — see P5's note.)
3. **E-47a → E-47b/E-47c** — `CapabilityMap`. Unblocks P2 brownfield
   whether or not the audit ships, which makes it the highest-leverage item in
   §11. **OQ-6 settled 2026-08-08** — the blocker is cleared and the item is
   ready to plan. **E-46 landed 2026-08-13**, so the pairing is now just
   E-47b/E-47c. Take **E-47a first**: it resolves identity, the other two
   attach findings to it, and it is the only one of the three that needs no
   proposer (pure matcher, synthetic-fingerprint tests). FR-102 still needs all
   three.
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

---

## 16. Agent board — persistent artifact & task state (`E-78`) → FR-1300…FR-1303

**Landed 2026-08-07.** Spec: `docs/superpowers/specs/2026-08-07-agent-board-design.md`.
Contracts: `src/sdlc/board/`. ADR-21.

> ⚠️ **Numbering correction.** Code comments introduced with this work label it
> `E-40` (`feature.py` `BOARD_ACT`, `models.py` `PipelineConfig.project_key`).
> **E-40 is already `Measurement` + `RepoTriage` contracts** (§10). The board is
> **E-78**; those comments are stale and should be corrected in place.

**Problem it closed.** Typed stage artifacts (`ClarifiedRequirements`,
`ArchitectureSpec`, `ImplementationPlan`, `DevTask[]`) reached only five
destinations — Temporal history, the next stage's prompt, a hash-keyed
memoization file, a one-line memory summary, and a `StageOutcome` row carrying
no content. Answering *"what design did run 019fb994 propose?"* required a
replay, and no task had a status anything could query mid-flight.

- [x] **FR-1300 — project-level artifact versioning.** `requirements`,
  `architecture`, `plan` versioned per project with `supersedes` lineage across
  runs; bodies in the claim-check store (`board_artifact` kind), graph in
  SQLite. A gate-rejected artifact is recorded as history with
  `status="rejected"` and does not move the pointer.
- [x] **FR-1301 — task lifecycle.** `pending → in_progress →
  done|failed|blocked|quarantined`, one state-machine table
  (`board/transitions.py`) shared by both writers. Tasks key off
  `(project, plan_version, task_id)` because `DevTask.id` is planner-assigned
  per run — `T01` in plan v2 need not be `T01` in v1.
- [x] **FR-1302 — append-only change log + board counters.** Every accepted
  transition writes one `event` row with actor and authority; rejected writes
  write none. `/stats` exposes only board-owned counters (transition counts,
  fix attempts, errors, time-in-status, `status`/`authoritative_status`
  divergence). **Deliberately disjoint from `benchmarks/`** — quality/cost/speed
  rollup stays there; duplicating it would yield two scores that disagree. The
  join key (`run_id`, `stage`, `task_id` on `BenchmarkRecord`) exists for a
  later spec.
- [x] **FR-1303 — dual write path with optimistic concurrency.** Workflow
  writes content through Temporal activities in-process (no HTTP dependency);
  agents write status through FastAPI with `If-Match: <row_version>`. Both
  reach one `BoardStore`, so exactly one place can move a status.

**Known gaps (not blocking, recorded rather than fixed).**

- ⚠️ **Publish dedupe is broader than retry-safety needs.**
  `publish_artifact_version` dedupes on `(project, key, sha256)` with no
  `run_id`, while `attach_task_evidence` correctly scopes to `(…, run_id, kind,
  sha256)`. Because `_cached_stage` memoization returns byte-identical
  artifacts for identical inputs, a re-run of the same idea leaves **no trace**
  — no version, no event, `run_id` still the first run's. Temporal
  re-execution is always same-run, so scoping the dedupe by `run_id` restores
  cross-run fidelity without losing idempotency.
- ⚠️ **`X-Actor` is self-asserted** — see OQ-11, now live.
- `/tasks?status=` filters live `status` while `/stats` counts
  `authoritative_status`. Intentional (an agent wants the live view to avoid
  claimed tasks), undocumented at the API surface.
- `tests/test_board_workflow.py` is the only place a workflow runs against a
  real board; the rest of the temporal suite registers no-op `BOARD_FAKES`.
  That test's worker does not register `notify`, so a future timing shift
  surfaces as a confusing unregistered-activity error rather than an assertion.

**Deferred: the agent orchestrator.** The originating idea was to replace the
pipeline with proposers plus an agent that reads board state and dispatches to
harnesses. Deferred, not rejected — it would trade replay determinism, gate
semantics (`GatePolicy`, `TimeoutAction`, `_check_budget` at serial
boundaries), and benchmark signal-to-noise for flexibility the board already
delivers. Temporal reading the board and dispatching yields dynamic task
graphs, resume, and re-entry without that cost. Once the board is in use the
orchestrator can be **measured** against the workflow rather than adopted on
faith. See ADR-21.

## 17. The crew — a Temporal-native multi-agent code stage (`E-88`)

**Landed 2026-09-01.** Spec:
`docs/superpowers/specs/2026-08-31-crew-temporal-native-multi-agent-design.md`
(step 2 addendum: `…/2026-08-31-crew-step-2-design.md`). Plans:
`docs/superpowers/plans/2026-08-31-crew-spine.md`,
`…/2026-08-31-crew-step-2.md`. Contracts: `src/sdlc/crew/`,
`src/sdlc/workflows/crew.py`, assets in `crew/`. ARCHITECTURE §§2–4.

**Problem it closed.** E-87 (`feat/e-87-herdr-harness`, never merged) put a
multi-agent round machine *inside an activity* — 782 lines of driver, a journal
file, and a hand-written recovery path — because an activity has no history of
its own. Everything that machine hand-rolled, Temporal already owns. E-88
rebuilds the same capability from `main` as a child workflow: the round loop,
the brakes, and the durable state are workflow code, and every side effect is
an activity. E-87 is not merged and not deleted; it stays as the archived ref
its measurement can be reproduced from.

- [x] **Step 1 — the spine.** `CrewTaskWorkflow` with a one-role crew, four
  activities (`prepare_crew`, `run_crew_turn`, `read_round`,
  `checkpoint_round`), heartbeat-details resume, and the four brakes (wall
  clock, per-turn timeout, cost cap, round bound). Roles and layouts as files
  (`crew/{roles,layouts,skills}/`), fail-at-boot loader checks, and the round
  protocol living inside the worktree but out of the diff — the checkpoint's
  `git add` is pathspec-scoped rather than relying on an exclude file.
  `HarnessKind.CREW` is a **composition mode, not a CLI**; the code stage
  routes to a child workflow and gets the same `HarnessRunResult` back.
  *Acceptance:* `bench-crew-probe-1788180917` matched the E-87b baseline's
  mechanical signals — the whole pipeline through code/qa/review/merge/handoff/
  deploy, 6 tasks, 11 real crew-turn attempts, valid `notes-v1` notes.
- [x] **Step 2 — the crew.** The critic role and the second round that can hear
  it (`rounds.max: 2`, because at `max: 1` a critic is spend with no consumer:
  the only thing that can read `advisor.md` is the next round's brief).
  Containment resolved **per role** — a non-lead keeps `cwd` at the worktree so
  it can read the code it is criticising, and confines its writes with
  `HarnessRequest.write_root`, which is an *argument* to the existing hook, not
  a fifth predicate and not a policy bump. `advisor-v1` / `review-v1` /
  `question-v1` join `notes-v1` under the same untrusted-input discipline.
  ADR-6's family rule extended to crews through one pure function called from
  both the loader and a client-side pre-flight. `CrewTaskWorkflow` becomes a
  `GateHost`, so `tool_approval` and `crew_question` are answered by the
  existing signals; `parent_run_id` on every pending decision lets the inbox
  group a crew's gate under its run while the fleet view stays run-level.
  *Acceptance:* `bench-crew-probe-1788215955` — two real rounds per task across
  `CREW-001`…`CREW-007`, non-null token counts on every code record, round-2
  notes incorporating round-1 critique, `deferred` escalations reaching the
  inbox under their parent run, and a broken-environment attempt failing
  cleanly instead of fabricating.
- [x] **Step 3 — the seams.** Absorbed into steps 1 and 2 rather than run as a
  third pass: `benchmarks/drift.py` names the crew turn in `CODING_ACTIVITIES`
  (without it, drift is silently uncomputed for crew tasks), the `crew` pytest
  marker is registered, `test_crew_{loader,worktree}.py` are the retargeted
  herdr tests, and the worker image installs `claude` beside `opencode` — pulled
  forward because step 2's critic needs a second vendor to exist.

**Known boundaries (recorded, not fixed).**

- ⚠️ **The reviewer role and the `critic || reviewer` fan-out are out**, and
  deliberately so: a third opinion needs a third vendor (`cursor-agent`
  installed or an `agy` adapter). Until it exists there is nothing to
  parallelise, and `require_reviewer_approval` stays a layout field with no
  behaviour behind it. Tracked as its own item.
- ⚠️ **`no-out-of-worktree-write` is hook-layer**, so a non-lead role on a
  harness that compiles only native-layer rules is not confined by the fence at
  all — the rule lands in `rules_unenforceable` and the turn refuses under
  `containment_strict`. Containment is therefore a statement about a crew's
  composition: in a contained run, a non-lead role wants a harness with a hook
  layer.
- ⚠️ **Session resume is not worker-pinned.** A retry taken by a different
  worker needs that CLI's session store to be reachable; Worker-Specific Task
  Queues would fix it and are not scheduled.
- ⚠️ **`CursorHarness` parses cost under `# ASSUMPTION: may be absent`**, so a
  cursor role may yield `cost_incomplete`.
- Quality is **not** a crew acceptance criterion. The `crew-probe` baseline
  scores 0.000 for an environment reason E-87b §7.2 identified (the retry brief
  references a worker-only mount); comparing quality across the two would
  measure the mount, not the design.
