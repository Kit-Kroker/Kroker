# L2 operations and entity ownership

**Date:** 2026-08-14
**Status:** approved design, ready for planning
**Scope:** E-47c, the last of the three-way E-47 split
**Satisfies:** FR-913 (third and fourth clauses); completes FR-102's `CapabilityMap` inputs; contributes to SC-8
**Depends on:** E-47a (identity), E-47b (attribution), E-46 (scan: S2, S3)
**Does not cover:** E-48 (the discover proposers that call this)

## Problem

FR-913 asks for a `CapabilityMap`. E-47a gave it stable `BC-NNN` identity;
E-47b gave it a coverage floor and classified orphans. What remains is the two
clauses the split deferred: **L2 decomposition** — what each capability
actually *does* — and **entity ownership**, stated in the roadmap as "exactly
one owner or a surfaced conflict."

Today the map can say *a payments capability exists, here are its files, and
the tree is 94% explained*. It cannot say *payments exposes four operations,
owns the `payments` table, and reads `customers` — which `accounts` owns.*
That second sentence is the one every downstream item needs. E-49 asks which
capability handles regulated data; E-53 seeds fix runs scoped to a capability;
FR-102's brownfield delta needs to know which capability a changed table
belongs to. All three are questions about operations and ownership, and none of
them can be asked of a map that only has files.

Three properties make this harder than a grouping:

1. **Ownership is a claim about a contest.** Any real repository has entities
   several capabilities touch. A rule that names an owner whenever *someone*
   touches an entity will name an owner for nearly every entity, and be wrong
   often enough that the map cannot be cited.
2. **Direction is not uniformly available.** An HTTP route carries its method,
   so `POST /payments` proves a write. A CLI command `sync-payments` proves
   contact and nothing about direction. A design that treats those alike either
   invents writes or discards evidence.
3. **The two upstreams degrade independently.** S2 (schema) can report
   `not_collected` while S3 (entry points) succeeds, and vice versa. Each
   degradation produces an answer of the *identical shape* to a healthy one —
   which is precisely the conflation FR-915 exists to forbid.

## Decision

Eleven decisions, numbered for the plan and for later citation.

### D1 — a pure module, unwired

E-47c ships as pure functions over explicit inputs, tested against synthetic
inputs, exactly as E-47a's matcher and E-47b's `attribute()` were. No phase
body is wired.

The reasoning is E-47b's D1, unchanged and now stronger. The phase that would
host this is `discover`, whose body is E-48's; E-48's clause D5 is literally
"L2 decomposition with entity ownership". Computing operations against scan
*candidates* — boundaries `discover` has not yet confirmed, split, de-scoped or
flagged — would attribute operations to capabilities that E-48 may dissolve.

`_discover` therefore keeps returning `unbuilt(PhaseId.DISCOVER)` and the
DISCOVER phase row stays honestly `not_collected` naming E-48. E-45's derived
`terminal_status` needs no edit, as designed (D6 there).

The division of labour this fixes is worth stating once: **E-47c computes what
the bytes prove; E-48 decides what it means.** Every rule below is deterministic
and cites evidence. Every judgment call — merging two operations, overriding a
conflict, assigning the `TRACKS` relationship — belongs to the proposer.

### D2 — placement: `src/sdlc/assessment/discover/`, and no reach into a signal

Two new pure modules beside `attribution.py`, with contracts in the package's
one `models.py`:

- `discover/operations.py` — `decompose()`
- `discover/ownership.py` — `assign()`

`assign()` needs the entities S2 declares. It does **not** import
`scan/signals/schema.py` to get them. E-47b's precedent is that `discover/`
imports scan *rule modules* (`configpaths`, `sources`, `testpaths`) and never a
signal: a signal is a producer with a memo key and a version, and depending on
one from here would make `discover/` part of that signal's hashed surface.

So `discover/models.py` declares a three-field `EntityDeclaration`
(`name`, `path`, `line`) and `assign()` takes a sequence of them. E-48 adapts
S2's `TableDecl` at the call site — one obvious mapping, in the module that
already depends on both. Keeps every input a parameter (D1's testability), and
keeps the dependency direction one-way.

### D3 — one operation per contract member

Each contract-tier member yields exactly one `L2Operation`. `POST /api/payments`
and `GET /api/payments/{id}` are two operations, not one "payments" operation
with two bindings.

The alternative — clustering members by normalized object — produces a coarser
list that reads more like a hand-written L2 decomposition, and that is exactly
why it was rejected. Clustering is a judgment call. Made here it is invisible:
a wrong merge leaves no trace downstream, because the merged operation looks
identical to a genuine one. Made in E-48 it is a `MERGE` disposition with a
rationale, which is the form the methodology already has for it.

The consequence to accept: an operation resolves 1:1 to a byte range at the
pinned commit. SC-7's "zero fabricated path/line refs" holds trivially for this
artifact, because no operation exists that was not read from a file.

### D4 — `CONTRACT_KINDS`, and what yields nothing

An operation is something the system *does*, reachable from outside the
capability. Six of the twelve `MemberKind`s qualify:

| Yields an operation | Yields none |
|---|---|
| `HTTP_ROUTE`, `CLI_COMMAND`, `GRPC_METHOD` | `ENTITY_NAME`, `DB_TABLE` — data, not behaviour |
| `SCHEDULED_JOB`, `QUEUE_TOPIC`, `FRONTEND_ROUTE` | `TEST_NAME` — describes behaviour, is not behaviour |
| | `EXPORTED_SYMBOL`, `PACKAGE_PATH`, `FILE_PATH` — structure |

`CONTRACT_KINDS` is a frozenset in `discover/models.py`. It is deliberately not
derived from `SignalTier.CONTRACT`: that mapping is E-48's (`MemberKind` →
`SignalTier`, noted as D13 in scan's `MemberKind` docstring as belonging to the
proposer), and two independent uses of the word "contract" that agree only by
coincidence is the failure mode `PipelineConfig.roles` mirroring exists to
prevent. A comment on each set names the other.

### D5 — `op_id` is positional and assessment-local

`op_id` is `f"{bc_id}-OP-{n:02d}"`, assigned in canonical sort order over
`(kind, binding, path, line)`.

This follows `ScanCandidate.candidate_id`'s "C-01" precedent, not `BC-NNN`'s.
An `op_id` is stable *within* one assessment and may move between them. Minting
an id a client can cite across assessments is identity work — it needs a
registry, a fingerprint, and a re-attachment rule, which is the entire content
of E-47a. Producing a second, weaker durable id here would give clients
something that looks citable and is not.

If operations later need durable identity, the mechanism exists and E-47a's
matcher is the thing to extend. That is not this item.

### D6 — two verb taxonomies, deliberately not one

`OperationVerb` describes what an operation does. `OwnershipVerb` describes a
capability's relationship to an entity. They are separate enums and must stay
separate — collapsing them reads plausibly right up to the point where an
operation's `CREATE` is mistaken for an ownership `CREATES`, which is a claim
about a different subject.

`OperationVerb`, derived from the member:

| Member | Verb | Direction |
|---|---|---|
| `HTTP_ROUTE` `POST` | `CREATE` | write |
| `HTTP_ROUTE` `PUT`/`PATCH` | `UPDATE` | write |
| `HTTP_ROUTE` `DELETE` | `DELETE` | write |
| `HTTP_ROUTE` `GET`/`HEAD` | `READ` | read |
| `CLI_COMMAND`, `GRPC_METHOD` | `INVOKE` | unknown |
| `SCHEDULED_JOB` | `SCHEDULE` | unknown |
| `QUEUE_TOPIC` | `CONSUME` | unknown |
| `FRONTEND_ROUTE` | `RENDER` | unknown |

Method extraction is total and safe: every `HTTP_ROUTE` member value is
`"<METHOD> <path>"`, because `entrypoints.py` forces `GET` even for Flask's
bare `@route` specifically to keep every HTTP member one shape. An
unrecognized method maps to `INVOKE` with the rule recorded, never dropped.

`OwnershipVerb` is `OWNS | CREATES | MANAGES | READS`.

**`TRACKS` is not emitted.** The roadmap's E-48 D5 lists five relationships;
four have a deterministic trigger and `TRACKS` has none — it means something
closer to *holds a reference for lifecycle purposes*, which no static signal
here distinguishes from `READS`. Emitting it would put a judgment call behind a
code-computed label, which is the exact defect this port exists to remove from
BrownKit's prose gates. `TRACKS` stays in the enum's docstring as reserved for
E-48's proposer, and `assign()` never returns it.

### D7 — ownership precedence: declaration, then writes, then reads

Six branches, first match wins, each recorded in the row's `rule` field:

| # | Rule | Outcome | Verb |
|---|---|---|---|
| 1 | `declared_in_sole_member` — the declaration's `path` is a member path of exactly one capability | `OWNED` | `OWNS` |
| 2 | `sole_writer` — exactly one capability has a write operation whose `object` reduces to this entity's key | `OWNED` | `CREATES` if every matching write is `CREATE`, else `MANAGES` |
| 3 | `sole_reader` — no writers, exactly one reader | `OWNED` | `READS` |
| 4 | `tied_writers` / `tied_readers` / `declared_in_shared_file` | `CONFLICT` | — |
| 5 | `undirected_only` — claimants exist, none directed | `UNDIRECTED` | — |
| — | no claimant at all | `UNCLAIMED` | — |

Declaration outranks access because it is the strongest evidence available and
the cheapest to explain: the capability whose files declare the table is the one
a customer would name. Access outranks nothing else because it is a
name-normalization match, not a data-flow trace.

**Object matching** is `normalize(head_token(x))` on both sides — the same
reduction S2's `_cluster_key` applies, so `order_items` and `orders` both reach
`order`. Both helpers are already public in `scan/naming.py`; nothing is
promoted for this.

**The known cost, accepted and pinned as a test (see Testing 6):** a shared
`models/` package puts every declaration in files belonging to one capability —
or to none. When it belongs to one, rule 1 hands that capability every entity in
the repository. This is not a bug to be worked around here; it is what the
evidence says, and E-48's proposer is the layer with the standing to override
it. E-47b pinned its dynamic-reference false positive the same way rather than
hiding it behind a caveat.

### D8 — `CONFLICT`, `UNDIRECTED` and `UNCLAIMED` are three outcomes, not one

Collapsing them would be the same defect as `coverage_pct: float | None`:

- `CONFLICT` — several capabilities contest this entity. **Actionable by E-48**;
  the proposer picks, with the claimants and their evidence in front of it.
- `UNDIRECTED` — something touches this entity, but only through operations
  whose direction we cannot read (a CLI-driven or queue-driven repository).
  **Not actionable by picking**; it is a limit of the signal, and reporting it
  as `UNCLAIMED` would tell a customer nothing touches a table their CLI writes
  to every night.
- `UNCLAIMED` — nothing in the identified capability set touches this entity at
  all. **This is a finding in its own right** — an orphaned table is E-47b's
  `dead` file with the stakes turned down, and E-49 will want it.

`owner` and `verb` are non-`None` **iff** the outcome is `OWNED`, enforced by a
validator. A row that names an owner and calls itself a conflict is
unrepresentable.

### D9 — fail closed on either upstream

`decompose()` takes `contract_collected: Measurement`; `assign()` takes both
that and `schema_collected`. If either is not `MEASURED`, the corresponding
report is `not_collected` naming the degraded signal and carries **no rows**.

The validator is `_unmeasured_carries_no_payload`, reusing the name scan plan 1
gave it, because it is the same invariant.

Fail-closed on S2 in particular deserves its reason. Without declarations,
rule 1 never fires and every entity falls to the access fallback — a
systematically weaker answer *in the identical shape*. The report would still
name owners; they would just be derived by a different rule than the one the
design claims. A caller cannot tell those apart, so the report must not be
produced. This is S3's own P2-D1 fail-closed reasoning applied one layer up.

The distinction to keep: a capability with **zero** contract members under a
`MEASURED` upstream gets `operations=()`. That is a genuine measured zero — a
pure library capability with no external surface — and it is not a gap.

### D10 — the route-object helper becomes a shared rule module

Deriving an operation's object needs the route's last *specific* path segment:
`POST /api/payments/{id}` → `payments`, skipping prefixes (`api`, `v1`) and
parameters (`{id}`, `:id`). That logic exists today, private to
`entrypoints.py` as `_business_name`'s `HTTP_ROUTE` branch plus `_PATH_PREFIXES`.

A second consumer is exactly the trigger `sources.py` documents for promoting a
table, and FR-902's one-implementation-per-signal rule is the same rule read
from the other side. So it moves to `scan/naming.py` as
`route_object(value) -> str | None`, and `entrypoints.py` calls it.

**Consequence, stated rather than discovered later:** `naming.py` is a declared
`rule_module` for S3 and `rules_sha` hashes rule modules transitively. This
promotion **invalidates S3's memo**, so the first assessment after it lands
re-runs S3. That is the memo key working correctly — S3's inputs did change —
and it is the reason the move belongs in this item's plan rather than in a
drive-by edit.

### D11 — no `CheckResult` here

E-47b's D8, unchanged. Nothing in this item gates anything. An ownership
conflict is a finding, not a failure; a coverage of undirected entities is not
a threshold. E-50 owns assessment gate checks and E-51 owns acceptance criteria,
and both need artifacts to compute over — which is what this produces.

## Data model

All in `src/sdlc/assessment/discover/models.py`, beside E-47b's contracts.

```python
# D4. The other half of this pairing is E-48's MemberKind -> SignalTier map;
# neither may be derived from the other (two coincidental agreements).
CONTRACT_KINDS: frozenset[MemberKind] = frozenset({
    MemberKind.HTTP_ROUTE, MemberKind.CLI_COMMAND, MemberKind.GRPC_METHOD,
    MemberKind.SCHEDULED_JOB, MemberKind.QUEUE_TOPIC,
    MemberKind.FRONTEND_ROUTE,
})


class OperationVerb(str, Enum):
    """What an operation does. NOT OwnershipVerb (D6): that describes a
    capability's relationship to an entity, a different subject."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    INVOKE = "invoke"        # direction unknown
    SCHEDULE = "schedule"    # direction unknown
    CONSUME = "consume"      # direction unknown
    RENDER = "render"        # direction unknown


WRITE_VERBS: frozenset[OperationVerb]   # CREATE, UPDATE, DELETE
READ_VERBS: frozenset[OperationVerb]    # READ
DIRECTED_VERBS = WRITE_VERBS | READ_VERBS


class L2Operation(BaseModel):
    model_config = {"frozen": True}
    op_id: str                  # "BC-014-OP-03", assessment-local (D5)
    capability: str             # bc_id
    verb: OperationVerb
    name: str                   # "create_payment"
    object: str                 # "payment"; "" when underivable
    binding: str                # "POST /api/payments", verbatim
    kind: MemberKind
    evidence: EvidenceRef
    rule: str                   # the mapping rule that fired


class DecompositionReport(BaseModel):
    operations: tuple[L2Operation, ...] = ()
    by_capability: dict[str, int] = Field(default_factory=dict)
    collected: Measurement
    # _counts_are_derived: by_capability carries every bc_id passed in,
    #   including zeros -- an absent key and a zero are different claims.
    # _unmeasured_carries_no_payload: operations empty unless MEASURED (D9).


class OwnershipVerb(str, Enum):
    """TRACKS is deliberately absent (D6): no deterministic trigger exists,
    and it is reserved for E-48's proposer."""
    OWNS = "owns"
    CREATES = "creates"
    MANAGES = "manages"
    READS = "reads"


class OwnershipOutcome(str, Enum):
    OWNED = "owned"
    CONFLICT = "conflict"          # 2+ tied claimants (D8)
    UNDIRECTED = "undirected"      # claimants, none with readable direction
    UNCLAIMED = "unclaimed"        # nothing touches it


class EntityDeclaration(BaseModel):
    """D2: what assign() needs from S2, without importing a signal."""
    model_config = {"frozen": True}
    name: str
    path: str
    line: int


class EntityOwnership(BaseModel):
    model_config = {"frozen": True}
    entity: str
    outcome: OwnershipOutcome
    owner: str | None = None
    verb: OwnershipVerb | None = None
    rule: str
    claimants: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    # _owner_matches_outcome: owner and verb set IFF outcome is OWNED (D8).
    # _claimants_match_outcome: CONFLICT needs >=2, UNCLAIMED needs 0,
    #   OWNED/UNDIRECTED need >=1.
    # _claimants_are_sorted: sorted and deduped, asserted not repaired
    #   (E-47b's FileAttribution precedent -- discovery order is a bug).


class OwnershipReport(BaseModel):
    entities: tuple[EntityOwnership, ...] = ()
    counts: dict[OwnershipOutcome, int] = Field(default_factory=dict)
    collected: Measurement
    # _counts_agree_with_entities: every outcome present incl. zeros, and
    #   derived from entities -- AttributionReport's rule, verbatim.
    # _unmeasured_carries_no_payload (D9).
```

## The two functions

```python
def decompose(
    members: Mapping[str, Sequence[CandidateMember]],
    *,
    contract_collected: Measurement,
) -> DecompositionReport:
    """bc_id -> its members, in; one operation per contract member, out."""
```

1. `contract_collected` not `MEASURED` → empty report naming the signal (D9).
2. For each `bc_id` in sorted order, filter members to `CONTRACT_KINDS` and sort
   by `CandidateMember.sort_key` — `(kind, value, path, line)` — so the
   canonical order is the one scan already defines. `binding` is the member's
   `value`, carried verbatim; the sort key and `op_id` order are therefore the
   same ordering under two names, not two orderings.
3. Map each to a verb (D6) and derive `object`:
   - `HTTP_ROUTE` → `naming.route_object(value)`
   - every other kind → `normalize(head_token(value))` on the member's own value
     (a CLI command name, a topic, a job name)

   `route_object` returns `str | None`; `None` and a blank reduction both store
   `object=""`. Name the operation `f"{verb}_{object}"`, falling back to the
   bare verb when `object` is empty, then assign `op_id` positionally.

```python
def assign(
    declarations: Sequence[EntityDeclaration],
    member_paths: Mapping[str, Sequence[str]],
    operations: Sequence[L2Operation],
    *,
    schema_collected: Measurement,
    contract_collected: Measurement,
) -> OwnershipReport:
    """Declarations + capability member paths + operations, in; one
    ownership row per distinct entity, out."""
```

1. Either upstream not `MEASURED` → empty report naming it (D9).
2. Group declarations by `normalize(head_token(name))`; one row per distinct
   key, named by the lexicographically first raw name that reduced to it, so the
   name is reproducible and not discovery-order dependent.
3. Build `path -> {bc_id}` from `member_paths` (`attribute()`'s `member_of`
   inversion, same shape).
4. Apply D7's rules in order, collecting evidence: the declaration's
   `EvidenceRef` for rule 1, the matching operations' for rules 2–3, all
   claimants' for conflicts.

Both are pure: every input a parameter, no disk, no subprocess, no repository
code executed (NFR-9).

## Failure modes

| Mode | Handling |
|---|---|
| S2 `not_collected` | `OwnershipReport` not_collected naming S2; no rows (D9) |
| S3 `not_collected` | Both reports not_collected naming S3; no rows (D9) |
| Capability with no contract members, upstream healthy | `operations=()`, a measured zero — not a gap (D9) |
| Route with an unextractable object (`POST /`) | Operation still emitted, `object=""`, name is the bare verb; it participates in no ownership rule |
| Unrecognized HTTP method | `INVOKE`, direction unknown, rule recorded — never dropped |
| Entity declared twice in two capabilities' files | `CONFLICT` / `declared_in_shared_file` |
| Shared `models/` package | Rule 1 fires broadly; accepted and pinned (D7, Testing 6) |
| Entity touched only by CLI/queue operations | `UNDIRECTED`, never `UNCLAIMED` (D8) |

## Testing

Two new files, `tests/test_discover_operations.py` and
`tests/test_discover_ownership.py`, synthetic inputs throughout.

1. **Grain (D3).** Four routes on one capability yield four operations, each
   with its own `EvidenceRef`; no merging.
2. **Kind filtering (D4).** A capability whose members are all `TEST_NAME` /
   `EXPORTED_SYMBOL` / `FILE_PATH` yields zero operations under a `MEASURED`
   upstream — a measured zero, asserted as such, not as `not_collected`.
3. **Verb mapping (D6).** Table-driven over every row of D6's table, plus an
   unrecognized method reaching `INVOKE` rather than being dropped.
4. **Ownership precedence (D7).** One test per rule, plus a case where a
   declaration-site owner and a different sole writer both exist — asserting
   rule 1 wins, which is the precedence claim itself.
5. **The three non-owned outcomes (D8).** Tied writers → `CONFLICT`; CLI-only
   claimant → `UNDIRECTED`; untouched table → `UNCLAIMED`. Asserted as three
   distinct outcomes, since the whole decision is that they do not collapse.
6. **Pinned known limitation (D7).**
   `test_known_limitation_a_shared_models_package_grants_blanket_ownership` —
   asserts the current behaviour explicitly, so a future change to the rule
   moves a test rather than surprising a customer. E-47b's
   `test_known_false_positive_a_dynamic_reference_reads_as_dead` is the model.
7. **Degradation (D9).** Both upstreams, independently: not_collected in,
   not_collected out, zero rows, reason names the signal.
8. **Determinism (NFR-10).** Each module's own test file asserts byte-identical
   output across shuffled input order, following `refgraph.py` and
   `attribution.py` rather than relying on scan's
   `test_every_pure_signal_module_is_order_independent`.
9. **S3 unchanged by D10.** The existing `entrypoints.py` tests must pass
   untouched after `route_object` is promoted — the promotion is a move, and a
   behavioural change in S3 would be a defect, not a feature of this item.

## Scope

This spec is **E-47c**, completing the E-47 split:

| E-47 clause | Item |
|---|---|
| L1 with stable `BC-NNN` | E-47a — landed 2026-08-08 |
| file→capability coverage floor + orphan classification | E-47b — landed 2026-08-13 |
| L2 operations | **E-47c — this spec** |
| Entity ownership (exactly one owner or a surfaced conflict) | **E-47c — this spec** |

### Not covered

- **Wiring.** `_discover` stays `unbuilt`; E-48 calls `decompose()` and
  `assign()` (D1).
- **The proposer.** E-48's D5 judgment layer: `MERGE`/`SPLIT` of operations,
  conflict resolution, and the `TRACKS` relationship (D6).
- **Durable operation identity.** `op_id` is assessment-local by design (D5).
- **Gating.** No `CheckResult` (D11); E-50 and E-51 own that.
- **SC-8.** Needs E-47 complete *and* a corpus of readiness-passing repos.
- **Data-flow tracing.** Direction comes from HTTP methods, not from following
  a write into a repository layer. That is a per-language AST project, and D6
  reports `INVOKE`/unknown rather than guessing.

## Roadmap deltas

| Item | Change |
|---|---|
| E-47c | `[ ]` → `[x]` on landing; E-47 group complete |
| FR-913 | Third and fourth clauses satisfied; all four clauses now closed |
| FR-102 | `CapabilityMap` inputs complete — still needs classify + delta for the full requirement |
| §1 stage 2 (context) | Note L2 and ownership land; FR-102's remaining half is classify/delta, no longer E-47 |
| NFR-9 | Note E-47c adds no execution of repository code — parameters only, as E-47b |
| NFR-10 | Two more pure modules under the order-independence assertion |
| E-46 / S3 | `route_object` promoted to `scan/naming.py`; S3's memo invalidated once by the move (D10) |
| SC-8 | Blocker narrows from "needs E-47a + E-47b" to "needs a corpus" |
