# Tier 0 — repository triage & tidy-up (`E-40`…`E-44`) → FR-900, FR-102, FR-108, NG5

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
