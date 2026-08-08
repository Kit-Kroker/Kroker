# Capability identity — resolving OQ-6

**Date:** 2026-08-08
**Status:** approved design, ready for planning
**Closes:** OQ-6
**Amends:** FR-913 (wording), FR-103 (memo key)
**Scope:** E-47a of a proposed three-way E-47 split

## Problem

FR-913 (ROADMAP:213) asks for a `CapabilityMap` with "content-derived stable
ids". E-47 (ROADMAP:868) repeats the phrase and records why it has never been
built:

> **Blocked on OQ-6** — a content key over file paths breaks when files move, one
> over entity names breaks on rename, and until that is settled "stable
> identifiers" is aspiration and every cross-reference in the bundle is fragile.

The blockage is real and the framing is the cause. *Content-derived* and
*stable* are in tension: every derivation runs over facts a refactor is free to
change. Both horns named in OQ-6 are correct, and there is no third derivation
that escapes them, because the property being sought — survival across arbitrary
edits — is not a property any function of the current tree can have.

This matters beyond the audit product. E-47 "is where the assessment product and
the core pipeline converge" (ROADMAP:872): it satisfies FR-102's `CodebaseMap`,
so it gates P2 brownfield as well as P6 audit. §15 ranks it third overall and
says "**Settle OQ-6 first** — it is genuinely blocking, not a detail."

### What identity is for

Four consumers, confirmed during design. All four are in scope, so the design
targets the strictest.

| Consumer | Requirement |
|---|---|
| Audit bundle internal cross-references | Ids consistent within one assessment |
| Re-assessment delta | Identity survives refactoring between engagements |
| Continuous brownfield runs | Identity survives ordinary daily development |
| Client-facing durable references | An id in a delivered document never silently means something else |

The fourth sets the bar. An id that appears in a remediation plan a client keeps
is a correctness obligation, not a convenience.

## Decision

**`BC-NNN` is a surrogate key.** It is allocated once at first discovery,
persisted, and re-attached on later scans by *similarity matching* against
stored fingerprints. It is never derived from the tree.

This is `git`'s rename detection — a similarity index rather than identity,
which is why `git log --follow` survives a move-plus-rename that no content hash
survives.

**FR-913's wording is amended:** strike "content-derived stable ids", read
"stable ids". The adjective is what kept OQ-6 open.

### Precedent in this codebase

E-78 met the same problem shape and resolved it the same way. Board tasks key
off `(project, plan_version, task_id)` because "`DevTask.id` is planner-assigned
per run — `T01` in plan v2 need not be `T01` in v1" (FR-1301). The response
was to scope and persist, not to seek a derivation that would make `T01` stable.

### Invariants

1. **Ids are never reused.** A retired `BC-007` is never handed to a different
   capability. A delivered document citing it resolves to what it meant, or to a
   tombstone — never to something else.
2. **Ids are never deleted, only retired.** Deletion dangles delivered
   references; retirement resolves them with a status. Growth is unbounded and
   accepted: one small row per capability per project.
3. **Identity is a recorded fact with evidence.** Every attachment stores which
   signals matched at what score. An audit bundle whose cross-references cannot
   be justified reproduces the BrownKit failure this tier exists to fix —
   "`*Source: ...*` cross-references are audited by an LLM asked to check its own
   citations" (ROADMAP:847).

## Data model

Four entities. Only the first is long-lived.

**`CapabilityIdentity`** — the registry row:

| Field | Meaning |
|---|---|
| `bc_id` | `BC-003` |
| `project` | Scope; see below |
| `first_seen_run` | Provenance |
| `status` | `active \| retired \| merged` |
| `retired_reason` | `not_observed \| absorbed`; required when `status = retired` |
| `merged_into` | `bc_id \| None`; set when `status = merged` |
| `derived_from` | `bc_id \| None`; set when this id was minted by a split |
| `fingerprint` | Last-known observed fingerprint |

Storing the fingerprint is load-bearing: matching assessment *N* requires what
assessment *N−1* observed. Retired rows keep theirs or they can never be
revived.

**`CapabilityFingerprint`** — what one assessment observed for one capability.
Computed from E-46 scan output; pure.

**`IdentityAttachment`** — the per-assessment join: `bc_id`, `fingerprint`,
`match_score`, `method ∈ {first_discovery, matched, forced_by_correction}`, and
the per-signal contributions. This is the evidence trail invariant 3 requires;
it falls out of the scoring function rather than being assembled separately.

**`IdentityCorrection`** — an audited human reversal, modelled field-for-field on
`gate.py`'s `GateOverride`: `approved_by`, `reason`, operation.

**Scope is per-project.** One capability appearing in two repos of one client
gets two ids.

### Consequence: E-47 becomes stateful across runs

E-46 is a pure function of the tree. E-47a is a function of the tree *and* the
identity registry. This is inherent to the requirement, not a design choice, and
it drives the memo-key amendment below.

## The matcher

Pure: fingerprints in, attachments out. No I/O, no `temporalio` — the tier
`triage/signals/*` and `gate.py` occupy.

### Signal tiers

Ordered by cost-to-change. That ordering *is* the weighting rationale: a signal
that can be changed carelessly is weak evidence of identity.

| Tier | Signals | Rationale |
|---|---|---|
| Contract | HTTP route path+method, CLI command names, DB table/collection names, queue topics, exported public API signatures | Changing these breaks somebody else's code |
| Behavioral | Referencing test *names* (not paths), owned entity names | Tests track behavior, not structure |
| Structural | Exported symbol names | Survives file moves, dies on rename |
| Locational | File paths, directory membership | Cheapest thing in a repo to change |

Weights are configuration with shipped defaults, not constants. They are a
calibration target — see *Calibration* below.

### Scoring

Per-signal **Jaccard**, then a weighted sum. Jaccard is symmetric, bounded in
[0,1], and degrades gracefully under additions and removals. Each term is
independently reportable, which is what makes the evidence trail free.

**Weights renormalize over tiers present on both sides.** An internal library has
no routes and no tables. Counting an absent Contract tier as zero would bias
systematically against exactly those capabilities whose other signals are also
weakest, so absent tiers are excluded from the denominator rather than scored 0.

### Assignment: greedy, not optimal

Matching is bipartite and must be one-to-one. The naive per-capability
`argmax` is wrong: two new capabilities can both best-match `BC-003` and both
claim it, breaking invariant 1 inside a single map.

**Algorithm:** score all pairs; sort by `(score desc, bc_id asc)`; walk the list
and attach the first time a pair is reached with neither side claimed, consuming
both.

**The Hungarian algorithm is rejected.** Global optimality means an unrelated
third capability's score can move a pair that matched perfectly well onto a
different id. For a client-facing identifier that is indefensible — there is no
way to explain why `BC-003` moved because of a change elsewhere. Greedy is
locally stable: a strong pair matches regardless of what else is in the set, and
the rule states in one sentence. Capability counts are in the tens; O(n²)
scoring is not a constraint.

Tie-breaking on `bc_id` (a total order) makes the procedure deterministic, which
NFR-10 requires and which a client re-running an assessment notices immediately
if it is wrong.

### Thresholds

| Condition | Outcome |
|---|---|
| `score ≥ T_match` | Attach existing id |
| `score < T_match` | Mint new id + `possible_rename` advisory naming the near-miss and its score |
| Runner-up within `ε` of winner | Decide anyway, deterministically; emit `ambiguous_match` |

The `ε` band is the human-override hook. Nothing blocks; nothing gates.

### Split, merge, retire, revive

- **Split (detected)** — `BC-003` best-matches two new capabilities. The higher
  scorer claims it; the other mints a new id carrying `derived_from: BC-003` and
  a `split` advisory. Never silent. Distinct from the `split` *correction*
  below: this is the matcher observing a divergence, not a human forcing one.
- **Merge** — two stored ids match one new capability. The winning pair takes
  the id; the loser becomes `merged_into`.
- **Retire** — an unmatched stored capability is *not* assumed gone; it may have
  fallen below threshold after a heavy refactor. It becomes
  `retired(reason=not_observed)`.
- **Revive** — a later scan that matches a retired capability re-attaches it.

Revival is not a violation of invariant 1. Reuse means handing `BC-007` to a
*different* capability; revival re-attaches it to the same one. The two are
indistinguishable in a schema diff and must be distinguished in review.

### Measurement discipline

A fingerprint that could not be computed — parse failure, unsupported language,
unreadable file — **must not score 0**. Zero asserts "definitely not the same".
An uncomputable fingerprint is `Measurement.not_collected`; its capability skips
matching and receives a new id plus an advisory recording that identity was not
assessed.

This is FR-915's hole in a new location. There, a scan that never ran read as a
clean absolute floor; here, a fingerprint that never computed would read as a
confident non-match. `measurement.py` exists to forbid the conflation.

## Storage

### One store, plus an export

`CapabilityIdentityStore` is an ABC per ADR-19 (adapters, not substrate):

```
load(project)           -> registry rows incl. fingerprints
apply(project, changes) -> new registry_version
```

**`BoardIdentityStore` is authoritative.** Tables in `runs/board.sqlite3` beside
artifact lineage, reusing E-78's `row_version` optimistic concurrency rather
than introducing a second scheme into the same file.

**The repo-side artifact is an export, not a store.** `.sdlc/capabilities.json`
carries `bc_id → human-readable name → fingerprint hash`, sorted by `bc_id` with
deterministic key order. Opt-in, off by default.

**Why an export and not a second store:** a hash cannot drive matching. Jaccard
needs the sets; a digest yields equality and nothing else. A file-driven store
would mint a new id on any refactor at all — precisely the failure OQ-6 names.
Per-tier hashes do not rescue it: set-hash equality is brittle in the wrong
direction, since one added route flips an entire tier.

The export has three jobs, all real:

1. **Durable client-facing resolution** — a delivered `BC-007` resolves without
   access to our infrastructure.
2. **Tamper-evidence** — the hash lets a client verify across engagements that
   the stored fingerprint is the one present at delivery, i.e. that no silent
   re-keying occurred.
3. **Cheap change detection** — a differing hash means the capability's shape
   moved. A signal, not an identity.

Default is board-only. Writing into a client repository is a trust-boundary
decision, matching the discipline of `MemoryConfig.backend` defaulting to `fake`
and `triage/advisories.py` collecting nothing by default. The opt-in is explicit
configuration, not an inference from the fact that the write happens to land
inside the worktree and therefore does not trip `no-out-of-worktree-write`.

**Accepted risk:** the board is a single point of failure for identity
continuity — the export cannot rebuild matching state. Accepted on the grounds
that the board already holds artifact lineage and task history of comparable
value, so this joins an existing backup obligation rather than creating a new
class of risk.

### Memo key amendment (FR-103)

E-46's `(tree_hash, signal_version)` becomes
`(tree_hash, signal_version, identity_registry_version)`, where
`registry_version` is a per-project integer bumped on any write — allocation,
retirement, or correction.

Deliberately coarse: any identity change invalidates the whole map for that
project. The `CapabilityMap` is a single artifact with no per-capability
memoization to preserve, so a finer key buys nothing and adds staleness risk.

FR-103 is checked `[x]` (ROADMAP:139). This is an **amendment to a completed
contract**: re-assessing an unchanged tree is no longer unconditionally a cache
hit. Recorded here rather than discovered during implementation.

## Corrections

Three operations. Each is a human forcing an outcome the matcher did not reach
on its own; `split` here is distinct from the matcher's *detected* split above.

| Operation | Meaning |
|---|---|
| `merge` | Two ids are one capability |
| `split` | One id should have been two; the human supplies the member partition |
| `reattach` | A newly minted id is really an existing capability, refactored |

`split` takes a richer input than the other two — the caller must say which
members go with which id, since no scored evidence exists for a partition the
matcher did not make.

Application follows E-78's established pattern — mutate the registry row, append
one `event` row with actor and authority (FR-1302). A purely event-sourced fold
would be more elegant; a second persistence model inside one SQLite file would
be worse than a slightly less pure one.

Corrections are never deleted. Undoing one is another correction. Each bumps
`registry_version`.

### Corrections must overwrite the stored fingerprint

The failure this prevents is subtle and expensive to find late.

`reattach` says `BC-012` is really `BC-003` after a heavy refactor. Retiring
`BC-012` and pointing it at `BC-003` is not sufficient: `BC-003` still holds its
*pre-refactor* fingerprint, so the next assessment scores the refactored
capability against stale data, misses threshold again, and mints another new id.
The human then corrects the same thing every run.

Therefore `reattach` sets `BC-003.fingerprint = BC-012.observed_fingerprint`, and
the surviving side of a `merge` does the same. **A correction teaches the
registry what the capability looks like now**, or it does not stick.

### Entry point, and the OQ-11 dependency

A correction rewrites identity that delivered documents cite — the
highest-trust write in this design.

The board HTTP API is **not** an acceptable home today. `X-Actor` is
self-asserted (OQ-11, ROADMAP:1119; README: "bind to localhost — there is no
auth yet"). An unauthenticated header cannot provide provenance for
`approved_by` on an audited override.

Corrections therefore land through the CLI, beside the existing
human-decision vocabulary (`cli approve --gate architecture`):

```
python -m sdlc.cli capability merge --project X --from BC-007 --into BC-003 --reason "..."
```

Authority is always `AUTHORITATIVE`; an agent may never issue one. Exposing
corrections over HTTP becomes reasonable once OQ-11 closes — an explicit
dependency, recorded because the API is otherwise the obvious place to add it.

Idempotency is by target-state check, not dedupe key: if `BC-007.merged_into` is
already `BC-003`, record a no-op event and return. Humans retry CLI invocations
in ways Temporal activities do not.

### Calibration

Every correction is labelled ground truth: *the matcher scored this pair at 0.61
and a human says it should have matched.* This is the input shape
`benchmarks/calibration.py` already consumes — hand-scored samples versus
computed scores, reported as agreement, advisory only.

`gate.py` already states the principle for `GateOverride.approved_by`: "human
identity (retained as calibration signal)". Identity corrections apply it to a
different judgment, and give the tier weights an empirical path: ship defaults,
let the corpus correct them.

## Pipeline integration

Identity resolution consumes proposed capability boundaries, so it cannot
precede the proposer that produces them. Ordering within E-45's DAG:

```
scan (E-46 signals) → discover (E-48 proposes boundaries) → fingerprint + resolve → assess
```

This lands exactly on E-48's **D4 "lock"** step (ROADMAP:879). Locking the
capability set and assigning identity to it are the same moment; the port
already has the hook.

**E-47a does not block on E-48.** The matcher is pure, so it builds and tests
against synthetic fingerprints with no proposer and no model call. Only the
wiring waits.

Store reads and writes happen in activities. The matcher never touches I/O.

## Failure modes

| Condition | Behavior |
|---|---|
| Store unreachable | **Fail closed.** |
| Fingerprint uncomputable | `not_collected` → new id + advisory. Never score 0. |
| Empty registry (first assessment) | Not an error. All attachments `first_discovery`, no score, no advisory. |
| Concurrent assessments, one project | `row_version` conflict; loser reloads and **re-matches** (not replays — the registry moved). |
| Export file missing or corrupt | No failure mode; it has no read path. |

Failing closed on an unreachable store is deliberate. The alternative — proceed
and mint fresh ids — produces a complete, plausible-looking map in which every
id is wrong, and the next successful write commits that corruption. This matches
how `loader.py` treats a missing registry or an absent `EXA_API_KEY`.

The empty-registry row also settles a question raised in design: the `ε`
ambiguity band does not apply on a first assessment, so a new engagement does not
emit an advisory per capability.

## Testing

**1. Pure matcher tables** — the `triage/signals/` pattern. Exact match; files
moved; symbols renamed; split; merge; tie-break determinism; renormalization
with a tier absent on both sides; `not_collected` propagation.

**2. Mechanical refactor corpus** — the primary investment. Take a repository,
apply *known* refactors programmatically (move files, rename symbols, extract a
module, rename a route, add an endpoint), assert identity survives each with a
labelled expected outcome.

This generates ground truth instead of hand-labelling it, which matters because
SC-8's corpus does not exist and will not until real audits have run. It permits
calibrating `T_match` and the tier weights before the first client repository,
and it directly falsifies the Contract-tier weighting claim: if renaming every
symbol preserves identity but changing one route breaks it, the weighting is
behaving as designed.

**3. Properties** — same tree twice yields identical ids and zero allocations
(NFR-10, asserted byte-for-byte); ids never reused across arbitrary correction
sequences; `registry_version` monotonic.

## Scope

This spec is **E-47a**. E-47 as written carries four clauses; a single plan
should not carry all of them:

| E-47 clause | Item |
|---|---|
| L1 with stable `BC-NNN` | **E-47a — this spec** |
| file→capability coverage floor (0.90) + orphans `attached \| infrastructure \| dead` | E-47b |
| L2 operations | E-47c |
| Entity ownership (exactly one owner or surfaced conflict) | E-47c |

E-47a comes first: the other two need something to attach findings to.

### Not covered

FR-102 (`CodebaseMap` + brownfield classify + delta) needs all of E-47. SC-8
needs E-47 complete plus a corpus. P2 brownfield and P6 audit sit behind FR-102.

### Related, deliberately untouched

E-5 — "Factory takes its own `agents/` folders as brownfield input to itself
(ADR-7's endpoint) … Needs E-1 and brownfield mode (FR-102) first" — is marked
*speculative, do not schedule* (ROADMAP:403). The E-47a → E-47b/c → FR-102 chain
is what would make it mechanically possible. The tag stands.

## Roadmap deltas

| Item | Change |
|---|---|
| OQ-6 | Closed |
| FR-913 | Strike "content-derived" from "content-derived stable ids" |
| E-47 | Split into E-47a / E-47b / E-47c; unblock |
| FR-103 | Amend memo key with `identity_registry_version` |
| §15 item 3 | "Settle OQ-6 first" satisfied |
