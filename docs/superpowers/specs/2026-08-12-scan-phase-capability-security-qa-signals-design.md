# The `scan` Phase — Capability, Security and QA Signals — Design

| | |
|---|---|
| Date | 2026-08-12 |
| Work items | **E-46** (fills §11's first unbuilt phase body; unblocks E-48, and through it E-47a's first live consumer) |
| Requirements | FR-912; FR-902 extended to Tier 2; FR-915; FR-103 (memoization); FR-108 (adapter escalation); NFR-10 |
| Scope input | `PRD.md` §FR-910; `ROADMAP.md` §11 (E-46), §15 item 3; `D:\own\BrownKit\commands\scan.md`; `docs/superpowers/specs/2026-08-10-assessment-workflow-edcr-shell-design.md` D5/D6; `docs/superpowers/specs/2026-08-08-oq6-capability-identity-design.md` (tiers, memo amendment); `docs/superpowers/specs/2026-08-06-repository-triage-hygiene-signals-design.md` D3/D15 |
| Status | Design approved 2026-08-12; plan 1 of 3 implemented |

E-45 shipped the EDCR DAG with six phase bodies stubbed, each reporting
`not_collected` naming the item that owes it. This increment writes the first of
those bodies. It is also the item that ends a two-deep chain of unconsumed
machinery: E-47a's matcher is pure, tested, and reachable only from a CLI
correction verb, because `ProposedCapability` has no producer. Its producer is
E-48, and E-48 has nothing to reason over until scan collects.

It contains no LLM call. Every signal is a deterministic function of the pinned
tree, which is what FR-912's memo key presupposes and what NFR-10 will be
measured against.

---

## 1. What exists today

**Built and load-bearing:**

- **`AssessmentWorkflow` (`workflows/assessment.py`)** — `_scan` returns
  `unbuilt(PhaseId.SCAN)`. `terminal_status` is derived (E-45 D6), so this
  increment flips `admitted:no-phases-implemented` → `assessed:partial` with no
  workflow edit.
- **`Assessment.triage`** — `_init` runs a `TriageWorkflow` child (E-45 D3), so
  by the time `_scan` runs the whole `RepoTriage` is in hand, including every
  `SignalResult` with its findings.
- **Seven triage signals (`triage/signals/`)** — `baseline`, `secrets`,
  `build_probe`, `dependencies`, `scaffold`, `misconfig`, `outliers`. Between
  them they already collect a substantial share of what BrownKit's `scan`
  specifies under SS1–SS3, QS1 and QS4.
- **`SIGNALS` registry (`triage/registry.py`)** — per-signal `version`,
  annotated as the term E-46 folds into its memo key.
- **`TriageWorkflow._one`** — the "a failed signal degrades alone" rule
  (E-41 D3), currently private to that workflow.
- **`Measurement` (`measurement.py`)** — three-valued, `MEASURED` /
  `NOT_COLLECTED` / `UNKNOWN`, with a validator forbidding a value on the
  latter two.
- **`ToolchainAdapter` (`toolchain/adapters.py`)** — language-level facts
  (`source_extensions`, `test_globs`, `manifests`, `lockfiles`) plus an
  `ast`-based `function_spans`. Python is the only adapter; Go/TS/Rust are
  E-30a/b/c, unbuilt.
- **`TreeReader` / `read_tree` (`triage/gitread.py`)** — batched blob reads at a
  pinned commit through one `git cat-file --batch`.
- **`CapabilityFingerprint` (`capability/models.py`)** — four tiers ordered by
  cost-to-change, Contract weighted 0.55.
- **`memoization/cache.py`** — `content_key` + `get`/`put` over a
  hash-named local store.

**Absent:**

- Any capability signal. Nothing in the codebase extracts routes, schema
  clusters, entry points or frontend routes.
- Data-sensitivity classification, testability findings, test-level
  classification, CI stage extraction, per-file coverage breakdown.
- Any producer of `ProposedCapability`.

---

## 2. Decisions

### D1 — All thirteen signals in one spec, three plans

BrownKit's `scan` specifies S1–S5, SS1–SS4 and QS1–QS4. Five of those overlap
signals this codebase already ships, and the overlap is the whole design
problem: it cannot be resolved one family at a time without risking a second
registry of the same fact. So the *design* covers all thirteen and the
*execution* is staged (§9), the way E-41 → E-41a–d staged seven triage signals
across two specs.

### D2 — Deduplication is by reference, never by copy

`SignalSource` is three-valued:

| Value | Meaning |
|---|---|
| `COMPUTED` | This phase computed the whole signal |
| `INHERITED` | The fact is already recorded in an artifact this assessment holds; this row cites it |
| `EXTENDED` | Both — an inherited base plus records computed here |

**`INHERITED` has a deliberately narrow definition: the fact is already
recorded in an artifact this assessment holds** — in practice `Assessment.triage`.
Reusing E-30's Cobertura *parser* for QS2 is code reuse, not inheritance, and
gets no producer row. Without that narrowing, "inherited" would erode into
"related to something that exists".

An inherited row cites findings by `finding_identity()` and copies none:

```python
class InheritedProducer(BaseModel):
    producer: str            # "triage:secrets"
    version: int             # the producer's declared version, pinned
    finding_ids: list[str]   # finding_identity() values
```

Pinning `version` makes a triage version bump visible in the assessment rather
than silently changing what an assessment claimed. Copying findings was
rejected on two grounds: two copies of every credential finding in the FR-921
bundle, and a copy re-labelled with a scan signal id would break the
`finding_identity` keying E-44's before/after delta depends on.

### D3 — Coverage is tracked per category, because a row cannot be half-measured

`ScanSignalResult.collected` is one `Measurement`, and SS1 genuinely has four
categories of which two are inherited and two are computed. So each row carries
`categories: dict[str, Measurement]`, reusing `SignalResult.metrics`' shape: the
row is `MEASURED` because it ran, while `categories["tls_enforcement"]` is
`NOT_COLLECTED` with a reason. This is also what lets §9's staging be honest —
plan 1 lands all thirteen rows with the extension categories reporting
`not_collected`, which is E-45's `unbuilt()` discipline applied one level down.

### D4 — Pattern fingerprints in signal modules; adapter escalation where a parser exists

Extraction follows E-41b/E-41c verbatim: declared pattern tables in the signal
module (`misconfig._FRAMEWORKS`, `scaffold.FINGERPRINTS`), escalating to
`ToolchainAdapter` parsing where a real parser exists — Python's `ast`, via the
member that already serves `function_spans`.

This is E-41's D15 rule extended rather than reinterpreted: *language-level
facts on the adapter; framework fingerprints in the signal module, because one
language serves many frameworks.* It also means E-46 needs no new adapter, so a
TS/JS repository is scannable before E-30b exists — which matters, because
`scaffold.FINGERPRINTS` already covers `create-next-app` and `create-react-app`
paths, i.e. the repositories Tier 0 actually receives.

Parser-only extraction via new `ToolchainAdapter` members was rejected: Python
is the only adapter, so every non-Python repository would report
`not_collected` for the entire capability family until E-30a/b/c land, making
Tier 2 Python-only in practice.

### D5 — An unmatched framework reports `not_collected`, never zero

A file whose framework matches no fingerprint contributes
`not_collected` naming the gap. Never an empty route list.

This is the sharpest instance of FR-915 in the increment, because of what
consumes it. S3's members become `CapabilityFingerprint`'s Contract tier at
weight 0.55. A silently-empty Contract tier does not merely under-report: it
makes E-47a's matcher renormalize onto weaker tiers and risk handing a stored
`BC-NNN` to an unrelated capability, and that spec's stated invariant is that
*"an id clients cite must not move because an unrelated capability's score
changed."* E-47a's evidence floor (no match may rest on Locational alone) is the
second line of defence. This is the first.

### D6 — Only tree-reading signals get an activity

Eleven signals read the tree and get one activity each, fanned out with
`asyncio.gather`. Two are pure derivations and run in workflow code, exactly as
`compute_readiness` does in `TriageWorkflow`:

| | Signals | Count |
|---|---|---|
| Activity (reads the tree) | S1, S2, S3, S4, SS1, SS3, SS4, QS1, QS2, QS3, QS4 | 11 |
| Pure, in-workflow | S5 (merge over other signals' output), SS2 (purely inherited) | 2 |

One activity per signal, not one `scan` activity, for FR-912's stated reason —
*editing one signal's logic invalidates exactly that signal* — and for E-41 D3's:
a slow or failing signal must not take the phase down with it.

### D7 — The inherited half is never memoized

An `EXTENDED` row is assembled from two sources: the activity computes the
records and category measurements that are a function of the tree, and
`scan/inherit.py` derives the inherited half in workflow code from
`Assessment.triage`. **Only the activity's output enters the memo.**

This is a correctness requirement, not tidiness. Triage findings are *not* a
pure function of the tree: `build_probe` executes the repository's own code and
can time out, so the same tree can yield different triage output across runs.
Folding that into a key of `(tree_hash, rules_sha, version)` would memoize a
value the key does not determine. Re-deriving the inherited half every run is
free — it is a pure function over an artifact already in memory.

### D8 — `ScanCandidate.confidence` is derived, never assigned

Derived from the count of **distinct source signals** contributing to the
candidate: 3+ → `HIGH`, 2 → `MEDIUM`, 1 → `LOW`. Enforced by a model validator,
the way `Assessment.terminal_status` is (E-45 D6), so a deserialized payload
cannot disagree with its own sources.

Distinct *signals*, not distinct candidates: two S1 groupings do not corroborate
each other. This is FR-912's *"never the depth of one source"* made structural.

### D9 — S5 never silently collapses

Two merge rules and no more:

1. **Merge on normalized name.** Strip layer suffixes (`Controller`, `Service`,
   `Repository`, `Handler`), lowercase, singularize. `PaymentController` (S3) +
   `payments/` (S1) + the `payments` FK cluster (S2) + `/payments` routes (S4)
   normalize to `payment` → one candidate at `HIGH`.
2. **Overlapping members, different names → do not merge.** Emit both, each
   flagged `possible_duplicate_of`.

Rule 2 is BrownKit's non-collapse rule ported verbatim, and it is what makes S5
safe: it never has to be *right*, only never silently wrong. Deciding a genuine
merge is E-48's D2 (`CONFIRM | SPLIT | MERGE | DE-SCOPE | FLAG`), which is a
proposer with the context to do it.

Normalization also drives S3's "group by business operation, not technical type"
rule — `PaymentController` + `PaymentSettlementJob` + `PaymentEventConsumer` is
one candidate, not three — so it is sited once in `scan/naming.py` and shared by
S3 and S5.

### D10 — The memo key hashes the rules, not just a version number

```python
def signal_key(signal_id: str, version: int, rules_sha: str,
               tree_hash: str) -> str:
```

Four terms, each earning its place:

- **`rules_sha`** hashes the source bytes of the signal's module, plus any shared
  rule module it declares, plus — transitively — the modules of every signal it
  `consumes`. D9 shares `naming.py` between S3 and S5, so editing a suffix list
  changes both signals' output while a hand-maintained `version: int` would not;
  and §5's wave-2 signals are functions of a wave-1 signal's output, so SS1's key
  must move when S3's rules move. Both are the class of bug E-3 was: *the memo
  key missed a real input.* Hashing the real bytes is `PROMPT_SHAS`' existing
  answer to exactly this, and it removes the forgot-to-bump hazard for all
  thirteen signals rather than only the ones that share a module.
- **`version`** stays, as legible declared intent and as the term FR-912 names.
- **`tree_hash`**, not `commit_sha`. Two commits can share a tree (amend,
  rebase, cherry-pick) and a commit-keyed cache would miss on all of them —
  which E-54's incremental re-assessment and E-44's before/after re-triage both
  lean on. Costs one small activity resolving `<commit>^{tree}`.

`content_key` was not reused. Its signature requires `prompt_sha` and
`model_id`; passing `""` for them would make "no model was involved"
indistinguishable from a bug that dropped the model id, in the one place where a
silently wrong value serves stale results indefinitely.

**Two rules on the store:**

- **Cache the row and its payload as one unit** (`SignalOutput`). Caching the
  status row alone would serve a `MEASURED` row with nothing behind it.
- **Never `put` a result that is not `MEASURED`.** Memoizing a timed-out signal
  returns that timeout as a cache hit forever.

**The key has two terms of FR-103's amendment, not three.** E-47a amends the key
to `(tree_hash, signal_version, identity_registry_version)`. That third term
belongs to the `CapabilityMap`, which is a function of the tree *and* the
identity registry; E-47a's own spec states that *"E-46 is a pure function of the
tree."* Recorded here because FR-103's roadmap note reads as though it amends
this key, and it does not.

### D11 — Deviation from the source methodology: the 15–25 candidate band is advisory

BrownKit hard-gates `scan` on producing 15–25 candidates and instructs the agent
to re-extract when under. Ported as a gate this would be wrong, and specifically
wrong for the repositories this tier exists to serve: Tier 0's rationale
(ROADMAP §10) is that target repositories are small and vibe-coded, and a
40-file Next.js application legitimately has four capabilities. BrownKit's band
comes from enterprise Java monoliths — its worked example is
Maven/Jenkins/JaCoCo.

So it ports as an advisory `candidate_count` metric plus an out-of-band
advisory, never a gate. E-51 (acceptance criteria as `CheckResult`s) is where a
binding version would properly live, consistent with FR-106's advisory/absolute
split.

### D12 — Two scope cuts

**SS2's transitive-dependency enumeration is cut.** BrownKit records direct and
transitive dependencies. The risk question — *are there known-vulnerable
dependencies* — is substantially answered by OSV over direct dependencies, which
E-41a already does. Transitive means a lockfile parser per ecosystem
(`poetry.lock`, `pnpm-lock.yaml`, `go.sum`, `Cargo.lock`,
`packages.lock.json`, …) for a marginal gain. SS2 is therefore purely
`INHERITED`. `ToolchainAdapter.lockfiles` is already declared if this is ever
wanted.

**QS2 must not run the test suite.** Executing it would run the assessed
repository's code a second time and widen NFR-9's exposure past E-41's build
probe, and a suite run is not a pure function of the tree, so it could not be
memoized under D10 anyway. Instead: parse `coverage.xml` if one is committed at
the pinned commit (E-30's existing reader, `source: report`), else compute
BrownKit's proxy — `tested_files / significant_files` from QS1's mapping,
`source: proxy`, confidence `LOW`. This is BrownKit's own
`adaptations.coverage_source` rule.

### D13 — `MemberKind` spans the identity tiers; E-46 does not map them

`MemberKind`'s value set is chosen so that every one of
`CapabilityFingerprint`'s four tiers has members that can populate it, making
the later `MemberKind → SignalTier` mapping total. That mapping is **not**
written here. E-47a's own pipeline is *scan → discover proposes boundaries →
fingerprint + resolve*, so siting a capability-identity fact in the scan phase
would put it two stages early, in a module that must not own it.

### D14 — `run_or_degrade` is hoisted so one rule has one home

`TriageWorkflow._one` holds E-41 D3's degradation rule. `AssessmentWorkflow`
needs the same rule over a different row type. Rather than restate it, the
try/except moves to `workflows/fanout.py`:

```python
async def run_or_degrade(activity, arg, opts, *, fallback):
    """A timeout, a lost worker, or an exhausted retry becomes fallback() for
    THIS signal while every other one still reports."""
    try:
        return await workflow.execute_activity(activity, arg, **opts)
    except Exception:                                   # noqa: BLE001
        return fallback()
```

`TriageWorkflow._one` becomes a one-line call passing
`lambda: skipped_signal(signal_id, reason)`. This is the move E-42 D2 made when
it extracted `GateHost` out of `FeatureWorkflow`, for the same reason: two
copies of a first-decision-wins or degrade-alone rule agree only by coincidence.

---

## 3. Module layout

```
src/sdlc/assessment/
  models.py                # E-45 -- gains `scan: ScanResult | None`
  activities.py            # NEW -- 11 signal activities + tree-hash resolver
  scan/
    models.py              # NEW -- ScanResult and its parts (pure)
    registry.py            # NEW -- SCAN_SIGNALS, asserted to cover SCAN_ORDER
    naming.py              # NEW -- shared normalization (S3 + S5), versioned
    merge.py               # NEW -- S5, pure
    inherit.py             # NEW -- inherited halves, pure over RepoTriage
    signals/
      packages.py          # S1
      schema.py            # S2
      entrypoints.py       # S3
      frontend.py          # S4
      security_static.py   # SS1 extension half
      config_infra.py      # SS3 extension half
      sensitivity.py       # SS4
      tests_inventory.py   # QS1 extension half
      coverage.py          # QS2
      testability.py       # QS3
      ci.py                # QS4 extension half
src/sdlc/workflows/
  fanout.py                # NEW -- run_or_degrade, shared with triage.py
  assessment.py            # E-45 -- _scan body
  triage.py                # E-42 -- _one refits onto run_or_degrade
src/sdlc/memoization/cache.py   # gains signal_key
```

`scan/models.py`, `scan/registry.py`, `scan/naming.py`, `scan/merge.py`,
`scan/inherit.py` and every `scan/signals/*.py` are **pure** — Pydantic,
`measurement.py`, `triage/models.py` and `toolchain/adapters.py` only. None may
import `models.py`, `activities.py` or `temporalio`, the discipline
`triage/models.py`, `capability/models.py` and `assessment/models.py` each state
in their own docstrings: a dependency there would appear as a reviewable import.

---

## 4. Contracts

### Signal identity

```python
class ScanSignalId(str, Enum):
    S1 = "S1"; S2 = "S2"; S3 = "S3"; S4 = "S4"; S5 = "S5"
    SS1 = "SS1"; SS2 = "SS2"; SS3 = "SS3"; SS4 = "SS4"
    QS1 = "QS1"; QS2 = "QS2"; QS3 = "QS3"; QS4 = "QS4"

# Declaration order IS the order -- a hand-written tuple beside the enum is a
# second registry, exactly as PHASE_ORDER records.
SCAN_ORDER: tuple[ScanSignalId, ...] = tuple(ScanSignalId)


class SignalFamily(str, Enum):
    CAPABILITY = "capability"    # S1-S5
    SECURITY = "security"        # SS1-SS4
    QA = "qa"                    # QS1-QS4


class SignalSource(str, Enum):
    COMPUTED = "computed"
    INHERITED = "inherited"
    EXTENDED = "extended"
```

### The registry

```python
class ScanSignalSpec(BaseModel):
    id: ScanSignalId
    family: SignalFamily
    version: int
    source: SignalSource
    activity: str = ""            # COMPUTED / EXTENDED: @activity.defn name
    inherits: str = ""            # INHERITED / EXTENDED: "triage:secrets"
    rule_modules: tuple[str, ...] = ()   # shared modules, folded into rules_sha
    consumes: tuple[ScanSignalId, ...] = ()   # upstream signals (§5)
    categories: tuple[str, ...] = ()     # the keys this signal owes (D3)

    @model_validator(mode="after")
    def _source_fields_agree(self) -> "ScanSignalSpec": ...
```

`consumes` does double duty and both uses are derivations, never second
declarations: the fan-out wave is `1` when it is empty and `2` otherwise (§5),
and `rules_sha` folds in the modules of everything consumed, transitively (D10).
A cycle in `consumes` is a boot failure, asserted beside the coverage check.

The validator mirrors `IdentityAttachment._score_matches_method`: `COMPUTED`
requires `activity` and forbids `inherits`; `INHERITED` requires `inherits` and
forbids `activity`; `EXTENDED` requires both. `SCAN_SIGNALS` is asserted at
import to cover `SCAN_ORDER` exactly, so a missing entry is a boot failure
rather than a runtime `KeyError` — the discipline `validate_registry` applies to
`agents.yaml`.

`categories` is the analogue of `SignalSpec.readiness_keys` (E-42 D8a): a signal
declares which category keys it owes, so a skipped signal reports
`not_collected` for exactly those rather than leaving them unreported.

### Records

```python
class MemberKind(str, Enum):
    HTTP_ROUTE = "http_route"
    CLI_COMMAND = "cli_command"
    DB_TABLE = "db_table"
    QUEUE_TOPIC = "queue_topic"
    GRPC_METHOD = "grpc_method"
    SCHEDULED_JOB = "scheduled_job"
    FRONTEND_ROUTE = "frontend_route"
    ENTITY_NAME = "entity_name"
    TEST_NAME = "test_name"
    EXPORTED_SYMBOL = "exported_symbol"
    PACKAGE_PATH = "package_path"
    FILE_PATH = "file_path"


class CandidateMember(BaseModel):
    kind: MemberKind
    value: str                    # "POST /api/payments", "orders", "settle-daily"
    path: str = ""
    line: int | None = None


class EvidenceRef(BaseModel):
    path: str
    lines: str = ""               # "42-78"; "" means whole file


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceCandidate(BaseModel):
    """One candidate as seen by ONE source signal (S1-S4). Not a capability:
    /discover (E-48) decides that and E-47a assigns the id."""
    signal: ScanSignalId
    local_id: str                 # "S1-payments"
    name: str
    rule: str                     # the rule that fired, e.g. "s1_layer_name"
    detail: str                   # why, in one sentence
    confidence_contribution: Confidence
    members: list[CandidateMember]
    evidence: list[EvidenceRef]
    metrics: dict[str, Measurement] = Field(default_factory=dict)
```

`(rule, detail)` is `TriageFinding`'s pair, carried for the same reason: the rule
that produced a confidence rating is what makes the rating auditable. S1's
domain-suggestive / generic / layer classification is expressed as the rule that
fired (`s1_domain_term`, `s1_generic_name`, `s1_layer_name`) rather than as a
boolean, because E-48's guardrail — *delivery channels and deployment boundaries
are not capabilities* — needs the distinction, not just its outcome.

`metrics` carries `file_count`, `loc_estimate`, `fk_edges` as `Measurement`s, so
a count that could not be computed is not a zero.

### The merged candidate

```python
class ScanCandidate(BaseModel):
    candidate_id: str             # "C-01" -- assessment-local, NOT a BC-NNN
    name: str
    sources: list[str]            # local_ids merged into this candidate
    confidence: Confidence        # DERIVED (D8), never assigned
    members: list[CandidateMember]
    possible_duplicate_of: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _confidence_is_derived(self) -> "ScanCandidate": ...
```

`candidate_id` is local to one assessment. `BC-NNN` is E-47a's surrogate key,
allocated after discover — flagged in the field comment because the two look
alike and conflating them would mint identity in the wrong phase.

### The status row and the artifact

```python
class ScanSignalResult(BaseModel):
    signal: ScanSignalId
    family: SignalFamily
    version: int
    source: SignalSource
    collected: Measurement                          # MEASURED value = record count
    categories: dict[str, Measurement] = Field(default_factory=dict)
    producer: InheritedProducer | None = None

    @model_validator(mode="after")
    def _producer_matches_source(self) -> "ScanSignalResult": ...


class SignalOutput(BaseModel):
    """One computed signal's whole output -- the row AND its payload, cached as
    a unit (D10). An activity returns this; the workflow folds in the inherited
    half (D7)."""
    row: ScanSignalResult
    sources: list[SourceCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)


class ScanResult(BaseModel):
    signals: list[ScanSignalResult]          # all 13, in SCAN_ORDER
    sources: list[SourceCandidate]           # S1-S4
    candidates: list[ScanCandidate]          # S5
    data_sensitivity: list[SensitivityRecord]
    testability: list[TestabilityFinding]

    @model_validator(mode="after")
    def _signals_are_the_whole_set(self) -> "ScanResult": ...

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "ScanResult": ...
```

`_signals_are_the_whole_set` mirrors `Assessment._phases_are_the_whole_dag`.
`_unmeasured_carries_no_payload` mirrors
`SignalResult._not_collected_has_no_findings` — partial output is `UNKNOWN`, and
a signal that did not run has no records.

`_producer_matches_source` is the row-level counterpart of the spec validator:
`COMPUTED` must carry no producer, `INHERITED` and `EXTENDED` must carry one.
It also requires every category key the registry declares for that signal to be
present, so a signal cannot silently omit a category it owes — the same move
`compute_readiness` makes when it fills an unreported dimension with
`not_collected` rather than leaving it absent.

### The two separately-typed payloads

`SensitivityRecord` (SS4) and `TestabilityFinding` (QS3) are typed apart from
`SourceCandidate` because their shapes share nothing with it. E-45's rule
against untyped payloads applies within scan as it does across phases:

```python
class Sensitivity(str, Enum):
    PII = "pii"
    FINANCIAL = "financial"
    AUTHENTICATION = "authentication"
    HEALTH = "health"
    REGULATORY = "regulatory"


class SensitivityRecord(BaseModel):
    classification: Sensitivity
    entity: str                        # table (S2) or model name
    origin: Literal["table", "model", "dto"]
    fields: list[str]
    # S3 entry points that read or write the entity, by local_id. Empty when S3
    # reported not_collected -- which the owing category's reason then states,
    # rather than this reading as "no entry point touches PII".
    accessed_by: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef]
    rule: str
    confidence: Confidence


class TestabilityFinding(BaseModel):
    severity: Literal["blocks", "impedes", "smell"]
    pattern: str                       # "static-clock-access"
    detail: str
    recommended_seam: str              # "Inject IClock"
    path: str
    line: int | None = None
    evidence: str = ""                 # verbatim quote from path@commit_sha
    key: str = ""                      # rule-scoped discriminator (E-44 D3)
```

`TestabilityFinding` deliberately carries `evidence` and `key` with
`TriageFinding`'s semantics: a testability blocker is a per-capability finding
E-49 will score and E-53 may seed a fix run from, so it needs the same
delta-stable identity that E-44's `finding_identity` gives triage findings.
`severity` is BrownKit's three-valued scale, not `TriageFinding`'s four-valued
one, because *blocks / impedes / smell* answers a different question than
*critical / high / medium / low* and collapsing them would lose the distinction
FR-916 needs.

### `Assessment` gains one field

```python
class Assessment(BaseModel):
    ...
    scan: ScanResult | None = None

    @model_validator(mode="after")
    def _scan_agrees_with_its_phase(self) -> "Assessment": ...
```

The validator ties the payload to the phase row: `scan` is present iff the SCAN
`PhaseResult` is `MEASURED`. Without it an assessment could report
`not_collected` for the phase while carrying a payload, which is the same
contradiction `_terminal_status_matches_derivation` exists to prevent.
`assemble()` gains a `scan` parameter and stays the only constructor.

---

## 5. The phase run

```python
async def _scan(self, inp: AssessmentInput,
                triage: RepoTriage) -> ScanOutcome:
```

`ScanOutcome(result: PhaseResult, scan: ScanResult | None)` mirrors E-45's
`InitOutcome`, for the same reason: a phase with an artifact has two halves and a
failed phase yields a row but no artifact.

1. **Resolve the tree hash** — one activity, `<commit>^{tree}` at the pinned
   commit. On failure the whole phase reports `not_collected`: without a tree
   hash nothing can be memoized and nothing can be reproduced, so proceeding
   would produce an unmemoizable, unverifiable scan.
2. **Derive the inherited halves** — `inherit.py`, pure over `triage`, in
   workflow code (D7).
3. **Fan out the eleven activities in two waves** — `asyncio.gather` over
   `run_or_degrade(...)` with a `skipped_scan_signal(id, reason)` fallback built
   from the registry's declared `categories`. Two waves, not one, because three
   signals consume another's members (below). A signal's wave is **derived** from
   its declared `consumes` — empty means wave 1 — never assigned, so adding a
   dependent signal is a registry edit rather than a workflow edit and the two
   cannot disagree.
4. **Fold each activity's `SignalOutput` together with its inherited half** into
   the final row: `categories` is the union, `producer` comes from the inherited
   half, `source` is `EXTENDED` when both contributed.
5. **Merge — S5** — `merge.py` over the collected `SourceCandidate`s, pure, in
   workflow code. Emits `ScanCandidate`s with derived confidence (D8) and
   `possible_duplicate_of` flags (D9).
6. **Assemble `ScanResult`** and report the phase `MEASURED` with a value of
   the candidate count.

Sequencing constraints inside the fan-out, recorded because three signals are
not independent:

| Wave | Signals | Consumes |
|---|---|---|
| 1 | S1, S2, S3, S4, SS3, QS1, QS3, QS4 (8) | the tree only |
| 2 | SS1, SS4, QS2 (3) | SS1 ← S3's entry points · SS4 ← S2's tables · QS2 ← QS1's test→file mapping |

A wave-2 signal whose input reported `not_collected` reports `not_collected` for
exactly the dependent category — SS1's `input_validation`, SS4 entirely, QS2's
proxy path — and never a zero. This is where D5's rule earns its keep twice: a
missing S3 must not make SS4 read as "no entry point touches PII", and it must
not make QS2 read as zero coverage.

**Cross-wave memoization needs `rules_sha` to be transitive**, and this is the
one place the naive key is wrong. SS1's output is a function of S3's output, so
if S3's pattern table changes, SS1's records change — but a key over SS1's own
module and the tree would not move, and the cache would serve SS1's stale
records against S3's fresh ones. So `rules_sha` is computed over the signal's own
module, its declared `rule_modules`, **and transitively over the modules of
everything it consumes**. D10's guarantee then holds across waves rather than
only within one.

---

## 6. Error handling & determinism

- **Per-signal degradation.** `run_or_degrade` (D14) turns a timeout, lost
  worker or exhausted retry into `not_collected` for that signal alone. The
  activity's own try/except cannot cover these, which is why the rule lives
  workflow-side.
- **Nothing raises out of `_scan`.** A failure at any step yields a phase row
  reporting `not_collected` with a reason, and `terminal_status` derives
  `assessed:partial`. An assessment that could not scan says so; it does not
  crash.
- **Determinism.** Every fan-out iterates `SCAN_ORDER`, never a bare `set` or
  `dict`. `SourceCandidate` lists are sorted by `(signal, local_id)` and members
  by `(kind, value, path, line)` before they enter the artifact, so the same tree
  yields byte-identical output — the property NFR-10 will be measured against
  and the one `CapabilityFingerprint._canonicalize` already assumes of its
  inputs.
- **No signal executes repository code.** Every one is a read of blob bytes
  through `TreeReader`. The build probe in `init` remains the only place the
  assessed repository runs, and D12 keeps it that way.
- **Blob size bound.** `MAX_BLOB_BYTES` applies per D12's precedent — a minified
  bundle costs more to scan than the finding is worth, and E-41d owns size
  outliers. A skipped oversized blob is recorded in the owing category's reason,
  not silently dropped.

---

## 7. Testing

**Unit, pure — the bulk of it.** Every signal module is a pure function from
`{path: text}` to records, so each pattern table is table-tested against
fixtures per framework, including a negative fixture per rule. `naming.py`,
`merge.py` and `inherit.py` are pure and tested directly.

**Properties worth asserting rather than exemplifying:**

1. **Same tree twice yields byte-identical `ScanResult`** (NFR-10), asserted on
   the serialized artifact, as E-47a asserts for identity allocation.
2. **`confidence` is never assignable** — constructing a `ScanCandidate` whose
   `confidence` disagrees with its `sources` raises (D8).
3. **A not-`MEASURED` signal carries no records** — asserted at the type
   through `_unmeasured_carries_no_payload`.
4. **Nothing not-`MEASURED` reaches the cache** (D10), asserted by driving a
   signal to timeout and confirming the next run recomputes.
5. **`rules_sha` moves when any input's bytes move, transitively** — edit a
   fixture copy of `naming.py` and assert both S3's and S5's keys change; edit
   S3's module and assert **SS1's** key changes too, since SS1 consumes S3
   (D10, §5). This is the test that would have caught E-3, and the second half is
   the one the first draft of this spec got wrong.
6. **Every `finding_id` on an inherited row resolves** in `Assessment.triage`
   (D2) — a dangling reference is exactly what E-51 will make an absolute check.

**Component.** `_scan` against a fabricated `RepoTriage` plus a fixture repo,
with `SCAN_SIGNALS` restricted to a subset, asserting the row set is still the
full thirteen with the rest `not_collected`.

**Temporal.** One `pytest -m temporal` e2e asserting `AssessmentWorkflow` now
reports `assessed:partial` rather than `admitted:no-phases-implemented` — the
E-45 D6 derivation flipping without a workflow edit, which is the claim that
increment made and this one is the first to test.

The fixture repositories come from `benchmarks/cases/` and the DevEval import
(E-79) rather than being hand-authored: nine real repositories already sit in
the tree, and a scan tested only against fixtures written by its own author
tests the author's assumptions.

---

## 8. CLI surface

`sdlc assess` already exists from E-45. Scan adds no verb. The summary output
gains the counts BrownKit's `scan` reports — candidates by confidence, security
signals per category, coverage source (`report <tool>` vs `proxy`), and an
explicit list of `not_collected` categories with reasons. That last line is the
one that matters: it is how an operator sees what the assessment did not
measure, which is the FR-915 claim made visible at the surface rather than only
in the artifact.

---

## 9. Staging

| Plan | Delivers | Rationale |
|---|---|---|
| **1** | Contracts, `SCAN_SIGNALS`, activity seam, `run_or_degrade` hoist, `signal_key`, tree-hash activity, `_scan` wiring, `inherit.py`, and **all thirteen rows** with every inherited half populated | The inherited halves are pure functions over an artifact already in hand, so this is the cheapest possible first increment that still flips `terminal_status` and installs every invariant while the artifact is small |
| **2** | **S1, S3, S5** + `naming.py` | The Contract tier and the candidate set: what E-48 consumes and what makes E-47a's matcher live |
| **3** | **S2, S4, SS4, QS3**, and the SS1 / SS3 / QS1 / QS2 / QS4 extension halves | Completes FR-912 |

During plans 1–2 the unbuilt categories report `not_collected` naming the plan
that owes them. If plan 3 slips, the roadmap gains an **E-46a** for the
remainder and the reasons name it instead — the split E-41 → E-41a–d took for
the same reason.

---

## 10. Out of scope

- **`MemberKind → SignalTier` mapping and fingerprint construction** — E-48 /
  E-47a (D13).
- **Deciding a candidate is a capability** — E-48's D1/D2. Scan proposes;
  discover disposes.
- **Per-capability STRIDE, vulnerability classification, composites** — E-49.
- **Risk thresholds as gate checks; FP dispositions** — E-50.
- **The 14 acceptance criteria, including a binding candidate-yield check** —
  E-51 (D11).
- **Role reports and the evidence bundle** — E-52.
- **Per-phase budgets** — E-55. Scan is the phase most likely to need one
  (assessment input size is the customer's choice), but a budget without the
  phase to bound it is untestable.
- **Transitive dependency enumeration** — cut (D12); reopenable behind
  `ToolchainAdapter.lockfiles`.
- **Go/TS/Rust `ToolchainAdapter`s** — E-30a/b/c. D4 means scan does not block
  on them.
- **Coverage from a suite run** — cut (D12).
- **Per-route authentication findings beyond pattern detection** — SS1 records
  which routes lack an auth marker; deciding whether a route *should* be
  authenticated is E-49, as `misconfig.py`'s own note says.

---

## 11. Roadmap consequences

| Item | Change |
|---|---|
| **E-46** | `[ ]` → `[x]` on plan 3; `[ ] ⚠️` with the delivered subset noted after plans 1 and 2 |
| **FR-912** | `[ ]` → `[x]` on plan 3. Note the memo key gained `rules_sha` beyond the specified `(tree hash, signal version)`, and why (D10) |
| **FR-911** | Stub count drops from six to five; `PHASE_OWNER` loses its `SCAN` entry |
| **§1 stage 2 (context / Cartographer)** | Unchanged, but note that S1–S5 is the extraction half of `CodebaseMap`; FR-102 still needs E-47b/c |
| **P6** | Its first phase body ships. Exit criterion still needs E-48…E-52 |
| **FR-902** | Extend the one-implementation-per-signal rule to cross-tier: an assessment signal that duplicates a triage signal cites it (D2) |
| **FR-103** | Clarify that E-47a's `identity_registry_version` term applies to the `CapabilityMap`, not to E-46's signal keys (D10) |
| **NFR-9** | Note that scan adds no new execution of repository code — every signal is a blob read (D12) |
| **NFR-10** | Now partly falsifiable: the deterministic half has an asserted byte-identical property (§7). The fused-layer variance half still needs runs |
| **§15 item 3** | E-46 lands; the item's remainder is E-47b/E-47c |
| **New: OQ-12** | S5's normalization is English-centric (layer suffixes, singularization). A non-English codebase degrades to LOW-confidence single-source candidates. Recorded rather than solved — it needs a corpus to calibrate against, which SC-8 also needs |
