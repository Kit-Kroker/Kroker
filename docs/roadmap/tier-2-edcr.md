# Tier 2 — the EDCR port (`E-45`…`E-56`) → FR-910

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
