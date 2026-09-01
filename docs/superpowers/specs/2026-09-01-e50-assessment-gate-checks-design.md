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
across re-runs of an unchanged finding) carries no `VulnerabilityDisposition`
in the store. All three disposition values —
`false_positive | mitigated_elsewhere | accepted_risk` — count as *accepted*
for this clause: FR-304 does not distinguish "the risk is dispositioned
because it isn't real" from "dispositioned because it's tolerated," and this
check should not either.

**Testability blocker in a high-criticality capability.** A `TestabilityFinding`
with `severity == "blocks"` (`scan/signals/testability.py`'s own severity
vocabulary — `blocks | impedes | smell`) on a capability whose
`CriticalityRating.level == HIGH`. A capability whose criticality is
`not_collected` is excluded — RD4 already refuses to treat an unrated
capability as low-criticality by absence, and this check refuses to treat it
as high-criticality by absence either. If **every** capability's criticality
is `not_collected` (SS4 did not collect), the check itself is deferred (GD4)
rather than silently passing.

### GD4 — verdict precedence, and the deferred composite clauses

```
BLOCK  if unaccepted confirmed vulnerability exists
       or a testability blocker exists on a HIGH capability
       or (unified composite is MEASURED and >= 0.8)
WARN   if none of the above BLOCK, and unified composite is MEASURED and in [0.6, 0.8)
PASS   otherwise
```

While the unified composite `is_partial` (RD3: true on every run until
E-56), **both** composite-keyed clauses — BLOCK's `>= 0.8` and WARN's
`[0.6, 0.8)` — are not evaluated. They contribute nothing to the verdict,
rather than reading as satisfied or failed either way. `RiskGateReport`
carries this as a `deferred: tuple[str, ...]` field naming exactly what
wasn't checked and why (`"unified composite thresholds (BLOCK >= 0.8, WARN
0.6-0.79): composite is partial pending E-56"`). A verdict of PASS with a
non-empty `deferred` is therefore visibly different from a verdict of PASS
with an empty one — FR-915's rule that an unmeasured check must never read
as a pass holds at the gate layer, not just the composite layer. This is the
roadmap's own note (E-49's landing entry) made literal: *"FR-917's composite
BLOCK clause waits on E-56 while its other two fire."*

The same testability-all-`not_collected` case from GD3 is named in `deferred`
too, using the same mechanism rather than a second field.

### GD5 — contracts, in `assessment/gates/`

New pure package, mirroring `risk/`, `discover/`, `scan/` — Pydantic and
`measurement.py` only, never `models.py`, `activities.py`, or `temporalio`.

| Contract | Role |
|---|---|
| `RiskGateVerdict` | `BLOCK \| WARN \| PASS` |
| `RiskGateReport` | `verdict`, `checks: tuple[CheckResult, ...]` (reusing `gate.py`'s `CheckResult`/`CheckClass`), `deferred: tuple[str, ...]`, `reasons: tuple[str, ...]` |
| `RiskGateOverride` | `approved_by: Literal["human","policy","timeout"]`, `reviewer`, `reason`, `decided_at`, `gate_round` — field-for-field on `triage/models.py`'s `ReadinessOverride`, for the same reason: local and pure, so a `GateDecision` cannot appear here and `AssessmentWorkflow` maps one to the other |

`checks.py` builds the two live `CheckResult`s (GD3) plus the composite
clause (`None` when deferred, per GD4) and assembles `RiskGateReport` with
GD4's precedence. Both live checks are **ABSOLUTE** in `gate.py`'s
`CheckClass` sense — FR-917 calls these deterministic gate checks with no
advisory-waiver lane, and the only two override paths are the FR-304
disposition (applied *before* the check runs, GD6) and the `GateHost`
decision (GD2, scoped to this run only). `gate.py`'s `GateOverride` /
`evaluate_quality_gate` override machinery is deliberately not reused here —
FR-917's trichotomy and its two distinct override mechanisms don't fit the
binary pass/advisory-waiver shape `evaluate_quality_gate` was built for; only
the `CheckResult`/`CheckClass` types are shared.

`Assessment` (`assessment/models.py`) gets two new typed fields, following
the `scan`/`discover`/`risk` pattern: `gates: RiskGateReport | None` and
`gate_override: RiskGateOverride | None`. A new validator
`_gates_agrees_with_risk` requires `gates is not None` iff `risk is not
None` — keyed off `self.risk`, not a `phases` row, because there is no
`PhaseId` for this (GD1).

### GD6 — dispositions are a separate input, not part of the risk map

The pure gate-check function's signature is
`evaluate(risk_map: UnifiedRiskMap, dispositions: tuple[VulnerabilityDisposition, ...]) -> RiskGateReport`.
`Vulnerability.key` (= `security_identity`) is the join key — the same
identity E-54's delta and E-53's seeds already match on, so a disposition
survives until the specific instance's evidence actually changes, not merely
until its weakness class recurs elsewhere.

E-49's already-landed `Vulnerability` model in `risk/models.py` is untouched.
Dispositions are looked up at gate-evaluation time, not denormalized onto
the risk map — `risk/models.py`'s docstring already forbids it importing
anything beyond `measurement.py` and its own package, and a `disposition`
field would couple the E-49 contract to E-50's persistence layer for a fact
that only the gate check needs.

### GD7 — persistence: a board-backed store, mirroring E-47a exactly

New top-level package `src/sdlc/dispositions/`, structured like
`capability/`:

- **`models.py`** (pure) — `Disposition` enum
  (`false_positive | mitigated_elsewhere | accepted_risk`),
  `VulnerabilityDisposition` (`key`, `disposition`, `approved_by`, `reason`,
  `decided_at`), with an `_audited` validator requiring non-empty
  `approved_by`/`reason` — modeled directly on `IdentityCorrection._audited`.
- **`store.py`** — `VulnerabilityDispositionStore(ABC)` +
  `BoardVulnerabilityDispositionStore`, reusing the E-78 board's SQLite file
  and `BoardIdentityStore`'s exact discipline: `load(project) -> list[...]`,
  `apply(project, disposition, *, expected_version, actor, ...) -> int`
  under `BEGIN IMMEDIATE` optimistic concurrency, plus a
  `vulnerability_disposition_event` audit table mirroring
  `capability_event`. One live disposition per `(project, key)`; a later
  `apply()` for the same key updates it (a human revising a prior call), the
  event row keeping the history — ADR-19 (adapters, not substrate), the same
  seam `CapabilityIdentityStore` uses.
- **`cli.py`** — `sdlc risk dispose --project P --key <Vulnerability.key>
  --disposition false_positive|mitigated_elsewhere|accepted_risk --reason ...
  --by ...`, plus `list`/`export` siblings. CLI, not HTTP, for the same
  reason `capability/cli.py` states: an unauthenticated dashboard route
  cannot provide real provenance for `approved_by` on an audited write
  (OQ-11 has not closed).

`assessment/gates/checks.py` imports only `dispositions.models`
(pure-to-pure — the same cross-package shape `risk/models.py` already uses
importing `scan/models.py`'s `EvidenceRef`), never `dispositions.store`.

### GD8 — re-runs read dispositions through one new activity, uncached

A `load_dispositions(project: str) -> tuple[VulnerabilityDisposition, ...]`
activity is added to `assessment/activities.py` — the single shared activity
module the assess/discover/scan phases already use (`discover_lock` wraps
`BoardIdentityStore()` there today; `load_dispositions` wraps
`BoardVulnerabilityDispositionStore()` the same way). `AssessmentWorkflow`
calls it right after `_assess`, before evaluating `checks.evaluate`.

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
`Vulnerability`/`TestabilityFinding` rows that fired — not just "risk gate
BLOCKed" — because the two available responses (APPROVE with a reason, or go
disposition the finding through `sdlc risk dispose` and re-run) require
knowing which finding is in question. This is descriptive of what
`GateContext` already carries for other gates; no new context type is
needed.

### GD10 — `RiskGateOverride` is this run only; disposition is the next-run mechanism

These are deliberately two different audited decisions under FR-304, not one
mechanism wearing two hats:

- `RiskGateOverride` (GD5) unblocks *this run*, the same way
  `ReadinessOverride` unblocks one triage. It does not change what the next
  assessment of an unchanged tree computes.
- A `VulnerabilityDisposition` (GD7) is what makes the *next* run compute PASS
  or WARN instead of BLOCK on the same finding — the persistence FR-917
  actually asks for ("SHALL persist across re-runs").

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
| unified composite `is_partial` | composite-keyed BLOCK/WARN clauses omitted from evaluation; named in `deferred` (GD4) |
| every capability's criticality `not_collected` | testability-blocker clause omitted; named in `deferred` (GD3/GD4) |
| `load_dispositions` activity fails | treated as zero dispositions loaded for this run — the gate check runs conservatively (nothing is treated as accepted that couldn't be confirmed accepted), never as "assume everything is dispositioned" |
| gate verdict BLOCK, human REJECTs or gate times out `HOLD` | `REPORT`/`GENERATE`/`FINISH` become `skipped()` naming the rejected risk gate; `terminal_status` derives `PARTIAL` as usual (GD2) |
| gate verdict BLOCK, human APPROVEs | `RiskGateOverride` stamped on `Assessment.gate_override`; `REPORT`/`GENERATE`/`FINISH` run normally |
| a disposition exists for a `Vulnerability.key` no longer present in the current risk map | inert for this run — `evaluate()` only reads dispositions whose key matches a row in the current map; a stale disposition is neither an error nor a phantom pass |

## Testing

- Order-independence assertion for `checks.py` in its own test file
  (`test_every_pure_signal_module_is_order_independent`'s per-module
  pattern) — `evaluate()` must be byte-identical regardless of the input
  order of `risk_map.capabilities` or `dispositions`.
- The three clauses pinned individually: unaccepted confirmed vulnerability
  fires BLOCK; a `false_positive`/`mitigated_elsewhere`/`accepted_risk`
  disposition on the same key does not; a `blocks`-severity testability
  finding on a HIGH capability fires BLOCK, the same finding on a MEDIUM/LOW
  capability does not, and on a `not_collected`-criticality capability does
  not (and is not silently treated as passing — covered by the deferred
  case below).
- `deferred` pinned in all three cases the composite clause can be in:
  partial composite defers both BLOCK and WARN; all-`not_collected`
  criticality defers the testability clause; a fully measured map with no
  deferrals leaves `deferred` empty.
- `RiskGateReport.verdict` precedence: a case with both a live BLOCK clause
  and a MEASURED composite in the WARN band asserts BLOCK wins.
- `VulnerabilityDispositionStore`: optimistic-concurrency conflict on a
  stale `expected_version`, `load()` returning the current row after two
  `apply()` calls to the same key (revision, not accumulation), and the
  event table recording both.
- Temporal e2e: a risk map with one unaccepted confirmed vulnerability opens
  the `"risk"` gate; `submit_gate_decision(REJECT)` leaves REPORT/GENERATE/
  FINISH as `skipped()` with an FR-917 reason; `submit_gate_decision(APPROVE)`
  stamps `gate_override` and lets them run; a second assessment of the same
  tree after `sdlc risk dispose --disposition accepted_risk` computes PASS
  with no gate opened.
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
| FR-304 | New consumer: `VulnerabilityDisposition` is an audited decision persisting across re-runs, alongside `IdentityCorrection` (E-47a) and `ReadinessOverride` (E-42/E-45) |
| NFR-10 | One more pure module (`assessment/gates/checks.py`) under the order-independence assertion |
| P6 | Unchanged at three of seven phase bodies (E-46/E-48/E-49) — this item adds a gate between ASSESS and REPORT, not a phase body of its own |
