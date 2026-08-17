# UnifiedRiskMap and risk proposers

**Date:** 2026-08-16
**Status:** approved design, ready for planning
**Scope:** E-49 — the assess phase body
**Satisfies:** FR-916 (whole); produces the inputs FR-917 (E-50) gates on; contributes to SC-9, SC-10
**Depends on:** E-45 (DAG shell), E-46 (scan), E-47a/b/c (identity, attribution, operations), E-48 (discover), E-43 (grounding), E-40 (`Measurement`)
**Does not cover:** E-50 (gate checks and dispositions), E-51 (acceptance criteria), E-52 (reports and bundle), E-54 (risk delta), E-55 (budgets), E-56 (`/enrich`)

## Problem

`workflows/assessment.py:395` returns `unbuilt(PhaseId.ASSESS)`. An admitted
assessment now scans thirteen signals, disposes a capability set, attributes
every file, decomposes L2 operations, resolves entity ownership, compares
against a blueprint — and then reports that it assessed no risk. `PHASE_OWNER`
names this item as the one that owes it.

The gap is not inputs. E-48's clauses D6/D6a already joined the scan's security,
sensitivity, testability and coverage records onto each `Capability`, and
`AttributionReport.graph` persists the file→file reference graph on the map. The
gap is the **judgment in the middle**, and three properties make it harder than
a scoring pass:

1. **The number is the product, and E-50 gates on it.** FR-917 turns a unified
   composite ≥ 0.8 into a BLOCK. A score that moves between runs on an unchanged
   tree is a gate that opens and closes for no reason a customer can act on.
   §11's thesis — BrownKit's prose gates *"become `CheckResult`s computed by pure
   code"* — binds here more tightly than anywhere else in the tier, because this
   is the first phase whose output is primarily a number rather than a set.
2. **Two of FR-916's named factors have no source.** The QA composite is
   specified over coverage gap, testability, defect density and change velocity.
   The first two are collected. Nothing in the thirteen scan signals reads git
   history or an issue tracker, and E-41b established that history is least
   reliable on exactly the single-initial-commit repositories this tier sees
   most. A composite that quietly averages the two it has is the conflation
   FR-915 exists to prevent.
3. **The scan does not cover FR-916's five control families evenly.** SS1
   collapses authentication and authorization into one `authn_authz` category,
   and no signal collects monitoring presence. Discovered while designing
   against `CATEGORIES` (`scan/models.py:327`), not derivable from the roadmap
   entry.

## Decision

Ten decisions, numbered **RD1–RD10**, distinct from FR-916's own clause
vocabulary so a later citation cannot mean two things.

### RD1 — code computes the composite; the proposer dispositions (→ ADR-22)

A pure function turns the deterministic per-capability inputs into all three
composites. The proposer judges STRIDE applicability, vulnerability
classification, and control state where evidence is ambiguous — each a
disposition over rows code already produced.

This is ADR-22 applied to the phase that most tempts the alternative. The
consequences are the ones E-47a's identity promise needs: re-assessing an
unchanged tree yields an identical score, so E-50's threshold gates a number no
model authored, and E-54's per-capability delta measures the repository rather
than sampling variance.

**Alternative rejected — the model scores and code validates the schema.**
Closer to BrownKit's own artifact, and a model can weigh factors code cannot.
Rejected because it makes FR-917's deterministic gate a threshold over a
model-authored number, and because the churn lands on the ids clients cite.

**Alternative rejected — code scores, the model may adjust within a bounded
delta.** Preserves determinism as the default. Rejected as speculative: it needs
an override contract and puts two numbers in the bundle, before any calibration
data exists to say the adjustment would be an improvement.

### RD2 — placement, and the single input

`src/sdlc/assessment/risk/`, mirroring `scan/` and `discover/`: pure modules
plus one activity seam, importing only Pydantic, `measurement.py`,
`grounding.py` and this package. Never `models.py`, `activities.py`, or
`temporalio` — the rule `assessment/models.py:3` states and both sibling
packages follow, so a dependency here would appear as a reviewable import.

The phase reads **one input, the `CapabilityMap`**:

```
CapabilityMap
├── capabilities[]
│   ├── security:    tuple[SecurityObservation]   -> severity, STRIDE, controls
│   ├── sensitivity: tuple[SensitivityRecord]     -> impact, criticality
│   ├── testability: tuple[TestabilityFinding]    -> QA factors, FR-917 BLOCK
│   ├── coverage:    tuple[CoverageRecord]        -> coverage gap
│   └── member_paths                              -> capability<->capability edges
└── attribution.graph.edges                       -> the file->file graph
```

`_assess` therefore reads no blobs and executes nothing. The single exception is
RD6's `verify_risk_refs`, which reads exactly the paths the proposer cited, at
the pinned commit. E-49 holds the NFR-9 line E-46, E-47 and E-48 all hold.

### RD3 — the QA composite is `partial`, and the unified composite propagates it

Defect density and change velocity report `not_collected`, each naming what
would supply it. The QA composite is a `partial` sentinel rather than a number
averaged over half its specification, and the unified composite propagates
`partial` upward with a reason naming the QA half.

FR-916 specifies exactly this latitude — *"a unified composite in [0,1] or a
`partial`/`unknown` sentinel"* — so the sentinel is the specified behaviour, not
a degradation of it.

**`partial` is derived, never stored.** `CollectionState` (`measurement.py:22`)
has three members — `MEASURED`, `NOT_COLLECTED`, `UNKNOWN` — and adding a fourth
would change a type that `CoverageReport`, `SecurityReport`, triage, scan and
discover all share, for one consumer's need. Instead a `Composite` carries its
factors, each with its own `Measurement`, and `is_partial` is a property: some
factors collected, some did not. This is the codebase's standing preference —
`terminal_status` is derived, every `counts` field is derived — and it means a
composite cannot claim a partiality its factors contradict. The composite's own
`value` is `not_collected` in that case, with a reason naming the missing
factors, so a consumer that ignores `is_partial` still cannot read a number that
was never computed.

The consequence lands on E-50 and is deliberate: FR-917's composite-threshold
BLOCK does not fire until `/enrich` (E-56) supplies the missing inputs, while
its other two BLOCK clauses — a confirmed unaccepted vulnerability, and a
testability blocker in a high-criticality capability — fire from day one. The
assessment gate is live; one of its three clauses is not yet decidable, and says
so.

**Alternative rejected — a git-churn signal for change velocity.** Three of four
factors instead of two. Rejected because E-41b already downweighted history for
this repository population, so the signal would degrade to `not_collected` on
the repositories that need it most, at the cost of a fourteenth signal to
version and memoize.

**Alternative rejected — renormalize the weights over collected factors.**
Always yields a number. Rejected because two repositories with different
collection states would produce scores that are not comparable, and the number
would mean something different per run — FR-915's exact target.

**Alternative rejected — a lower bound on the partial that E-50 could BLOCK
on.** Attractive ("insufficient data can prove BLOCK but never prove PASS") and
structurally the same move as splitting `security_scan_collected` from
`security_no_critical`. Rejected as YAGNI: it is machinery for a consumer that
is not written, and FR-917 already has two working BLOCK clauses. If E-50 finds
it needs the bound, adding a field to a composite is a smaller change than
removing one.

### RD4 — severity is a table, and criticality is derived

**Severity.** `SecurityObservation.severity_hint` carries its own instruction
(`scan/models.py:369`): *"scan emits hints and /assess assigns severity
(E-49). A field called `severity` would invite a consumer to treat a pattern
match as a rating."* This item is that consumer.

Severity is `f(severity_hint, criticality, confidence)` expressed as a **stated
table**: a `high` hint on a `HIGH`-criticality capability is critical; the same
hint on a `LOW`-criticality capability at `LOW` confidence is medium. A table is
auditable in the FR-921 bundle and reviewable as a diff. A tuned arithmetic
expression producing the same mapping is neither.

**Criticality.** FR-917's BLOCK clause names a "high-criticality capability" and
nothing produces criticality today. It is derived from two things already on the
capability: the `SensitivityRecord` classifications it handles, and whether its
members include externally-reachable kinds (`HTTP_ROUTE`, `FRONTEND_ROUTE`).

A capability with no sensitivity records and no reachable entry point is **not
thereby low-criticality**. If SS4 did not collect, criticality is
`not_collected` — `SensitivityRecord.accessed_by`'s own docstring warns that an
empty list "must never be read as 'no entry point touches PII'", and a
criticality derived from that emptiness would launder the warning into a rating.

### RD5 — control coverage is five families over three sources

Mapping FR-916's families onto what `CATEGORIES` (`scan/models.py:327`) collects:

| Family | Source | State |
|---|---|---|
| Authentication | `authn_authz` (SS1) | collects |
| Validation | `input_validation` (SS1) | collects |
| Encryption | `tls_enforcement` (SS1), `db_security` (SS3) | collects |
| Authorization | — SS1 collapses authn and authz into one category | `not_collected` |
| Monitoring | — `log_masking` is masking, not monitoring presence | `not_collected` |

Authorization does **not** mirror Authentication's state. Two families derived
identically from one category is five families that are really four, and a
customer reading "authorization: present" would be reading an authentication
result — a stronger claim than the evidence supports, in the field where
over-claiming is most expensive.

Both gaps are recorded as roadmap follow-ups (an SS1 v2 that separates the
categories; a monitoring-presence signal) rather than absorbed into E-49's
scope. Fixing a scan signal from inside the assess phase would put a second
producer of a scan category in the tree.

### RD6 — the verifier is lifted, not copied

`verify_refs` (`discover/verify.py:128`) is typed to `DiscoverProposal` /
`ProposedDisposition`, and E-49 needs the byte-identical invariant over a
different row type. Copying it would put two fail-closed grounding invariants in
the tree that must never disagree — the shape `triage/admission.py` already
refactored away into "one function at two strictnesses", after
`workflows/tidyup.py` documented the trap that two copies create.

The row-level logic moves to `assessment/verification.py` over a structural
protocol (`evidence: tuple[EvidenceRef, ...]`, `quote: str`, an id).
`discover/verify.py` keeps its typed wrapper, so **E-48's call sites do not
change shape**. The 0.10 fabrication threshold becomes one shared constant
rather than two numbers agreeing by coincidence.

This is the only landed code E-49 touches, and the scope is a pure lift with no
behaviour change. The proof is E-48's existing verification tests passing
unchanged.

### RD7 — degradation is layer-scoped, and the difference from E-48 is deliberate

In discover, dispositions *are* the map's content, so a tripped guard fails the
phase. Here the deterministic composites never depended on the proposer — plan 1
ships without one. So a missing role, a failed call, or a tripped guard degrades
**the judgment layer only**: STRIDE rationales and vulnerability classifications
report `not_collected`, and the composites survive.

This is the correct scope given the artifact's structure, not a weakening of
E-48's rule. The rule in both places is the same: the guard fails whatever
consumed the model, and nothing else.

The proposer role is optional exactly as E-48's DD7 made discover's optional:
`AGENTS.get("risk")` yields `None` when the folder is absent, `t_risk` is then
`None`, and `inp.propose_risk` gates the call. No folder means no model call and
a phase that is still MEASURED.

### RD8 — an absent capability set is `not_collected`, never an empty map

If discover reported `not_collected` there are no capabilities, and a
`UnifiedRiskMap` over zero capabilities carries zero vulnerabilities — which
renders as a clean risk map.

That is byte-for-byte the hole E-40 closed on the absolute floor:
`report_from_sarif` returning `SecurityReport(critical=0, findings=[])` for a
document that never parsed, indistinguishable from a clean scan. `_assess`
reports `not_collected` naming discover and never constructs an empty map.

This is the load-bearing FR-915 case for the phase, and it is cheap to install
now for the same reason the SARIF guard was: nothing depends on the empty map
yet.

### RD9 — drivers are typed references, not prose

The `unified-risk-map` v1.0 schema guards drivers with `minItems: 1,
maxItems: 3` plus a minimum string length. The length check exists because
BrownKit's driver is model-authored prose, and length is the only property prose
admits.

Under RD1 the composite is computed, so a `Driver` is a **typed reference to a
factor that exists** — factor key, computed value, contribution — rather than a
string. FR-916's "a generic label is not a driver" becomes unrepresentable
rather than merely improbable, and `maxItems: 3` becomes "the three largest
contributors", which is derivable rather than a stylistic cap.

**Where this meets `_unmeasured_carries_no_payload`.** The package rule is that
a report which did not collect has no rows; FR-916 says a composite carries one
to three drivers. The `partial` case touches both, so the rule is stated once:

- every factor collected → drivers over all factors
- **some** factors collected (`is_partial`) → drivers over the factors that did
  collect; the composite's own `value` is `not_collected`, its reason naming
  those that did not
- **no** factor collected → **no drivers**

The middle case is why drivers hang off the composite rather than off its
`value`: a `Measurement` that is `not_collected` may carry no value, but the
factors underneath it are real and are exactly what a customer needs to see.

### RD10 — cross-capability splits by mechanism

The capability→capability edges are a projection: `attribution.graph.edges` is
file→file, `Capability.member_paths` is file→`bc_id`. Build the index, map each
edge, drop intra-capability edges and edges touching files no capability owns.
No new tree read, and no contract change to the landed E-48 artifact.
Enumeration is sorted and traversal bounded — NFR-10 requires byte-identical
output across input order, and an unbounded path search over a dense graph is
not a bounded activity.

**Computed outright:**

- **Shared vulnerabilities.** The join key is deliberately coarser than
  `Vulnerability.key`. `security_identity` includes `path`, which is right for a
  per-instance identity that E-54's delta and E-53's seeds match on — but it
  means two capabilities never share one. What "shared" means is a *weakness
  class recurring across capabilities*, so the grouping is `(signal, rule, key)`,
  the path-excluded prefix, emitted when ≥2 distinct `bc_id`s carry it. Both
  keys are on the artifact and answer different questions.
- **Cascades.** Bounded reachability from capabilities whose security composite
  is high, over the projected edges.

**Enumerated by code, dispositioned by the proposer:**

- **Trust boundaries.** Candidates are edges whose endpoints differ in
  criticality or sensitivity exposure. The proposer returns
  `WEAK | SOUND | UNCLEAR` with a rationale per candidate edge.
- **Privilege-escalation chains.** Candidates are bounded paths from an
  externally-reachable capability whose authentication control is absent or
  unknown, to one handling sensitive entities.

Neither judgment family may invent an edge: candidates come from the projected
graph, which is ADR-22 over a graph instead of over a candidate list.

**A known limit, written down rather than discovered by a customer.** Escalation
candidates depend on the authentication control family, and RD5 established that
Authorization has no separate source. The chains E-49 enumerates are therefore
authentication-gated, not authorization-gated — a narrower claim than FR-916's
wording implies.

**Alternative rejected — one proposer call over the whole graph for all four
families.** Fewer moving parts, and the model sees the system whole. Rejected
because two of the four are facts code can prove, and asserting them through a
model reintroduces exactly the churn ADR-22 exists to prevent.

## Contracts

In `risk/models.py`. `Assessment.risk: UnifiedRiskMap | None` hangs off the
artifact with a paired `_risk_agrees_with_its_phase` validator — the third
instance of the pattern `assessment/models.py:146,169` established, written
explicitly rather than looped, for the reason
`_discover_agrees_with_its_phase`'s docstring gives: the error message is what a
reader debugs against, and a generic one would name neither the phase nor the
artifact.

| Contract | Role |
|---|---|
| `StrideCategory` | the six categories |
| `ThreatAssessment` | `category`, `applicable`, `rationale`, `vulnerability_keys` — all six always present |
| `VulnerabilityClass` | `CONFIRMED \| PROBABLE \| POTENTIAL` |
| `Vulnerability` | `key` (= `security_identity`), classification, assigned severity, STRIDE linkage, path/line, evidence, source |
| `ControlFamily` | the five families |
| `ControlCoverage` | family, `state: ControlState \| None`, `collected: Measurement`, evidence, rule — all five always present |
| `ControlState` | `PRESENT \| ABSENT` |
| `CriticalityRating` | `level: Criticality \| None`, `collected: Measurement` |
| `Criticality` | `HIGH \| MEDIUM \| LOW` |
| `Driver` | RD9's typed factor reference |
| `Factor` | `key`, `value: Measurement`, `weight` — one input to a composite |
| `Composite` | `value: Measurement`, `factors: tuple[Factor, ...]`, `drivers: tuple[Driver, ...]`, `is_partial` (property) |
| `CapabilityRisk` | one per `bc_id`: criticality, threats, vulnerabilities, controls, three composites |
| `SharedVulnerability` / `Cascade` / `TrustBoundary` / `EscalationPath` | RD10's four families |
| `SystemRisk` | the four families, each with its own `Measurement` |
| `RiskProposal` | the proposer's `output_type` |
| `UnifiedRiskMap` | the phase artifact: capabilities, system, derived counts, `collected` |

**Neither `ControlState` nor `Criticality` carries an `UNKNOWN` member.** Both
pair an optional level with a `Measurement` instead, because an `UNKNOWN` enum
member would be a second way to say `not_collected` — and two registries for one
fact is the defect this codebase has paid for more than once (ADR-6's duplicate
role lists, E-41b's duplicated readiness dimension). The `Measurement` is the one
place a reader looks to learn whether the fact was collected.

Requiring all six STRIDE categories and all five control families at the type is
what makes FR-916's "a category with no applicable threat carries an explicit
rationale rather than being omitted" enforceable: omission is unrepresentable,
so it cannot come to mean "not applicable".

Contract discipline follows the package's existing rules, which bind every new
contract here without restatement: counts derived from rows and never assigned;
sorted-and-deduped asserted rather than repaired (a producer emitting discovery
order is an NFR-10 determinism bug, and repairing it hides that); and
`_unmeasured_carries_no_payload`, as refined by RD9 for the `partial` case.

## Memoization

The assess memo key is `(project, tree_hash, map_digest, risk_rules_sha)`.

`map_digest` is a content hash over the serialized `CapabilityMap`, taken
canonically so it does not depend on field emission order (NFR-10). It is used
rather than a restatement of the map's own key terms because the
`CapabilityMap` already folds `identity_registry_version` (E-47a's FR-103
amendment, landed with E-48's DD10), so digesting the map inherits it rather
than maintaining a second copy of the term list.

`risk_rules_sha` hashes transitively over the modules carrying the weight table,
the severity table, and RD10's depth and result caps. **The weights are an
input.** E-46 learned this at plan-3 cost — a hand-maintained version int misses
a real input, which is why its key carries `rules_sha` beyond the two terms the
roadmap specified. Retuning a weight must invalidate exactly the assessments it
would move.

## Failure modes

| Condition | Behaviour |
|---|---|
| discover reported `not_collected` | ASSESS reports `not_collected` naming discover; no empty map is constructed (RD8) |
| SS4 did not collect | criticality `not_collected`; no capability is rated low by absence (RD4) |
| QS2/QS3 did not collect | the affected QA factor is `not_collected`; the composite's `value` is `not_collected` naming it, and `is_partial` derives True (RD3) |
| `agents/risk/` absent, or the call fails | judgment layer `not_collected`; composites survive; phase MEASURED (RD7) |
| fabrication rate > 0.10 | judgment layer `not_collected`; composites survive (RD7) |
| a proposer cites an unresolvable path or an unverifiable quote | that row drops; the rate feeds the guard (RD6) |

## Testing

- Order-independence assertions in each pure module's own test file —
  `factors`, `severity`, `controls`, `composites`, `crosscap`. Per-module, not
  one central test: the E-47b/E-47c and E-48-plan-3 pattern.
- `_unmeasured_carries_no_payload` per report; counts derived and asserted,
  never repaired.
- RD9's boundary pinned explicitly in all three cases: drivers over every
  factor when all collected; drivers over the collected subset with
  `is_partial` True and a `not_collected` `value` when some did; **no** drivers
  when none did. Plus the derivation itself — `is_partial` must never be
  settable, and must agree with the factors it is read from.
- Structural completeness: six STRIDE categories and five control families
  required at the type, so omission cannot come to mean "not applicable".
- RD6's lift proved by **E-48's existing verification tests passing
  unchanged** — that is what makes it a lift rather than a rewrite.
- One known-limit test pinning cost as a test rather than a caveat, the
  `test_known_false_positive_a_dynamic_reference_reads_as_dead` precedent: a
  cascade path routed through an infrastructure file reading as a capability
  dependency.
- Temporal e2e at plan 1, asserting ASSESS is MEASURED with no model
  registered.

## Plans

| Plan | Lands | State after |
|---|---|---|
| **1 — the deterministic score** | `risk/models.py`, factors / severity / controls / criticality / composites, `assess_risk` activity, the memo, `Assessment.risk` + validator, `_assess` wired | ASSESS **measured** with no model call (landed 2026-08-16) |
| **2 — judgment** | `assessment/verification.py` lift, `agents/risk/`, `t_risk`, STRIDE + vulnerability + control dispositions, the guard, memo refusal, `verify_risk_refs`, e2e | FR-916's per-capability half complete (landed 2026-08-16) |
| **3 — the system view** | the graph projection, shared vulnerabilities + cascades computed, trust-boundary + escalation candidates enumerated and dispositioned | FR-916 complete |

Plan 1 is a live phase rather than a stub because RD1's deterministic score is
the real artifact, not a placeholder. If plan 3 slipped, the tier would still
have advanced and the risk map would still be defensible — it would lack the
system view, and say so. This is E-48's DD13 rhythm, and the ordering ADR-22
needs: contracts before proposer, because a model may only disposition rows that
already exist.

## Scope

### Not covered

- **Gate checks and FP dispositions** — E-50. E-49 produces the numbers;
  turning thresholds into `CheckResult`s and dispositions into audited overrides
  is that item's. `GateHost` is already inherited for it.
- **Acceptance criteria and cross-reference integrity** — E-51. RD1 and ADR-22
  make its absolute check satisfiable by construction; the check is not this
  item's.
- **Reports and the evidence bundle** — E-52.
- **Per-capability risk delta** — E-54, which consumes `Vulnerability.key`.
- **Per-phase budgets** — E-55.
- **Fixing SS1's collapsed `authn_authz`, or adding a monitoring signal** —
  RD5's follow-ups. Fixing a scan signal from inside assess would put a second
  producer of a scan category in the tree.
- **Defect density and change velocity inputs** — E-56 (`/enrich`).

## Roadmap deltas

| Item | Change |
|---|---|
| E-49 | `[ ]` → `[x]` on landing |
| FR-916 | `[ ]` → `[x]` |
| FR-911 | Stub count 4 → 3; `PHASE_OWNER` loses its `ASSESS` entry |
| FR-917 | Unchanged (E-50), but its two non-composite BLOCK clauses become computable; the composite clause waits on E-56 (RD3) |
| FR-902 | New follow-up: SS1 v2 separating `authn_authz`; a monitoring-presence signal (RD5) |
| NFR-9 | E-49 adds no execution of repository code: one model call over a packet, plus blob reads at the pinned commit for verification |
| NFR-10 | Five more pure modules under the order-independence assertion |
| SC-9 | Its input lands — the per-capability composite E-54 deltas |
| SC-10 | Unchanged; still needs E-55 budgets and runs |
| P6 | Third of seven phase bodies ships |
