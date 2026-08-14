# Discover proposers

**Date:** 2026-08-15
**Status:** approved design, ready for planning
**Scope:** E-48 — the discover phase body, clauses D1–D8
**Satisfies:** FR-913 (wires all four clauses); FR-914 (its awaited consumer); FR-103 (E-47a's pending amendment); contributes to FR-102, SC-7, SC-8
**Depends on:** E-45 (DAG shell), E-46 (scan), E-47a (identity), E-47b (attribution), E-47c (operations, ownership), E-43 (grounding)
**Does not cover:** E-49 (risk), E-50 (gates), E-51 (acceptance criteria), E-52 (bundle), E-56 (`/enrich`)

## Problem

Four mechanisms have landed pure and unwired. `attribute()` classifies every
file and computes the coverage floor. `decompose()` turns contract members into
L2 operations. `assign()` resolves entity ownership or surfaces the contest.
`resolve()` attaches stable `BC-NNN` ids by weighted-Jaccard similarity. Each
was built against synthetic inputs, and each spec deferred the same thing to
this item: **the phase that calls them.**

`workflows/assessment.py:433` still returns `unbuilt(PhaseId.DISCOVER)`, so an
admitted assessment scans thirteen signals, produces a merged candidate set, and
then reports that it never discovered anything. The gap is not mechanism. It is
the decision in the middle: **a scan candidate is not a capability.** S5 merges
what four signals independently noticed; something must then decide which of
those are real business capabilities, which are two views of one thing, which
are a delivery channel wearing a domain name, and which need splitting.

Three properties make that decision harder than a filter:

1. **It is genuinely judgment, and this tier exists to distrust judgment.**
   §11's whole thesis is that BrownKit's prose gates *"become `CheckResult`s
   computed by pure code."* A design that hands the capability map to a model
   and grades it with another model has ported the problem, not the method.
2. **The map's identity is load-bearing and long-lived.** E-47a's surrogate
   `BC-NNN` is cited by clients across assessments. Its promise is that *"an id
   clients cite must not move because an unrelated capability's score changed."*
   Anything that makes the proposed boundary set churn between runs on an
   unchanged tree breaks that promise through the fingerprint.
3. **This is the first LLM-proposing stage in the assessment tier.** FR-914 has
   been held open for exactly this moment — the roadmap says the verifier
   "stays open until an LLM-proposing assessment stage cites the same way,
   which is where the check stops being a drift guard." Whatever citation
   discipline lands here is the one E-49 and E-52 will inherit.

## Decision

Thirteen decisions, numbered **DD1–DD13**. The roadmap's E-48 entry already
numbers BrownKit's `/discover` clauses D1–D8, and those numbers appear
throughout this document; the design decisions carry a distinct prefix so a
later citation cannot mean two things.

### DD1 — proposers dispose, they do not author (→ ADR-22)

Code computes everything computable and hands the model a packet it can only
*judge*. The model emits one action per candidate —
`CONFIRM | SPLIT | MERGE | DE_SCOPE | FLAG`, clause D2 — with a rationale and
evidence references. It cannot mint a candidate, name a file that is not in the
tree, invent a metric, or write the map.

This is not a local preference, which is why it becomes **ADR-22**. It resolves
clause D1 (cohesion, coupling, boundary clarity) as arithmetic rather than
opinion: cohesion is intra-capability edge density and coupling is
cross-capability edge count, both over the reference graph `refgraph.build()`
already produces. It resolves clause D3 as `attribute()`. Clauses D6 and D6a
become joins against `ScanResult.security`, `.testability` and `.coverage`,
carrying their `Measurement`s through unmodified so a QA context that was never
collected says so (FR-915).

The alternative — the model authors L1 directly — was considered and rejected.
It buys recall, and it costs the map's determinism: fingerprints move between
runs on an identical tree, so ids move, and E-47a's central guarantee fails. The
recall it buys is also recoverable another way; see DD11.

One consequence, stated rather than hidden: **a capability no scan signal saw
at all stays invisible until a blueprint flags the gap.** That is the correct
failure direction. A missing capability is a reported gap; a hallucinated one is
a wrong map that looks right.

### DD2 — placement

Five new modules in `src/sdlc/assessment/discover/`, beside E-47b/c's:

| Module | Contents | Pure? |
|---|---|---|
| `map.py` | phase-level contracts, incl. `CapabilityMap` | yes |
| `tiers.py` | `MemberKind → SignalTier` (DD3) | yes |
| `context.py` | cohesion, coupling, guardrail flags, security/QA joins | yes |
| `apply.py` | dispositions → the locked candidate set | yes |
| `blueprint.py` | clause D8 loader and comparison | yes |

Contracts go in `map.py` rather than the package's `models.py`. E-47b/c's
`models.py` holds *sub-mechanism* reports and is already 387 lines; the phase
artifact is a different layer, and a 600-line contract module is the file-doing-
too-much signal.

The package rule from E-47c D2 is unchanged and still binds: `discover/` imports
scan **rule** modules and never a signal. A signal is a producer with a memo key
and a version, and importing one here would make this package part of that
signal's hashed surface.

### DD3 — the `MemberKind → SignalTier` map, and why it is not `CONTRACT_KINDS`

Two modules explicitly reserve this map for E-48 and forbid deriving it from its
neighbour. `scan/models.py:95` (D13) requires it be **total** — "the value set
is chosen so every `CapabilityFingerprint` tier has members that can populate
it." `discover/models.py:151` (E-47c D4) warns that it and `CONTRACT_KINDS`
must never be derived from each other, because "two uses of the word 'contract'
that agree only by coincidence is precisely the defect `PipelineConfig.roles`'
boot-time mirror assertion exists to prevent."

```python
MEMBER_TIERS: dict[MemberKind, SignalTier] = {
    MemberKind.HTTP_ROUTE:      SignalTier.CONTRACT,
    MemberKind.CLI_COMMAND:     SignalTier.CONTRACT,
    MemberKind.DB_TABLE:        SignalTier.CONTRACT,
    MemberKind.QUEUE_TOPIC:     SignalTier.CONTRACT,
    MemberKind.GRPC_METHOD:     SignalTier.CONTRACT,
    MemberKind.SCHEDULED_JOB:   SignalTier.CONTRACT,
    MemberKind.FRONTEND_ROUTE:  SignalTier.CONTRACT,
    MemberKind.TEST_NAME:       SignalTier.BEHAVIORAL,
    MemberKind.ENTITY_NAME:     SignalTier.BEHAVIORAL,
    MemberKind.EXPORTED_SYMBOL: SignalTier.STRUCTURAL,
    MemberKind.PACKAGE_PATH:    SignalTier.LOCATIONAL,
    MemberKind.FILE_PATH:       SignalTier.LOCATIONAL,
}
```

Totality is asserted by a test over `MemberKind`, so adding a kind to the enum
fails CI rather than silently landing in no tier.

**The warning was written before either set existed, and it is correct on the
merits: the CONTRACT tier and `CONTRACT_KINDS` genuinely differ, by exactly
`DB_TABLE`.**

A table is contract-tier *identity* evidence — E-47a's `SignalTier` docstring
reads "routes, CLI commands, tables, topics," and a table name survives
refactors that rename every symbol in the tree. A table is **not an operation**:
`CONTRACT_KINDS` excludes it because an operation is "something the system
DOES, reachable from outside the capability," and a table is something the
system *has*.

`ENTITY_NAME` makes the same point from outside both sets. It reads as
contract-ish vocabulary, but it lands `BEHAVIORAL` for identity and is not an
operation either — so it belongs to neither set. The two vocabularies are not
a wide set and a narrow one; they classify on different axes, which is why
deriving one from the other would be wrong even where they happen to agree.

The test asserts the difference in both directions:

```python
tier_contract = {k for k, t in MEMBER_TIERS.items() if t is SignalTier.CONTRACT}
assert tier_contract - CONTRACT_KINDS == {MemberKind.DB_TABLE}
assert CONTRACT_KINDS - tier_contract == set()
```

A future edit that collapses them fails rather than drifts.

### DD4 — the phase pipeline

```
_discover(inp, triage, scan)
  1  discover_context      [activity]  blobs → refgraph → cohesion/coupling,
                                       guardrail flags, security/QA joins
  2  memo lookup           [activity]  DD10's key → hit? return the stored map
  3  t_discover            [proposer]  one disposition per candidate
  4  verify_discover_refs  [activity]  DD8's grounding checks
  5  apply()               [pure]      dispositions → locked candidate set
  6  discover_lock         [activity]  fingerprint → resolve() → BC-NNN  ← D4
  7  discover_finalize     [activity]  attribute() + decompose() + assign()
  8  compare_blueprint()   [pure]      clause D8
```

The activity/workflow split follows E-46's rule: pure functions run in workflow
code, anything touching bytes or the identity store runs in an activity.

**Attribution runs after disposition, not before.** E-47b's D1 anticipated
this — computing coverage earlier "would mean either building part of E-48 or
computing coverage against a candidate set nobody had confirmed." `attribute()`
takes `members: bc_id → paths`, and no `bc_id` exists until step 6.

**Steps 1 and 7 each read blobs at the pinned commit.** Deliberate. The
alternative — building the reference graph once and passing it between
activities — pushes an entire tree's edge list through workflow history, which
is the FR-702 hazard the roadmap carries as open. Blob reads are cheap beside a
model call, and `_source_blobs` already returns the `(blobs, skipped)` pair
`attribute()` wants.

The phase returns `Assessment.discover: CapabilityMap | None`, carrying the same
paired validator `scan` has: a `not_collected` DISCOVER row shipping a
`CapabilityMap` is a contradiction the type refuses. `terminal_status` needs no
edit — it derives `assessed:partial` as designed (E-45 D6).

### DD5 — the lock is identity resolution, and there is no gate here

Clause D4 ("lock") is step 6 and nothing more. E-47a settled it: *"Locking the
capability set and assigning identity to it are the same moment; the port
already has the hook."*

No human gate opens in discover. The audited reversal path exists already and is
E-47a's `IdentityCorrection`, modelled on `gate.py`'s `GateOverride` and
CLI-only until **OQ-11** closes. E-50 owns assessment gate checks; adding a
second approval surface here would be two mechanisms for one judgment.

### DD6 — the deterministic baseline disposition

Before the model is consulted, code computes a disposition for every candidate:

| Condition | Baseline |
|---|---|
| supported only by `s1_layer_name` / `s1_generic_name` | `DE_SCOPE` |
| non-empty `possible_duplicate_of` | `FLAG` |
| otherwise | `CONFIRM` |

The first row **is** the clause-D2 guardrail — *delivery channels and deployment
boundaries are not capabilities* — and it is code-computable because S1 already
records which rule fired. The scan spec says so directly: the classification is
expressed as a rule rather than a boolean "because E-48's guardrail needs the
distinction, not only its outcome."

The second row is the honest limit of code: S5 detects the possible duplicate,
but only judgment decides MERGE versus genuinely-distinct.

The baseline is a real rule, not a placeholder. It makes plan 2 a live,
defensible discover phase with no model in it (DD13), and it gives DD7 a
fallback that is better than refusing to answer.

### DD7 — the proposer role is optional, and the two fallbacks differ

`agents/discover/` (`agent.yaml`, `instructions.md`, `agent.py`) joins
`OPTIONAL_ROLES`, not `PROPOSER_ROLES`. Every stage-gated agent in this repo is
optional — `research`, `deep_review`, `handoff`, `adversary` — and making an
assessment-only agent required would fail boot on a feature-only deployment.
`KNOWN_ROLES` still contains it, so `loader.py`'s unknown-directory check keeps
biting. `_discover` guards on `t_discover is not None`, feature.py's `t_research`
pattern.

Two fallbacks, deliberately not one:

- **proposer absent** (role not shipped, or the stage is off) → DD6's baseline
  for every candidate, and the map records that no proposer ran.
- **disposition dropped** (the model cited something fabricated, DD8) → `FLAG`
  for that candidate, never the baseline.

This is `unbuilt_signal` versus `failed_signal`, which `activities.py:136`
already separates on exactly this ground: *"'we tried and could not' is not
'nobody has written this yet' — the reason strings must not converge."* A model
that cited garbage is evidence about that candidate; quietly laundering its
verdict into the baseline would discard that evidence.

### DD8 — grounding: resolve every reference, verify every quote, drop the item

Before any disposition is applied, code enforces:

1. every `candidate_id` resolves to a candidate in the context;
2. exactly one disposition per candidate — missing or duplicated becomes `FLAG`;
3. `MERGE` targets resolve, and a `SPLIT` partitions **the candidate's own
   members** — no invented members;
4. every `EvidenceRef` path exists at the pinned commit and its line range lies
   inside that file;
5. any quote byte-verifies under `Profile.VERBATIM_BYTES` — the profile for
   code, where "a quote glyph is content, not noise."

**A violation drops the item; it does not fail the phase.** The E-43 rule is
"research fails its stage, the two lenses drop the item," and discover is a lens
over many candidates rather than a single artifact.

**A phase-level citation guard bounds that leniency**, mirroring E-47b's dead
guard (`DEAD_GUARD_MAX_UNRESOLVED = 0.10`). Its logic transfers unchanged: past
a fabrication rate of 0.10 over all references, too many failed to resolve for
the surviving ones to be evidence, and the phase reports `not_collected` rather
than shipping a map built on a proposal that mostly cites nothing.

Two consequences. **FR-914 closes** — this is the LLM-proposing assessment stage
it was held open for. And **SC-7's second clause stops being sampled**: "zero
fabricated path/line refs" is computed for every reference on every run.

### DD9 — degradation

Discover composes fail-closed behaviour that already exists rather than
inventing new rules: `decompose()` fails closed on S3, `assign()` on either S2
or S3, `attribute()` returns an empty report carrying its reason. Two rules are
this item's own.

**The phase is `not_collected`** only when the capability set itself could not be
produced:

| Condition | Result |
|---|---|
| S5 did not collect (no candidates) | phase `not_collected`, naming S5 |
| proposer role absent | **not** a failure — DD7's baseline runs |
| citation guard tripped (DD8) | phase `not_collected` |
| identity store unreachable | phase `not_collected` — E-47a's fail-closed rule |
| `discover_context` activity failed | phase `not_collected` |

Failing closed on the store is E-47a's call, not a new one: proceeding "produces
a complete, plausible-looking map in which every id is wrong, and the next
successful write commits that corruption."

**Everything else degrades per-report inside the map**, following scan's
precedent — the SCAN phase reports `measured(count)` while individual rows carry
their own `not_collected`. A map whose ownership half did not collect because S2
degraded still ships, with the gap visible where it happened.

### DD10 — memoization: FR-103's pending amendment lands here

Key: `(tree_hash, context_digest, identity_registry_version, prompt_sha, model)`.

The memo is over the **whole phase**: a hit returns the stored `CapabilityMap`
and steps 3–8 are skipped entirely, including the lock. That is safe precisely
because `identity_registry_version` is a key term — if the registry moved, the
key moved, so a hit implies the stored map's ids are still the registry's, and
`resolve()` would re-apply rows the store already holds.

`tree_hash` alone is insufficient — the same tree yields a different
`ScanResult` when a signal's `version` or `rules_sha` moves, and a tree-keyed
memo would serve a stale map. `context_digest` is a canonical digest over the
`DiscoverContext` produced in step 1, which is by construction exactly the set
of facts the rest of the phase reads. Digesting the packet rather than
hand-listing its parts follows `brief_digest`'s reasoning — prose and ordering
drop out, facts remain, so identical facts hit and new facts invalidate — and
removes the hazard that a later field added to the context escapes the key.

The two terms cover different variation: `context_digest` catches scan-version
and rules changes on an unchanged tree; `tree_hash` catches the blob-dependent
steps (`attribute()` reads the whole inventory, not just the context).

`identity_registry_version` is FR-103's amendment from E-47a, and it needs no
new store API — `CapabilityIdentityStore.registry_version(project)` already
exists. It is deliberately coarse: any identity write invalidates the whole map
for that project, and the map is a single artifact with no per-capability
memoization to preserve.

`prompt_sha` and `model` follow the established `content_key` discipline, so a
prompt edit or a per-role model change invalidates exactly this stage.

Store rule is `scan/memo.py`'s, verbatim in intent: **only a MEASURED map is
stored.** Never serve a failure forever.

### DD11 — clause D8: a typed seam and one reference blueprint

`blueprints/<name>.yaml` at the repo root, matching `schedules/`' flat-file
convention and the same filesystem-as-registry thesis `agents/` follows.
`discover/blueprint.py` loads and compares; `MISSING` is context, not failure.

**One reference blueprint ships: APQC's cross-industry process classification,
trimmed to its top two levels.** This is the ADR-15 precedent — Python end-to-end
with Go/TS/Rust deferred to E-30a/b/c — applied to reference data. APQC is in
BrownKit's own set, so the port stays faithful, and unlike BIAN, ACORD or HL7 it
applies to arbitrary repositories, which means it can be exercised against the
existing corpus instead of requiring a banking repo. The trade is that it is the
least specific of the seven and will produce broader `MISSING` sets than a
domain-matched blueprint; given MISSING is context, that is the correct
direction to err. Curating the remaining six is data work and gets its own item.

This is also where DD1's acknowledged blind spot is recovered. Comparing the
discovered set against a blueprint and reporting `MISSING` **is** the recall
check — "what does this repository not have that its industry normally does" —
so approach A forfeits nothing that an adversarial second lens would have found,
without a second model call and without letting a model touch the map.

### DD12 — clause D7 is derived, not re-judged

The consolidated domain model is built from `assign()`'s output: entities, their
owner where one resolved, the capabilities that read them, and the `CONFLICT` /
`UNDIRECTED` / `UNCLAIMED` outcomes surfaced as they are. E-47c kept those three
distinct precisely so a CLI-written table is never reported as untouched, and
D7 must not re-collapse them.

The model is not asked to re-decide ownership. Its standing to override a
conflict is exercised through a disposition on the *capability*, which changes
the member set `assign()` runs over — not by editing the ownership table.

`OwnershipVerb.TRACKS` remains unemitted. E-47c reserved it for "E-48's
proposer," and under DD1 the proposer does not author rows, so nothing in this
item emits it. Recorded as a deliberate deferral rather than an oversight: it
needs a producer with the standing to write an ownership row, and no such
producer exists in this design.

### DD13 — no `CheckResult`, and the three-plan split

Discover computes no gate check. E-50 owns risk thresholds as deterministic
gate checks; E-51 owns the acceptance criteria and the absolute
cross-reference-integrity check. DD1 makes E-51's job tractable — a model that
can only cite ids present in its input cannot produce a dangling reference —
but the check itself is not this item's.

| Plan | Lands | State after |
|---|---|---|
| **1 — inputs** | `map.py`, `tiers.py`, `context.py`, `discover_context` activity, `Assessment.discover` + paired validator | `_discover` still `unbuilt` |
| **2 — the deterministic spine** | `apply.py`, fingerprint construction, `discover_lock`, `discover_finalize`, the DD10 memo, `_discover` wired, temporal e2e | DISCOVER **measured** with no model; `terminal_status` → `assessed:partial` |
| **3 — judgment** | `agents/discover/`, `t_discover`, DD8's verification + guard, `blueprint.py` + `blueprints/apqc.yaml`, D7's domain model | clauses D1–D8 complete |

Plan 2 is a live phase rather than a stub because DD6's baseline is a real rule.
If plan 3 slipped, the tier would still have advanced and the map would still be
defensible — it would simply lack the judgment layer, and say so.

## Contracts

In `discover/map.py`:

| Contract | Role |
|---|---|
| `DiscoverAction` | `CONFIRM \| SPLIT \| MERGE \| DE_SCOPE \| FLAG` |
| `CandidateDisposition` | candidate_id, action, rationale, `EvidenceRef`s, split/merge targets |
| `DiscoverProposal` | the proposer's `output_type` — dispositions and nothing else |
| `DiscoverContext` | the deterministic packet handed to the proposer |
| `Capability` | one L1 record: `bc_id`, local_key, name, members, cohesion, coupling, security join, QA join, the disposition that produced it |
| `DomainModel` | DD12, derived from `assign()` |
| `BlueprintGap` / `BlueprintComparison` | DD11 — `PRESENT` / `MISSING` / `EXTRA` |
| `CapabilityMap` | the phase artifact |

`CapabilityMap` carries capabilities, the `AttributionReport`, the
`DecompositionReport`, the `OwnershipReport`, the domain model, the blueprint
comparison, E-47a's advisories, the dropped-disposition record, and `collected`.

Contract discipline follows the package's existing rules, which are not restated
per-model but do bind every new contract here: counts derived from rows and
never assigned; sorted-and-deduped asserted rather than repaired (a producer
emitting discovery order is an NFR-10 determinism bug, and repairing it hides
that); and `_unmeasured_carries_no_payload` — a report that did not collect has
no rows.

## Failure modes

| Condition | Behaviour |
|---|---|
| S5 did not collect | Phase `not_collected` naming S5 |
| S2 or S3 degraded, S5 healthy | Map ships; ownership and/or decomposition `not_collected` inside it |
| Fingerprint uncomputable for a capability | E-47a: `not_collected` → fresh id + advisory. Never scored 0 |
| Proposer absent | DD6 baseline; map records no proposer ran |
| Proposer returns a malformed disposition | That candidate → `FLAG` |
| Fabricated path/line ref | Disposition dropped → `FLAG`; counted toward the guard |
| Fabrication rate > 0.10 | Phase `not_collected` (DD8) |
| Identity store unreachable | Phase `not_collected` (E-47a fail-closed) |
| Concurrent assessments, one project | E-47a: `row_version` conflict; loser reloads and re-matches |
| Blueprint file missing or unparseable | Comparison `not_collected` naming the file; the rest of the map ships |

## Testing

**Unit, per pure module** — `tiers.py` (totality over `MemberKind`; the
`CONTRACT_KINDS` difference is exactly `{DB_TABLE, ENTITY_NAME}`), `context.py`
(cohesion/coupling arithmetic, the guardrail rule), `apply.py` (each action,
each malformed-disposition path), `blueprint.py` (PRESENT/MISSING/EXTRA,
unparseable file).

**NFR-10 determinism** — `tiers.py`, `context.py`, `apply.py` and `blueprint.py`
each carry a byte-identical-across-input-order assertion in their own test file,
following E-47b/c.

**The seam test carries the most weight.** E-47c's pre-merge review found a
fabricated non-route `object` that every unit test missed, and the fix commit
names the cause: *"unit tests built inputs `decompose()` would never produce."*
So the seam is tested with real producer output end to end — `ScanResult` →
`discover_context` → proposal → `apply()` → lock → `attribute()`/`decompose()`/
`assign()` — with no hand-built intermediate structs.

**Grounding** — a fabricated path drops its disposition to `FLAG`; a quote that
does not byte-verify does the same; a fabrication rate past 0.10 takes the phase
to `not_collected`.

**Memo** — an unchanged tree hits; an identity write invalidates; a prompt edit
invalidates; a `not_collected` map is never stored.

**Temporal e2e** — the integration test E-47b deferred to this item ("E-48 brings
the first integration test when it wires discover"). It extends the existing
`AssessmentWorkflow` e2e with a `TestModel` proposer, proving DISCOVER goes
measured and `terminal_status` flips to `assessed:partial`. It adds no new
workflow fan-out, which matters on a host that already struggles with the
`TidyUpWorkflow` case (P5's deferred e2e).

## Scope

### Not covered

- **Risk.** No STRIDE, no composites, no `UnifiedRiskMap` — E-49.
- **Gates.** No `CheckResult` and no gate opens in discover — E-50, E-51.
- **The other six blueprints.** DD11 ships one; curating BIAN, TM Forum, ACORD,
  HL7, ARTS is data work with its own item.
- **`OwnershipVerb.TRACKS`.** DD12 — no producer in this design has standing.
- **Intake classification and brownfield delta.** FR-102's remaining half; E-48
  completes the `CodebaseMap` inputs only.
- **SC-8.** Needs a corpus of readiness-passing repos, unchanged by this item.
- **`/enrich` as a declared stage input.** E-56.

## ADR-22 — assessment proposers dispose, they do not author

**Context.** The assessment tier's purpose is to make BrownKit's prose
judgments enforceable: gates graded by the model that produced the artifacts
become `CheckResult`s computed from typed artifacts. Its phases nonetheless
need genuine judgment — which candidates are capabilities, which risks are
real, which findings matter.

**Decision.** An assessment proposer receives a deterministically computed
packet and returns a **disposition over items code already produced**. It never
authors the artifact, mints an identifier, or names a file, id, or metric that
was not in its input. Every reference it emits is resolved against the pinned
commit before anything is applied, and an unresolvable reference drops the item
rather than failing the phase — bounded by a rate guard above which the phase
reports `not_collected`.

**Consequences.** The artifact stays deterministic given the same inputs, which
is what keeps E-47a's surrogate ids stable across assessments. E-51's absolute
cross-reference-integrity check becomes satisfiable by construction. Recall is
bounded by what the deterministic signals see, and is recovered through
blueprint comparison (clause D8) rather than by loosening the proposer. E-49's
risk proposers and E-52's report generators inherit this constraint.

**Alternatives rejected.** A model authoring the capability map directly: better
recall, but the map churns across runs on an unchanged tree and destabilises the
ids clients cite. A second adversarial recall lens: real coverage gain, but a
second model call per assessment before any calibration data exists to price it,
and blueprint comparison already covers the gap.

## Roadmap deltas

| Item | Change |
|---|---|
| E-48 | `[ ]` → `[x]` on landing |
| FR-913 | ⚠️ → `[x]` — the wiring all four landed mechanisms waited for |
| FR-911 | Stub count 5 → 4; `PHASE_OWNER` loses its `DISCOVER` entry |
| FR-914 | → `[x]` — its awaited LLM-proposing assessment consumer |
| FR-103 | E-47a's pending `identity_registry_version` amendment lands; the ⚠️ resolves |
| FR-102 | `CodebaseMap` inputs complete and wired; still needs intake classify + brownfield delta |
| SC-7 | Second clause ("zero fabricated path/line refs") computed every run, not sampled |
| SC-8 | Unchanged — still a corpus problem |
| NFR-9 | E-48 adds no execution of repository code: blob reads at the pinned commit plus a model call |
| NFR-10 | Four more pure modules under the order-independence assertion |
| §1 stage 2 (context) | Discover live; FR-102's remainder is classify + delta |
| §6 ADRs | **ADR-22** added |
| P6 | Second of seven phase bodies ships |
