# Capability coverage floor and orphan classification

**Date:** 2026-08-13
**Status:** approved design, ready for planning
**Scope:** E-47b of the three-way E-47 split
**Satisfies:** FR-913 (second clause); contributes to FR-102, SC-8
**Depends on:** E-47a (identity), E-46 (scan)
**Does not cover:** E-47c (L2 operations, entity ownership)

## Problem

FR-913 asks for a `CapabilityMap` carrying a "file→capability coverage floor
(default 0.90)" with orphans classified `attached | infrastructure | dead`.
E-47a split that clause out as E-47b and recorded why it comes second: "an
orphan is defined against an identified capability set."

The identified set now has a mechanism. E-47a's matcher allocates `BC-NNN`
surrogate ids and re-attaches them across assessments; E-46's scan produces
`ScanCandidate`s whose `members` carry paths. What does not exist is anything
that answers the question a customer actually asks first — *is this model of my
repository complete?* A capability map covering 40% of a tree and a capability
map covering 95% of it are the same artifact today, and the difference is the
whole basis on which the audit's later claims can be trusted.

Three properties make this harder than a division:

1. **The denominator is a policy choice**, and the wrong one makes the floor
   trivially passable. Every file excluded from the denominator is a file the
   floor stops asking about.
2. **`dead` is the highest-stakes claim in the assessment.** A customer acts on
   it by deleting code. It is the one orphan verdict where being wrong is
   destructive rather than merely unhelpful.
3. **The evidence for `dead` is a negative** — the absence of an inbound
   reference — and a negative computed by an incomplete extractor is
   indistinguishable from a negative computed by a complete one, unless the
   design makes it distinguishable.

## Decision

Ten decisions, numbered for the plan and for later citation.

### D1 — a pure module, unwired

E-47b ships as pure functions over explicit inputs, tested against synthetic
inventories exactly as E-47a's matcher was. No phase body is wired.

The phase that would host it is `discover`, whose body is E-48's; E-48's clause
D3 is "coverage verification with orphan disposition". Wiring E-47b into a
phase now would mean either building part of E-48 or computing coverage against
scan *candidates* — boundaries `discover` has not yet confirmed, split,
de-scoped or flagged. The orphan set would then move under the customer when
discover ran, which is the opposite of what a coverage number is for.

`_discover` therefore keeps returning `unbuilt(PhaseId.DISCOVER)` and the
DISCOVER phase row stays honestly `not_collected` naming E-48. E-45's derived
`terminal_status` needs no edit, as designed (D6 there).

### D2 — placement: `src/sdlc/assessment/discover/`

Not `src/sdlc/capability/`. E-47b needs three path-rule tables that live under
`assessment/scan/` (`SOURCE_EXTENSIONS`, `is_test_path`, `is_config_path`).
Siting the code in `capability/` would make the identity layer import the
assessment layer, inverting the dependency E-48 will establish
(`scan → discover → capability`). A new `assessment/discover/` package imports
*down* into both and is where E-48's proposers land next.

```
src/sdlc/assessment/discover/
    __init__.py
    models.py         # AttributionReport and its parts -- pure, as
                      # capability/models.py and scan/models.py are pure
    attribution.py    # bucket classification + the ratio
    refgraph.py       # import-edge extraction and resolution
```

### D3 — strict denominator

The denominator is **every blob at the pinned commit whose extension is in
`SOURCE_EXTENSIONS`** (18 languages). Test files are in it. Source-language
infrastructure (`setup.py`, `webpack.config.js`, `manage.py`, `conftest.py`) is
in it. Nothing is filtered out.

Outside the denominator: files whose extension is not a source extension —
`README.md`, `LICENSE`, `.yaml`, `Dockerfile`, images. Attributing a docs file
to a capability is not a question with an answer, and a denominator containing
unanswerable questions measures nothing.

The rejected alternative was "source minus tests and infrastructure, exclusions
enumerated". It is more likely to reach 0.90, and that is the objection: a
denominator that shrinks to make its own floor passable is the same defect
class as E-46's review findings, where a gap read as a zero.

### D4 — accounted-for numerator

```
coverage = |member ∪ infrastructure ∪ attached| / |denominator|
```

A file counts *for* coverage when the assessment can say what it is. It counts
*against* only when the assessment cannot — `dead` and `unclassified`.

This is what keeps D3's strict denominator from turning the floor into constant
noise. Infrastructure and test files can never be capability members, so a
numerator of members alone would cap most real repositories well below 0.90 and
the check would report the same failure everywhere. Under D4 the floor means
*the tree is explained*, not *the tree is capability-owned* — and the thing that
depresses the score is precisely the thing the assessment could not account for,
which is FR-915's discipline applied to a ratio.

`dead` counts against deliberately. It is accounted for in the sense that it has
a verdict, but a tree with substantial unreferenced code is a tree this model
does not cleanly explain, and SC-8's "capability coverage ≥90% with classified
orphans" is exactly a claim about how much of the tree the model reaches.

### D5 — five buckets, precedence fixed once

Every file in the denominator lands in exactly one bucket. Precedence is
declaration order, derived from the enum rather than restated — the
`PHASE_ORDER` pattern, for the reason recorded there.

| # | Bucket | Rule | Counts |
|---|---|---|---|
| 1 | `member` | path appears in an attached capability's members | for |
| 2 | `infrastructure` | `is_config_path`, or a `BUILD_TOOLING_NAMES` basename | for |
| 3 | `attached` | graph-connected to a member file | for |
| 4 | `dead` | passes every clause of the dead guard (D7) | against |
| 5 | `unclassified` | anything else | against |

`is_config_path` alone would leave bucket 2 nearly empty, because D3's
denominator holds only source-extension files and that table matches
`Dockerfile`, `docker-compose.yml`, `.env` — none of which are in it. The
infrastructure that *is* in the denominator is source-language build and
tooling config, so a small basename table sits beside it:

```python
BUILD_TOOLING_NAMES: frozenset[str] = frozenset({
    "setup.py", "conftest.py", "manage.py", "noxfile.py", "tasks.py",
    "webpack.config.js", "vite.config.ts", "rollup.config.js",
    "jest.config.js", "karma.conf.js", "next.config.js",
    "babel.config.js", "tailwind.config.js", "gulpfile.js", "build.rs",
})
```

It lives in `discover/attribution.py`, not a shared `scan/` rule module: it has
exactly one consumer, and `sources.py`'s own rationale is that a table moves out
of its module when a *second* signal reads it. Promoting it early would add a
`rule_modules` declaration nothing needs.

`attached` falls out of the reference graph rather than needing its own rule: a
test importing `payments/service.py` is connected to that capability, and so is
a helper a member imports. No separate test bucket exists, and none is needed —
a test file with no connection to any member is genuinely not attributable, and
saying so is more useful than filing it under "test".

### D6 — broad, shallow edge extraction

One regex table keyed by import *form*, dispatched by extension, covering all 18
languages in `SOURCE_EXTENSIONS`: Python `import`/`from` (absolute and
relative), JS/TS/Vue/Svelte `import`/`require`/`export…from`/dynamic `import()`,
Go grouped blocks, JVM `import a.b.C;`, Ruby `require`/`require_relative`, PHP
`use`/`include`, C# `using`, Rust `use`/`mod`, Elixir `alias`/`import`, Swift
`import`.

Resolution has two paths, and the distinction between them is load-bearing:

- **Relative / path-like** (`./x`, `require_relative`, `from ..pkg`, `mod x;`)
  resolves against the importer's directory, trying the extension set plus
  `index.*`, `__init__.py`, `mod.rs`.
- **Dotted / absolute** (`a.b.c`, `A\B`, `crate::a::b`) converts to a path
  fragment and suffix-matches the inventory. **An ambiguous match — two or more
  candidate paths — is recorded unresolved, never a guessed edge.** A wrong edge
  makes a dead file look live *and* an attached file look attached to the wrong
  capability; one guess corrupts two answers.

A dotted import resolving to nothing is an external package: expected, benign,
not recorded as failure. A *relative* import resolving to nothing is extractor
failure, and that rate is the number D7 depends on.

The rejected alternatives were Python-only (most of an arriving repository would
be `unclassified`, driving the floor straight to failure under D4) and a
full per-language AST (correct, and far beyond one increment). The cost of
breadth is accepted false `dead` verdicts on dynamic references, which D7 bounds
and the testing section pins.

### D7 — the dead guard

A file is `dead` only when **all four** hold:

1. Its extension is in the extractor table — a language actually parsed.
2. Zero inbound resolved edges.
3. **It is not framework-discovered.** Two forms, one species — reached by
   convention rather than by an import statement, which is the reference form no
   static extractor can see:
   - it hosts no entry point. Entry-point paths arrive as **data** from S3's
     members (`HTTP_ROUTE`, `CLI_COMMAND`, `QUEUE_TOPIC`, `SCHEDULED_JOB`,
     `GRPC_METHOD`, `FRONTEND_ROUTE`), so nothing here imports a signal module.
   - it does not match `is_test_path`. A test runner collects `test_*.py` and
     `conftest.py` by convention; nothing imports them. Without this clause the
     first repository scanned would be told its entire unmapped test suite is
     dead code, which is both wrong and the most alarming way to be wrong.
4. The tree's unresolved-relative-edge rate is under threshold
   (`DEAD_GUARD_MAX_UNRESOLVED`, default 0.10).

Clause 4 is the one that makes D6 safe to ship. When an extractor fails broadly
— an unanticipated import syntax, a monorepo with path aliases, a build step
that rewrites module specifiers — *every* file looks unreferenced, and a shallow
regex would mass-produce false `dead` verdicts precisely when it is least
trustworthy. Above the threshold the entire `dead` bucket collapses into
`unclassified`, `AttributionReport.dead_guard_tripped` is set, and the ratio is
still measured. A repository whose graph could not be read scores low because it
could not be read, which is the correct outcome.

Any clause failing sends the file to `unclassified`, never to a weaker positive.

The bucket keeps the roadmap's name `dead`, but every record carries
`rule="no_static_inbound_reference"`. Dependency injection, reflection,
string-keyed module loading and framework auto-discovery are invisible to any
regex. The artifact must claim what it saw — that nothing statically references
this file — and not what a reader would like it to mean. This mirrors
`SourceCandidate`'s (rule, detail) discipline, where the rule that fired is what
makes a rating auditable.

### D8 — no `CheckResult` here

The report carries `coverage`, `floor` and `meets_floor`, and stops. E-50 owns
assessment gate checks (FR-917) and E-51 owns per-phase exit criteria as
`CheckResult`s (FR-918). Emitting one here would put the gate in two places, and
this codebase has paid for a second registry before (ADR-6, 2026-07-16).

Whether the floor is absolute or advisory is therefore E-50's call, not this
spec's. The recommendation recorded for it: advisory. A repository this model
cannot fully reach is a weaker audit, not an unverifiable one — unlike E-51's
cross-reference integrity, which is absolute for exactly that reason.

### D9 — naming, to keep two coverages apart

`AttributionReport` in `discover/attribution.py`, not `CoverageReport` in
`discover/coverage.py`. Both names are already taken by *test* coverage:
`CoverageReport` is E-30's model read by the merge gate, and
`scan/signals/coverage.py` is QS2. Two types named `CoverageReport` measuring
different things inside one assessment is a defect waiting for a reader to
conflate them.

### D10 — `is_config_path` becomes a shared rule module

`is_config_path` currently lives in `scan/signals/config_infra.py`, a signal
module. E-47b is its second consumer, which is the exact condition that produced
`scan/testpaths.py` ("a scan-level constant belonging to no single signal") and
`scan/sources.py`. It moves to `scan/configpaths.py`, and **SS3 adds
`_CONFIGPATHS` to its `rule_modules`**.

That second half is not tidiness. `rules_sha` hashes a signal's declared rule
modules transitively into its memo key (D10 of E-46); a shared table that SS3
reads but does not declare means editing a config pattern silently serves a
stale SS3 — the E-3 / D10 hazard both existing shared modules were created to
close.

`discover/` may import `scan/configpaths.py`, `scan/testpaths.py` and
`scan/sources.py`: all three are pure rule modules with no signal semantics.
It may not import `scan/signals/*`, matching the purity rule `sources.py`
records in the other direction.

## Data model

`discover/models.py`, pure — Pydantic and `measurement.py` only, as
`capability/models.py` and `assessment/models.py` are.

```python
class FileBucket(str, Enum):
    MEMBER = "member"
    INFRASTRUCTURE = "infrastructure"
    ATTACHED = "attached"
    DEAD = "dead"
    UNCLASSIFIED = "unclassified"

# Precedence IS declaration order; derived, never restated (PHASE_ORDER's rule).
BUCKET_PRECEDENCE: tuple[FileBucket, ...] = tuple(FileBucket)
ACCOUNTED_FOR: frozenset[FileBucket] = frozenset(
    {FileBucket.MEMBER, FileBucket.INFRASTRUCTURE, FileBucket.ATTACHED})


class FileAttribution(BaseModel):
    """One file's verdict, carrying the rule that produced it."""
    model_config = {"frozen": True}
    path: str
    bucket: FileBucket
    rule: str
    detail: str
    capabilities: tuple[str, ...] = ()   # bc_ids, sorted
```

`capabilities` is non-empty if and only if the bucket is `MEMBER` or `ATTACHED`,
enforced by validator: a `dead` file citing a capability, or an `attached` file
citing none, is a contradiction the type should not be able to express. This is
`_unmeasured_carries_no_payload`'s rule at file scope.

```python
class UnresolvedEdge(BaseModel):
    model_config = {"frozen": True}
    source_path: str
    target: str          # the raw module string, verbatim
    form: str            # "python_relative", "js_bare", "rust_mod", ...
    reason: str          # "no_matching_path" | "ambiguous_suffix"
    relative: bool       # only relative failures feed the guard rate


class ReferenceGraph(BaseModel):
    edges: tuple[tuple[str, str], ...] = ()      # (importer, imported), sorted
    unresolved: tuple[UnresolvedEdge, ...] = ()
    parsed: tuple[str, ...] = ()                 # extractor covered these
    unparsed: tuple[str, ...] = ()               # extension not in the table
    unresolved_relative_rate: Measurement


class AttributionReport(BaseModel):
    files: tuple[FileAttribution, ...] = ()
    counts: dict[FileBucket, int]
    coverage: Measurement                        # the ratio, or not_collected
    floor: float = DEFAULT_COVERAGE_FLOOR        # 0.90
    meets_floor: bool
    dead_guard_tripped: bool
    graph: ReferenceGraph
    skipped: tuple[str, ...] = ()                # blobs that could not be read
```

`meets_floor` is **derived and validated, never assigned** — the
`_confidence_is_derived` / `_terminal_status_matches_derivation` pattern, so a
deserialized payload cannot disagree with its own arithmetic:

```
meets_floor == (coverage.state is MEASURED and coverage.value >= floor)
```

A `not_collected` coverage therefore **never** meets the floor. This is the
FR-915 case that matters most here: an assessment that could not measure
coverage must not read as one that measured it and passed.

`counts` is validated to sum to `len(files)` and to carry every bucket key,
including zeros — an absent key and a zero count are different claims, and only
one of them is true.

## The classifier

```python
def attribute(
    inventory: Mapping[str, str],          # path -> blob text
    skipped: Sequence[str],                # paths that could not be read
    members: Mapping[str, Sequence[str]],  # bc_id -> member paths
    entry_points: Sequence[str],           # paths hosting an S3 entry point
    *,
    floor: float = DEFAULT_COVERAGE_FLOOR,
    max_unresolved: float = DEAD_GUARD_MAX_UNRESOLVED,
) -> AttributionReport:
```

Every input is a parameter. Nothing is read from disk, no git command runs, and
no repository code executes — E-47b joins E-46 in adding no new exposure under
NFR-9. The caller (E-48) supplies the blobs it already read at the pinned
commit.

Order of operations:

1. Build the denominator: `inventory` keys — plus `skipped` paths — whose
   extension is in `SOURCE_EXTENSIONS`. A file that could not be read is still a
   file the model failed to attribute, so dropping it from the denominator would
   let an unreadable tree score 1.0. Empty denominator →
   `not_collected("no source files in the tree")`, **not** `1.0`; a division by
   zero must never read as perfect coverage.
2. Empty `members` → `not_collected("no capabilities to attribute against")`.
   Attribution never happened; a `0.0` here would claim it happened and found
   nothing.
3. Build the graph (`refgraph.build`), yielding edges, unresolved records and
   the relative-failure rate.
4. Walk `BUCKET_PRECEDENCE`, assigning each file its first matching bucket.
5. Compute the ratio over `ACCOUNTED_FOR`, derive `meets_floor`, assemble.

Files in `skipped` are `unclassified` with `rule="blob_unreadable"` and appear
in `AttributionReport.skipped`. E-46's review finding F1 established the
precedent: a blob that could not be read is a gap, and a gap that reads as a
zero is the defect.

Determinism (NFR-10): the denominator, the edge list, `unresolved` and `files`
are all sorted before use, so discovery order cannot change the artifact. Both
new modules join `test_every_pure_signal_module_is_order_independent` rather
than growing a second determinism test.

## Failure modes

| Condition | Result |
|---|---|
| Blob unreadable / skipped | that file `unclassified`, `rule="blob_unreadable"`, listed in `skipped` |
| Capability set empty | `coverage` `not_collected`; `meets_floor` False |
| Denominator empty | `coverage` `not_collected`; never `1.0` |
| Unresolved-relative rate over threshold | `dead` bucket collapses into `unclassified`; `dead_guard_tripped=True`; ratio still measured |
| Extension outside the extractor table | listed in `graph.unparsed`; eligible for `member`/`infrastructure`/`attached`, never `dead` |
| Test path with no member connection | `unclassified`, never `dead` (D7 clause 3) |
| Ambiguous dotted resolution | no edge; `UnresolvedEdge(reason="ambiguous_suffix")` |
| Dotted import matching nothing | external package; not recorded as failure, does not feed the guard |

`dead` and `unclassified` are never summed into a single "unaccounted" figure
anywhere in the artifact. Both are negative for the ratio, but one is a measured
negative and the other an unmeasured one, and conflating those is the exact
defect FR-915 exists to prevent.

## Testing

Follows E-47a's shape — pure tables, a mechanical corpus, properties — rather
than inventing a second one.

**1. Bucket precedence tables.** One case per precedence edge on synthetic
inventories: a file that is both a member and a config path resolves `member`; a
config path with an inbound edge resolves `infrastructure` (rule 2 beats rule
3); an unparsed-language file with zero edges resolves `unclassified`, never
`dead`.

**2. Resolver tables, one fixture per import form.** Python absolute and
relative, JS bare / relative / dynamic, Go grouped block, JVM dotted, Ruby
`require_relative`, PHP namespace, C# `using`, Rust `use` and `mod`, Elixir
`alias`, Swift `import`. Each asserts either the resolved path or an
`UnresolvedEdge` with its reason. Ambiguous suffix match is asserted to produce
**no** edge.

**3. The dead guard's four clauses, one test each.** The load-bearing tests,
because `dead` is the claim a customer acts on by deleting code:

- unparsed language, zero edges → `unclassified`
- entry-point file, zero inbound edges → not `dead`
- synthetic tree whose relative imports broadly fail → whole `dead` bucket
  collapses to `unclassified`, `dead_guard_tripped` set
- genuinely unreferenced parsed file, no entry point, guard untripped → `dead`
  with `rule="no_static_inbound_reference"`

**4. Mechanical mutation corpus.** E-47a's primary investment, same technique:
build a synthetic repository, apply *known* mutations programmatically, assert
the labelled outcome. Delete a file's only import → it becomes `dead`. Move a
file without changing references → coverage unchanged. Reference a file only
through a dynamic `importlib` call → **assert it reads `dead`**.

That last case deliberately pins a known false positive. D6 accepts that dynamic
references are invisible; recording the limitation as a passing test rather than
a docstring caveat means a later increment that adds dynamic-form detection gets
a failing test telling it exactly what it fixed.

**5. FR-915 degradation.** Empty capability set, empty denominator, skipped
blobs. Each asserts `not_collected` *with a reason*, and asserts explicitly that
the value is not `measured(0.0)` or `measured(1.0)`.

**6. Determinism.** Both modules join
`test_every_pure_signal_module_is_order_independent`; plus shuffled-inventory
equality over a whole `AttributionReport`.

**7. Ratio arithmetic and boundaries.** An all-infrastructure tree scores 1.0
(everything accounted for). A half-dead tree scores 0.5. Exactly 0.90 is
`meets_floor=True`. `not_collected` coverage is `meets_floor=False`.

**8. The D10 refactor.** `is_config_path` behaves identically after the move
(SS3's existing tests cover this unchanged), and `rules_sha(ScanSignalId.SS3)`
changes when `configpaths.py` bytes change — asserting the declaration actually
took, rather than trusting that it was remembered.

No temporal e2e: D1 leaves the module unwired, so no workflow path exercises it.
E-48 brings the first integration test when it wires `discover`.

## Scope

This spec is **E-47b**. E-47's remaining clauses are E-47c:

| E-47 clause | Item |
|---|---|
| L1 with stable `BC-NNN` | E-47a — landed 2026-08-08 |
| file→capability coverage floor + orphan classification | **E-47b — this spec** |
| L2 operations | E-47c |
| Entity ownership (exactly one owner or a surfaced conflict) | E-47c |

### Not covered

- **Wiring.** `_discover` stays `unbuilt`; E-48 calls `attribute()`.
- **Gating.** No `CheckResult` (D8); E-50 and E-51 own that.
- **FR-102.** Needs all three of E-47a/b/c plus classify and delta.
- **SC-8.** Needs E-47 complete *and* a corpus of readiness-passing repos.
- **Per-language AST extraction.** D6 chose breadth over depth deliberately; a
  future increment can deepen one language at a time behind the same interface,
  and test 4 will tell it what changed.

## Roadmap deltas

| Item | Change |
|---|---|
| E-47b | `[ ]` → `[x]` on landing |
| FR-913 | Second clause satisfied; still open on E-47c |
| §1 stage 2 (context) | Note that attribution and orphan classification land; FR-102 still needs E-47c |
| NFR-9 | Note E-47b adds no execution of repository code — blob reads only, as E-46 |
| NFR-10 | Two more pure modules under the order-independence assertion |
| E-46 / SS3 | `is_config_path` promoted to `scan/configpaths.py`; SS3 declares it as a rule module |
