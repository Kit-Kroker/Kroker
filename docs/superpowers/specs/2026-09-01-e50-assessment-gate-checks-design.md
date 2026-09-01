# Assessment gate checks and false-positive dispositions

**Date:** 2026-09-01
**Status:** approved design, ready for planning
**Scope:** E-50 — the assessment gate checks
**Satisfies:** FR-917 (whole), FR-106 (deterministic gate checks), FR-304 (audited human decisions persisting across re-runs)
**Depends on:** E-49 (`UnifiedRiskMap`, landed), E-45 (`GateHost`, `AssessmentWorkflow` DAG), E-47a (`IdentityCorrection`/`BoardIdentityStore` — the audited-persistence precedent this item follows)
**Does not cover:** E-51 (acceptance criteria as code, FR-918), E-52 (reports and the evidence bundle), E-53 (spec seeds consuming a BLOCKed assessment), E-56 (`/enrich` — the QA composite's missing factors, which is what keeps the composite-threshold clause deferred)

## Problem

`UnifiedRiskMap` (E-49) produces a number and a set of dispositionable rows,
but nothing turns them into a verdict. FR-917 names a deterministic
trichotomy — BLOCK / WARN / PASS — over three clauses, and a persistence
requirement for the one place a human's judgment legitimately overrides code:
a finding disposed as `false_positive`, `mitigated_elsewhere`, or
`accepted_risk` must not re-trigger the same BLOCK on the next run.

Two properties make this harder than "three `if` statements":

1. **One of the three clauses is not yet decidable.** RD3 (E-49) established
   that the QA composite, and therefore the unified composite, is `partial`
   on every run until E-56 supplies defect density and change velocity. FR-917's
   composite-threshold BLOCK clause and its WARN band both key on that same
   composite. A gate that reads a `partial` composite as either "under 0.8"
   or "in [0.6, 0.8)" would be manufacturing a verdict FR-915's discipline
   exists to forbid — the malformed-SARIF-reads-as-clean shape, moved one
   layer up.
2. **The FR-304 override is not `gate.py`'s override.** `GateOverride`
   (`gate.py`) is an ephemeral, per-run waiver of one advisory check. FR-917's
   disposition is a per-*finding* judgment that must survive to the *next*
   run against the same tree — closer in shape to E-47a's `IdentityCorrection`
   than to anything in `gate.py`.

There is also no merge to block. `AssessmentWorkflow` produces a report, not
a change someone is trying to land, so "BLOCK" cannot mean what it means in
`gate.py`'s docstring. It has to mean something specific to a durable,
human-in-the-loop assessment run.

## Decision

Ten decisions, numbered **GD1–GD10**, distinct from FR-916's RD-vocabulary and
`gate.py`'s own terms so a later citation cannot mean two things.

### GD1 — the gate opens right after ASSESS, and BLOCK is blocking

`AssessmentWorkflow` already inherits `GateHost` for exactly this
(`workflows/assessment.py`'s docstring says so). Right after `_assess`
produces a MEASURED `UnifiedRiskMap`, the workflow evaluates the three FR-917
clauses. If the verdict is BLOCK, it opens a `"risk"` gate — the same
mechanism `TriageWorkflow` uses for the FR-903 readiness gate — and awaits a
human decision before `REPORT`/`GENERATE`/`FINISH` run. WARN and PASS never
open a gate.

This is not a new `PhaseId`. The roadmap already states `/gate` is not a
DAG stage (§11: *"`/enrich`, `/gate` and `/validate` are not stages"*), and
the risk-gate result therefore agrees with `Assessment.risk` being present,
not with a `phases` row (GD5).

**Alternative rejected — non-blocking, REPORT/GENERATE/FINISH always run.**
Attractive because there is no merge to protect, and the customer needs the
bundle regardless of verdict. Rejected because `GateHost` is durable HITL
machinery built to pause a workflow on exactly this kind of decision, and a
BLOCK that never pauses anything is not meaningfully different from a WARN —
FR-917 draws the line between them for a reason.

**Alternative rejected — defer entirely into FINISH (E-51).** E-51 already
computes the 14 terminal `CheckResult`s from typed artifacts, and folding
FR-917's three clauses in as three more would avoid a second gate-opening
site. Rejected because E-51 is FINISH-time, after REPORT/GENERATE would
already have run — by which point a BLOCK cannot mean "pause before doing
more work," which is the property this item's `GateHost` inheritance exists
for.

### GD2 — APPROVE overrides and continues; REJECT halts downstream phases

The gate's two outcomes are not symmetric wrappers around the same
continuation:

- **APPROVE** (with a reason) records an audited override, mirroring FR-903's
  `ReadinessOverride` exactly (see GD5's `RiskGateOverride`), and
  `REPORT`/`GENERATE`/`FINISH` proceed normally.
- **REJECT**, or a `HOLD` timeout without approval, leaves those three phases
  un-reached. `run()` supplies them with `skipped()`-shaped `PhaseResult`s
  directly (never calling `_report`/`_generate`/`_finish`), with a reason
  naming the rejected risk gate rather than "not implemented."

**No new `terminal_status` value is needed.** `terminal_status()` already
derives `PARTIAL` whenever not every non-init phase is MEASURED — D6's
existing rule — and the *why* lives in each phase's own `Measurement.reason`,
the same pattern `skipped()`/`unbuilt()` already use to distinguish "not
admitted" from "not implemented." A rejected risk gate is a third reason
string in that same slot, not a fourth top-level status. Until E-51/E-52 land
this is moot in practice — `REPORT`/`GENERATE`/`FINISH` are unconditionally
`unbuilt()` today — but the distinction becomes real, and free, the moment
those items ship: a rejected run reads `PARTIAL` with phase reasons naming
FR-917, distinguishable at the `Measurement.reason` string from an ordinary
"not yet built" partial.

### GD3 — the two live clauses, defined precisely

**Unaccepted confirmed vulnerability.** A `Vulnerability` with
`classification == CONFIRMED` whose `key` (= `security_identity`, stable
across re-runs of an unchanged finding) carries no `FindingDisposition`
(GD7) in the store. All three disposition values —
`false_positive | mitigated_elsewhere | accepted_risk` — count as *accepted*
for this clause: FR-304 does not distinguish "the risk is dispositioned
because it isn't real" from "dispositioned because it's tolerated," and this
check should not either.

`CONFIRMED` is reachable only through the judgment layer — `risk/build.py`
stamps every baseline `Vulnerability` `POTENTIAL`, never `CONFIRMED`;
promotion is the proposer's alone (RD1). So when
`risk_map.judgment.state is not MEASURED` (no proposer configured, the call
failed, or the citation guard tripped — RD7's three reasons), **no**
`Vulnerability` in the map can ever be `CONFIRMED`, and the clause would
compute PASS by construction rather than because nothing was found. That is
exactly the shape FR-915 exists to forbid, one layer up from `UnifiedRiskMap`
itself. The clause therefore **defers** (named in `deferred`, GD4) whenever
`judgment.state is not MEASURED`, rather than reading the absence of a
judgment layer as the absence of risk.

**Testability blocker in a high-criticality capability.** Testability
findings live on `CapabilityMap.capabilities[].testability`
(`discover/map.py`'s `Capability`), not on `UnifiedRiskMap` — `CapabilityRisk`
carries criticality, threats, vulnerabilities, controls and composites, but
no testability rows of its own. `evaluate()` therefore takes the
`CapabilityMap` as a third input alongside the risk map and joins on `bc_id`
(GD5, GD6) — read, not copied, the same citing discipline E-46 D2 established
for a signal that duplicates another tier's finding.

The check is evaluated **per `(bc_id, TestabilityFinding)` pair**, not once
globally. For every `blocks`-severity finding (`scan/signals/testability.py`'s
three-valued scale — `blocks | impedes | smell`) on capability `bc_id`,
joined against that `bc_id`'s `CriticalityRating` on the risk map:

- `level == HIGH` → fires BLOCK.
- `level` is `MEDIUM` or `LOW` → does not fire, and is **not** deferred — a
  genuinely measured non-HIGH rating is a decided answer, not a gap.
- `criticality.collected.state is not MEASURED` (RD4: SS4 did not collect
  for this capability) → **that pair** is deferred, named individually in
  `deferred` by `bc_id` and finding identity (`testability_identity()`,
  GD7). This replaces a coarser "defer only when *every* capability is
  uncollected" rule: under that rule, one uncollected capability carrying a
  `blocks` finding would read as a silent pass the instant any *other*
  capability happened to have a measured non-HIGH rating — an unrated
  candidate must never read as satisfying the check (FR-915), regardless of
  what a sibling capability's criticality says.

### GD4 — verdict precedence, the per-capability composite quantifier, and who reads `deferred`

`CapabilityRisk.unified` is a per-capability `Composite` — there is no
single map-level "the unified composite" field on `UnifiedRiskMap`. FR-917's
threshold is therefore evaluated **per capability**, with worst-instance
semantics matching the other two clauses (one qualifying vulnerability is
enough to BLOCK; one qualifying capability is enough to BLOCK):

```
For each CapabilityRisk:
  if unified.value.state is MEASURED:
      contributes BLOCK  if unified.value.value >= 0.8
      contributes WARN   if 0.6 <= unified.value.value < 0.8
  else (partial or fully not_collected):
      contributes nothing; bc_id named individually in `deferred`

verdict = BLOCK if unaccepted-confirmed-vulnerability clause fires
             or testability-blocker clause fires (any pair, GD3)
             or any capability contributes BLOCK
        = WARN  if no BLOCK, and any capability contributes WARN
        = PASS  otherwise
```

Under RD3, every capability's `unified` composite is partial on every run
today (the QA composite's `partial` propagates upward for all of them), so
in practice this clause defers for every `bc_id` until E-56 — the same
behaviour the original single-flag version described, now derived from a
per-capability rule that also does the right thing once some capabilities
start reporting MEASURED and others don't. `RiskGateReport.deferred` names
each undecidable instance individually (`"unified composite for BC-014:
partial pending E-56"`), not one blanket line — the same fix GD3 applies to
the testability clause, stated once here because both clauses share the
mechanism.

A verdict of PASS with a non-empty `deferred` is therefore visibly different
from a verdict of PASS with an empty one — FR-915's rule that an unmeasured
check must never read as a pass holds at the gate layer, not just the
composite layer. This is the roadmap's own note (E-49's landing entry) made
literal: *"FR-917's composite BLOCK clause waits on E-56 while its other two
fire."*

**Who reads `deferred`.** Nothing in E-50's own scope does — no phase body
this item touches branches on it. It exists so `Assessment.gates` is
self-describing to a reader of the artifact directly, the same reason
`unbuilt()`'s `Measurement.reason` exists before E-46/E-48/E-49 gave it a
consumer. The two intended future readers are named as roadmap follow-ups,
not built here: **E-52**'s report rendering (a customer reading "PASS"
should see what wasn't actually checked), and **E-51**'s FINISH, which may
choose to fold "the risk gate has an unresolved deferral" into its own
acceptance-criteria computation — that choice is E-51's to make, not
assumed here.

**WARN is deliberately non-blocking and non-notifying.** It never opens a
`GateHost` gate (GD1) and it never fires an FR-303 notification either —
`NotifyReason` (`notify/contract.py`) is scoped to `OPENED | REMIND |
ESCALATE | EXPIRE`, all driven by a gate's own pending-decision lifecycle,
and a WARN that pauses nothing has no such lifecycle to attach a
notification to. Adding a reason and a delivery path for a signal that
blocks nothing would be new infrastructure this item does not need — YAGNI,
the same call RD3 made for a lower BLOCK-only bound on `partial`. WARN
surfaces exactly where PASS with a non-empty `deferred` does: the artifact
(`Assessment.gates.verdict`), read today via the `assessment()` query and,
eventually, E-52's rendered report.

### GD5 — contracts, in `assessment/gates/`

New pure package, mirroring `risk/`, `discover/`, `scan/` — Pydantic and
`measurement.py` only, never `models.py`, `activities.py`, or `temporalio`.

| Contract | Role |
|---|---|
| `RiskGateVerdict` | `BLOCK \| WARN \| PASS` |
| `RiskGateReport` | `verdict`, `checks: tuple[CheckResult, ...]` (reusing `gate.py`'s `CheckResult`/`CheckClass`), `deferred: tuple[str, ...]`, `reasons: tuple[str, ...]` |
| `RiskGateOverride` | `approved_by: Literal["human","policy","timeout"]`, `reviewer`, `reason`, `decided_at`, `gate_round` — field-for-field on `triage/models.py`'s `ReadinessOverride`, for the same reason: local and pure, so a `GateDecision` cannot appear here and `AssessmentWorkflow` maps one to the other |

`checks.py`'s entry point is
`evaluate(risk_map: UnifiedRiskMap, capability_map: CapabilityMap, dispositions: tuple[FindingDisposition, ...]) -> RiskGateReport`
(`CapabilityMap` imported from `discover.map` — pure-to-pure, GD3/GD6). It
builds one `CheckResult` per **clause**, not per capability or per finding:
`risk_no_unaccepted_confirmed_vuln` and
`risk_no_high_criticality_testability_blocker` are always present (each
`ABSOLUTE` in `gate.py`'s `CheckClass` sense, per FR-917's "no advisory lane"
reading); a third, `risk_composite_below_threshold`, is present only when at
least one capability's `unified` composite was actually MEASURED (GD4) — a
clause with nothing to decide contributes no row at all, never a row with
some third `passed` state. Each `CheckResult.detail` names every contributing
`bc_id`/`Vulnerability.key`/finding identity, so a single row stays
self-describing without one row per instance. The only two override paths
are the FR-304 disposition (applied *before* the check runs, GD6) and the
`GateHost` decision (GD2, scoped to this run only) — `gate.py`'s
`GateOverride`/`evaluate_quality_gate` machinery is deliberately not reused
beyond the `CheckResult`/`CheckClass` types themselves, since FR-917's
trichotomy and its two override mechanisms don't fit the binary
pass/advisory-waiver shape `evaluate_quality_gate` was built for.

`RiskGateReport` carries two structural validators, NFR-10 at the model
boundary (the house style `Composite`/`SystemRisk` already establish):
`checks` sorted by `.name`, and `deferred`/`reasons` each sorted-and-deduped
tuples of strings — a producer emitting discovery order is a determinism bug
to catch at the type, not repair silently.

`Assessment` (`assessment/models.py`) gets two new typed fields, following
the `scan`/`discover`/`risk` pattern: `gates: RiskGateReport | None` and
`gate_override: RiskGateOverride | None`. Two validators:
`_gates_agrees_with_risk` requires `gates is not None` iff `risk is not
None` — keyed off `self.risk`, not a `phases` row, because there is no
`PhaseId` for this (GD1); `_override_only_on_block` requires
`gate_override is None` unless `gates is not None and gates.verdict is
RiskGateVerdict.BLOCK` — a stamped override on a WARN or PASS run (which
never opened a gate to decide) is a contradiction the same way a `ScanResult`
on a not_collected `SCAN` phase is.

### GD6 — dispositions and the capability map are separate inputs, not folded into the risk map

Neither addition denormalizes onto a landed E-49/E-48 contract:

- **Dispositions.** `FindingDisposition.key` — either `Vulnerability.key`
  (= `security_identity`) or `testability_identity()`'s output (GD7) — is
  the join key, matching the exact identity E-54's delta and E-53's seeds
  already use, so a disposition survives until the specific instance's
  evidence actually changes, not merely until its weakness class recurs
  elsewhere. `risk/models.py`'s docstring already forbids it importing
  anything beyond `measurement.py` and its own package, and a `disposition`
  field on `Vulnerability` would couple the E-49 contract to E-50's
  persistence layer for a fact only the gate check needs — so dispositions
  are looked up at gate-evaluation time, never stored on the risk map.
- **`CapabilityMap`.** The testability-blocker clause (GD3) needs
  `Capability.testability`, which lives on `discover/map.py`'s
  `CapabilityMap`, not on `UnifiedRiskMap`. `checks.evaluate()` takes the
  `CapabilityMap` as a parameter and reads it directly — the same "cite,
  don't copy" discipline E-46 D2 established for a signal duplicating
  another tier's finding, rather than E-50 re-deriving or caching a second
  copy of testability rows inside `risk/` or `gates/`.

E-49's already-landed `Vulnerability` model in `risk/models.py`, and E-48's
already-landed `Capability` in `discover/map.py`, are both untouched by this
item.

### GD7 — persistence: a board-backed store, mirroring E-47a exactly, covering both finding kinds

FR-917 names three BLOCK clauses and one persistence requirement over "false
positive dispositions," with no textual restriction to vulnerabilities —
and GD3 already found that limiting dispositions to `Vulnerability.key`
would leave a testability blocker permanently un-dispositionable, re-BLOCKing
identically on every re-run with nothing but a per-run `RiskGateOverride`
(GD10) to show for it. The store therefore covers both finding kinds from
the start, distinguished by an explicit discriminator rather than by
sniffing key prefixes — `Vulnerability.key` (`security_identity`, always
prefixed by a security signal id such as `SS1`) and `testability_identity()`
(always prefixed `QS3:`) happen not to collide today, but a `kind` field
makes that a stated invariant rather than an accident the store's row
lookup silently relies on.

New top-level package `src/sdlc/dispositions/`, structured like
`capability/`:

- **`models.py`** (pure) — `Disposition` enum
  (`false_positive | mitigated_elsewhere | accepted_risk`),
  `FindingDisposition` (`kind: Literal["vulnerability", "testability"]`,
  `key`, `disposition`, `approved_by`, `reason`, `decided_at`), with an
  `_audited` validator requiring non-empty `approved_by`/`reason` — modeled
  directly on `IdentityCorrection._audited`.
- **`store.py`** — `FindingDispositionStore(ABC)` +
  `BoardFindingDispositionStore`, reusing the E-78 board's SQLite file and
  `BoardIdentityStore`'s exact discipline: `load(project) -> list[...]`,
  `apply(project, disposition, *, expected_version, actor, ...) -> int`
  under `BEGIN IMMEDIATE` optimistic concurrency, plus a
  `finding_disposition_event` audit table mirroring `capability_event`. One
  live disposition per `(project, kind, key)`; a later `apply()` for the
  same `(kind, key)` updates it (a human revising a prior call), the event
  row keeping the history — ADR-19 (adapters, not substrate), the same seam
  `CapabilityIdentityStore` uses.
- **`cli.py`** — `sdlc risk dispose --project P --kind
  vulnerability|testability --key <Vulnerability.key or
  testability_identity()> --disposition
  false_positive|mitigated_elsewhere|accepted_risk --reason ... --by ...`,
  plus `list`/`export` siblings. CLI, not HTTP, for the same reason
  `capability/cli.py` states: an unauthenticated dashboard route cannot
  provide real provenance for `approved_by` on an audited write (OQ-11 has
  not closed).

`assessment/gates/checks.py` imports only `dispositions.models`
(pure-to-pure — the same cross-package shape `risk/models.py` already uses
importing `scan/models.py`'s `EvidenceRef`), never `dispositions.store`.

### GD8 — re-runs read dispositions through one new activity, uncached

A `load_dispositions(project: str) -> tuple[FindingDisposition, ...]`
activity is added to `assessment/activities.py` — the single shared activity
module the assess/discover/scan phases already use (`discover_lock` wraps
`BoardIdentityStore()` there today; `load_dispositions` wraps
`BoardFindingDispositionStore()` the same way). `AssessmentWorkflow` calls it
right after `_assess`, before evaluating `checks.evaluate` (which also
receives `discover_out.map`, already in memory — no new activity is needed
to supply the `CapabilityMap` input GD3/GD6 added).

The gate evaluation itself is **not memoized**. It is a pure function over
already-loaded typed data (no LLM call, no blob read), so recomputing it
every run costs nothing, and a disposition can change between runs — caching
it under the risk map's own memo key would silently serve a stale verdict
against a disposition a human just recorded. This is a deliberate difference
from `assess_risk`'s own memoization (E-49), which caches expensive
proposer/verification work that dispositions don't touch.

### GD9 — the risk gate's context names what a human needs to decide

`GateContext` (from `pending.py`, already used by the readiness gate) is
populated with the `RiskGateReport`'s `reasons` and the specific
`Vulnerability.key` / `testability_identity()` values that fired — not just
"risk gate BLOCKed" — because the two available responses (APPROVE with a
reason, or go disposition the finding through `sdlc risk dispose --kind ...
--key ...` and re-run) require knowing which finding, and which `kind`, is
in question. This is descriptive of what `GateContext` already carries for
other gates; no new context type is needed.

### GD10 — `RiskGateOverride` is this run only; disposition is the next-run mechanism

These are deliberately two different audited decisions under FR-304, not one
mechanism wearing two hats:

- `RiskGateOverride` (GD5) unblocks *this run*, the same way
  `ReadinessOverride` unblocks one triage. It does not change what the next
  assessment of an unchanged tree computes.
- A `FindingDisposition` (GD7) is what makes the *next* run compute PASS
  or WARN instead of BLOCK on the same finding — the persistence FR-917
  actually asks for ("SHALL persist across re-runs"). This applies uniformly
  to both finding kinds: a `kind="testability"` disposition unblocks a
  recurring testability blocker on future runs exactly as a
  `kind="vulnerability"` one does for a confirmed vulnerability.

A human facing a BLOCK gate has both tools available: approve-and-continue
for this run without touching the disposition store, or open a second
terminal, run `sdlc risk dispose`, and *then* approve — at which point the
override records "why we proceeded today" while the disposition ensures
tomorrow's run doesn't ask again. Neither substitutes for the other, and
conflating them would either make every override permanent (an
under-audited blanket waiver) or make every disposition transient (missing
FR-917's persistence clause entirely).

## Failure modes

| Condition | Behaviour |
|---|---|
| ASSESS did not measure (`risk` is `None`) | `gates` and `gate_override` stay `None`; no gate opens (GD5's validator) |
| a capability's `unified` composite is not MEASURED | that `bc_id` contributes nothing to the composite clause; named individually in `deferred` (GD4) — other capabilities' MEASURED composites still count |
| `risk_map.judgment.state is not MEASURED` | the confirmed-vulnerability clause defers (no `Vulnerability` can be `CONFIRMED` without the judgment layer); named in `deferred` (GD3) |
| a capability's criticality is `not_collected` and it carries a `blocks`-severity testability finding | that `(bc_id, finding)` pair defers, named individually in `deferred` — never silently excluded because another capability happened to be rated (GD3) |
| `load_dispositions` activity fails | treated as zero dispositions loaded for this run — the gate check runs conservatively (nothing is treated as accepted that couldn't be confirmed accepted), never as "assume everything is dispositioned" |
| gate verdict BLOCK, human REJECTs or gate times out `HOLD` | `REPORT`/`GENERATE`/`FINISH` become `skipped()` naming the rejected risk gate; `terminal_status` derives `PARTIAL` as usual (GD2) |
| gate verdict BLOCK, human APPROVEs | `RiskGateOverride` stamped on `Assessment.gate_override`; `REPORT`/`GENERATE`/`FINISH` run normally |
| gate verdict WARN or PASS | no gate opens, no notification fires (GD4); `gate_override` stays `None` (`_override_only_on_block`, GD5) |
| a disposition exists for a `(kind, key)` no longer present in the current risk map / capability map | inert for this run — `evaluate()` only reads dispositions whose `(kind, key)` matches a row in the current inputs; a stale disposition is neither an error nor a phantom pass |

## Testing

- Order-independence assertion for `checks.py` in its own test file
  (`test_every_pure_signal_module_is_order_independent`'s per-module
  pattern) — `evaluate()` must be byte-identical regardless of the input
  order of `risk_map.capabilities`, `capability_map.capabilities`, or
  `dispositions`.
- The two live clauses pinned individually: unaccepted confirmed
  vulnerability fires BLOCK; a `false_positive`/`mitigated_elsewhere`/
  `accepted_risk` disposition on the same `(kind="vulnerability", key)` does
  not; a `blocks`-severity testability finding on a HIGH capability fires
  BLOCK; the same finding on a MEASURED MEDIUM/LOW capability does not (and
  is not deferred); the same finding on a `not_collected`-criticality
  capability defers that pair specifically, even when a *different*
  capability in the same map is measured MEDIUM/LOW — the mixed-criticality
  case GD3 fixed.
- The composite clause pinned per capability: one capability MEASURED
  `>= 0.8` fires BLOCK regardless of a second capability being partial; one
  capability MEASURED in `[0.6, 0.8)` with no BLOCK anywhere fires WARN; all
  capabilities partial defers the whole clause (today's RD3 reality) with
  every `bc_id` named in `deferred`.
- The judgment-degraded case: a map with a `CONFIRMED`-shaped vulnerability
  that never was, because `judgment.state is not MEASURED`, asserts the
  confirmed-vulnerability clause is deferred (not silently PASS) and that
  `deferred` names it.
- `RiskGateReport.verdict` precedence: a case with both a live BLOCK clause
  and a MEASURED composite in the WARN band asserts BLOCK wins.
- `RiskGateReport`'s structural validators: `checks` sorted by name;
  `deferred`/`reasons` sorted-and-deduped; `gate_override` present only when
  `gates.verdict is BLOCK` (`_override_only_on_block`).
- `FindingDispositionStore`: optimistic-concurrency conflict on a stale
  `expected_version`; `load()` returning the current row after two
  `apply()` calls to the same `(kind, key)` (revision, not accumulation);
  the event table recording both; a `kind="vulnerability"` and
  `kind="testability"` disposition sharing the same literal `key` string
  never collide (the `(kind, key)` composite primary key, not prefix
  sniffing, is what the test pins).
- Temporal e2e: a risk map with one unaccepted confirmed vulnerability opens
  the `"risk"` gate; `submit_gate_decision(REJECT)` leaves REPORT/GENERATE/
  FINISH as `skipped()` with an FR-917 reason; `submit_gate_decision(APPROVE)`
  stamps `gate_override` and lets them run; a second assessment of the same
  tree after `sdlc risk dispose --kind vulnerability --disposition
  accepted_risk` computes PASS with no gate opened. A second e2e case pins a
  `blocks`-severity testability finding on a HIGH capability opening the
  gate and `sdlc risk dispose --kind testability` clearing it on re-run.
- Structural: `RiskGateReport.checks` never contains a `CheckResult` for a
  deferred clause — deferral is represented by absence plus `deferred`,
  never by a `CheckResult` with some third `passed` state, keeping `gate.py`'s
  `CheckResult.passed: bool` unchanged.

## Scope

### Not covered

- **Acceptance criteria and cross-reference integrity** — E-51. `gates`
  becoming one more `CheckResult` FINISH folds in is that item's call to
  make.
- **Reports and the evidence bundle rendering the gate outcome** — E-52.
- **Whether a rejected assessment blocks E-53's spec-seed brownfield runs**
  — E-53's own scope; this item stamps `terminal_status`/`gate_override`
  legibly enough for that item to read, and does not reach forward into it.
- **Activating the composite-keyed clauses** — E-56 (`/enrich`), per RD3.
- **A monitoring or authorization control source** — RD5's own follow-ups
  (E-49), unaffected by this item.
- **A dashboard route for recording dispositions** — deferred until OQ-11
  closes, per GD7.

## Roadmap deltas

| Item | Change |
|---|---|
| E-50 | `[ ]` → `[x]` on landing |
| FR-917 | `[ ]` → `[ ] ⚠️`: the two non-composite clauses live; the composite-threshold BLOCK and WARN clauses remain deferred pending E-56 (unchanged from E-49's note, now enforced in code rather than merely documented) |
| FR-106 | New consumer: the risk gate's two live checks are `CheckResult`s under `gate.py`'s existing `CheckClass.ABSOLUTE` |
| FR-304 | New consumer: `FindingDisposition` (both `vulnerability` and `testability` kinds) is an audited decision persisting across re-runs, alongside `IdentityCorrection` (E-47a) and `ReadinessOverride` (E-42/E-45) |
| NFR-10 | One more pure module (`assessment/gates/checks.py`) under the order-independence assertion |
| P6 | Unchanged at three of seven phase bodies (E-46/E-48/E-49) — this item adds a gate between ASSESS and REPORT, not a phase body of its own |
