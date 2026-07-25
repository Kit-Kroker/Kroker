# Brownfield assessment & outcome measurement — design

| | |
|---|---|
| Date | 2026-07-25 |
| Status | Design approved; PRD v1.1 amended, ROADMAP §§10–14 added |
| Scope added | FR-900 (triage), FR-910 (EDCR audit), FR-1000 (platform), FR-1100 (product outcome) |
| Work items | E-40…E-71 |
| Related | `PRD.md` v1.1, `ROADMAP.md` §§10–14, [`BrownKit`](https://github.com/MaksimShevtsov/BrownKit) |

## 1. What prompted this

Two candidate user groups for a hosted or on-premises service over the existing
factory:

1. **Clients with an existing, often vibe-coded repository** who want it fixed,
   tidied, its weak points identified, then a full audit with subsequent fixes —
   all through the factory's governed workflows.
2. **Product owners** who want to take an idea to production and measure the
   result, PoC-style.

The factory as it stands cannot serve either group, for reasons that are
structural rather than incidental.

## 2. Why the existing pipeline does not already cover this

**The entry shape is wrong.** The pipeline is `IdeaBrief → feature → deploy`.
Group 1 arrives with no idea and no acceptance criteria — just a repository and a
complaint. There is no artifact for that. Compounding it, ROADMAP §1 records DAG
stage 0 (intake routing) and stage 2 (Cartographer / `CodebaseMap`) as **not
started**, and P2 brownfield mode as unbuilt. Reading a codebase the factory did
not write — the literal first act of group 1's product — is the largest missing
capability.

**The gate grades only what the factory authored.** `DeterministicQualityGate`
runs against factory-produced code. Group 1's value is a *baseline* grade of
unmodified customer code and a delta afterwards. The FR-108 `ToolchainAdapter`
seam is the right machinery pointed the wrong direction.

**Containment is a blocker, not a task.** FR-703's own note concedes that egress
enforcement is tool-level only: *"a socket opened from inside an allowed `Bash`
call is not visible to it."* The container and restricted-OS-user tiers remain
open under E-21. Running a stranger's repository today means their `npm install`
executes as the worker user with the worker's toolchain and unrestricted network
access. For a multi-tenant service that is arbitrary code execution by design.

**There is no tenancy.** OQ-4 deferred it to fleet scale. Artifact store,
Temporal namespace and — most dangerously — Hindsight memory banks are
project-scoped with no tenant boundary. Cross-run learning is the factory's
differentiator and, unbounded, its first data-breach path.

**Group 2's measurement does not exist at all.** The factory measures *itself*
thoroughly (SC-1..6, benchmark matrix, rubric calibration FR-110, capture-always
transcripts FR-109) and measures the product it ships not at all. DAG stage 13
is a single hardcoded `make deploy ENV=staging`.

## 3. Decision: port BrownKit's methodology as native stages

An existing methodology, [`BrownKit`](https://github.com/MaksimShevtsov/BrownKit),
already encodes the assessment thinking as spec-kit slash commands: an EDCR
pipeline (`init / scan / discover / report / assess / generate / finish`, plus
`enrich`, `gate`, `validate`), stable `BC-NNN` capability identifiers, a unified
risk map schema, and 14 terminal acceptance criteria.

The mapping onto the factory is close to structural:

| BrownKit | Factory |
|---|---|
| `/scan` deterministic scripts | activities, memoizable per FR-103 |
| `/discover` → `BC-NNN` model | `CapabilityMap` — **satisfies FR-102 / stage 2** |
| `/assess` → `unified-risk-map.json` | typed `UnifiedRiskMap` |
| `/gate` PASS/WARN/BLOCK at `<0.6 / 0.6–0.79 / ≥0.8` | `DeterministicQualityGate` checks |
| `/generate` → `spec-seeds/BC-*.md` | `IdeaBrief(mode=brownfield)` |
| `/validate` D1–D4 / A1–A3 / G1–G3 | reviewer + analyst, post-fix |
| 14 acceptance criteria | `CheckResult` with absolute/advisory class |
| `workflow.json` phase tracker | Temporal history (deleted, not ported) |

### Alternatives considered

**Invoke BrownKit as an external tool**, running it inside a harness and parsing
its evidence tree into typed artifacts. Cheaper and preserves the existing
investment, but forfeits every reason to do this in the factory: gates stay
LLM-self-graded, stages cannot be memoized individually, and the boundary becomes
a markdown-parsing problem. **Rejected.**

**Shared core with two front-ends** — phase logic usable both as spec-kit
commands and factory stages. Bridging a prompt-driven CLI and a typed workflow
engine tends to serve neither. **Rejected.**

**Port `scan`+`discover` only, keep `/assess` external** for a while. Lowest
risk, but leaves the product incomplete and splits the grounding invariant across
two systems. **Rejected**, though the ordering in ROADMAP §14 delivers
essentially this sequence without the split.

## 4. What the port fixes in BrownKit

**Gates become enforceable.** `/gate` writes no files and permits continuation
when `/assess` never ran. `/finish`'s 14 criteria are graded by the model that
produced the artifacts. `*Source: ...*` cross-references are audited by an LLM
checking its own citations. Ported, each becomes a `CheckResult` computed by pure
code, with FR-106's absolute/advisory split. This is the whole point.

**Grounding becomes verified rather than asserted.** FR-107 already solved this
for research: a `GroundedFinding` requires a verbatim quote matched byte-exact
against bytes fetched *this run*, fail-closed, with unverifiable claims
downgraded to inferred or dropped. FR-914 applies the identical invariant to
code — quote vs. bytes at `path@commit_sha` — and **shares the implementation**.
This single invariant is the product's credibility (SC-7).

**Determinism and reproducibility.** BrownKit ships bash, PowerShell *and*
Python variants of `detect-stack`, `find-secrets`, `git-churn`, `parse-coverage`,
`list-manifests` — three behaviours to keep in sync. FR-902 collapses them onto
the single FR-108 adapter. And `BC-NNN` stability, currently asserted, becomes a
function of content (FR-913) — though **OQ-6** must be settled first.

**Cost bounds.** LLM-fusing every candidate in a large monorepo has no ceiling.
Assessment is the one stage family where input size is the customer's choice, so
FR-922 per-phase budgets are load-bearing.

**The loop closes.** BrownKit ends by handing spec seeds to a human or an IDE
agent. The factory executes them under a gate with cross-family review (ADR-6),
and `/validate`'s criteria become the fix run's acceptance criteria — so a fix is
graded against the assessment that motivated it, and the before/after risk delta
is provable (FR-919, FR-920).

**What BrownKit does better, flowing back.** `not-collected` as a first-class
state with a recorded reason, and `unknown`/`partial` composite sentinels. The
factory's `QAReport.coverage_pct: float | None` conflates a measured zero with a
never-measured value — a defect in a product that sells measurement. FR-915
retrofits this onto the existing contracts (E-40).

## 5. Decision: triage is a separate tier that gates the audit

This is the correction that most changed the design. EDCR is **enterprise
brownfield** machinery — blueprints BIAN, TM Forum, ACORD, HL7, ARTS, APQC;
worked example Java/Maven/Jenkins/JaCoCo. It decomposes a system that has
structure.

A vibe-coded repository does not. It may not build, has no tests, has `.env`
committed and the service key reachable from the client bundle, and half its
files are untouched generator scaffolding. Applied there, EDCR's ≥90%
file→capability coverage has nothing to map to, every QA composite degenerates to
`unknown`, and per-capability STRIDE reasoning is paid for over a structure that
does not exist.

So **Tier 0 (triage)** is deliberately cheap and mostly deterministic, completes
on repositories that do not build, and **gates Tier 2** (FR-903). It also happens
to be the tier whose findings are mechanically fixable — pin dependencies, delete
dead files, move secrets to env, add a smoke test, add CI — which makes Tier 0/1
the shortest path to a demonstrable assess → fix → prove loop, and a better first
product than the full audit.

The original framing had this ordering right: *fix, tidy up, identify weak
points, **then** a full audit with subsequent fixes.*

## 6. Decision: outcome measurement adapts, it does not build substrate

Group 2 initially looked like a different company: it needs deployment targets,
environments, feature flags and product analytics. That read was wrong in one
specific way — it is only true if the substrate gets **built**. Treating hosting
target and analytics source as **adapters** resolved from config (NG7, following
FR-108) leaves work that is squarely in this codebase's competence:

- **`Hypothesis` at intake** — metric, direction, minimum effect, decision rule,
  kill condition, observation window — gated before any code (FR-1101).
- **Pre-registration** — the rule is frozen and hashed at approval, reusing
  `ValidationContract.frozen` semantics (FR-1102). The owner commits to how they
  will decide before seeing data, and the factory makes that structural rather
  than cultural. This is the differentiating mechanic.
- **Metric traceability** — every metric traces to ≥1 instrumentation task and
  ≥1 emitted event, via the same mechanism as criterion→test (FR-1103). An
  uninstrumented hypothesis cannot reach deploy.
- **Durable observation** — a timer spanning the window, which is precisely what
  NFR-1 already guarantees; then collect, evaluate, and open a keep/kill/extend
  gate (FR-1106).
- **`inconclusive` as a real verdict** (FR-1108) — FR-915 applied to product
  metrics.

`DeployPlan`/`DeployReport` (FR-1104) also closes DAG stage 13 for ordinary
feature runs, so it earns its place regardless.

## 7. Proposed ADRs

- **ADR-18 — Triage precedes capability modelling.** A repository that does not
  build or whose structure is not discernible is not capability-mapped; the
  factory reports the precondition as unmet rather than emit a low-confidence
  model. Rationale: a capability model over absent structure is not a weaker
  answer, it is a misleading one.
- **ADR-19 — Deployment and analytics are adapters, not substrate.** The factory
  never reimplements hosting, feature flagging, or analytics. Rationale: it keeps
  FR-1100 an adjacent feature rather than a second product, and mirrors the
  FR-108 precedent that adding a language changes no workflow code.
- **ADR-20 — Pre-registration reuses contract-freeze semantics.** The
  experiment's decision rule is frozen and hashed exactly as `ValidationContract`
  freezes at planning. Rationale: one freeze mechanism, one audit shape, and the
  property that matters (cannot be edited after the data arrives) is inherited
  rather than reinvented.

## 8. Phase independence

P5 (triage/tidy-up) and P6 (audit) **do not depend on P7** (hosted
multi-tenant). Assessment delivered by an operator on repositories they are
authorised to run needs neither tenancy nor self-serve onboarding. P7 is what
converts operator-delivered work into a product strangers can use, and FR-1002
(container isolation, network-level egress) is its gating item.

FR-913 lands *inside* P2, because it is how FR-102's `CodebaseMap` gets built.

## 9. Open risks

- **OQ-6 blocks FR-913.** No canonical key yet makes `BC-NNN` both
  content-derived and stable across refactoring: a key over file paths breaks on
  a move, one over entity names breaks on rename. Until settled, every
  cross-reference in the evidence bundle is fragile.
- **OQ-9 has no good answer.** FR-1106 reads a metric from a customer-controlled
  analytics source to decide keep/kill — FR-914's grounding problem inside a
  system the factory does not control.
- **OQ-8 needs non-engineering review.** Given NG6 (no compliance
  certification, not a substitute for human audit or pentest), the exact
  language of what the FR-921 bundle asserts should be reviewed by someone
  qualified in liability *before* the first external hand-off.
- **OQ-7** — inline vs. batch quote verification; a correctness-neutral
  performance choice, but it should be made before findings exist at volume.
- **OQ-5** — whether some repository class makes Tier 2 never worth running.
  A packaging question that only real repositories can answer.
- **Scope realism.** §§10–13 are 32 work items across four requirement families.
  This document records the whole picture deliberately, per the roadmap's
  purpose; it is not a claim that all of it is near-term. ROADMAP §14 ranks what
  actually unblocks what.

## 10. Not addressed here

Each of E-40…E-71 still needs its own spec before implementation. This document
settles *scope and sequencing*, not designs. The first implementation spec should
cover **E-40 + E-43** (the two invariants), since both land in existing code
paths and both get materially more expensive to install after finding-producing
stages exist.
