# E-47c — L2 operations and entity ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `CapabilityMap` its last two clauses — what each capability *does* (L2 operations) and which capability owns each data entity — as pure, deterministic functions over explicit inputs.

**Architecture:** Two pure modules beside E-47b's `attribution.py`, with contracts in the package's one `models.py`. `decompose()` turns each contract-tier `CandidateMember` into one `L2Operation` carrying its own byte range. `assign()` resolves entity ownership by a fixed precedence — declaration site, then write access, then read access — surfacing a conflict rather than guessing. Nothing is wired into a workflow: `_discover` keeps reporting `not_collected` naming E-48, which calls both functions when it lands.

**Tech Stack:** Python 3.14, Pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-14-e47c-l2-operations-and-entity-ownership-design.md`

## Global Constraints

- **Purity.** `discover/` modules import Pydantic, `measurement.py`, and scan **rule** modules (`naming`, `sources`, `testpaths`, `configpaths`) only. Never `models.py` (root), `activities.py`, `temporalio`, or a scan **signal** module (`scan/signals/*`). A dependency here must be visible as a reviewable import.
- **NFR-9.** No disk, no subprocess, no repository code executed. Every input is a parameter.
- **NFR-10.** Byte-identical output across shuffled input order. Sort deterministically; assert sortedness rather than repairing it silently.
- **FR-915.** A gap is `Measurement.not_collected(reason)`, never a zero and never a one. An unmeasured report carries no rows.
- **Derived, never assigned.** Counts and outcome-dependent fields are validated against their own derivation, so a deserialized payload cannot disagree with its arithmetic.
- **Test command:** `pytest` (the default addopts already exclude `slow`/`temporal`/`docker`/`prompt_eval`).
- **Commit style:** `type(scope): subject`, e.g. `feat(discover): ...`, `test(discover): ...`, `refactor(scan): ...`.

---

### Task 1: Promote `route_object` + `PATH_PREFIXES` into `scan/naming.py`

Spec D10. Do this first — Task 3 imports `route_object`. This task changes **landed** code, so it is a pure move behind a parity test.

**Files:**
- Modify: `src/sdlc/assessment/scan/naming.py` (append after `normalize`)
- Modify: `src/sdlc/assessment/scan/signals/entrypoints.py:124-128` (delete `_PATH_PREFIXES`), `:158-162` (`_is_non_specific`), `:198-204` (`_business_name`'s route branch), and its import block
- Test: `tests/test_scan_naming.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `sdlc.assessment.scan.naming.route_object(value: str) -> str | None` and `sdlc.assessment.scan.naming.PATH_PREFIXES: frozenset[str]`, both used by Task 3.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scan_naming.py`:

```python
from sdlc.assessment.scan.naming import PATH_PREFIXES, route_object


def test_route_object_skips_prefixes_and_parameters():
    assert route_object("POST /api/v1/payments") == "payments"
    assert route_object("GET /api/payments/{id}") == "payments"
    assert route_object("GET /v2/orders/:id/items") == "orders"


def test_route_object_reads_a_method_less_value():
    """S4's FRONTEND_ROUTE members carry no method; the last whitespace
    field of a method-less value is the whole path."""
    assert route_object("/payments/:id") == "payments"


def test_route_object_returns_none_when_every_segment_is_a_prefix():
    assert route_object("GET /api/v1") is None
    assert route_object("GET /") is None


def test_route_object_keeps_segment_case():
    """The raw segment, not a key: callers reduce it themselves."""
    assert route_object("GET /Payments") == "Payments"


def test_path_prefixes_is_importable_and_populated():
    assert "api" in PATH_PREFIXES and "v1" in PATH_PREFIXES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_naming.py -v`
Expected: FAIL — `ImportError: cannot import name 'PATH_PREFIXES' from 'sdlc.assessment.scan.naming'`

- [ ] **Step 3: Add the table and the function to `naming.py`**

Append to `src/sdlc/assessment/scan/naming.py`:

```python
# Route segments that prefix an API rather than name a business operation.
# Moved here from entrypoints.py when E-47c's decompose() became a second
# consumer -- sources.py's rule: a table moves out when the second one
# appears (D10). _is_non_specific reads it too, which is why the table moves
# with route_object rather than the function alone.
PATH_PREFIXES: frozenset[str] = frozenset(
    {
        "api",
        "apis",
        "rest",
        "graphql",
        "v1",
        "v2",
        "v3",
        "internal",
        "public",
        "admin",
        "_next",
    }
)


def route_object(value: str) -> str | None:
    """The first segment of a route that names a business object, or None.

    `value` is a member value in S3's uniform "<METHOD> <path>" shape, so the
    path is its last whitespace-separated field -- which for S4's method-less
    FRONTEND_ROUTE values is the whole string, by construction rather than by
    accident.

    Returns the RAW segment. Callers wanting a comparison key reduce it with
    normalize(head_token(...)); returning a key here would make the S3
    business name lossy, which this move must not do.
    """
    for segment in value.split()[-1].split("/"):
        if not segment or segment[0] in "{:<*":
            continue
        if segment.lower() in PATH_PREFIXES:
            continue
        return segment
    return None
```

- [ ] **Step 4: Point `entrypoints.py` at the promoted names**

In `src/sdlc/assessment/scan/signals/entrypoints.py`:

1. Delete the local `_PATH_PREFIXES` block (the `# Route segments that prefix an API...` comment and the frozenset).
2. Extend the naming import:

```python
from ..naming import (
    GENERIC_NAMES,
    LAYER_NAMES,
    PATH_PREFIXES,
    head_token,
    normalize,
    route_object,
)
```

3. In `_is_non_specific`, replace `_PATH_PREFIXES` with `PATH_PREFIXES`:

```python
def _is_non_specific(word: str) -> bool:
    """A stem/segment that names a technical layer, a generic bucket, or an
    API prefix -- none of which is a business operation."""
    key = word.lower()
    return key in LAYER_NAMES or key in GENERIC_NAMES or key in PATH_PREFIXES
```

4. In `_business_name`, replace the inline route loop with the call. The fall-through to the stem logic is load-bearing and must be preserved — a route whose segments are all prefixes still gets a name from its path:

```python
    if kind is MemberKind.HTTP_ROUTE:
        segment = route_object(value)
        if segment is not None:
            return segment
    stem = posixpath.splitext(posixpath.basename(path))[0]
```

- [ ] **Step 5: Run the naming tests and the full S3 parity suite**

Run: `pytest tests/test_scan_naming.py tests/test_scan_s3_entrypoints.py tests/test_scan_rules_sha.py -v`
Expected: PASS. `test_scan_s3_entrypoints.py` must pass **untouched** — this is a move, and any behavioural change in S3 is a defect of this task, not a feature of it.

- [ ] **Step 6: Run the whole suite**

Run: `pytest`
Expected: PASS. Six signals declare `naming` as a rule module (S1, S2, S3, S4, S5, SS4), so their `rules_sha` values all move; `test_scan_rules_sha.py` monkeypatches `module_sha` rather than pinning literals, so no test needs updating.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/naming.py src/sdlc/assessment/scan/signals/entrypoints.py tests/test_scan_naming.py
git commit -m "refactor(scan): promote route_object to naming.py for its second consumer (E-47c D10)"
```

---

### Task 2: Operation contracts

Spec D3, D4, D5, D6, D9 and the Data model section.

**Files:**
- Modify: `src/sdlc/assessment/discover/models.py` (append)
- Test: `tests/test_discover_models.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CONTRACT_KINDS: frozenset[MemberKind]`, `OperationVerb`, `WRITE_VERBS`/`READ_VERBS`/`DIRECTED_VERBS: frozenset[OperationVerb]`, `L2Operation`, `DecompositionReport` — all from `sdlc.assessment.discover.models`, used by Tasks 3 and 5.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_discover_models.py`:

```python
import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.models import (
    CONTRACT_KINDS,
    DIRECTED_VERBS,
    DecompositionReport,
    L2Operation,
    OperationVerb,
)
from sdlc.assessment.scan.models import EvidenceRef, MemberKind
from sdlc.measurement import CollectionState, Measurement

OP = L2Operation(
    op_id="BC-014-OP-01",
    capability="BC-014",
    verb=OperationVerb.CREATE,
    name="create_payment",
    object="payment",
    binding="POST /api/payments",
    kind=MemberKind.HTTP_ROUTE,
    rule="http_post",
    evidence=EvidenceRef(path="api/pay.py", lines="31"),
)


def test_contract_kinds_names_behaviour_not_data_or_structure():
    assert MemberKind.HTTP_ROUTE in CONTRACT_KINDS
    assert MemberKind.SCHEDULED_JOB in CONTRACT_KINDS
    for absent in (
        MemberKind.ENTITY_NAME,
        MemberKind.DB_TABLE,
        MemberKind.TEST_NAME,
        MemberKind.EXPORTED_SYMBOL,
        MemberKind.PACKAGE_PATH,
        MemberKind.FILE_PATH,
    ):
        assert absent not in CONTRACT_KINDS


def test_only_read_and_write_verbs_are_directed():
    assert OperationVerb.CREATE in DIRECTED_VERBS
    assert OperationVerb.READ in DIRECTED_VERBS
    for undirected in (
        OperationVerb.INVOKE,
        OperationVerb.SCHEDULE,
        OperationVerb.CONSUME,
        OperationVerb.RENDER,
    ):
        assert undirected not in DIRECTED_VERBS


def test_by_capability_carries_every_capability_including_zeros():
    report = DecompositionReport(
        operations=(OP,),
        by_capability={"BC-014": 1, "BC-021": 0},
        collected=Measurement.measured(1.0),
    )
    assert report.by_capability["BC-021"] == 0


def test_by_capability_counts_are_derived_from_operations():
    with pytest.raises(ValidationError, match="derived from operations"):
        DecompositionReport(
            operations=(OP,), by_capability={"BC-014": 7}, collected=Measurement.measured(1.0)
        )


def test_an_unmeasured_report_carries_no_operations():
    with pytest.raises(ValidationError, match="carries no payload"):
        DecompositionReport(
            operations=(OP,),
            by_capability={"BC-014": 1},
            collected=Measurement.not_collected("S3 did not collect"),
        )


def test_an_unmeasured_report_with_no_rows_is_valid():
    report = DecompositionReport(collected=Measurement.not_collected("S3 did not collect"))
    assert report.operations == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'CONTRACT_KINDS'`

- [ ] **Step 3: Write the contracts**

Append to `src/sdlc/assessment/discover/models.py`. Extend the existing imports with `from ..scan.models import CandidateMember, EvidenceRef, MemberKind` — scan's `models.py` is a contracts module, not a signal, so this respects the Global Constraint.

```python
# D4. An operation is something the system DOES, reachable from outside the
# capability. The other half of this pairing is E-48's MemberKind ->
# SignalTier map; NEITHER may be derived from the other, because two uses of
# the word "contract" that agree only by coincidence is precisely the defect
# PipelineConfig.roles' boot-time mirror assertion exists to prevent.
CONTRACT_KINDS: frozenset[MemberKind] = frozenset(
    {
        MemberKind.HTTP_ROUTE,
        MemberKind.CLI_COMMAND,
        MemberKind.GRPC_METHOD,
        MemberKind.SCHEDULED_JOB,
        MemberKind.QUEUE_TOPIC,
        MemberKind.FRONTEND_ROUTE,
    }
)

# Kinds whose value is a URL path. head_token("/users/:id") is "/users/:id",
# so these MUST go through naming.route_object before being reduced.
ROUTE_SHAPED_KINDS: frozenset[MemberKind] = frozenset(
    {
        MemberKind.HTTP_ROUTE,
        MemberKind.FRONTEND_ROUTE,
    }
)


class OperationVerb(str, Enum):
    """What an operation does.

    NOT OwnershipVerb (D6). That describes a capability's relationship to an
    entity -- a different subject -- and collapsing the two reads plausibly
    right up to the point where an operation's CREATE is mistaken for an
    ownership CREATES.
    """

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    INVOKE = "invoke"  # CLI command, gRPC method -- direction unknown
    SCHEDULE = "schedule"  # cron/job -- direction unknown
    CONSUME = "consume"  # queue topic -- direction unknown
    RENDER = "render"  # frontend route -- direction unknown


WRITE_VERBS: frozenset[OperationVerb] = frozenset(
    {OperationVerb.CREATE, OperationVerb.UPDATE, OperationVerb.DELETE}
)
READ_VERBS: frozenset[OperationVerb] = frozenset({OperationVerb.READ})

# Ownership rules 2 and 3 consider ONLY these. An operation whose direction we
# cannot read proves contact and nothing else; counting it as a read would
# invent evidence (D8's UNDIRECTED outcome exists for exactly this case).
DIRECTED_VERBS: frozenset[OperationVerb] = WRITE_VERBS | READ_VERBS


class L2Operation(BaseModel):
    """One thing a capability does, resolving 1:1 to a byte range at the
    pinned commit (D3) -- which is why SC-7 holds trivially here."""

    model_config = {"frozen": True}
    op_id: str  # "BC-014-OP-03", assessment-local (D5)
    capability: str  # bc_id
    verb: OperationVerb
    name: str  # "create_payment"
    object: str  # "payment"; "" when underivable
    binding: str  # "POST /api/payments", verbatim
    kind: MemberKind
    rule: str  # the mapping rule that fired
    evidence: EvidenceRef


class DecompositionReport(BaseModel):
    operations: tuple[L2Operation, ...] = ()
    by_capability: dict[str, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> "DecompositionReport":
        for bc_id, claimed in self.by_capability.items():
            actual = sum(1 for o in self.operations if o.capability == bc_id)
            if claimed != actual:
                raise ValueError(
                    f"by_capability[{bc_id}]={claimed} but {actual} "
                    f"operation(s) carry it -- counts are derived from "
                    f"operations, never assigned"
                )
        unlisted = sorted({o.capability for o in self.operations} - set(self.by_capability))
        if unlisted:
            raise ValueError(
                f"operations name capabilities absent from by_capability "
                f"({unlisted}) -- an absent key and a zero count are "
                f"different claims and only one of them is true"
            )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "DecompositionReport":
        if self.collected.state is not CollectionState.MEASURED and self.operations:
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but {len(self.operations)} operation(s) are present -- a "
                f"decomposition that did not happen has no rows (FR-915)"
            )
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/models.py tests/test_discover_models.py
git commit -m "feat(discover): L2 operation contracts -- two verb taxonomies, never one (E-47c D3-D6)"
```

---

### Task 3: `decompose()`

Spec D3, D5, D6, D9 and "The two functions".

**Files:**
- Create: `src/sdlc/assessment/discover/operations.py`
- Test: `tests/test_discover_operations.py`

**Interfaces:**
- Consumes: Task 1's `route_object`; Task 2's `CONTRACT_KINDS`, `ROUTE_SHAPED_KINDS`, `OperationVerb`, `L2Operation`, `DecompositionReport`.
- Produces: `decompose(members: Mapping[str, Sequence[CandidateMember]], *, contract_collected: Measurement) -> DecompositionReport`, used by Task 5 and later by E-48.

- [ ] **Step 1: Write the failing test**

Create `tests/test_discover_operations.py`:

```python
"""FR-913 (E-47c): one operation per contract member, each resolving to a
byte range at the pinned commit (D3)."""

from __future__ import annotations

import random

from sdlc.assessment.discover.models import OperationVerb
from sdlc.assessment.discover.operations import decompose
from sdlc.assessment.scan.models import CandidateMember, MemberKind
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)


def _m(kind: MemberKind, value: str, path: str = "api/pay.py", line: int = 1):
    return CandidateMember(kind=kind, value=value, path=path, line=line)


PAYMENTS = [
    _m(MemberKind.HTTP_ROUTE, "POST /api/payments", line=31),
    _m(MemberKind.HTTP_ROUTE, "GET /api/payments/{id}", line=47),
    _m(MemberKind.HTTP_ROUTE, "DELETE /api/payments/{id}", line=62),
    _m(MemberKind.SCHEDULED_JOB, "settle_nightly", "jobs/settle.py", 12),
]


def test_each_contract_member_becomes_its_own_operation():
    """D3: no clustering. Four members, four operations."""
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    assert len(report.operations) == 4
    assert report.by_capability == {"BC-014": 4}


def test_every_operation_carries_its_own_byte_range():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    located = {(o.evidence.path, o.evidence.lines) for o in report.operations}
    assert ("api/pay.py", "31") in located
    assert ("jobs/settle.py", "12") in located
    assert len(located) == 4


def test_http_methods_map_to_verbs():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    by_binding = {o.binding: o.verb for o in report.operations}
    assert by_binding["POST /api/payments"] is OperationVerb.CREATE
    assert by_binding["GET /api/payments/{id}"] is OperationVerb.READ
    assert by_binding["DELETE /api/payments/{id}"] is OperationVerb.DELETE
    assert by_binding["settle_nightly"] is OperationVerb.SCHEDULE


def test_an_unrecognized_method_is_invoke_not_dropped():
    report = decompose(
        {"BC-014": [_m(MemberKind.HTTP_ROUTE, "TRACE /debug")]}, contract_collected=MEASURED
    )
    assert len(report.operations) == 1
    assert report.operations[0].verb is OperationVerb.INVOKE
    assert report.operations[0].rule == "unrecognized_http_method"


def test_operations_are_named_verb_object():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    names = {o.name for o in report.operations}
    assert "create_payment" in names
    assert "read_payment" in names


def test_a_frontend_route_reduces_through_route_object():
    """A raw URL through head_token would reduce to garbage."""
    report = decompose(
        {"BC-014": [_m(MemberKind.FRONTEND_ROUTE, "/payments/:id", "app.tsx")]},
        contract_collected=MEASURED,
    )
    assert report.operations[0].object == "payment"
    assert report.operations[0].verb is OperationVerb.RENDER


def test_an_underivable_object_is_empty_and_named_by_its_verb():
    report = decompose(
        {"BC-014": [_m(MemberKind.HTTP_ROUTE, "GET /api/v1")]}, contract_collected=MEASURED
    )
    assert report.operations[0].object == ""
    assert report.operations[0].name == "read"


def test_non_contract_kinds_yield_no_operations():
    """D4, and a MEASURED zero -- not a gap."""
    report = decompose(
        {
            "BC-009": [
                _m(MemberKind.EXPORTED_SYMBOL, "parse"),
                _m(MemberKind.TEST_NAME, "test_parse"),
                _m(MemberKind.DB_TABLE, "orders"),
            ]
        },
        contract_collected=MEASURED,
    )
    assert report.operations == ()
    assert report.by_capability == {"BC-009": 0}
    assert report.collected.state is CollectionState.MEASURED


def test_op_ids_are_positional_and_capability_scoped():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    assert [o.op_id for o in report.operations] == [
        "BC-014-OP-01",
        "BC-014-OP-02",
        "BC-014-OP-03",
        "BC-014-OP-04",
    ]


def test_a_degraded_contract_tier_yields_no_rows():
    """D9/FR-915: S3 failing closed must not read as a capability with no
    operations."""
    report = decompose(
        {"BC-014": PAYMENTS},
        contract_collected=Measurement.not_collected("S3 reported not_collected"),
    )
    assert report.operations == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
    assert "S3" in report.collected.reason


def test_output_is_byte_identical_across_input_order():
    """NFR-10, asserted in this module's own test file."""
    shuffled = list(PAYMENTS)
    random.Random(20260814).shuffle(shuffled)
    first = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    second = decompose({"BC-014": shuffled}, contract_collected=MEASURED)
    assert first.model_dump_json() == second.model_dump_json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_operations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.operations'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/assessment/discover/operations.py`:

```python
"""FR-913 (E-47c): L2 decomposition -- one operation per contract member.

D3 chose the fine grain deliberately. Clustering members into coarser
operations is a judgment call, and a judgment made here is invisible: a wrong
merge looks exactly like a genuine operation. Made in E-48 it is a MERGE
disposition with a rationale, which is the form the methodology already has.

The payoff is that an operation resolves 1:1 to a byte range at the pinned
commit, so SC-7's "zero fabricated path/line refs" holds by construction.

Pure: every input is a parameter. No disk, no subprocess, no repository code
executed (NFR-9).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ...measurement import CollectionState, Measurement
from ..scan.models import CandidateMember, EvidenceRef, MemberKind
from ..scan.naming import head_token, normalize, route_object
from .models import (
    CONTRACT_KINDS,
    ROUTE_SHAPED_KINDS,
    DecompositionReport,
    L2Operation,
    OperationVerb,
)

_METHOD_VERBS: dict[str, OperationVerb] = {
    "POST": OperationVerb.CREATE,
    "PUT": OperationVerb.UPDATE,
    "PATCH": OperationVerb.UPDATE,
    "DELETE": OperationVerb.DELETE,
    "GET": OperationVerb.READ,
    "HEAD": OperationVerb.READ,
}

_KIND_VERBS: dict[MemberKind, OperationVerb] = {
    MemberKind.CLI_COMMAND: OperationVerb.INVOKE,
    MemberKind.GRPC_METHOD: OperationVerb.INVOKE,
    MemberKind.SCHEDULED_JOB: OperationVerb.SCHEDULE,
    MemberKind.QUEUE_TOPIC: OperationVerb.CONSUME,
    MemberKind.FRONTEND_ROUTE: OperationVerb.RENDER,
}


def _verb(member: CandidateMember) -> tuple[OperationVerb, str]:
    """(verb, rule). An unrecognized method reaches INVOKE and records the
    rule -- never dropped, because a route we extracted is a contract we
    observed, whatever its method (D6)."""
    if member.kind is MemberKind.HTTP_ROUTE:
        fields = member.value.split()
        method = fields[0].upper() if fields else ""
        verb = _METHOD_VERBS.get(method)
        if verb is None:
            return OperationVerb.INVOKE, "unrecognized_http_method"
        return verb, f"http_{method.lower()}"
    return _KIND_VERBS[member.kind], f"kind_{member.kind.value}"


def _object(member: CandidateMember) -> str:
    """The entity key this operation is about, or "".

    Both branches end in normalize(head_token(...)) -- S2's _cluster_key --
    so an operation's object and an entity's key are comparable by
    construction rather than by two tables agreeing.
    """
    raw = member.value
    if member.kind in ROUTE_SHAPED_KINDS:
        segment = route_object(member.value)
        if segment is None:
            return ""
        raw = segment
    return normalize(head_token(raw))


def decompose(
    members: Mapping[str, Sequence[CandidateMember]],
    *,
    contract_collected: Measurement,
) -> DecompositionReport:
    """bc_id -> its members, in; one operation per contract member, out.

    `contract_collected` is S3's (and S4's) collection state. Fail closed:
    a degraded contract tier must not read as a capability that genuinely
    exposes nothing (D9).
    """
    if contract_collected.state is not CollectionState.MEASURED:
        return DecompositionReport(
            by_capability={bc_id: 0 for bc_id in sorted(members)}, collected=contract_collected
        )

    operations: list[L2Operation] = []
    for bc_id in sorted(members):
        contract = sorted(
            (m for m in members[bc_id] if m.kind in CONTRACT_KINDS), key=CandidateMember.sort_key
        )
        for index, member in enumerate(contract, start=1):
            verb, rule = _verb(member)
            obj = _object(member)
            operations.append(
                L2Operation(
                    op_id=f"{bc_id}-OP-{index:02d}",
                    capability=bc_id,
                    verb=verb,
                    name=f"{verb.value}_{obj}" if obj else verb.value,
                    object=obj,
                    binding=member.value,
                    kind=member.kind,
                    rule=rule,
                    evidence=EvidenceRef(
                        path=member.path, lines="" if member.line is None else str(member.line)
                    ),
                )
            )

    return DecompositionReport(
        operations=tuple(operations),
        by_capability={
            bc_id: sum(1 for o in operations if o.capability == bc_id) for bc_id in sorted(members)
        },
        # The value is the row count, following SS4's convention that a
        # Measurement carries something worth reading, not a bare flag.
        collected=Measurement.measured(float(len(operations))),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_operations.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/operations.py tests/test_discover_operations.py
git commit -m "feat(discover): decompose() -- one operation per contract member (E-47c D3)"
```

---

### Task 4: Ownership contracts

Spec D2, D6, D7, D8, D9 and the Data model section.

**Files:**
- Modify: `src/sdlc/assessment/discover/models.py` (append)
- Test: `tests/test_discover_models.py` (append)

**Interfaces:**
- Consumes: Task 2's imports already present in `models.py`.
- Produces: `EntityDeclaration`, `OwnershipVerb`, `OwnershipOutcome`, `EntityOwnership`, `OwnershipReport`, used by Task 5.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_discover_models.py`:

```python
from sdlc.assessment.discover.models import (
    EntityOwnership,
    OwnershipOutcome,
    OwnershipReport,
    OwnershipVerb,
)


def _counts(*rows: EntityOwnership) -> dict[OwnershipOutcome, int]:
    return {o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome}


OWNED = EntityOwnership(
    entity="order",
    outcome=OwnershipOutcome.OWNED,
    owner="BC-014",
    verb=OwnershipVerb.OWNS,
    rule="declared_in_sole_member",
    claimants=("BC-014",),
)


def test_tracks_is_not_a_deterministic_verb():
    """D6: four relationships have a trigger; TRACKS has none, and it is
    reserved for E-48's proposer."""
    assert not hasattr(OwnershipVerb, "TRACKS")
    assert {v.value for v in OwnershipVerb} == {"owns", "creates", "manages", "reads"}


def test_an_owner_requires_the_owned_outcome():
    with pytest.raises(ValidationError, match="owner and verb are set"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.CONFLICT,
            owner="BC-014",
            verb=OwnershipVerb.OWNS,
            rule="tied_writers",
            claimants=("BC-014", "BC-021"),
        )


def test_the_owned_outcome_requires_an_owner():
    with pytest.raises(ValidationError, match="owner and verb are set"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.OWNED,
            rule="sole_writer",
            claimants=("BC-014",),
        )


def test_a_conflict_needs_at_least_two_claimants():
    with pytest.raises(ValidationError, match="at least two claimants"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tied_writers",
            claimants=("BC-014",),
        )


def test_an_unclaimed_entity_names_no_claimants():
    with pytest.raises(ValidationError, match="names no claimants"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.UNCLAIMED,
            rule="no_claimant",
            claimants=("BC-014",),
        )


def test_claimants_are_asserted_sorted_never_repaired():
    with pytest.raises(ValidationError, match="not sorted"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tied_writers",
            claimants=("BC-021", "BC-014"),
        )


def test_counts_carry_every_outcome_including_zeros():
    report = OwnershipReport(
        entities=(OWNED,), counts=_counts(OWNED), collected=Measurement.measured(1.0)
    )
    assert report.counts[OwnershipOutcome.UNCLAIMED] == 0


def test_a_missing_outcome_key_is_rejected():
    with pytest.raises(ValidationError, match="every outcome"):
        OwnershipReport(
            entities=(OWNED,),
            counts={OwnershipOutcome.OWNED: 1},
            collected=Measurement.measured(1.0),
        )


def test_an_unmeasured_ownership_report_carries_no_rows():
    with pytest.raises(ValidationError, match="carries no payload"):
        OwnershipReport(
            entities=(OWNED,), counts=_counts(OWNED), collected=Measurement.not_collected("S2 gap")
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'EntityOwnership'`

- [ ] **Step 3: Write the contracts**

Append to `src/sdlc/assessment/discover/models.py`:

```python
class OwnershipVerb(str, Enum):
    """A capability's relationship to an entity. NOT OperationVerb (D6).

    TRACKS is deliberately absent. The other four have a deterministic
    trigger; TRACKS means something closer to "holds a reference for
    lifecycle purposes", which no static signal here distinguishes from
    READS. Emitting it would put a judgment call behind a code-computed
    label -- the exact defect this port exists to remove from BrownKit's
    prose gates. It is reserved for E-48's proposer.
    """

    OWNS = "owns"
    CREATES = "creates"
    MANAGES = "manages"
    READS = "reads"


class OwnershipOutcome(str, Enum):
    """D8: three non-owned outcomes, deliberately not one.

    Collapsing them would repeat coverage_pct's defect. A CLI-written table
    reported as UNCLAIMED tells a customer nothing touches data their job
    writes nightly -- a different and worse claim than "we cannot read the
    direction of the thing that touches it".
    """

    OWNED = "owned"
    CONFLICT = "conflict"  # 2+ tied claimants; E-48 picks
    UNDIRECTED = "undirected"  # claimants, none with readable direction
    UNCLAIMED = "unclaimed"  # nothing in the capability set touches it


class EntityDeclaration(BaseModel):
    """D2: what assign() needs from S2, WITHOUT importing a signal.

    discover/ imports scan RULE modules and never a signal: a signal is a
    producer with a memo key and a version, and depending on one here would
    make this package part of that signal's hashed surface. E-48 adapts S2's
    TableDecl at the call site, where both are already in scope.
    """

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

    @model_validator(mode="after")
    def _owner_matches_outcome(self) -> "EntityOwnership":
        owned = self.outcome is OwnershipOutcome.OWNED
        if owned != (self.owner is not None and self.verb is not None):
            raise ValueError(
                f"owner and verb are set IFF outcome is owned -- got "
                f"outcome={self.outcome.value} owner={self.owner} "
                f"verb={self.verb}. A row that names an owner and calls "
                f"itself a conflict is not a weaker claim, it is two claims"
            )
        return self

    @model_validator(mode="after")
    def _claimants_match_outcome(self) -> "EntityOwnership":
        if self.outcome is OwnershipOutcome.CONFLICT and len(self.claimants) < 2:
            raise ValueError(
                f"outcome=conflict needs at least two claimants, got "
                f"{self.claimants} -- one claimant is not a contest"
            )
        if self.outcome is OwnershipOutcome.UNCLAIMED and self.claimants:
            raise ValueError(f"outcome=unclaimed names no claimants, got {self.claimants}")
        if (
            self.outcome in (OwnershipOutcome.OWNED, OwnershipOutcome.UNDIRECTED)
            and not self.claimants
        ):
            raise ValueError(
                f"outcome={self.outcome.value} requires at least one "
                f"claimant -- it is defined by something touching the entity"
            )
        return self

    @model_validator(mode="after")
    def _claimants_are_sorted(self) -> "EntityOwnership":
        """Asserted, not repaired: a producer emitting discovery order is a
        determinism bug (NFR-10), and fixing it here would hide it. This is
        FileAttribution._capabilities_are_sorted's rule."""
        if list(self.claimants) != sorted(set(self.claimants)):
            raise ValueError(
                f"claimants {self.claimants} are not sorted and deduped -- "
                f"discovery order must not reach the artifact"
            )
        return self


class OwnershipReport(BaseModel):
    entities: tuple[EntityOwnership, ...] = ()
    counts: dict[OwnershipOutcome, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_agree_with_entities(self) -> "OwnershipReport":
        """AttributionReport._counts_agree_with_files, verbatim in intent."""
        missing = [o.value for o in OwnershipOutcome if o not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every outcome, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true"
            )
        for outcome in OwnershipOutcome:
            actual = sum(1 for e in self.entities if e.outcome is outcome)
            if self.counts[outcome] != actual:
                raise ValueError(
                    f"counts[{outcome.value}]={self.counts[outcome]} but "
                    f"{actual} entit(ies) carry it -- counts are derived "
                    f"from entities, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "OwnershipReport":
        if self.collected.state is not CollectionState.MEASURED and self.entities:
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but {len(self.entities)} entit(ies) are present -- an "
                f"ownership map that did not happen has no rows (FR-915)"
            )
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/models.py tests/test_discover_models.py
git commit -m "feat(discover): ownership contracts -- three non-owned outcomes, no TRACKS (E-47c D6-D8)"
```

---

### Task 5: `assign()`

Spec D7, D8, D9 and "The two functions".

**Files:**
- Create: `src/sdlc/assessment/discover/ownership.py`
- Test: `tests/test_discover_ownership.py`

**Interfaces:**
- Consumes: Task 3's `L2Operation` values; Task 4's `EntityDeclaration`, `EntityOwnership`, `OwnershipOutcome`, `OwnershipReport`, `OwnershipVerb`; Task 2's `WRITE_VERBS`, `READ_VERBS`, `DIRECTED_VERBS`.
- Produces: `assign(declarations, member_paths, operations, *, schema_collected, contract_collected) -> OwnershipReport`, called by E-48.

- [ ] **Step 1: Write the failing test**

Create `tests/test_discover_ownership.py`:

```python
"""FR-913 (E-47c): exactly one owner, or a surfaced conflict (D7/D8)."""

from __future__ import annotations

import random

from sdlc.assessment.discover.models import (
    EntityDeclaration,
    OperationVerb,
    OwnershipOutcome,
    OwnershipVerb,
)
from sdlc.assessment.discover.ownership import assign
from sdlc.assessment.scan.models import EvidenceRef, MemberKind
from sdlc.assessment.discover.models import L2Operation
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)
ORDERS = EntityDeclaration(name="orders", path="db/models/order.py", line=8)


def _op(bc_id: str, verb: OperationVerb, obj: str, n: int = 1) -> L2Operation:
    return L2Operation(
        op_id=f"{bc_id}-OP-{n:02d}",
        capability=bc_id,
        verb=verb,
        name=f"{verb.value}_{obj}",
        object=obj,
        binding=f"{verb.value.upper()} /{obj}",
        kind=MemberKind.HTTP_ROUTE,
        rule="http_post",
        evidence=EvidenceRef(path="api/a.py", lines="3"),
    )


def _assign(decls, members, ops):
    return assign(decls, members, ops, schema_collected=MEASURED, contract_collected=MEASURED)


def _row(report, entity: str):
    return next(e for e in report.entities if e.entity == entity)


def test_declaration_site_confers_ownership():
    report = _assign([ORDERS], {"BC-014": ["db/models/order.py"]}, [])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.OWNED
    assert row.owner == "BC-014"
    assert row.verb is OwnershipVerb.OWNS
    assert row.rule == "declared_in_sole_member"


def test_declaration_outranks_a_different_sole_writer():
    """The precedence claim itself (D7)."""
    report = _assign(
        [ORDERS], {"BC-014": ["db/models/order.py"]}, [_op("BC-021", OperationVerb.CREATE, "order")]
    )
    row = _row(report, "order")
    assert row.owner == "BC-014"
    assert row.rule == "declared_in_sole_member"


def test_a_sole_writer_owns_when_the_declaring_file_is_unattributed():
    report = _assign(
        [ORDERS], {"BC-014": ["api/orders.py"]}, [_op("BC-014", OperationVerb.CREATE, "order")]
    )
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.OWNED
    assert row.owner == "BC-014"
    assert row.verb is OwnershipVerb.CREATES


def test_mixed_writes_read_as_manages_not_creates():
    report = _assign(
        [ORDERS],
        {},
        [
            _op("BC-014", OperationVerb.CREATE, "order", 1),
            _op("BC-014", OperationVerb.DELETE, "order", 2),
        ],
    )
    assert _row(report, "order").verb is OwnershipVerb.MANAGES


def test_a_sole_reader_owns_when_nothing_writes():
    report = _assign([ORDERS], {}, [_op("BC-007", OperationVerb.READ, "order")])
    row = _row(report, "order")
    assert row.owner == "BC-007"
    assert row.verb is OwnershipVerb.READS
    assert row.rule == "sole_reader"


def test_a_reader_never_outranks_a_writer():
    report = _assign(
        [ORDERS],
        {},
        [
            _op("BC-014", OperationVerb.CREATE, "order", 1),
            _op("BC-007", OperationVerb.READ, "order", 2),
        ],
    )
    assert _row(report, "order").owner == "BC-014"


def test_tied_writers_surface_a_conflict():
    report = _assign(
        [ORDERS],
        {},
        [
            _op("BC-021", OperationVerb.CREATE, "order", 1),
            _op("BC-014", OperationVerb.UPDATE, "order", 2),
        ],
    )
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.CONFLICT
    assert row.owner is None
    assert row.claimants == ("BC-014", "BC-021")
    assert row.rule == "tied_writers"


def test_a_shared_declaration_file_surfaces_a_conflict():
    report = _assign(
        [ORDERS], {"BC-014": ["db/models/order.py"], "BC-021": ["db/models/order.py"]}, []
    )
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.CONFLICT
    assert row.rule == "declared_in_shared_file"


def test_an_undirected_claimant_is_not_unclaimed():
    """D8: a CLI-written table must not read as untouched."""
    report = _assign([ORDERS], {}, [_op("BC-014", OperationVerb.INVOKE, "order")])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.UNDIRECTED
    assert row.claimants == ("BC-014",)
    assert row.rule == "undirected_only"


def test_an_untouched_entity_is_unclaimed():
    report = _assign([ORDERS], {}, [])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.UNCLAIMED
    assert row.claimants == ()


def test_declarations_reduce_to_one_row_per_entity_key():
    """order_items and orders share a key, as S2's _cluster_key intends."""
    report = _assign(
        [ORDERS, EntityDeclaration(name="order_items", path="db/m.py", line=2)], {}, []
    )
    assert [e.entity for e in report.entities] == ["order"]


def test_known_limitation_a_shared_models_package_grants_blanket_ownership():
    """D7, pinned rather than caveated. Every declaration lives in one
    capability's files, so rule 1 hands it the whole schema. E-48's proposer
    is the layer with standing to override this; a change to the rule should
    move this test rather than surprise a customer."""
    decls = [
        ORDERS,
        EntityDeclaration(name="payments", path="db/models/pay.py", line=3),
        EntityDeclaration(name="users", path="db/models/user.py", line=5),
    ]
    report = _assign(
        decls, {"BC-002": ["db/models/order.py", "db/models/pay.py", "db/models/user.py"]}, []
    )
    assert {e.owner for e in report.entities} == {"BC-002"}
    assert report.counts[OwnershipOutcome.OWNED] == 3


def test_a_degraded_schema_signal_yields_no_rows():
    report = assign(
        [ORDERS],
        {},
        [],
        schema_collected=Measurement.not_collected("S2 gap"),
        contract_collected=MEASURED,
    )
    assert report.entities == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
    assert "S2" in report.collected.reason


def test_a_degraded_contract_signal_yields_no_rows():
    """Without S3 every entity would fall to the declaration rule -- a
    weaker answer in the identical shape, which is what FR-915 forbids."""
    report = assign(
        [ORDERS],
        {"BC-014": ["db/models/order.py"]},
        [],
        schema_collected=MEASURED,
        contract_collected=Measurement.not_collected("S3 gap"),
    )
    assert report.entities == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
    assert "S3" in report.collected.reason


def test_a_not_collected_report_still_carries_every_outcome_count():
    report = assign(
        [ORDERS],
        {},
        [],
        schema_collected=Measurement.not_collected("S2 gap"),
        contract_collected=MEASURED,
    )
    assert set(report.counts) == set(OwnershipOutcome)
    assert sum(report.counts.values()) == 0


def test_output_is_byte_identical_across_input_order():
    """NFR-10, in this module's own test file."""
    decls = [ORDERS, EntityDeclaration(name="payments", path="db/models/pay.py", line=3)]
    ops = [
        _op("BC-021", OperationVerb.CREATE, "payment", 1),
        _op("BC-014", OperationVerb.READ, "order", 2),
    ]
    members = {"BC-014": ["db/models/order.py"], "BC-002": ["x.py"]}
    shuffled_decls, shuffled_ops = list(decls), list(ops)
    rng = random.Random(20260814)
    rng.shuffle(shuffled_decls)
    rng.shuffle(shuffled_ops)
    first = _assign(decls, members, ops)
    second = _assign(shuffled_decls, dict(reversed(list(members.items()))), shuffled_ops)
    assert first.model_dump_json() == second.model_dump_json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_ownership.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.ownership'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/assessment/discover/ownership.py`:

```python
"""FR-913 (E-47c): which capability owns each data entity.

D7's precedence -- declaration site, then write access, then read access --
is ordered by strength of evidence. Declaration is the strongest and the
cheapest to explain: the capability whose files declare the table is the one
a customer would name. Access ranks below it because it is a
name-normalization match, not a data-flow trace.

Nothing here decides consequences. An ownership conflict is a finding, not a
failure; E-50 owns gate checks and E-48 owns resolution (D11).

Pure: every input is a parameter. No disk, no subprocess, no repository code
executed (NFR-9).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ...measurement import CollectionState, Measurement
from ..scan.models import EvidenceRef
from ..scan.naming import head_token, normalize
from .models import (
    DIRECTED_VERBS,
    READ_VERBS,
    WRITE_VERBS,
    EntityDeclaration,
    EntityOwnership,
    L2Operation,
    OperationVerb,
    OwnershipOutcome,
    OwnershipReport,
    OwnershipVerb,
)


def _key(name: str) -> str:
    """S2's _cluster_key: order_items and orders both reach 'order'. Both
    helpers are already public in naming.py, so nothing is promoted here."""
    return normalize(head_token(name)) or name.strip().lower()


def _empty(reason: str) -> OwnershipReport:
    """FR-915: ownership was not computed, so there are no rows -- not zero
    owners, and certainly not a map of unclaimed entities."""
    return OwnershipReport(
        entities=(),
        counts={o: 0 for o in OwnershipOutcome},
        collected=Measurement.not_collected(reason),
    )


def _write_verb(verbs: set[OperationVerb]) -> OwnershipVerb:
    """CREATES only when every matching write creates; anything else is the
    broader MANAGES (D7 rule 2)."""
    return OwnershipVerb.CREATES if verbs == {OperationVerb.CREATE} else OwnershipVerb.MANAGES


def _resolve(
    entity: str, decls: Sequence[EntityDeclaration], declarers: set[str], ops: Sequence[L2Operation]
) -> EntityOwnership:
    decl_evidence = tuple(EvidenceRef(path=d.path, lines=str(d.line)) for d in decls)

    # Rule 1 -- declaration site.
    if len(declarers) == 1:
        return EntityOwnership(
            entity=entity,
            outcome=OwnershipOutcome.OWNED,
            owner=next(iter(declarers)),
            verb=OwnershipVerb.OWNS,
            rule="declared_in_sole_member",
            claimants=tuple(sorted(declarers)),
            evidence=decl_evidence,
        )
    if len(declarers) > 1:
        return EntityOwnership(
            entity=entity,
            outcome=OwnershipOutcome.CONFLICT,
            rule="declared_in_shared_file",
            claimants=tuple(sorted(declarers)),
            evidence=decl_evidence,
        )

    op_evidence = tuple(o.evidence for o in ops)
    writers = {o.capability for o in ops if o.verb in WRITE_VERBS}
    readers = {o.capability for o in ops if o.verb in READ_VERBS}

    # Rule 2 -- sole writer.
    if len(writers) == 1:
        owner = next(iter(writers))
        return EntityOwnership(
            entity=entity,
            outcome=OwnershipOutcome.OWNED,
            owner=owner,
            verb=_write_verb(
                {o.verb for o in ops if o.capability == owner and o.verb in WRITE_VERBS}
            ),
            rule="sole_writer",
            claimants=tuple(sorted(writers | readers)),
            evidence=op_evidence,
        )
    if len(writers) > 1:
        return EntityOwnership(
            entity=entity,
            outcome=OwnershipOutcome.CONFLICT,
            rule="tied_writers",
            claimants=tuple(sorted(writers | readers)),
            evidence=op_evidence,
        )

    # Rule 3 -- sole reader.
    if len(readers) == 1:
        return EntityOwnership(
            entity=entity,
            outcome=OwnershipOutcome.OWNED,
            owner=next(iter(readers)),
            verb=OwnershipVerb.READS,
            rule="sole_reader",
            claimants=tuple(sorted(readers)),
            evidence=op_evidence,
        )
    if len(readers) > 1:
        return EntityOwnership(
            entity=entity,
            outcome=OwnershipOutcome.CONFLICT,
            rule="tied_readers",
            claimants=tuple(sorted(readers)),
            evidence=op_evidence,
        )

    # Rules 4/5 -- something touched it, but nothing readable said which way.
    undirected = {o.capability for o in ops if o.verb not in DIRECTED_VERBS}
    if undirected:
        return EntityOwnership(
            entity=entity,
            outcome=OwnershipOutcome.UNDIRECTED,
            rule="undirected_only",
            claimants=tuple(sorted(undirected)),
            evidence=op_evidence,
        )
    return EntityOwnership(
        entity=entity,
        outcome=OwnershipOutcome.UNCLAIMED,
        rule="no_claimant",
        evidence=decl_evidence,
    )


def assign(
    declarations: Sequence[EntityDeclaration],
    member_paths: Mapping[str, Sequence[str]],
    operations: Sequence[L2Operation],
    *,
    schema_collected: Measurement,
    contract_collected: Measurement,
) -> OwnershipReport:
    """Declarations + capability member paths + operations, in; one ownership
    row per distinct entity key, out.

    Fail closed on EITHER upstream (D9). Without S2 nothing declares, so every
    entity falls to the access fallback; without S3 nothing accesses, so every
    entity falls to declaration. Both produce a systematically different answer
    in the IDENTICAL shape, which a caller cannot tell from a healthy one.
    """
    if schema_collected.state is not CollectionState.MEASURED:
        return _empty(f"S2 did not collect: {schema_collected.reason}")
    if contract_collected.state is not CollectionState.MEASURED:
        return _empty(f"S3 did not collect: {contract_collected.reason}")

    owner_of: dict[str, set[str]] = {}
    for bc_id, paths in member_paths.items():
        for path in paths:
            owner_of.setdefault(path, set()).add(bc_id)

    grouped: dict[str, list[EntityDeclaration]] = {}
    for decl in sorted(declarations, key=lambda d: (d.path, d.line, d.name)):
        grouped.setdefault(_key(decl.name), []).append(decl)

    rows: list[EntityOwnership] = []
    for entity in sorted(grouped):
        decls = grouped[entity]
        declarers = {bc for d in decls for bc in owner_of.get(d.path, ())}
        ops = sorted((o for o in operations if o.object == entity), key=lambda o: o.op_id)
        rows.append(_resolve(entity, decls, declarers, ops))

    return OwnershipReport(
        entities=tuple(rows),
        counts={o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome},
        collected=Measurement.measured(float(len(rows))),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_ownership.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Run the whole suite**

Run: `pytest`
Expected: PASS — no regressions in scan, discover, or capability.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/assessment/discover/ownership.py tests/test_discover_ownership.py
git commit -m "feat(discover): assign() -- declaration, then writes, then reads (E-47c D7/D8)"
```

---

### Task 6: Roadmap deltas

The spec's "Roadmap deltas" table. E-47c closes the E-47 group, so several §§1–4 rows change with it.

**Files:**
- Modify: `ROADMAP.md:1011-1012` (E-47c), `:226` (FR-913), `:138` (FR-102), `:117` (§1 stage 2), `:270` (NFR-9), `:271` (NFR-10), `:292` (SC-8), `:6` (Last verified)

**Interfaces:**
- Consumes: Tasks 1–5 landed and green.
- Produces: nothing consumed by code.

- [ ] **Step 1: Verify the whole suite is green before claiming anything**

Run: `pytest`
Expected: PASS. Record the summary line — the roadmap's "Last verified" cell cites it, and a claim written before the run is the defect this project's tracker exists to avoid.

- [ ] **Step 2: Apply the deltas**

| Line | Change |
|---|---|
| `:1011` E-47c | `[ ]` → `[x]`; append "**Landed 2026-08-14.** Pure and unwired (D1): E-48 calls `decompose()` and `assign()`. Decisions worth carrying: operations are one-per-contract-member (D3) so each resolves to a byte range; `OperationVerb` and `OwnershipVerb` stay separate and **`TRACKS` is not emitted** (D6) because it has no deterministic trigger; ownership is declaration → writes → reads with ties surfaced (D7); and `CONFLICT`/`UNDIRECTED`/`UNCLAIMED` are three outcomes (D8) so a CLI-written table never reads as untouched. Spec `docs/superpowers/specs/2026-08-14-e47c-l2-operations-and-entity-ownership-design.md`, plan `docs/superpowers/plans/2026-08-14-e47c-l2-operations-and-entity-ownership.md`." |
| `:226` FR-913 | `[ ]` ⚠️ → `[x]`; note all four clauses closed, L2 + ownership landed 2026-08-14, still unwired pending E-48 |
| `:138` FR-102 | Note E-47a/b/c are all complete; the remaining half is intake classification + brownfield delta, no longer E-47 |
| `:117` §1 stage 2 | Append "**E-47c (2026-08-14):** L2 operations and entity ownership land; the E-47 group is closed and FR-102's remainder is classify + delta." |
| `:270` NFR-9 | Append "**E-47c (2026-08-14)** adds no execution of repository code: every input is a parameter, as E-47b." |
| `:271` NFR-10 | Append "**E-47c (2026-08-14):** two more pure modules (`discover/operations.py`, `discover/ownership.py`) carry their own byte-identical-across-input-order assertions." |
| `:292` SC-8 | Blocker narrows: E-47a/b/c are done; what remains is a corpus of readiness-passing repos |
| `:6` Last verified | Prepend "2026-08-14 (E-47c against `src/sdlc/assessment/discover/` + `src/sdlc/assessment/scan/naming.py` + unit suite green); " |

Also add a line to E-46's entry noting `route_object`/`PATH_PREFIXES` moved into `naming.py` for E-47c's second consumer, moving the memo keys of all six `_NAMING` signals (S1, S2, S3, S4, S5, SS4) once (D10).

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs: record E-47c -- L2 operations and entity ownership landed, E-47 group closed"
```

---

## Self-Review

**Spec coverage.** D1 (unwired) — no task touches `_discover`, asserted by omission and stated in Task 6's note. D2 (placement, `EntityDeclaration`) — Tasks 4, 5. D3 (grain) — Tasks 2, 3. D4 (`CONTRACT_KINDS`) — Task 2. D5 (`op_id`) — Tasks 2, 3. D6 (two taxonomies, no `TRACKS`) — Tasks 2, 4. D7 (precedence) — Tasks 4, 5. D8 (three outcomes) — Tasks 4, 5. D9 (fail closed) — Tasks 2–5. D10 (promotion) — Task 1. D11 (no `CheckResult`) — satisfied by omission; nothing in any task imports `CheckResult`. All nine Testing items map to tests in Tasks 1, 3, 5.

**Type consistency.** `decompose(members, *, contract_collected)` and `assign(declarations, member_paths, operations, *, schema_collected, contract_collected)` are used identically in their own tests and in Task 5's imports. `L2Operation` field names (`op_id`, `capability`, `verb`, `name`, `object`, `binding`, `kind`, `rule`, `evidence`) are the same in Tasks 2, 3 and 5. `EvidenceRef` takes `lines: str` (not `line: int`) throughout — that is scan's existing contract, so operation line numbers are stringified at construction.

**One deviation from the spec, deliberate.** The spec's "The two functions" says route-shaped kinds go through `route_object`; the plan names that set explicitly as `ROUTE_SHAPED_KINDS = {HTTP_ROUTE, FRONTEND_ROUTE}` in `models.py` rather than inlining the check, so the two consumers (`_object` and any future one) cannot disagree. Same rule, one home.
