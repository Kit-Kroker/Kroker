# Scan Phase — Plan 1 of 3: Contracts, Registry, Seam and Inherited Halves

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land E-46's contracts, signal registry, memoized activity seam and the five inherited signal halves, so `AssessmentWorkflow` reports a real thirteen-row `ScanResult` and `terminal_status` flips `admitted:no-phases-implemented` → `assessed:partial`.

**Architecture:** A new pure `src/sdlc/assessment/scan/` subpackage holds contracts, a `SCAN_SIGNALS` registry and the `RepoTriage` read-through. Eleven signals get one Temporal activity each — shipped in this plan as stubs reporting `not_collected` naming the plan that owes them, exactly as E-45 shipped six stub phase bodies. The two remaining signals (S5's merge, SS2's pure inheritance) are pure derivations that run in workflow code.

**Tech Stack:** Python 3.12, Pydantic v2, Temporal (`temporalio`), pytest.

## Global Constraints

- **Purity.** Every module under `assessment/scan/` may import Pydantic, `..measurement`, `..triage.models` and `..toolchain.adapters` **only**. Never `sdlc.models`, `sdlc.activities` or `temporalio`. This mirrors the docstring contract in `triage/models.py`, `capability/models.py` and `assessment/models.py`: a dependency there would appear as a reviewable import.
- **FR-915.** A value that was never measured must not be representable as a measured value. Never `Measurement.measured(0.0)` for something that did not run.
- **Determinism (NFR-10).** Iterate `SCAN_ORDER`, never a bare `set` or `dict`. Sort every list before it enters an artifact.
- **No repository code executes.** Every signal is a blob read. The `init` phase's build probe stays the only place the assessed repo runs.
- **Derived, never assigned.** `ScanCandidate.confidence`, a signal's fan-out wave, and `Assessment.terminal_status` are all computed from their inputs and validated at the type.
- **Spec:** `docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md`. Decision ids (D1–D14) below refer to its §2.
- **Test commands:** `pytest tests/<file> -v` for unit; `pytest -m temporal tests/<file> -v` for workflow e2e. Default `pytest` runs unit only.

---

### Task 1: Signal identity enums and `SCAN_ORDER`

**Files:**
- Create: `src/sdlc/assessment/scan/__init__.py` (empty)
- Create: `src/sdlc/assessment/scan/models.py`
- Test: `tests/test_scan_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ScanSignalId` (13 members `S1`–`S5`, `SS1`–`SS4`, `QS1`–`QS4`), `SCAN_ORDER: tuple[ScanSignalId, ...]`, `SignalFamily` (`CAPABILITY`/`SECURITY`/`QA`), `SignalSource` (`COMPUTED`/`INHERITED`/`EXTENDED`), `Confidence` (`HIGH`/`MEDIUM`/`LOW`), `confidence_from(signals) -> Confidence`, `family_of(signal_id) -> SignalFamily`.

- [ ] **Step 1: Write the failing test**

```python
"""E-46 contracts. Pure -- no Temporal, no filesystem."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan.models import (
    SCAN_ORDER,
    Confidence,
    ScanSignalId,
    SignalFamily,
    SignalSource,
    confidence_from,
    family_of,
)


def test_thirteen_signals_in_declaration_order():
    assert len(SCAN_ORDER) == 13
    assert SCAN_ORDER == tuple(ScanSignalId)
    assert [s.value for s in SCAN_ORDER[:5]] == ["S1", "S2", "S3", "S4", "S5"]
    assert SCAN_ORDER[-1] is ScanSignalId.QS4


def test_family_is_derived_from_the_id_prefix():
    assert family_of(ScanSignalId.S3) is SignalFamily.CAPABILITY
    assert family_of(ScanSignalId.SS1) is SignalFamily.SECURITY
    assert family_of(ScanSignalId.QS2) is SignalFamily.QA


@pytest.mark.parametrize(
    "signals,expected",
    [
        ([ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3], Confidence.HIGH),
        ([ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3, ScanSignalId.S4], Confidence.HIGH),
        ([ScanSignalId.S1, ScanSignalId.S3], Confidence.MEDIUM),
        ([ScanSignalId.S1], Confidence.LOW),
    ],
)
def test_confidence_counts_distinct_signals(signals, expected):
    assert confidence_from(signals) is expected


def test_confidence_counts_signals_not_candidates():
    """FR-912: never the depth of one source. Two S1 groupings do not
    corroborate each other."""
    assert confidence_from([ScanSignalId.S1, ScanSignalId.S1, ScanSignalId.S1]) is Confidence.LOW


def test_confidence_from_nothing_is_low_not_an_error():
    """A candidate with no sources cannot be constructed (Task 3 enforces it);
    the scorer stays total so it is never the thing that raises."""
    assert confidence_from([]) is Confidence.LOW


def test_source_has_exactly_three_states():
    assert {s.value for s in SignalSource} == {"computed", "inherited", "extended"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.scan'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/assessment/scan/__init__.py` empty, then `src/sdlc/assessment/scan/models.py`:

```python
"""FR-912 (E-46): the scan phase artifact and its contracts.

Pure by design -- Pydantic, measurement.py and triage/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
triage/models.py, capability/models.py and assessment/models.py must not: a
dependency here would appear as a reviewable import.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum


class ScanSignalId(str, Enum):
    """BrownKit's scan signal ids, kept verbatim: they are the traceable
    contract with the source methodology, and renaming them would make every
    cross-reference to `scan.md` a translation step.

    Declaration order IS the order (see SCAN_ORDER) -- a hand-written tuple
    beside the enum is a second registry, exactly as PHASE_ORDER records.
    """

    S1 = "S1"  # package structure
    S2 = "S2"  # database schema clusters
    S3 = "S3"  # backend entry points
    S4 = "S4"  # frontend entry points
    S5 = "S5"  # cross-source merge and confidence
    SS1 = "SS1"  # static security
    SS2 = "SS2"  # dependency vulnerabilities
    SS3 = "SS3"  # configuration and infrastructure
    SS4 = "SS4"  # data sensitivity
    QS1 = "QS1"  # test inventory
    QS2 = "QS2"  # coverage
    QS3 = "QS3"  # testability
    QS4 = "QS4"  # environment and CI


SCAN_ORDER: tuple[ScanSignalId, ...] = tuple(ScanSignalId)


class SignalFamily(str, Enum):
    CAPABILITY = "capability"
    SECURITY = "security"
    QA = "qa"


def family_of(signal_id: ScanSignalId) -> SignalFamily:
    """Derived from the id prefix rather than declared per signal: the prefix
    IS the family in BrownKit's scheme, and a declaration could disagree."""
    if signal_id.value.startswith("QS"):
        return SignalFamily.QA
    if signal_id.value.startswith("SS"):
        return SignalFamily.SECURITY
    return SignalFamily.CAPABILITY


class SignalSource(str, Enum):
    """D2. INHERITED is narrow: the fact is already recorded in an artifact
    this assessment holds (Assessment.triage). Reusing a parser is code reuse,
    not inheritance."""

    COMPUTED = "computed"
    INHERITED = "inherited"
    EXTENDED = "extended"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def confidence_from(signals: Iterable[ScanSignalId]) -> Confidence:
    """S5's rule (D8): 3+ distinct source SIGNALS high, 2 medium, else low.

    Distinct signals, not distinct candidates -- two S1 groupings are one
    source's opinion twice, which is FR-912's "never the depth of one source".
    Total by construction so it is never the thing that raises; a candidate
    with no sources is refused by ScanCandidate instead.
    """
    n = len(set(signals))
    if n >= 3:
        return Confidence.HIGH
    if n == 2:
        return Confidence.MEDIUM
    return Confidence.LOW
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_models.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/__init__.py src/sdlc/assessment/scan/models.py tests/test_scan_models.py
git commit -m "feat(scan): signal ids, families and the derived confidence rule (E-46)"
```

---

### Task 2: Candidate members, evidence refs and `SourceCandidate`

**Files:**
- Modify: `src/sdlc/assessment/scan/models.py` (append)
- Test: `tests/test_scan_source_candidate.py`

**Interfaces:**
- Consumes: `ScanSignalId`, `Confidence` (Task 1).
- Produces: `MemberKind` (12 members), `CandidateMember`, `EvidenceRef`, `SourceCandidate`, `signal_of(local_id) -> ScanSignalId`.

- [ ] **Step 1: Write the failing test**

```python
"""S1-S4 emit one shape whose members are typed by kind (D13)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CandidateMember,
    Confidence,
    EvidenceRef,
    MemberKind,
    ScanSignalId,
    SourceCandidate,
    signal_of,
)
from sdlc.measurement import Measurement


def _member() -> CandidateMember:
    return CandidateMember(
        kind=MemberKind.HTTP_ROUTE, value="POST /api/payments", path="src/api/payments.py", line=42
    )


def _candidate(
    local_id: str = "S3-payments", signal: ScanSignalId = ScanSignalId.S3
) -> SourceCandidate:
    return SourceCandidate(
        signal=signal,
        local_id=local_id,
        name="Payments",
        rule="s3_http_route",
        detail="Three routes under /api/payments.",
        confidence_contribution=Confidence.MEDIUM,
        members=[_member()],
        evidence=[EvidenceRef(path="src/api/payments.py", lines="42-78")],
    )


def test_member_kinds_span_the_four_identity_tiers():
    """D13: the value set must be able to populate every
    CapabilityFingerprint tier, so E-48's mapping can be total."""
    kinds = {k.value for k in MemberKind}
    assert {
        "http_route",
        "cli_command",
        "db_table",
        "queue_topic",
        "grpc_method",
    } <= kinds  # contract
    assert {"test_name", "entity_name"} <= kinds  # behavioral
    assert {"exported_symbol"} <= kinds  # structural
    assert {"package_path", "file_path"} <= kinds  # locational


def test_local_id_must_be_prefixed_by_its_signal():
    """signal_of() parses the prefix, so the two cannot disagree."""
    c = _candidate()
    assert signal_of(c.local_id) is ScanSignalId.S3


def test_local_id_not_matching_its_signal_is_refused():
    with pytest.raises(ValidationError, match="local_id"):
        _candidate(local_id="S1-payments", signal=ScanSignalId.S3)


def test_signal_of_refuses_a_malformed_id():
    with pytest.raises(ValueError, match="malformed"):
        signal_of("payments")


def test_members_and_evidence_are_sorted_canonically():
    """NFR-10: discovery order must not change the artifact."""
    a = CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /b")
    b = CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /a")
    c = SourceCandidate(
        signal=ScanSignalId.S3,
        local_id="S3-x",
        name="X",
        rule="r",
        detail="d",
        confidence_contribution=Confidence.LOW,
        members=[a, b],
        evidence=[EvidenceRef(path="z.py"), EvidenceRef(path="a.py")],
    )
    assert [m.value for m in c.members] == ["GET /a", "GET /b"]
    assert [e.path for e in c.evidence] == ["a.py", "z.py"]


def test_metrics_are_measurements_so_an_uncomputable_count_is_not_zero():
    c = _candidate()
    c2 = c.model_copy(
        update={
            "metrics": {
                "file_count": Measurement.measured(12.0),
                "loc_estimate": Measurement.not_collected("no parser for this language"),
            }
        }
    )
    assert c2.metrics["loc_estimate"].value is None


def test_a_candidate_with_no_members_is_refused():
    """A candidate is a claim that something is there; an empty one is a
    silently-empty tier, which is exactly what D5 forbids."""
    with pytest.raises(ValidationError, match="at least one member"):
        SourceCandidate(
            signal=ScanSignalId.S1,
            local_id="S1-x",
            name="X",
            rule="r",
            detail="d",
            confidence_contribution=Confidence.LOW,
            members=[],
            evidence=[],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_source_candidate.py -v`
Expected: FAIL — `ImportError: cannot import name 'MemberKind'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/assessment/scan/models.py`:

```python
from pydantic import BaseModel, Field, model_validator

from ..measurement import Measurement


class MemberKind(str, Enum):
    """What a candidate is made of. The value set is chosen so every
    CapabilityFingerprint tier has members that can populate it, making
    E-48's MemberKind -> SignalTier mapping total (D13).

    That mapping is deliberately NOT here: E-47a's pipeline is
    scan -> discover proposes boundaries -> fingerprint + resolve, so siting a
    capability-identity fact in the scan phase would put it two stages early.
    """

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


def signal_of(local_id: str) -> ScanSignalId:
    """The signal that minted a local id. Parsed rather than stored beside it,
    so the id and its owner cannot disagree."""
    head, _, rest = local_id.partition("-")
    if not rest:
        raise ValueError(f"malformed local_id {local_id!r} -- expected '<signal>-<slug>'")
    try:
        return ScanSignalId(head)
    except ValueError:
        raise ValueError(
            f"malformed local_id {local_id!r} -- {head!r} is not a signal id"
        ) from None


class CandidateMember(BaseModel):
    kind: MemberKind
    value: str  # "POST /api/payments", "orders"
    path: str = ""
    line: int | None = None

    def sort_key(self) -> tuple[str, str, str, int]:
        return (self.kind.value, self.value, self.path, self.line or 0)


class EvidenceRef(BaseModel):
    path: str
    lines: str = ""  # "42-78"; "" means whole file


class SourceCandidate(BaseModel):
    """One candidate as seen by ONE source signal (S1-S4). Not a capability:
    /discover (E-48) decides that, and E-47a assigns the BC-NNN id.

    (rule, detail) is TriageFinding's pair, carried for the same reason -- the
    rule that produced a confidence rating is what makes it auditable. S1's
    domain/generic/layer classification is expressed as the rule that fired
    (s1_domain_term, s1_generic_name, s1_layer_name) rather than a boolean,
    because E-48's "delivery channels and deployment boundaries are not
    capabilities" guardrail needs the distinction, not only its outcome.
    """

    signal: ScanSignalId
    local_id: str  # "S3-payments"
    name: str
    rule: str
    detail: str
    confidence_contribution: Confidence
    members: list[CandidateMember]
    evidence: list[EvidenceRef] = Field(default_factory=list)
    metrics: dict[str, Measurement] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _local_id_declares_its_signal(self) -> "SourceCandidate":
        if signal_of(self.local_id) is not self.signal:
            raise ValueError(
                f"local_id {self.local_id!r} is not prefixed by its signal "
                f"{self.signal.value!r} -- signal_of() must agree with the "
                f"field, or a merged candidate miscounts its sources (D8)"
            )
        return self

    @model_validator(mode="after")
    def _has_members(self) -> "SourceCandidate":
        if not self.members:
            raise ValueError(
                "a SourceCandidate needs at least one member -- an empty "
                "candidate is a silently-empty extraction, which is the "
                "conflation D5 forbids"
            )
        return self

    @model_validator(mode="after")
    def _canonicalize(self) -> "SourceCandidate":
        # NFR-10: discovery order must not change the artifact.
        self.members = sorted(set(self.members), key=CandidateMember.sort_key)
        self.evidence = sorted(set(self.evidence), key=lambda e: (e.path, e.lines))
        return self
```

`CandidateMember` and `EvidenceRef` need to be hashable for the `set()` dedupe. Add to both:

```python
    model_config = {"frozen": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_source_candidate.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/models.py tests/test_scan_source_candidate.py
git commit -m "feat(scan): SourceCandidate with kind-typed members (E-46)"
```

---

### Task 3: `ScanCandidate` with derived confidence

**Files:**
- Modify: `src/sdlc/assessment/scan/models.py` (append)
- Test: `tests/test_scan_candidate.py`

**Interfaces:**
- Consumes: `confidence_from`, `signal_of`, `CandidateMember` (Tasks 1–2).
- Produces: `ScanCandidate`.

- [ ] **Step 1: Write the failing test**

```python
"""D8: confidence is derived from distinct source signals, never assigned."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CandidateMember,
    Confidence,
    MemberKind,
    ScanCandidate,
)


def _m(value: str) -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value)


def _candidate(sources: list[str], confidence: Confidence) -> ScanCandidate:
    return ScanCandidate(
        candidate_id="C-01",
        name="Payments",
        sources=sources,
        confidence=confidence,
        members=[_m("GET /pay")],
    )


def test_three_distinct_signals_is_high():
    c = _candidate(["S1-pay", "S2-pay", "S3-pay"], Confidence.HIGH)
    assert c.confidence is Confidence.HIGH


def test_two_distinct_signals_is_medium():
    assert _candidate(["S1-pay", "S3-pay"], Confidence.MEDIUM).confidence is Confidence.MEDIUM


def test_two_candidates_from_one_signal_is_low():
    """The load-bearing case: S1 seeing two groupings is one opinion."""
    assert _candidate(["S1-pay", "S1-billing"], Confidence.LOW).confidence is Confidence.LOW


def test_a_disagreeing_confidence_does_not_construct():
    """Derived, never assigned -- a deserialized payload cannot lie about its
    own corroboration, the way Assessment.terminal_status cannot (E-45 D6)."""
    with pytest.raises(ValidationError, match="derived"):
        _candidate(["S1-pay"], Confidence.HIGH)


def test_no_sources_is_refused():
    with pytest.raises(ValidationError, match="at least one source"):
        _candidate([], Confidence.LOW)


def test_a_malformed_source_id_is_refused():
    with pytest.raises(ValidationError, match="malformed"):
        _candidate(["payments"], Confidence.LOW)


def test_candidate_id_is_not_a_bc_id():
    """C-NN is assessment-local. BC-NNN is E-47a's surrogate key, allocated
    after discover; minting one here would create identity two stages early."""
    c = _candidate(["S1-pay", "S2-pay"], Confidence.MEDIUM)
    assert c.candidate_id.startswith("C-")
    assert not c.candidate_id.startswith("BC-")


def test_possible_duplicate_defaults_empty_and_is_sorted():
    c = ScanCandidate(
        candidate_id="C-02",
        name="Refunds",
        sources=["S3-refunds"],
        confidence=Confidence.LOW,
        members=[_m("GET /refund")],
        possible_duplicate_of=["C-09", "C-01"],
    )
    assert c.possible_duplicate_of == ["C-01", "C-09"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_candidate.py -v`
Expected: FAIL — `ImportError: cannot import name 'ScanCandidate'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/assessment/scan/models.py`:

```python
class ScanCandidate(BaseModel):
    """S5's merge: one distinct candidate corroborated across sources.

    candidate_id is local to ONE assessment. BC-NNN is E-47a's surrogate key,
    allocated after discover -- the two look alike, and conflating them would
    mint capability identity in the wrong phase.
    """

    candidate_id: str  # "C-01"
    name: str
    sources: list[str]  # SourceCandidate.local_id values
    confidence: Confidence  # DERIVED (D8)
    members: list[CandidateMember]
    possible_duplicate_of: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_sources(self) -> "ScanCandidate":
        if not self.sources:
            raise ValueError(
                "a ScanCandidate needs at least one source -- it is a merge "
                "of source candidates, and a merge of nothing has no evidence"
            )
        return self

    @model_validator(mode="after")
    def _confidence_is_derived(self) -> "ScanCandidate":
        expected = confidence_from(signal_of(s) for s in self.sources)
        if self.confidence is not expected:
            raise ValueError(
                f"confidence {self.confidence.value!r} does not match the "
                f"derived {expected.value!r} for sources {self.sources} -- "
                f"confidence is derived from the count of DISTINCT source "
                f"signals, never assigned (D8)"
            )
        return self

    @model_validator(mode="after")
    def _canonicalize(self) -> "ScanCandidate":
        self.sources = sorted(set(self.sources))
        self.members = sorted(set(self.members), key=CandidateMember.sort_key)
        self.possible_duplicate_of = sorted(set(self.possible_duplicate_of))
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_candidate.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/models.py tests/test_scan_candidate.py
git commit -m "feat(scan): ScanCandidate confidence derived from distinct sources (E-46 D8)"
```

---

### Task 4: The two separately-typed payloads

**Files:**
- Modify: `src/sdlc/assessment/scan/models.py` (append)
- Test: `tests/test_scan_payloads.py`

**Interfaces:**
- Consumes: `Confidence`, `EvidenceRef` (Tasks 1–2).
- Produces: `Sensitivity`, `SensitivityRecord`, `TestabilityFinding`, `testability_identity(f) -> str`.

- [ ] **Step 1: Write the failing test**

```python
"""SS4 and QS3 payloads. Typed apart from SourceCandidate because their
shapes share nothing with it (E-45's no-untyped-bag rule, applied within
scan)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    Confidence,
    EvidenceRef,
    Sensitivity,
    SensitivityRecord,
    TestabilityFinding,
    testability_identity,
)


def test_sensitivity_record_carries_its_accessors_by_local_id():
    r = SensitivityRecord(
        classification=Sensitivity.PII,
        entity="customers",
        origin="table",
        fields=["email", "phone"],
        accessed_by=["S3-customers"],
        evidence=[EvidenceRef(path="migrations/0002_customers.sql")],
        rule="ss4_pii_field_name",
        confidence=Confidence.MEDIUM,
    )
    assert r.accessed_by == ["S3-customers"]
    assert r.fields == ["email", "phone"]


def test_empty_accessed_by_is_allowed_and_means_unknown_not_none():
    """When S3 reported not_collected, SS4 has no accessors to cite. The
    owing category's reason says so; this field must not be read as
    'no entry point touches PII' (D5, section 5)."""
    r = SensitivityRecord(
        classification=Sensitivity.FINANCIAL,
        entity="Payment",
        origin="model",
        fields=["card_last4"],
        evidence=[],
        rule="ss4_financial_field_name",
        confidence=Confidence.LOW,
    )
    assert r.accessed_by == []


def test_testability_severity_is_brownkit_three_valued():
    f = TestabilityFinding(
        severity="blocks",
        pattern="static-clock-access",
        detail="DateTime.Now read inside a branch.",
        recommended_seam="Inject a clock",
        path="src/sched.py",
        line=142,
    )
    assert f.severity == "blocks"
    with pytest.raises(ValidationError):
        f.model_copy(update={"severity": "critical"}).model_validate(
            f.model_dump() | {"severity": "critical"}
        )


def test_testability_identity_is_delta_stable_and_ignores_line():
    """E-44 D3: a fix landing above a finding shifts its line, and an identity
    keyed on line would report a phantom resolved+new pair."""
    a = TestabilityFinding(
        severity="impedes",
        pattern="global-state",
        detail="d",
        recommended_seam="s",
        path="src/a.py",
        line=10,
        key="CACHE",
    )
    b = a.model_copy(update={"line": 99})
    assert testability_identity(a) == testability_identity(b)
    assert "src/a.py" in testability_identity(a)
    assert "CACHE" in testability_identity(a)


def test_two_patterns_on_one_path_need_distinct_keys():
    a = TestabilityFinding(
        severity="smell", pattern="p", detail="d", recommended_seam="s", path="src/a.py", key="X"
    )
    b = a.model_copy(update={"key": "Y"})
    assert testability_identity(a) != testability_identity(b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_payloads.py -v`
Expected: FAIL — `ImportError: cannot import name 'Sensitivity'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/assessment/scan/models.py` (add `from typing import Literal` to the imports):

```python
class Sensitivity(str, Enum):
    PII = "pii"
    FINANCIAL = "financial"
    AUTHENTICATION = "authentication"
    HEALTH = "health"
    REGULATORY = "regulatory"


class SensitivityRecord(BaseModel):
    """SS4. Classifies an entity, not a file: the question E-49 asks is which
    capability handles regulated data."""

    classification: Sensitivity
    entity: str
    origin: Literal["table", "model", "dto"]
    fields: list[str]
    # S3 entry points reading or writing the entity, by local_id. Empty when
    # S3 reported not_collected -- the owing category's reason states that,
    # so this must never be read as "no entry point touches PII".
    accessed_by: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    rule: str
    confidence: Confidence


class TestabilityFinding(BaseModel):
    """QS3. Carries TriageFinding's `evidence` and `key` semantics because a
    testability blocker is a per-capability finding E-49 scores and E-53 may
    seed a fix run from, so it needs the same delta-stable identity.

    `severity` is BrownKit's three-valued scale, not TriageFinding's four:
    blocks/impedes/smell answers a different question than
    critical/high/medium/low, and collapsing them loses what FR-916 needs.
    """

    severity: Literal["blocks", "impedes", "smell"]
    pattern: str  # "static-clock-access"
    detail: str
    recommended_seam: str
    path: str
    line: int | None = None
    evidence: str = ""  # verbatim quote from path@commit_sha
    key: str = ""  # rule-scoped discriminator (E-44 D3)


def testability_identity(f: TestabilityFinding) -> str:
    """The identity a delta matches on. Deliberately excludes `line`, exactly
    as triage's finding_identity does."""
    return f"QS3:{f.pattern}:{f.path}:{f.key}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_payloads.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/models.py tests/test_scan_payloads.py
git commit -m "feat(scan): SensitivityRecord and TestabilityFinding payloads (E-46)"
```

---

### Task 5: Category keys, `InheritedProducer` and `ScanSignalResult`

**Files:**
- Modify: `src/sdlc/assessment/scan/models.py` (append)
- Test: `tests/test_scan_signal_result.py`

**Interfaces:**
- Consumes: `ScanSignalId`, `SignalFamily`, `SignalSource` (Task 1).
- Produces: the `C_*` category-key constants, `CATEGORIES: dict[ScanSignalId, tuple[str, ...]]`, `InheritedProducer`, `ScanSignalResult`.

- [ ] **Step 1: Write the failing test**

```python
"""D2/D3: an inherited row cites findings and copies none, and coverage is
tracked per category because a row cannot be half-measured."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    C_CREDENTIAL_STORAGE,
    C_INPUT_VALIDATION,
    CATEGORIES,
    InheritedProducer,
    ScanSignalId,
    ScanSignalResult,
    SignalFamily,
    SignalSource,
)
from sdlc.measurement import CollectionState, Measurement


def _producer() -> InheritedProducer:
    return InheritedProducer(
        producer="triage:secrets", version=2, finding_ids=["secrets:aws_key:.env:abc123"]
    )


def _row(source: SignalSource, **kw) -> ScanSignalResult:
    base = dict(
        signal=ScanSignalId.SS1,
        family=SignalFamily.SECURITY,
        version=1,
        source=source,
        collected=Measurement.measured(1.0),
        categories={k: Measurement.not_collected("plan 3") for k in CATEGORIES[ScanSignalId.SS1]},
    )
    return ScanSignalResult(**(base | kw))


def test_every_signal_declares_its_categories():
    assert set(CATEGORIES) == set(ScanSignalId)
    assert C_CREDENTIAL_STORAGE in CATEGORIES[ScanSignalId.SS1]
    assert C_INPUT_VALIDATION in CATEGORIES[ScanSignalId.SS1]


def test_computed_must_not_carry_a_producer():
    with pytest.raises(ValidationError, match="producer"):
        _row(SignalSource.COMPUTED, producer=_producer())


def test_inherited_and_extended_require_a_producer():
    for source in (SignalSource.INHERITED, SignalSource.EXTENDED):
        with pytest.raises(ValidationError, match="producer"):
            _row(source)


def test_extended_with_a_producer_constructs():
    row = _row(SignalSource.EXTENDED, producer=_producer())
    assert row.producer.producer == "triage:secrets"
    assert row.producer.version == 2


def test_a_missing_declared_category_is_refused():
    """The row-level analogue of compute_readiness filling an unreported
    dimension rather than leaving it absent."""
    with pytest.raises(ValidationError, match="categor"):
        _row(SignalSource.COMPUTED, categories={})


def test_an_undeclared_category_is_refused():
    cats = {k: Measurement.not_collected("x") for k in CATEGORIES[ScanSignalId.SS1]}
    with pytest.raises(ValidationError, match="undeclared"):
        _row(SignalSource.COMPUTED, categories=cats | {"invented": Measurement.measured(1.0)})


def test_producer_version_is_pinned_so_a_triage_bump_is_visible():
    p = _producer()
    assert p.version == 2, (
        "the producing signal's version is recorded, so a triage version bump "
        "changes the assessment visibly rather than silently"
    )


def test_not_collected_row_may_still_declare_its_categories():
    row = _row(SignalSource.COMPUTED, collected=Measurement.not_collected("scan stub (plan 2)"))
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert set(row.categories) == set(CATEGORIES[ScanSignalId.SS1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_signal_result.py -v`
Expected: FAIL — `ImportError: cannot import name 'C_CREDENTIAL_STORAGE'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/assessment/scan/models.py`:

```python
# --- Category keys (D3) -------------------------------------------------
# A signal's coverage is tracked per category because ScanSignalResult
# carries ONE `collected` and a signal like SS1 genuinely has an inherited
# half and a computed half. Declared here, beside the artifact, so the
# registry and the row cannot disagree about what a signal owes.

C_PACKAGES = "packages"  # S1
C_SCHEMA = "schema_clusters"  # S2
C_BACKEND_ENTRY = "backend_entry_points"  # S3
C_FRONTEND_ENTRY = "frontend_entry_points"  # S4
C_MERGE = "candidate_merge"  # S5

C_CREDENTIAL_STORAGE = "credential_storage"  # SS1, inherited
C_AUTHN_AUTHZ = "authn_authz"  # SS1, inherited
C_TLS = "tls_enforcement"  # SS1, computed
C_INPUT_VALIDATION = "input_validation"  # SS1, computed
C_DIRECT_DEPS = "direct_dependencies"  # SS2, inherited
C_FRAMEWORK_DEFAULTS = "framework_defaults"  # SS3, inherited
C_EXPOSED_PORTS = "exposed_ports"  # SS3, computed
C_ENV_DIVERGENCE = "env_divergence"  # SS3, computed
C_DB_SECURITY = "db_security"  # SS3, computed
C_LOG_MASKING = "log_masking"  # SS3, computed
C_DATA_SENSITIVITY = "data_sensitivity"  # SS4

C_TESTS_PRESENT = "tests_present"  # QS1, inherited
C_TEST_LEVELS = "test_levels"  # QS1, computed
C_TEST_MAPPING = "test_mapping"  # QS1, computed
C_COVERAGE = "coverage"  # QS2
C_TESTABILITY = "testability"  # QS3
C_CI_PRESENT = "ci_present"  # QS4, inherited
C_CI_STAGES = "ci_stages"  # QS4, computed
C_ENV_DRIFT = "env_drift"  # QS4, computed

CATEGORIES: dict[ScanSignalId, tuple[str, ...]] = {
    ScanSignalId.S1: (C_PACKAGES,),
    ScanSignalId.S2: (C_SCHEMA,),
    ScanSignalId.S3: (C_BACKEND_ENTRY,),
    ScanSignalId.S4: (C_FRONTEND_ENTRY,),
    ScanSignalId.S5: (C_MERGE,),
    ScanSignalId.SS1: (C_CREDENTIAL_STORAGE, C_AUTHN_AUTHZ, C_TLS, C_INPUT_VALIDATION),
    ScanSignalId.SS2: (C_DIRECT_DEPS,),
    ScanSignalId.SS3: (
        C_FRAMEWORK_DEFAULTS,
        C_EXPOSED_PORTS,
        C_ENV_DIVERGENCE,
        C_DB_SECURITY,
        C_LOG_MASKING,
    ),
    ScanSignalId.SS4: (C_DATA_SENSITIVITY,),
    ScanSignalId.QS1: (C_TESTS_PRESENT, C_TEST_LEVELS, C_TEST_MAPPING),
    ScanSignalId.QS2: (C_COVERAGE,),
    ScanSignalId.QS3: (C_TESTABILITY,),
    ScanSignalId.QS4: (C_CI_PRESENT, C_CI_STAGES, C_ENV_DRIFT),
}


class InheritedProducer(BaseModel):
    """D2. Which producer already recorded this fact, and which findings of
    its this row cites. Findings are cited, never copied: two copies in the
    FR-921 bundle, and a copy re-labelled with a scan signal id would break
    the finding_identity keying E-44's delta depends on.
    """

    producer: str  # "triage:secrets"
    version: int  # the producer's declared version, PINNED
    finding_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _canonicalize(self) -> "InheritedProducer":
        self.finding_ids = sorted(set(self.finding_ids))
        return self


class ScanSignalResult(BaseModel):
    """One signal's status row. The payload lives on ScanResult beside it,
    exactly as Readiness lives beside RepoTriage.signals."""

    signal: ScanSignalId
    family: SignalFamily
    version: int
    source: SignalSource
    collected: Measurement  # MEASURED value = record count
    categories: dict[str, Measurement] = Field(default_factory=dict)
    producer: InheritedProducer | None = None

    @model_validator(mode="after")
    def _producer_matches_source(self) -> "ScanSignalResult":
        if self.source is SignalSource.COMPUTED:
            if self.producer is not None:
                raise ValueError(
                    f"{self.signal.value}: source=computed carries a producer "
                    f"-- a signal this phase computed inherits nothing (D2)"
                )
        elif self.producer is None:
            raise ValueError(
                f"{self.signal.value}: source={self.source.value} requires a "
                f"producer -- an inherited fact must name what recorded it "
                f"(D2)"
            )
        return self

    @model_validator(mode="after")
    def _declares_every_category_it_owes(self) -> "ScanSignalResult":
        owed = set(CATEGORIES[self.signal])
        got = set(self.categories)
        if missing := owed - got:
            raise ValueError(
                f"{self.signal.value}: missing category/categories "
                f"{sorted(missing)} -- a signal reports every category it "
                f"owes, so an unreported one cannot pass as absent"
            )
        if undeclared := got - owed:
            raise ValueError(
                f"{self.signal.value}: undeclared category/categories "
                f"{sorted(undeclared)} -- CATEGORIES is the one declaration"
            )
        return self

    @model_validator(mode="after")
    def _family_matches_its_id(self) -> "ScanSignalResult":
        if self.family is not family_of(self.signal):
            raise ValueError(
                f"{self.signal.value}: family {self.family.value!r} contradicts the id prefix"
            )
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_signal_result.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/models.py tests/test_scan_signal_result.py
git commit -m "feat(scan): ScanSignalResult with per-category coverage and cited producers (E-46 D2/D3)"
```

---

### Task 6: `SignalOutput` and `ScanResult`

**Files:**
- Modify: `src/sdlc/assessment/scan/models.py` (append)
- Test: `tests/test_scan_result.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: `SignalOutput`, `ScanResult`.

- [ ] **Step 1: Write the failing test**

```python
"""The artifact: a completeness ledger plus typed payloads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CATEGORIES,
    CandidateMember,
    Confidence,
    MemberKind,
    SCAN_ORDER,
    ScanCandidate,
    ScanResult,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    family_of,
)
from sdlc.measurement import Measurement


def _row(sid: ScanSignalId, measured: bool = True) -> ScanSignalResult:
    val = Measurement.measured(0.0) if measured else Measurement.not_collected(f"{sid.value} stub")
    return ScanSignalResult(
        signal=sid,
        family=family_of(sid),
        version=1,
        source=SignalSource.COMPUTED,
        collected=val,
        categories={k: val for k in CATEGORIES[sid]},
    )


def _all_rows(measured: bool = True) -> list[ScanSignalResult]:
    return [_row(s, measured) for s in SCAN_ORDER]


def _candidate() -> ScanCandidate:
    return ScanCandidate(
        candidate_id="C-01",
        name="Payments",
        sources=["S1-pay", "S3-pay"],
        confidence=Confidence.MEDIUM,
        members=[CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /p")],
    )


def test_signals_must_be_the_whole_set_in_order():
    r = ScanResult(
        signals=_all_rows(), sources=[], candidates=[], data_sensitivity=[], testability=[]
    )
    assert [s.signal for s in r.signals] == list(SCAN_ORDER)


def test_a_missing_signal_is_refused():
    with pytest.raises(ValidationError, match="whole set"):
        ScanResult(
            signals=_all_rows()[:-1], sources=[], candidates=[], data_sensitivity=[], testability=[]
        )


def test_out_of_order_signals_are_refused():
    rows = _all_rows()
    rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(ValidationError, match="whole set"):
        ScanResult(signals=rows, sources=[], candidates=[], data_sensitivity=[], testability=[])


def test_a_not_measured_signal_carrying_a_payload_is_refused():
    """Mirrors SignalResult._not_collected_has_no_findings: partial output is
    UNKNOWN, and a signal that did not run has no records."""
    rows = _all_rows()
    rows[SCAN_ORDER.index(ScanSignalId.S5)] = _row(ScanSignalId.S5, measured=False)
    with pytest.raises(ValidationError, match="did not run"):
        ScanResult(
            signals=rows, sources=[], candidates=[_candidate()], data_sensitivity=[], testability=[]
        )


def test_a_measured_signal_may_carry_an_empty_payload():
    """MEASURED with zero records is a real finding: it ran and found none."""
    r = ScanResult(
        signals=_all_rows(), sources=[], candidates=[], data_sensitivity=[], testability=[]
    )
    assert r.candidates == []


def test_signal_output_bundles_the_row_with_its_payload():
    """D10: cached as a unit, so a hit cannot serve a MEASURED row with
    nothing behind it."""
    out = SignalOutput(row=_row(ScanSignalId.S3), sources=[])
    assert out.row.signal is ScanSignalId.S3
    assert out.sources == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_result.py -v`
Expected: FAIL — `ImportError: cannot import name 'SignalOutput'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/assessment/scan/models.py` (import `CollectionState` alongside `Measurement`):

```python
# Which ScanResult field each signal's payload lands in. Declared once so
# _unmeasured_carries_no_payload can check the right field per signal rather
# than a hardcoded pairing in the validator.
PAYLOAD_FIELD: dict[ScanSignalId, str] = {
    ScanSignalId.S1: "sources",
    ScanSignalId.S2: "sources",
    ScanSignalId.S3: "sources",
    ScanSignalId.S4: "sources",
    ScanSignalId.S5: "candidates",
    ScanSignalId.SS4: "data_sensitivity",
    ScanSignalId.QS3: "testability",
}


class SignalOutput(BaseModel):
    """One computed signal's whole output -- the row AND its payload, cached
    as a unit (D10). An activity returns this; the workflow folds in the
    inherited half (D7)."""

    row: ScanSignalResult
    sources: list[SourceCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)


class ScanResult(BaseModel):
    signals: list[ScanSignalResult]
    sources: list[SourceCandidate] = Field(default_factory=list)
    candidates: list[ScanCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _signals_are_the_whole_set(self) -> "ScanResult":
        got = tuple(s.signal for s in self.signals)
        if got != SCAN_ORDER:
            raise ValueError(
                f"signals must be the whole set in order -- expected "
                f"{[s.value for s in SCAN_ORDER]}, got "
                f"{[s.value for s in got]}"
            )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "ScanResult":
        by_id = {s.signal: s for s in self.signals}
        for signal_id, field_name in PAYLOAD_FIELD.items():
            row = by_id[signal_id]
            if row.collected.state is CollectionState.MEASURED:
                continue
            # The field can hold other signals' records too (S1-S4 all land
            # in `sources`), so only this signal's own records are checked.
            payload = getattr(self, field_name)
            mine = [r for r in payload if getattr(r, "signal", signal_id) is signal_id]
            if mine:
                raise ValueError(
                    f"{signal_id.value} is {row.collected.state.value} but "
                    f"carries {len(mine)} record(s) in {field_name!r} -- a "
                    f"signal that did not run has no records; partial output "
                    f"is UNKNOWN"
                )
        return self
```

Note on `_unmeasured_carries_no_payload`: `SourceCandidate` has a `signal` field so S1–S4 records self-identify inside the shared `sources` list. `ScanCandidate`, `SensitivityRecord` and `TestabilityFinding` do not, so `getattr(r, "signal", signal_id)` treats every record in those single-owner fields as belonging to that field's signal — which is correct, since each of `candidates`, `data_sensitivity` and `testability` has exactly one producer.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_result.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/models.py tests/test_scan_result.py
git commit -m "feat(scan): ScanResult ledger + payload invariants (E-46)"
```

---

### Task 7: `SCAN_SIGNALS` registry, derived waves and boot assertions

**Files:**
- Create: `src/sdlc/assessment/scan/registry.py`
- Test: `tests/test_scan_registry.py`

**Interfaces:**
- Consumes: `ScanSignalId`, `SCAN_ORDER`, `SignalSource`, `CATEGORIES`, `family_of` (Tasks 1, 5).
- Produces: `ScanSignalSpec`, `SCAN_SIGNALS: dict[ScanSignalId, ScanSignalSpec]`, `wave_of(signal_id) -> int`, `WAVES: tuple[tuple[ScanSignalId, ...], ...]`.

- [ ] **Step 1: Write the failing test**

```python
"""The registry is the one place that says which scan signals exist, what
runs them, what they inherit and what they consume."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    ScanSignalId,
    SignalSource,
    family_of,
)
from sdlc.assessment.scan.registry import (
    SCAN_SIGNALS,
    WAVES,
    ScanSignalSpec,
    wave_of,
)


def test_registry_covers_exactly_the_thirteen_signals():
    assert set(SCAN_SIGNALS) == set(SCAN_ORDER)


def test_each_spec_agrees_with_its_id():
    for sid, spec in SCAN_SIGNALS.items():
        assert spec.id is sid
        assert spec.family is family_of(sid)
        assert spec.categories == CATEGORIES[sid]


def test_computed_declares_an_activity_and_no_inherits():
    spec = SCAN_SIGNALS[ScanSignalId.S3]
    assert spec.source is SignalSource.COMPUTED
    assert spec.activity == "scan_entrypoints"
    assert spec.inherits == ()


def test_ss2_is_purely_inherited_and_has_no_activity():
    """D12 cut transitive deps, so SS2 computes nothing."""
    spec = SCAN_SIGNALS[ScanSignalId.SS2]
    assert spec.source is SignalSource.INHERITED
    assert spec.activity == ""
    assert spec.inherits == ("triage:dependencies",)


def test_ss1_is_extended_and_names_both_triage_producers():
    spec = SCAN_SIGNALS[ScanSignalId.SS1]
    assert spec.source is SignalSource.EXTENDED
    assert spec.activity == "scan_security_static"
    assert spec.inherits == ("triage:misconfig", "triage:secrets")


def test_s5_is_computed_in_workflow_and_has_no_activity():
    """S5 is a pure derivation over other signals' output, like
    compute_readiness in TriageWorkflow."""
    spec = SCAN_SIGNALS[ScanSignalId.S5]
    assert spec.activity == ""
    assert spec.in_workflow is True


def test_exactly_eleven_signals_have_an_activity():
    with_activity = [s for s in SCAN_SIGNALS.values() if s.activity]
    assert len(with_activity) == 11
    assert {s.id for s in SCAN_SIGNALS.values() if not s.activity} == {
        ScanSignalId.S5,
        ScanSignalId.SS2,
    }


def test_wave_is_derived_from_consumes():
    assert wave_of(ScanSignalId.S3) == 1
    assert wave_of(ScanSignalId.SS1) == 2  # consumes S3
    assert wave_of(ScanSignalId.SS4) == 2  # consumes S2
    assert wave_of(ScanSignalId.QS2) == 2  # consumes QS1


def test_waves_partition_the_activity_signals_eight_then_three():
    assert len(WAVES) == 2
    assert len(WAVES[0]) == 8
    assert len(WAVES[1]) == 3
    assert set(WAVES[1]) == {ScanSignalId.SS1, ScanSignalId.SS4, ScanSignalId.QS2}
    assert not set(WAVES[0]) & set(WAVES[1])


def test_a_wave_two_signal_only_consumes_wave_one_signals():
    """Two waves is the whole supported depth; a chain of three would be
    silently truncated."""
    for sid in WAVES[1]:
        for upstream in SCAN_SIGNALS[sid].consumes:
            assert wave_of(upstream) == 1, f"{sid.value} -> {upstream.value}"


def test_computed_spec_without_an_activity_or_in_workflow_is_refused():
    with pytest.raises(ValidationError, match="activity"):
        ScanSignalSpec(
            id=ScanSignalId.S1,
            family=family_of(ScanSignalId.S1),
            version=1,
            source=SignalSource.COMPUTED,
            module="sdlc.assessment.scan.signals.packages",
            categories=CATEGORIES[ScanSignalId.S1],
        )


def test_inherited_spec_declaring_an_activity_is_refused():
    with pytest.raises(ValidationError, match="inherit"):
        ScanSignalSpec(
            id=ScanSignalId.SS2,
            family=family_of(ScanSignalId.SS2),
            version=1,
            source=SignalSource.INHERITED,
            activity="scan_deps",
            inherits=("triage:dependencies",),
            module="sdlc.assessment.scan.inherit",
            categories=CATEGORIES[ScanSignalId.SS2],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.scan.registry'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/assessment/scan/registry.py`:

```python
"""The declared set of scan signals (FR-912).

One entry per signal. `version` and `module` are what signal_key folds into
its memo key, and `consumes` does double duty -- both uses are DERIVATIONS,
never second declarations: the fan-out wave (wave_of) and the transitive
rules_sha (rules.py).

Pure of temporalio: `activity` is the activity's NAME, resolved by the
workflow, so this module stays importable without a Temporal runtime -- the
same discipline triage/registry.py keeps.
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from .models import (
    CATEGORIES,
    SCAN_ORDER,
    ScanSignalId,
    SignalFamily,
    SignalSource,
    family_of,
)

_SIG = "sdlc.assessment.scan.signals"


class ScanSignalSpec(BaseModel):
    id: ScanSignalId
    family: SignalFamily
    version: int
    source: SignalSource
    module: str  # dotted path, hashed by rules_sha
    activity: str = ""  # @activity.defn name, or ""
    in_workflow: bool = False  # pure derivation, no activity
    inherits: tuple[str, ...] = ()  # "triage:<signal>"
    rule_modules: tuple[str, ...] = ()  # shared modules, hashed too
    consumes: tuple[ScanSignalId, ...] = ()  # upstream signals
    categories: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _source_fields_agree(self) -> "ScanSignalSpec":
        if self.source is SignalSource.COMPUTED and self.inherits:
            raise ValueError(
                f"{self.id.value}: source=computed declares inherits "
                f"{self.inherits} -- a computed signal inherits nothing (D2)"
            )
        if self.source is not SignalSource.COMPUTED and not self.inherits:
            raise ValueError(
                f"{self.id.value}: source={self.source.value} declares no "
                f"inherits -- an inherited fact must name its producer (D2)"
            )
        if self.source is SignalSource.INHERITED and self.activity:
            raise ValueError(
                f"{self.id.value}: source=inherited declares activity "
                f"{self.activity!r} -- it computes nothing, so it runs no "
                f"activity"
            )
        if not self.activity and not self.in_workflow and self.source is not SignalSource.INHERITED:
            raise ValueError(
                f"{self.id.value}: declares no activity and is not "
                f"in_workflow -- nothing would ever run it"
            )
        if self.activity and self.in_workflow:
            raise ValueError(
                f"{self.id.value}: declares both an activity and "
                f"in_workflow -- exactly one runs a signal"
            )
        return self

    @model_validator(mode="after")
    def _agrees_with_the_artifact(self) -> "ScanSignalSpec":
        if self.family is not family_of(self.id):
            raise ValueError(f"{self.id.value}: family contradicts its id")
        if self.categories != CATEGORIES[self.id]:
            raise ValueError(
                f"{self.id.value}: categories {self.categories} disagree with "
                f"CATEGORIES {CATEGORIES[self.id]} -- models.py is the one "
                f"declaration"
            )
        return self


def _spec(
    sid: ScanSignalId,
    version: int,
    source: SignalSource,
    *,
    module: str,
    activity: str = "",
    in_workflow: bool = False,
    inherits: tuple[str, ...] = (),
    rule_modules: tuple[str, ...] = (),
    consumes: tuple[ScanSignalId, ...] = (),
) -> ScanSignalSpec:
    return ScanSignalSpec(
        id=sid,
        family=family_of(sid),
        version=version,
        source=source,
        module=module,
        activity=activity,
        in_workflow=in_workflow,
        inherits=inherits,
        rule_modules=rule_modules,
        consumes=consumes,
        categories=CATEGORIES[sid],
    )


_NAMING = f"{_SIG.rsplit('.', 1)[0]}.naming"  # scan.naming, shared by S3+S5

SCAN_SIGNALS: dict[ScanSignalId, ScanSignalSpec] = {
    ScanSignalId.S1: _spec(
        ScanSignalId.S1,
        1,
        SignalSource.COMPUTED,
        module=f"{_SIG}.packages",
        activity="scan_packages",
    ),
    ScanSignalId.S2: _spec(
        ScanSignalId.S2, 1, SignalSource.COMPUTED, module=f"{_SIG}.schema", activity="scan_schema"
    ),
    ScanSignalId.S3: _spec(
        ScanSignalId.S3,
        1,
        SignalSource.COMPUTED,
        module=f"{_SIG}.entrypoints",
        activity="scan_entrypoints",
        rule_modules=(_NAMING,),
    ),
    ScanSignalId.S4: _spec(
        ScanSignalId.S4,
        1,
        SignalSource.COMPUTED,
        module=f"{_SIG}.frontend",
        activity="scan_frontend",
    ),
    ScanSignalId.S5: _spec(
        ScanSignalId.S5,
        1,
        SignalSource.COMPUTED,
        module="sdlc.assessment.scan.merge",
        in_workflow=True,
        rule_modules=(_NAMING,),
        consumes=(ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3, ScanSignalId.S4),
    ),
    ScanSignalId.SS1: _spec(
        ScanSignalId.SS1,
        1,
        SignalSource.EXTENDED,
        module=f"{_SIG}.security_static",
        activity="scan_security_static",
        inherits=("triage:misconfig", "triage:secrets"),
        consumes=(ScanSignalId.S3,),
    ),
    ScanSignalId.SS2: _spec(
        ScanSignalId.SS2,
        1,
        SignalSource.INHERITED,
        module="sdlc.assessment.scan.inherit",
        inherits=("triage:dependencies",),
    ),
    ScanSignalId.SS3: _spec(
        ScanSignalId.SS3,
        1,
        SignalSource.EXTENDED,
        module=f"{_SIG}.config_infra",
        activity="scan_config_infra",
        inherits=("triage:misconfig",),
    ),
    ScanSignalId.SS4: _spec(
        ScanSignalId.SS4,
        1,
        SignalSource.COMPUTED,
        module=f"{_SIG}.sensitivity",
        activity="scan_sensitivity",
        consumes=(ScanSignalId.S2,),
    ),
    ScanSignalId.QS1: _spec(
        ScanSignalId.QS1,
        1,
        SignalSource.EXTENDED,
        module=f"{_SIG}.tests_inventory",
        activity="scan_tests_inventory",
        inherits=("triage:baseline",),
    ),
    ScanSignalId.QS2: _spec(
        ScanSignalId.QS2,
        1,
        SignalSource.COMPUTED,
        module=f"{_SIG}.coverage",
        activity="scan_coverage",
        consumes=(ScanSignalId.QS1,),
    ),
    ScanSignalId.QS3: _spec(
        ScanSignalId.QS3,
        1,
        SignalSource.COMPUTED,
        module=f"{_SIG}.testability",
        activity="scan_testability",
    ),
    ScanSignalId.QS4: _spec(
        ScanSignalId.QS4,
        1,
        SignalSource.EXTENDED,
        module=f"{_SIG}.ci",
        activity="scan_ci",
        inherits=("triage:baseline",),
    ),
}

# S5 is in_workflow, so its `consumes` drives rules_sha but not a wave.
MAX_WAVE = 2


def wave_of(signal_id: ScanSignalId) -> int:
    """DERIVED from `consumes`, never assigned: adding a dependent signal is a
    registry edit, not a workflow edit, and the two cannot disagree."""
    return 1 if not SCAN_SIGNALS[signal_id].consumes else 2


def _build_waves() -> tuple[tuple[ScanSignalId, ...], ...]:
    """Activity-bearing signals grouped by wave, in SCAN_ORDER within each."""
    waves: list[tuple[ScanSignalId, ...]] = []
    for wave in range(1, MAX_WAVE + 1):
        waves.append(
            tuple(s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity and wave_of(s) == wave)
        )
    return tuple(waves)


WAVES: tuple[tuple[ScanSignalId, ...], ...] = _build_waves()


def _assert_registry_is_sound() -> None:
    """Boot assertions. A drifted registry fails at import, not at the first
    assessment -- the discipline validate_registry applies to agents.yaml.
    """
    missing = set(SCAN_ORDER) - set(SCAN_SIGNALS)
    if missing:
        raise RuntimeError(
            f"SCAN_SIGNALS is missing {sorted(s.value for s in missing)} -- "
            f"the registry must cover SCAN_ORDER exactly"
        )
    for sid, spec in SCAN_SIGNALS.items():
        for upstream in spec.consumes:
            if upstream is sid:
                raise RuntimeError(f"{sid.value} consumes itself")
            if SCAN_SIGNALS[upstream].consumes and spec.activity:
                raise RuntimeError(
                    f"{sid.value} consumes {upstream.value}, which itself "
                    f"consumes -- only {MAX_WAVE} waves are supported, so a "
                    f"three-deep chain would be silently truncated"
                )
    covered = {s for wave in WAVES for s in wave}
    expected = {s for s, spec in SCAN_SIGNALS.items() if spec.activity}
    if covered != expected:
        raise RuntimeError(
            f"WAVES cover {sorted(s.value for s in covered)} but "
            f"{sorted(s.value for s in expected)} declare an activity"
        )


_assert_registry_is_sound()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_registry.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/registry.py tests/test_scan_registry.py
git commit -m "feat(scan): SCAN_SIGNALS registry with derived waves and boot assertions (E-46)"
```

---

### Task 8: Transitive `rules_sha`

**Files:**
- Create: `src/sdlc/assessment/scan/rules.py`
- Create: `src/sdlc/assessment/scan/naming.py` (minimal — S3/S5 fill it in plan 2)
- Test: `tests/test_scan_rules_sha.py`

**Interfaces:**
- Consumes: `SCAN_SIGNALS` (Task 7).
- Produces: `rules_sha(signal_id) -> str`, `module_sha(dotted) -> str`.

- [ ] **Step 1: Write the failing test**

```python
"""D10: the memo key hashes the rules, not just a version number. This is the
test that would have caught E-3 -- and its second half is the one the spec's
first draft got wrong."""

from __future__ import annotations

from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.assessment.scan.rules import module_sha, rules_sha


def test_every_signal_has_a_hashable_module():
    for sid in SCAN_SIGNALS:
        assert len(rules_sha(sid)) == 64


def test_rules_sha_is_stable_across_calls():
    assert rules_sha(ScanSignalId.S3) == rules_sha(ScanSignalId.S3)


def test_two_signals_have_different_shas():
    assert rules_sha(ScanSignalId.S1) != rules_sha(ScanSignalId.S3)


def test_a_shared_rule_module_reaches_both_its_consumers(monkeypatch):
    """S3 and S5 both declare scan.naming. Editing it must move both keys."""
    naming = SCAN_SIGNALS[ScanSignalId.S3].rule_modules[0]
    before_s3, before_s5 = rules_sha(ScanSignalId.S3), rules_sha(ScanSignalId.S5)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == naming else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.S3) != before_s3
    assert rules_sha(ScanSignalId.S5) != before_s5


def test_an_upstream_signals_module_reaches_its_consumer(monkeypatch):
    """The transitive half. SS1 consumes S3, so editing S3's pattern table
    must move SS1's key -- otherwise the cache serves SS1's stale records
    against S3's fresh ones."""
    s3_module = SCAN_SIGNALS[ScanSignalId.S3].module
    before = rules_sha(ScanSignalId.SS1)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.SS1) != before


def test_an_unrelated_signals_module_does_not_move_the_key(monkeypatch):
    """The guard against over-invalidation: QS3 consumes nothing S3 produces."""
    s3_module = SCAN_SIGNALS[ScanSignalId.S3].module
    before = rules_sha(ScanSignalId.QS3)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.QS3) == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_rules_sha.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.scan.rules'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/assessment/scan/naming.py`:

```python
"""Name normalization shared by S3's grouping and S5's merge (D9).

Sited once because both need the same rule -- S3 groups
PaymentController + PaymentSettlementJob + PaymentEventConsumer into one
candidate, and S5 merges that candidate with S1's payments/ package. Two
copies would agree only by coincidence.

Plan 2 fills in the tables. This module exists now because the registry
declares it as a rule module and rules_sha must be able to hash it.
"""

from __future__ import annotations

VERSION = 1

# Suffixes that describe a technical layer rather than a capability. Plan 2
# populates this; an empty tuple normalizes to lowercase-only, which is
# correct-but-weak rather than wrong.
LAYER_SUFFIXES: tuple[str, ...] = ()


def normalize(name: str) -> str:
    """The normalized form two candidates must share to be merged."""
    out = name.strip()
    for suffix in LAYER_SUFFIXES:
        if out.lower().endswith(suffix.lower()) and len(out) > len(suffix):
            out = out[: -len(suffix)]
            break
    return out.strip("_-").lower()
```

Create `src/sdlc/assessment/scan/rules.py`:

```python
"""D10: rules_sha -- the memo term that makes a stale cache impossible.

A hand-maintained `version: int` invalidates only when someone remembers to
bump it, and two of E-46's signals share a rule module while three consume
another signal's output. Hashing the real bytes is PROMPT_SHAS' existing
answer to exactly this, and it removes the forgot-to-bump hazard for all
thirteen signals rather than only the ones that share a module.

Pure of temporalio; reads module source from disk, so it is called from
ACTIVITY code, never from a workflow.
"""

from __future__ import annotations

import hashlib
import importlib.util

from .models import ScanSignalId
from .registry import SCAN_SIGNALS


def module_sha(dotted: str) -> str:
    """sha256 of a module's source bytes, by dotted path.

    Uses find_spec rather than importing: hashing must not execute the
    module, and a signal module's import side effects are none of this
    function's business.
    """
    spec = importlib.util.find_spec(dotted)
    if spec is None or not spec.origin:
        raise RuntimeError(
            f"cannot locate module {dotted!r} to hash -- the registry names "
            f"it, so a missing module is registry drift, not a cache miss"
        )
    with open(spec.origin, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def rules_sha(signal_id: ScanSignalId) -> str:
    """Hash of everything whose bytes change this signal's output: its own
    module, its declared rule_modules, and -- transitively -- the modules of
    every signal it consumes.

    Sorted before hashing, so traversal order cannot change the key.
    """
    seen: set[ScanSignalId] = set()
    modules: set[str] = set()

    def walk(sid: ScanSignalId) -> None:
        if sid in seen:
            return
        seen.add(sid)
        spec = SCAN_SIGNALS[sid]
        modules.add(spec.module)
        modules.update(spec.rule_modules)
        for upstream in spec.consumes:
            walk(upstream)

    walk(signal_id)
    payload = "|".join(f"{m}:{module_sha(m)}" for m in sorted(modules))
    return hashlib.sha256(payload.encode()).hexdigest()
```

The eleven signal modules named by the registry do not exist yet — Task 9 creates them as stubs. Until then `rules_sha` raises for those ids, which is why Task 8's test only asserts the shared-module and transitive behaviour through `monkeypatch`. **Reorder note:** run Task 9's stub-module creation before Task 8's `test_every_signal_has_a_hashable_module` will pass. Implement Task 8's `rules.py` and `naming.py`, then create the eleven stub modules as Step 3b below, then run the tests.

- [ ] **Step 3b: Create the eleven stub signal modules**

Create `src/sdlc/assessment/scan/signals/__init__.py` (empty) and one module per activity-bearing signal. Each is a placeholder whose bytes will change when its real body lands in plan 2 or 3, which is exactly what `rules_sha` needs. Use this template, substituting the values from the table:

```python
"""<SIGNAL> -- <description>. Body lands in <plan>.

The module exists now because the registry names it and rules_sha hashes it;
editing this file in <plan> moves the memo key by construction.
"""

from __future__ import annotations

SIGNAL_ID = "<SIGNAL>"
VERSION = 1
OWED_BY = "<plan>"
```

| File | `SIGNAL_ID` | `OWED_BY` |
|---|---|---|
| `signals/packages.py` | `S1` | `plan 2` |
| `signals/schema.py` | `S2` | `plan 3` |
| `signals/entrypoints.py` | `S3` | `plan 2` |
| `signals/frontend.py` | `S4` | `plan 3` |
| `signals/security_static.py` | `SS1` | `plan 3` |
| `signals/config_infra.py` | `SS3` | `plan 3` |
| `signals/sensitivity.py` | `SS4` | `plan 3` |
| `signals/tests_inventory.py` | `QS1` | `plan 3` |
| `signals/coverage.py` | `QS2` | `plan 3` |
| `signals/testability.py` | `QS3` | `plan 3` |
| `signals/ci.py` | `QS4` | `plan 3` |

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_rules_sha.py tests/test_scan_registry.py -v`
Expected: PASS (18 tests — 6 new plus Task 7's 12 still green)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/rules.py src/sdlc/assessment/scan/naming.py src/sdlc/assessment/scan/signals/ tests/test_scan_rules_sha.py
git commit -m "feat(scan): transitive rules_sha over modules, shared rules and upstreams (E-46 D10)"
```

---

### Task 9: `signal_key` and the MEASURED-only memo

**Files:**
- Modify: `src/sdlc/memoization/cache.py`
- Create: `src/sdlc/assessment/scan/memo.py`
- Test: `tests/test_scan_memo.py`

**Interfaces:**
- Consumes: `SignalOutput` (Task 6), `rules_sha` (Task 8), `cache.get`/`cache.put`.
- Produces: `cache.signal_key(signal_id, version, rules_sha, tree_hash) -> str`, `memo.load(signal_id, tree_hash) -> SignalOutput | None`, `memo.store(signal_id, tree_hash, out) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
"""D10: cache the row with its payload, and never cache a result that is not
MEASURED."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan import memo
from sdlc.assessment.scan.models import (
    CATEGORIES,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    family_of,
)
from sdlc.measurement import Measurement
from sdlc.memoization.cache import signal_key


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


def _out(sid: ScanSignalId, measured: bool) -> SignalOutput:
    val = Measurement.measured(3.0) if measured else Measurement.not_collected("activity timed out")
    return SignalOutput(
        row=ScanSignalResult(
            signal=sid,
            family=family_of(sid),
            version=1,
            source=SignalSource.COMPUTED,
            collected=val,
            categories={k: val for k in CATEGORIES[sid]},
        )
    )


def test_key_changes_with_every_term():
    base = signal_key("S3", 1, "aaa", "bbb")
    assert base != signal_key("S1", 1, "aaa", "bbb")
    assert base != signal_key("S3", 2, "aaa", "bbb")
    assert base != signal_key("S3", 1, "zzz", "bbb")
    assert base != signal_key("S3", 1, "aaa", "zzz")


def test_key_is_stable_and_hex():
    k = signal_key("S3", 1, "aaa", "bbb")
    assert k == signal_key("S3", 1, "aaa", "bbb")
    assert len(k) == 64


def test_store_then_load_round_trips_row_and_payload():
    out = _out(ScanSignalId.QS3, measured=True)
    assert memo.store(ScanSignalId.QS3, "tree1", out) is True
    got = memo.load(ScanSignalId.QS3, "tree1")
    assert got is not None
    assert got.row.collected.value == 3.0
    assert got.row.signal is ScanSignalId.QS3


def test_a_not_measured_result_is_never_stored():
    """Memoizing a timeout returns that timeout as a cache hit forever."""
    out = _out(ScanSignalId.QS3, measured=False)
    assert memo.store(ScanSignalId.QS3, "tree1", out) is False
    assert memo.load(ScanSignalId.QS3, "tree1") is None


def test_a_different_tree_misses():
    memo.store(ScanSignalId.QS3, "tree1", _out(ScanSignalId.QS3, True))
    assert memo.load(ScanSignalId.QS3, "tree2") is None


def test_corrupt_cache_content_is_a_miss_not_a_crash():
    from sdlc.memoization import cache
    from sdlc.assessment.scan.rules import rules_sha

    key = signal_key(ScanSignalId.QS3.value, 1, rules_sha(ScanSignalId.QS3), "tree1")
    cache.put(key, "{not json")
    assert memo.load(ScanSignalId.QS3, "tree1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_memo.py -v`
Expected: FAIL — `ImportError: cannot import name 'signal_key'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/memoization/cache.py`:

```python
def signal_key(signal_id: str, version: int, rules_sha: str, tree_hash: str) -> str:
    """Memo key for one deterministic scan signal (E-46 D10).

    A sibling of content_key rather than a call into it: content_key requires
    prompt_sha and model_id, and passing "" for them would make "no model was
    involved" indistinguishable from a bug that dropped the model id -- in the
    one place where a silently wrong value serves stale results indefinitely.

    tree_hash, not commit_sha: two commits can share a tree (amend, rebase,
    cherry-pick) and a commit-keyed cache would miss on all of them.
    """
    payload = "|".join(["scan", signal_id, str(version), rules_sha, tree_hash])
    return hashlib.sha256(payload.encode()).hexdigest()
```

Create `src/sdlc/assessment/scan/memo.py`:

```python
"""The scan signal memo (FR-103, FR-912, E-46 D10).

Filesystem I/O, so this is ACTIVITY-side code: a workflow must never call it.
Kept out of models.py and registry.py so those stay pure.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from ..._sdlc_marker import None_ if False else None   # noqa: F401  (placeholder-free import guard)
from ...measurement import CollectionState
from ...memoization import cache
from .models import ScanSignalId, SignalOutput
from .registry import SCAN_SIGNALS
from .rules import rules_sha

_log = logging.getLogger(__name__)


def _key(signal_id: ScanSignalId, tree_hash: str) -> str:
    return cache.signal_key(signal_id.value,
                            SCAN_SIGNALS[signal_id].version,
                            rules_sha(signal_id), tree_hash)


def load(signal_id: ScanSignalId, tree_hash: str) -> SignalOutput | None:
    """A cached output, or None on miss or unparseable content.

    Corrupt content is a MISS, never a crash: a truncated cache file must
    cost a recompute, not an assessment.
    """
    raw = cache.get(_key(signal_id, tree_hash))
    if raw is None:
        return None
    try:
        return SignalOutput.model_validate_json(raw)
    except ValidationError:
        _log.warning("scan memo for %s did not validate; recomputing",
                     signal_id.value)
        return None


def store(signal_id: ScanSignalId, tree_hash: str,
          out: SignalOutput) -> bool:
    """Cache `out` and report whether it was stored.

    ONLY a MEASURED result is stored. Memoizing a timed-out or uninterpretable
    signal would return that failure as a cache hit forever, which is worse
    than never caching at all.
    """
    if out.row.collected.state is not CollectionState.MEASURED:
        return False
    cache.put(_key(signal_id, tree_hash), out.model_dump_json())
    return True
```

Remove the placeholder import guard line — the real import block is:

```python
from ...measurement import CollectionState
from ...memoization import cache
from .models import ScanSignalId, SignalOutput
from .registry import SCAN_SIGNALS
from .rules import rules_sha
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_memo.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memoization/cache.py src/sdlc/assessment/scan/memo.py tests/test_scan_memo.py
git commit -m "feat(scan): signal_key + MEASURED-only memo (E-46 D10)"
```

---

### Task 10: Hoist `run_or_degrade` and refit `TriageWorkflow._one`

**Files:**
- Create: `src/sdlc/workflows/fanout.py`
- Modify: `src/sdlc/workflows/triage.py:131-141`
- Test: `tests/test_workflow_fanout.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `run_or_degrade(activity, arg, opts, *, fallback) -> T`.

- [ ] **Step 1: Write the failing test**

```python
"""D14: the degrade-alone rule has one home. Two copies of it in two
workflows agree only by coincidence -- the reason E-42 D2 extracted
GateHost."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from sdlc.workflows import fanout, triage


def test_triage_no_longer_owns_its_own_try_except():
    """The refit is the point: TriageWorkflow._one must DELEGATE, not keep a
    second copy of the rule."""
    src = inspect.getsource(triage.TriageWorkflow._one)
    assert "run_or_degrade" in src
    assert "except Exception" not in src


def test_fanout_module_is_the_only_place_the_rule_lives():
    src = inspect.getsource(fanout.run_or_degrade)
    assert "except Exception" in src


def test_fallback_is_called_with_no_arguments_on_failure(monkeypatch):
    """Pure-Python exercise of the contract; workflow-level behaviour is
    covered by tests/test_triage_workflow_e2e.py, which stays green."""
    calls: list[str] = []

    async def boom(*a, **kw):
        raise RuntimeError("worker lost")

    monkeypatch.setattr(fanout.workflow, "execute_activity", boom)

    def fallback():
        calls.append("fallback")
        return "degraded"

    got = asyncio.run(fanout.run_or_degrade("act", "arg", {}, fallback=fallback))
    assert got == "degraded"
    assert calls == ["fallback"]


def test_success_returns_the_activity_result(monkeypatch):
    async def ok(activity, arg, **kw):
        return f"ran:{arg}"

    monkeypatch.setattr(fanout.workflow, "execute_activity", ok)
    got = asyncio.run(
        fanout.run_or_degrade("act", "arg", {}, fallback=lambda: pytest.fail("not reached"))
    )
    assert got == "ran:arg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow_fanout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.workflows.fanout'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/workflows/fanout.py`:

```python
"""One home for the degrade-alone rule (E-41 D3, E-46 D14).

TriageWorkflow and AssessmentWorkflow both fan out per-signal activities over
different row types, and both need the same guarantee: a timeout, a lost
worker or an exhausted retry becomes not_collected for THAT signal while
every other one still reports. The activity's own try/except cannot keep it,
because these failures happen outside the activity.

Two copies of that rule would agree only by coincidence -- the reason E-42 D2
extracted GateHost out of FeatureWorkflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from temporalio import workflow

T = TypeVar("T")


async def run_or_degrade(
    activity: Any, arg: Any, opts: dict[str, Any], *, fallback: Callable[[], T]
) -> T:
    """Run one activity, or return `fallback()` if it could not run.

    `fallback` takes no arguments so the caller closes over whatever its own
    row type needs -- the one thing the two tiers do not share.
    """
    try:
        return await workflow.execute_activity(activity, arg, **opts)
    except Exception:  # noqa: BLE001
        return fallback()
```

Replace `TriageWorkflow._one` (`src/sdlc/workflows/triage.py:131-141`) with:

```python
async def _one(self, signal_id: str, activity, arg, opts) -> SignalResult:
    """Run one signal, degrading to not_collected for THIS signal alone
    (E-41 D3). The rule itself lives in fanout.run_or_degrade so
    AssessmentWorkflow shares it rather than restating it (E-46 D14)."""
    return await run_or_degrade(
        activity,
        arg,
        opts,
        fallback=lambda: skipped_signal(signal_id, f"{signal_id} activity failed or timed out"),
    )
```

Add to the `workflow.unsafe.imports_passed_through()` block in `triage.py`:

```python
    from .fanout import run_or_degrade
```

**Behaviour change to note in the commit:** the old message interpolated the
exception type and text. `run_or_degrade` does not pass the exception to the
fallback, so the reason is now generic. Temporal already records the activity
failure in history with full detail, so nothing is lost that an operator
cannot reach — and keeping the signature argument-free is what lets both tiers
share one rule.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_workflow_fanout.py tests/test_triage_workflow.py -v`
Expected: PASS — new tests plus the existing triage suite still green

Then confirm the workflow-level path: `pytest -m temporal tests/test_triage_workflow_e2e.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/fanout.py src/sdlc/workflows/triage.py tests/test_workflow_fanout.py
git commit -m "refactor(workflows): hoist the degrade-alone rule into fanout.run_or_degrade (E-46 D14)"
```

---

### Task 11: The tree-hash activity

**Files:**
- Create: `src/sdlc/assessment/activities.py`
- Test: `tests/test_assessment_resolve_tree.py`

**Interfaces:**
- Consumes: `_git` from `sdlc.activities`.
- Produces: `AssessmentTreeInput`, `AssessmentTree`, `assessment_resolve_tree(inp) -> AssessmentTree`.

- [ ] **Step 1: Write the failing test**

```python
"""D10: tree_hash, not commit_sha -- two commits sharing a tree must hit the
same cache."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment.activities import (
    AssessmentTreeInput,
    assessment_resolve_tree,
)


def _run(args: list[str], cwd) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    _run(["git", "init", "-q"], tmp_path)
    _run(["git", "config", "user.email", "t@t.t"], tmp_path)
    _run(["git", "config", "user.name", "T"], tmp_path)
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-qm", "one"], tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_resolves_the_tree_of_a_commit(repo):
    sha = _run(["git", "rev-parse", "HEAD"], repo)
    got = await assessment_resolve_tree(AssessmentTreeInput(repo_dir=str(repo), commit_sha=sha))
    assert len(got.tree_hash) == 40
    assert got.tree_hash == _run(["git", "rev-parse", "HEAD^{tree}"], repo)


@pytest.mark.asyncio
async def test_amending_the_message_keeps_the_tree_hash(repo):
    """The whole reason for tree_hash: an amend changes the commit sha and
    nothing about the content."""
    before = await assessment_resolve_tree(
        AssessmentTreeInput(repo_dir=str(repo), commit_sha=_run(["git", "rev-parse", "HEAD"], repo))
    )
    _run(["git", "commit", "-q", "--amend", "-m", "one, reworded"], repo)
    after = await assessment_resolve_tree(
        AssessmentTreeInput(repo_dir=str(repo), commit_sha=_run(["git", "rev-parse", "HEAD"], repo))
    )
    assert after.tree_hash == before.tree_hash


@pytest.mark.asyncio
async def test_changing_content_changes_the_tree_hash(repo):
    before = await assessment_resolve_tree(
        AssessmentTreeInput(repo_dir=str(repo), commit_sha=_run(["git", "rev-parse", "HEAD"], repo))
    )
    (repo / "a.txt").write_text("goodbye\n", encoding="utf-8")
    _run(["git", "commit", "-qam", "two"], repo)
    after = await assessment_resolve_tree(
        AssessmentTreeInput(repo_dir=str(repo), commit_sha=_run(["git", "rev-parse", "HEAD"], repo))
    )
    assert after.tree_hash != before.tree_hash


@pytest.mark.asyncio
async def test_an_unresolvable_commit_raises(repo):
    """Deliberately NOT never-raising, matching triage_resolve_commit: without
    a tree hash nothing can be memoized or reproduced, so this is the absence
    of the tree the artifact claims to describe, not a not_collected
    dimension."""
    with pytest.raises(RuntimeError, match="does not resolve"):
        await assessment_resolve_tree(AssessmentTreeInput(repo_dir=str(repo), commit_sha="f" * 40))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_resolve_tree.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.activities'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/assessment/activities.py`:

```python
"""E-46 scan activities (FR-912). One activity per computed signal,
deliberately: a signal that crashes or times out yields not_collected for
ITSELF while every other signal still reports (E-41 spec D3).

Every signal reads blob bytes at the pinned commit. NOTHING here executes the
assessed repository's code -- the init phase's build probe remains the only
place that happens (NFR-9, E-46 D12).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel
from temporalio import activity

from ..activities import _git

_log = logging.getLogger(__name__)


class AssessmentTreeInput(BaseModel):
    repo_dir: str
    commit_sha: str


class AssessmentTree(BaseModel):
    tree_hash: str


@activity.defn
async def assessment_resolve_tree(inp: AssessmentTreeInput) -> AssessmentTree:
    """The tree object of the pinned commit, which is what the scan memo keys
    on (D10).

    Two commits can share a tree -- amend, rebase, cherry-pick -- and a
    commit-keyed cache would miss on all of them, which E-54's incremental
    re-assessment and E-44's before/after re-triage both lean on.

    Deliberately NOT never-raising, matching triage_resolve_commit: a commit
    that does not resolve is not a not_collected dimension, it is the absence
    of the tree the whole artifact claims to describe.
    """
    proc = _git(["rev-parse", "--verify", f"{inp.commit_sha}^{{tree}}"], cwd=inp.repo_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            f"commit {inp.commit_sha!r} does not resolve to a tree in "
            f"{inp.repo_dir}: {proc.stderr.strip()}"
        )
    return AssessmentTree(tree_hash=proc.stdout.strip())
```

The `@pytest.mark.asyncio` markers in the test above match this repo's convention — `asyncio_mode` is not set in `pyproject.toml`, and `tests/test_board_activities.py` marks each async test explicitly. Do not introduce a second convention.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assessment_resolve_tree.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/activities.py tests/test_assessment_resolve_tree.py
git commit -m "feat(scan): assessment_resolve_tree pins the tree hash the memo keys on (E-46 D10)"
```

---

### Task 12: The eleven stub signal activities

**Files:**
- Modify: `src/sdlc/assessment/activities.py` (append)
- Test: `tests/test_scan_stub_activities.py`

**Interfaces:**
- Consumes: `SCAN_SIGNALS`, `CATEGORIES`, `SignalOutput`, `memo` (Tasks 5–9).
- Produces: `ScanSignalInput`, `unbuilt_signal(signal_id) -> SignalOutput`, and the eleven `@activity.defn`s named in the registry: `scan_packages`, `scan_schema`, `scan_entrypoints`, `scan_frontend`, `scan_security_static`, `scan_config_infra`, `scan_sensitivity`, `scan_tests_inventory`, `scan_coverage`, `scan_testability`, `scan_ci`.

- [ ] **Step 1: Write the failing test**

```python
"""Plan 1 ships the eleven activities as stubs reporting not_collected and
naming the plan that owes them -- E-45's unbuilt() discipline, one level
down. Plans 2 and 3 replace bodies, not wiring."""

from __future__ import annotations

import pytest

from sdlc.assessment import activities as scan_acts
from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    ScanSignalId,
    SignalSource,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState


def _activity_signals() -> list[ScanSignalId]:
    return [s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity]


def test_every_declared_activity_exists_on_the_module():
    """Registry drift fails here rather than at the first assessment."""
    for sid in _activity_signals():
        name = SCAN_SIGNALS[sid].activity
        assert hasattr(scan_acts, name), f"{sid.value} -> {name}"


def test_no_activity_is_declared_for_the_two_in_workflow_signals():
    for sid in (ScanSignalId.S5, ScanSignalId.SS2):
        assert SCAN_SIGNALS[sid].activity == ""


@pytest.mark.parametrize("sid", _activity_signals(), ids=lambda s: s.value)
def test_stub_reports_not_collected_naming_the_plan(sid):
    out = scan_acts.unbuilt_signal(sid)
    assert out.row.signal is sid
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "plan" in out.row.collected.reason.lower()
    assert sid.value in out.row.collected.reason


@pytest.mark.parametrize("sid", _activity_signals(), ids=lambda s: s.value)
def test_stub_reports_every_category_it_owes(sid):
    """A stub must not leave a category unreported -- that would be
    indistinguishable from a category nobody owes."""
    out = scan_acts.unbuilt_signal(sid)
    assert set(out.row.categories) == set(CATEGORIES[sid])
    for m in out.row.categories.values():
        assert m.state is CollectionState.NOT_COLLECTED


@pytest.mark.parametrize("sid", _activity_signals(), ids=lambda s: s.value)
def test_stub_carries_no_records(sid):
    out = scan_acts.unbuilt_signal(sid)
    assert out.sources == []
    assert out.data_sensitivity == []
    assert out.testability == []


def test_stub_source_matches_its_registry_declaration():
    """An EXTENDED signal's stub still declares EXTENDED; the workflow folds
    the inherited producer in (D7), so the activity's own row is COMPUTED-
    shaped and carries no producer."""
    out = scan_acts.unbuilt_signal(ScanSignalId.SS1)
    assert out.row.source is SignalSource.COMPUTED
    assert out.row.producer is None
    assert SCAN_SIGNALS[ScanSignalId.SS1].source is SignalSource.EXTENDED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_stub_activities.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.assessment.activities' has no attribute 'unbuilt_signal'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/assessment/activities.py`:

```python
from .scan.models import (
    CATEGORIES,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    family_of,
)
from .scan.registry import SCAN_SIGNALS

# Which plan owes each signal's body. Plan 1 ships every activity as a stub so
# the seam, the memo and the never-cache-unmeasured rule all have a real
# consumer immediately -- the same reason E-45 shipped the DAG with six stub
# phase bodies rather than waiting for one.
OWED_BY: dict[ScanSignalId, str] = {
    ScanSignalId.S1: "plan 2",
    ScanSignalId.S3: "plan 2",
    ScanSignalId.S2: "plan 3",
    ScanSignalId.S4: "plan 3",
    ScanSignalId.SS1: "plan 3",
    ScanSignalId.SS3: "plan 3",
    ScanSignalId.SS4: "plan 3",
    ScanSignalId.QS1: "plan 3",
    ScanSignalId.QS2: "plan 3",
    ScanSignalId.QS3: "plan 3",
    ScanSignalId.QS4: "plan 3",
}


class ScanSignalInput(BaseModel):
    """One signal's activity input. `upstream` is empty for wave 1 and carries
    the consumed signals' candidates for wave 2 (spec section 5)."""

    repo_dir: str
    commit_sha: str
    tree_hash: str
    upstream: list[SourceCandidate] = []


def unbuilt_signal(signal_id: ScanSignalId) -> SignalOutput:
    """A signal whose body is a later plan. Never Measurement.measured(0.0):
    a signal that did not run has no value (FR-915).

    `source` is COMPUTED and `producer` is None regardless of the registry's
    declaration: this is the ACTIVITY's half of the row, and the workflow
    folds the inherited producer in afterwards (D7).
    """
    reason = f"{signal_id.value} not implemented ({OWED_BY[signal_id]}, E-46)"
    return SignalOutput(
        row=ScanSignalResult(
            signal=signal_id,
            family=family_of(signal_id),
            version=SCAN_SIGNALS[signal_id].version,
            source=SignalSource.COMPUTED,
            collected=Measurement.not_collected(reason),
            categories={k: Measurement.not_collected(reason) for k in CATEGORIES[signal_id]},
        )
    )
```

Add `from ..measurement import Measurement` to the imports, then define the eleven activities. Each is identical in shape; write all eleven explicitly rather than generating them, so `@activity.defn` names are greppable and the worker registration in Task 15 can import them by name:

```python
@activity.defn
async def scan_packages(inp: ScanSignalInput) -> SignalOutput:
    """S1 -- package structure. Body lands in plan 2."""
    return unbuilt_signal(ScanSignalId.S1)


@activity.defn
async def scan_schema(inp: ScanSignalInput) -> SignalOutput:
    """S2 -- database schema clusters. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.S2)


@activity.defn
async def scan_entrypoints(inp: ScanSignalInput) -> SignalOutput:
    """S3 -- backend entry points, the Contract tier. Body lands in plan 2."""
    return unbuilt_signal(ScanSignalId.S3)


@activity.defn
async def scan_frontend(inp: ScanSignalInput) -> SignalOutput:
    """S4 -- frontend entry points. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.S4)


@activity.defn
async def scan_security_static(inp: ScanSignalInput) -> SignalOutput:
    """SS1 -- TLS and input validation. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.SS1)


@activity.defn
async def scan_config_infra(inp: ScanSignalInput) -> SignalOutput:
    """SS3 -- ports, env divergence, DB security, log masking. Plan 3."""
    return unbuilt_signal(ScanSignalId.SS3)


@activity.defn
async def scan_sensitivity(inp: ScanSignalInput) -> SignalOutput:
    """SS4 -- data sensitivity classification. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.SS4)


@activity.defn
async def scan_tests_inventory(inp: ScanSignalInput) -> SignalOutput:
    """QS1 -- test levels and test->file mapping. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.QS1)


@activity.defn
async def scan_coverage(inp: ScanSignalInput) -> SignalOutput:
    """QS2 -- committed report or proxy. Never runs the suite (D12). Plan 3."""
    return unbuilt_signal(ScanSignalId.QS2)


@activity.defn
async def scan_testability(inp: ScanSignalInput) -> SignalOutput:
    """QS3 -- testability findings. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.QS3)


@activity.defn
async def scan_ci(inp: ScanSignalInput) -> SignalOutput:
    """QS4 -- CI stages and env drift. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.QS4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_stub_activities.py -v`
Expected: PASS (46 tests — 6 plus 4 parametrized sets of 11 minus overlap; the exact count follows from the parametrization)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/activities.py tests/test_scan_stub_activities.py
git commit -m "feat(scan): eleven signal activities as not_collected stubs naming their plan (E-46)"
```

---

### Task 13: `inherit.py` — the five inherited halves

**Files:**
- Create: `src/sdlc/assessment/scan/inherit.py`
- Test: `tests/test_scan_inherit.py`

**Interfaces:**
- Consumes: `RepoTriage`, `SignalResult`, `finding_identity` (`triage/models.py`); `InheritedProducer`, category constants (Task 5).
- Produces: `InheritedHalf`, `inherited_halves(triage) -> dict[ScanSignalId, InheritedHalf]`.

- [ ] **Step 1: Write the failing test**

```python
"""D2/D7: the read-through. Findings are cited by identity, never copied, and
this half is derived in workflow code from an artifact already in hand."""

from __future__ import annotations

from sdlc.assessment.scan.inherit import inherited_halves
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ,
    C_CI_PRESENT,
    C_CREDENTIAL_STORAGE,
    C_DIRECT_DEPS,
    C_FRAMEWORK_DEFAULTS,
    C_TESTS_PRESENT,
    ScanSignalId,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import (
    FixClass,
    Readiness,
    RepoTriage,
    SignalResult,
    TriageFinding,
    Verdict,
    finding_identity,
)


def _finding(signal: str, rule: str, path: str = "x.py", key: str = "") -> TriageFinding:
    return TriageFinding(
        signal=signal,
        rule=rule,
        severity="high",
        detail="d",
        path=path,
        fix_class=FixClass.MECHANICAL,
        key=key,
    )


def _triage(*signals: SignalResult, tests: float = 2.0) -> RepoTriage:
    ok = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        toolchain="python",
        readiness=Readiness(
            buildable=ok,
            runnable=ok,
            tests_present=Measurement.measured(tests),
            structure_discernible=ok,
            verdict=Verdict.READY,
        ),
        signals=list(signals),
    )


def _sig(
    signal: str,
    version: int,
    findings: list[TriageFinding],
    metrics: dict[str, Measurement] | None = None,
) -> SignalResult:
    return SignalResult(
        signal=signal,
        version=version,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics=metrics or {},
    )


def test_five_signals_have_an_inherited_half():
    halves = inherited_halves(_triage())
    assert set(halves) == {
        ScanSignalId.SS1,
        ScanSignalId.SS2,
        ScanSignalId.SS3,
        ScanSignalId.QS1,
        ScanSignalId.QS4,
    }


def test_ss1_cites_secrets_findings_by_identity_and_copies_none():
    f = _finding("secrets", "aws_key", ".env", "abc")
    halves = inherited_halves(_triage(_sig("secrets", 2, [f])))
    producer = halves[ScanSignalId.SS1].producer
    assert finding_identity(f) in producer.finding_ids
    assert producer.version == 2
    assert "secrets" in producer.producer


def test_ss1_credential_storage_is_measured_with_the_finding_count():
    f = _finding("secrets", "aws_key", ".env", "abc")
    cats = (
        inherited_halves(_triage(_sig("secrets", 2, [f]))).categories
        if False
        else inherited_halves(_triage(_sig("secrets", 2, [f])))[ScanSignalId.SS1].categories
    )
    assert cats[C_CREDENTIAL_STORAGE].state is CollectionState.MEASURED
    assert cats[C_CREDENTIAL_STORAGE].value == 1.0


def test_a_missing_triage_signal_yields_not_collected_not_zero():
    """The signal never ran, so the category has no value (FR-915)."""
    cats = inherited_halves(_triage())[ScanSignalId.SS1].categories
    assert cats[C_CREDENTIAL_STORAGE].state is CollectionState.NOT_COLLECTED
    assert cats[C_CREDENTIAL_STORAGE].value is None
    assert "secrets" in cats[C_CREDENTIAL_STORAGE].reason


def test_a_not_collected_triage_signal_propagates_its_reason():
    sig = SignalResult(
        signal="secrets", version=2, collected=Measurement.not_collected("scan timed out")
    )
    cats = inherited_halves(_triage(sig))[ScanSignalId.SS1].categories
    assert cats[C_CREDENTIAL_STORAGE].state is CollectionState.NOT_COLLECTED
    assert "timed out" in cats[C_CREDENTIAL_STORAGE].reason


def test_only_inherited_categories_appear_in_the_half():
    """The computed categories (TLS, input validation) are the activity's, so
    the half must not claim them -- the workflow unions the two (D7)."""
    cats = inherited_halves(_triage(_sig("secrets", 2, [])))[ScanSignalId.SS1].categories
    assert set(cats) == {C_CREDENTIAL_STORAGE, C_AUTHN_AUTHZ}


def test_ss3_inherits_framework_defaults_from_misconfig():
    f = _finding("misconfig", "permissive_cors", "app.py", "x")
    cats = inherited_halves(_triage(_sig("misconfig", 2, [f])))[ScanSignalId.SS3].categories
    assert set(cats) == {C_FRAMEWORK_DEFAULTS}
    assert cats[C_FRAMEWORK_DEFAULTS].value == 1.0


def test_ss2_inherits_direct_dependencies_and_is_the_whole_signal():
    """D12 cut transitive deps, so SS2 has no computed half at all."""
    f = _finding("dependencies", "known_vulnerable", "poetry.lock", "pkg")
    half = inherited_halves(_triage(_sig("dependencies", 1, [f])))[ScanSignalId.SS2]
    assert set(half.categories) == {C_DIRECT_DEPS}
    assert half.categories[C_DIRECT_DEPS].value == 1.0


def test_qs1_inherits_the_test_count_from_baselines_metric_not_its_findings():
    """tests_present is a COUNT on baseline.metrics, not a finding tally."""
    sig = _sig("baseline", 2, [], {"tests_present": Measurement.measured(7.0)})
    cats = inherited_halves(_triage(sig))[ScanSignalId.QS1].categories
    assert set(cats) == {C_TESTS_PRESENT}
    assert cats[C_TESTS_PRESENT].value == 7.0


def test_qs4_ci_present_is_the_absence_of_baselines_no_ci_finding():
    """baseline reports a finding when CI is MISSING, so ci_present is 1.0
    when that finding is absent and 0.0 when it fires. This inversion is why
    the mapping is a declared function rather than a generic tally."""
    with_ci = inherited_halves(_triage(_sig("baseline", 2, [])))[ScanSignalId.QS4].categories
    assert with_ci[C_CI_PRESENT].value == 1.0

    without = inherited_halves(_triage(_sig("baseline", 2, [_finding("baseline", "no_ci")])))[
        ScanSignalId.QS4
    ].categories
    assert without[C_CI_PRESENT].value == 0.0


def test_qs4_ci_present_is_not_collected_when_baseline_did_not_run():
    sig = SignalResult(signal="baseline", version=2, collected=Measurement.not_collected("boom"))
    cats = inherited_halves(_triage(sig))[ScanSignalId.QS4].categories
    assert cats[C_CI_PRESENT].state is CollectionState.NOT_COLLECTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_inherit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.scan.inherit'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/assessment/scan/inherit.py`:

```python
"""D2/D7: the Tier 0 read-through.

Five scan signals inherit a base from RepoTriage. This module derives that
base and NOTHING else: the computed halves belong to the activities, and the
workflow unions the two.

Pure -- and deliberately so, because it must run in workflow code. Triage
findings are not a function of the tree (build_probe executes the repository's
own code and can time out), so this half must never enter a tree-keyed memo
(D7). Re-deriving it every run is free.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...measurement import CollectionState, Measurement
from ...triage.models import RepoTriage, SignalResult, finding_identity
from .models import (
    C_AUTHN_AUTHZ,
    C_CI_PRESENT,
    C_CREDENTIAL_STORAGE,
    C_DIRECT_DEPS,
    C_FRAMEWORK_DEFAULTS,
    C_TESTS_PRESENT,
    InheritedProducer,
    ScanSignalId,
)

# Which triage rules feed each inherited category. Declared rather than
# inferred from the signal name: `misconfig` feeds BOTH SS1's authn_authz
# (unauthenticated_app) and SS3's framework_defaults (everything else), so a
# whole-signal tally would double-count one signal into two categories.
_AUTHZ_RULES = ("unauthenticated_app",)
_CI_RULES = ("no_ci",)


def _by_signal(triage: RepoTriage) -> dict[str, SignalResult]:
    return {s.signal: s for s in triage.signals}


def _absent(signal: str) -> Measurement:
    return Measurement.not_collected(f"triage signal {signal!r} is not present in this triage")


def _unavailable(sig: SignalResult) -> Measurement | None:
    """The category's Measurement when the producing signal did not collect,
    or None when it did. Propagates the reason so the assessment says WHY."""
    if sig.collected.state is CollectionState.MEASURED:
        return None
    return Measurement.not_collected(
        f"triage signal {sig.signal!r} reported {sig.collected.state.value}: {sig.collected.reason}"
    )


def _tally(sig: SignalResult, rules: tuple[str, ...] | None = None) -> Measurement:
    """Count of matching findings, or not_collected when the signal did not
    collect. `rules=None` counts every finding."""
    if (unavailable := _unavailable(sig)) is not None:
        return unavailable
    if rules is None:
        return Measurement.measured(float(len(sig.findings)))
    return Measurement.measured(float(sum(1 for f in sig.findings if f.rule in rules)))


def _absence_of(sig: SignalResult, rules: tuple[str, ...]) -> Measurement:
    """1.0 when none of `rules` fired, else 0.0.

    baseline reports a finding when CI is MISSING, so ci_present is the
    INVERSE of its tally. This inversion is why the mapping is a declared
    function per category rather than a generic finding count.
    """
    if (unavailable := _unavailable(sig)) is not None:
        return unavailable
    fired = any(f.rule in rules for f in sig.findings)
    return Measurement.measured(0.0 if fired else 1.0)


def _metric(sig: SignalResult, key: str) -> Measurement:
    """A metric the producing signal already computed, passed through
    unchanged -- including its own not_collected state."""
    if (unavailable := _unavailable(sig)) is not None:
        return unavailable
    return sig.metrics.get(
        key, Measurement.not_collected(f"triage signal {sig.signal!r} reported no {key!r} metric")
    )


def _producer(sig: SignalResult, rules: tuple[str, ...] | None = None) -> InheritedProducer:
    """Cite the producing signal and the findings this row rests on.

    version is PINNED, so a triage version bump changes the assessment
    visibly rather than silently.
    """
    cited = [f for f in sig.findings if rules is None or f.rule in rules]
    return InheritedProducer(
        producer=f"triage:{sig.signal}",
        version=sig.version,
        finding_ids=[finding_identity(f) for f in cited],
    )


class InheritedHalf(BaseModel):
    """One signal's inherited contribution: who produced it and which
    categories it answers. The workflow unions this with the activity's
    computed half (D7)."""

    producer: InheritedProducer
    categories: dict[str, Measurement] = Field(default_factory=dict)


def _merge_producers(*producers: InheritedProducer) -> InheritedProducer:
    """SS1 inherits from two triage signals. The row carries one producer, so
    the two are folded with a composite name and the union of their citations;
    `version` becomes the max, which is the coarse-but-honest choice -- a bump
    in either producer moves it."""
    names = ",".join(sorted(p.producer for p in producers))
    ids: list[str] = []
    for p in producers:
        ids.extend(p.finding_ids)
    return InheritedProducer(
        producer=names, version=max(p.version for p in producers), finding_ids=ids
    )


def inherited_halves(triage: RepoTriage) -> dict[ScanSignalId, InheritedHalf]:
    """The inherited half of every signal that has one (D2).

    Five signals, each mapped explicitly. A generic "same-named signal" rule
    was rejected: misconfig feeds two different scan signals with different
    rule subsets, and baseline feeds one category as a metric and another as
    the ABSENCE of a finding.
    """
    found = _by_signal(triage)
    missing = SignalResult(signal="", version=0, collected=Measurement.not_collected(""))

    def sig(name: str) -> SignalResult | None:
        return found.get(name)

    out: dict[ScanSignalId, InheritedHalf] = {}

    # SS1 -- credential storage from secrets, app-level auth from misconfig.
    secrets, misconfig = sig("secrets"), sig("misconfig")
    out[ScanSignalId.SS1] = InheritedHalf(
        producer=_merge_producers(
            _producer(secrets)
            if secrets
            else InheritedProducer(producer="triage:secrets", version=0),
            _producer(misconfig, _AUTHZ_RULES)
            if misconfig
            else InheritedProducer(producer="triage:misconfig", version=0),
        ),
        categories={
            C_CREDENTIAL_STORAGE: (_tally(secrets) if secrets else _absent("secrets")),
            C_AUTHN_AUTHZ: (_tally(misconfig, _AUTHZ_RULES) if misconfig else _absent("misconfig")),
        },
    )

    # SS2 -- purely inherited; D12 cut transitive enumeration.
    deps = sig("dependencies")
    out[ScanSignalId.SS2] = InheritedHalf(
        producer=(
            _producer(deps)
            if deps
            else InheritedProducer(producer="triage:dependencies", version=0)
        ),
        categories={C_DIRECT_DEPS: (_tally(deps) if deps else _absent("dependencies"))},
    )

    # SS3 -- framework defaults, excluding the rule SS1 already claims.
    ss3_rules = None
    out[ScanSignalId.SS3] = InheritedHalf(
        producer=(
            _producer(misconfig)
            if misconfig
            else InheritedProducer(producer="triage:misconfig", version=0)
        ),
        categories={
            C_FRAMEWORK_DEFAULTS: (
                _tally(misconfig, ss3_rules) if misconfig else _absent("misconfig")
            ),
        },
    )

    # QS1 -- the test COUNT, which baseline carries as a metric.
    baseline = sig("baseline")
    out[ScanSignalId.QS1] = InheritedHalf(
        producer=(
            _producer(baseline)
            if baseline
            else InheritedProducer(producer="triage:baseline", version=0)
        ),
        categories={
            C_TESTS_PRESENT: (
                _metric(baseline, "tests_present") if baseline else _absent("baseline")
            ),
        },
    )

    # QS4 -- ci_present is the ABSENCE of baseline's no_ci finding.
    out[ScanSignalId.QS4] = InheritedHalf(
        producer=(
            _producer(baseline, _CI_RULES)
            if baseline
            else InheritedProducer(producer="triage:baseline", version=0)
        ),
        categories={
            C_CI_PRESENT: (_absence_of(baseline, _CI_RULES) if baseline else _absent("baseline")),
        },
    )

    del missing
    return out
```

Clean up before committing: delete the unused `missing` local and its `del`, and replace `ss3_rules = None` with a direct `None` argument. They are shown here only to make the two subtleties explicit — that SS3 tallies *all* misconfig findings while SS1 tallies only `_AUTHZ_RULES`, and that a wholly absent signal still yields a producer row with `version=0`.

**Known overlap to record in the commit message:** SS3's `framework_defaults` tallies every `misconfig` finding including `unauthenticated_app`, which SS1's `authn_authz` also counts. The finding is cited twice across two categories but copied nowhere, and each citation resolves to the same `finding_identity`. Narrowing SS3 to exclude `_AUTHZ_RULES` is a one-line change if E-49 later needs the partition to be disjoint; it is left inclusive because SS3's question is *"how many framework defaults are unsafe"* and an unauthenticated app is one.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scan_inherit.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/inherit.py tests/test_scan_inherit.py
git commit -m "feat(scan): inherit the five Tier 0 halves by citation, never by copy (E-46 D2/D7)"
```

---

### Task 14: `Assessment.scan` and the phase-agreement validator

**Files:**
- Modify: `src/sdlc/assessment/models.py`
- Modify: `src/sdlc/workflows/assessment.py` (`assemble` signature)
- Test: `tests/test_assessment_models.py` (extend)

**Interfaces:**
- Consumes: `ScanResult` (Task 6).
- Produces: `Assessment.scan: ScanResult | None`, `assemble(..., scan=None)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_models.py`:

```python
from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    ScanResult,
    ScanSignalResult,
    SignalSource,
    family_of,
)


def _scan_result() -> ScanResult:
    val = Measurement.measured(0.0)
    return ScanResult(
        signals=[
            ScanSignalResult(
                signal=s,
                family=family_of(s),
                version=1,
                source=SignalSource.COMPUTED,
                collected=val,
                categories={k: val for k in CATEGORIES[s]},
            )
            for s in SCAN_ORDER
        ]
    )


def _phases(scan_measured: bool) -> list[PhaseResult]:
    """The whole DAG with SCAN either measured or not."""
    out = []
    for phase in PHASE_ORDER:
        if phase is PhaseId.SCAN and not scan_measured:
            out.append(
                PhaseResult(phase=phase, collected=Measurement.not_collected("scan not run"))
            )
        else:
            out.append(PhaseResult(phase=phase, collected=Measurement.measured(1.0)))
    return out


def test_a_scan_payload_requires_a_measured_scan_phase():
    """Mirrors _terminal_status_matches_derivation: the artifact cannot
    contradict its own phase row."""
    phases = _phases(scan_measured=False)
    with pytest.raises(ValueError, match="scan"):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="verdict ready",
            phases=phases,
            terminal_status=terminal_status(True, phases),
            scan=_scan_result(),
        )


def test_a_measured_scan_phase_requires_a_payload():
    phases = _phases(scan_measured=True)
    with pytest.raises(ValueError, match="scan"):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="verdict ready",
            phases=phases,
            terminal_status=terminal_status(True, phases),
            scan=None,
        )


def test_a_measured_scan_phase_with_a_payload_constructs():
    phases = _phases(scan_measured=True)
    a = Assessment(
        repo_dir="/r",
        triage=_triage(),
        admitted=True,
        admission_reason="verdict ready",
        phases=phases,
        terminal_status=terminal_status(True, phases),
        scan=_scan_result(),
    )
    assert a.scan is not None
    assert len(a.scan.signals) == 13


def test_assemble_threads_the_scan_payload_through():
    from sdlc.workflows.assessment import assemble, unbuilt

    rest = [PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(0.0))]
    rest += [unbuilt(p) for p in PHASE_ORDER if p not in (PhaseId.INIT, PhaseId.SCAN)]
    a = assemble("/r", _init(), True, "verdict ready", rest, scan=_scan_result())
    assert a.scan is not None
    assert a.terminal_status == PARTIAL
```

Add `PARTIAL` and `terminal_status` to the file's existing import from `sdlc.assessment.models` if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_models.py -v`
Expected: FAIL — `TypeError: Assessment() got an unexpected keyword argument 'scan'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/assessment/models.py`, add the import and the field:

```python
from .scan.models import ScanResult
```

Add to `Assessment`, after `phases`:

```python
    # E-46's typed field. There is deliberately no generic payload bag: each
    # later item adds its OWN typed field, because an untyped bag would be a
    # schema-less hole in the one artifact handed to a customer (FR-921).
    scan: ScanResult | None = None
```

Add the validator:

```python
@model_validator(mode="after")
def _scan_agrees_with_its_phase(self) -> Assessment:
    """The payload and its phase row cannot contradict each other, the
    same guarantee _terminal_status_matches_derivation gives the status.

    A not_collected SCAN phase carrying a ScanResult would be an
    assessment claiming it did not scan while shipping scan output.
    """
    row = next((p for p in self.phases if p.phase is PhaseId.SCAN), None)
    if row is None:  # unreachable: the DAG validator
        return self  # already required every phase
    measured = row.collected.state is CollectionState.MEASURED
    if measured and self.scan is None:
        raise ValueError(
            "scan phase is measured but no ScanResult is present -- a "
            "measured phase produced an artifact by definition"
        )
    if not measured and self.scan is not None:
        raise ValueError(
            f"scan phase is {row.collected.state.value} but a ScanResult "
            f"is present -- an assessment cannot claim it did not scan "
            f"while shipping scan output"
        )
    return self
```

In `src/sdlc/workflows/assessment.py`, thread the payload through `assemble`:

```python
def assemble(repo_dir: str, init: InitOutcome, admitted: bool, reason: str,
             rest: list[PhaseResult] | None = None,
             scan: ScanResult | None = None) -> Assessment:
```

and pass `scan=scan` to the `Assessment(...)` construction. Add `ScanResult` to the `workflow.unsafe.imports_passed_through()` block:

```python
    from ..assessment.scan.models import ScanResult
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assessment_models.py tests/test_assessment_workflow.py -v`
Expected: PASS — new tests plus the existing E-45 suite still green

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/models.py src/sdlc/workflows/assessment.py tests/test_assessment_models.py
git commit -m "feat(scan): Assessment.scan, tied to its phase row by a validator (E-46)"
```

---

### Task 15: Wire `_scan` and register the activities

**Files:**
- Modify: `src/sdlc/workflows/assessment.py`
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_assessment_scan_phase.py`

**Interfaces:**
- Consumes: everything from Tasks 1–14.
- Produces: `ScanOutcome`, `skipped_scan_signal(signal_id, reason)`, `fold_row(activity_row, half)`, `AssessmentWorkflow._scan`.

- [ ] **Step 1: Write the failing test**

```python
"""Plan 1's payoff: _scan produces a real thirteen-row ScanResult and
terminal_status derives assessed:partial with no edit to E-45's derivation."""

from __future__ import annotations

import pytest

from sdlc.assessment.models import PARTIAL, PhaseId
from sdlc.assessment.scan.inherit import inherited_halves
from sdlc.assessment.scan.models import (
    C_CREDENTIAL_STORAGE,
    C_TLS,
    CATEGORIES,
    SCAN_ORDER,
    ScanSignalId,
    ScanSignalResult,
    SignalSource,
    family_of,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import (
    FixClass,
    Readiness,
    RepoTriage,
    SignalResult,
    TriageFinding,
    Verdict,
)
from sdlc.workflows.assessment import (
    ScanOutcome,
    fold_row,
    skipped_scan_signal,
)


def _triage() -> RepoTriage:
    ok = Measurement.measured(1.0)
    f = TriageFinding(
        signal="secrets",
        rule="aws_key",
        severity="critical",
        detail="d",
        path=".env",
        fix_class=FixClass.MECHANICAL,
        key="k",
    )
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        toolchain="python",
        readiness=Readiness(
            buildable=ok,
            runnable=ok,
            tests_present=ok,
            structure_discernible=ok,
            verdict=Verdict.READY,
        ),
        signals=[
            SignalResult(
                signal="secrets", version=2, collected=Measurement.measured(1.0), findings=[f]
            )
        ],
    )


def test_skipped_scan_signal_reports_every_owed_category():
    row = skipped_scan_signal(ScanSignalId.QS3, "activity failed")
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert set(row.categories) == set(CATEGORIES[ScanSignalId.QS3])
    assert "activity failed" in row.collected.reason


def test_fold_row_unions_categories_and_promotes_source_to_extended():
    """D7: the activity computed one half, inherit.py derived the other."""
    nc = Measurement.not_collected("plan 3")
    activity_row = ScanSignalResult(
        signal=ScanSignalId.SS1,
        family=family_of(ScanSignalId.SS1),
        version=1,
        source=SignalSource.COMPUTED,
        collected=nc,
        categories={k: nc for k in CATEGORIES[ScanSignalId.SS1]},
    )
    half = inherited_halves(_triage())[ScanSignalId.SS1]

    folded = fold_row(activity_row, half)
    assert folded.source is SignalSource.EXTENDED
    assert folded.producer is not None
    # the inherited half wins its own categories
    assert folded.categories[C_CREDENTIAL_STORAGE].state is CollectionState.MEASURED
    # and the computed ones stay the activity's
    assert folded.categories[C_TLS].state is CollectionState.NOT_COLLECTED
    assert set(folded.categories) == set(CATEGORIES[ScanSignalId.SS1])


def test_fold_row_without_a_half_leaves_the_row_computed():
    nc = Measurement.not_collected("plan 2")
    row = ScanSignalResult(
        signal=ScanSignalId.S1,
        family=family_of(ScanSignalId.S1),
        version=1,
        source=SignalSource.COMPUTED,
        collected=nc,
        categories={k: nc for k in CATEGORIES[ScanSignalId.S1]},
    )
    folded = fold_row(row, None)
    assert folded.source is SignalSource.COMPUTED
    assert folded.producer is None


def test_ss2_is_built_from_its_half_alone():
    """SS2 has no activity at all (D12), so the workflow must synthesize its
    row from the inherited half rather than from an activity result."""
    assert SCAN_SIGNALS[ScanSignalId.SS2].activity == ""
    half = inherited_halves(_triage())[ScanSignalId.SS2]
    assert set(half.categories) == set(CATEGORIES[ScanSignalId.SS2])


def test_scan_outcome_pairs_a_row_with_its_payload():
    out = ScanOutcome(result=None, scan=None) if False else None
    assert out is None  # shape asserted through the e2e below
```

Delete that last placeholder test before committing — it exists only to mark that `ScanOutcome`'s end-to-end shape is asserted in the temporal test, not here.

Then append to `tests/test_assessment_workflow_e2e.py`:

```python
@pytest.mark.temporal
async def test_scan_phase_flips_terminal_status_to_partial(...):
    """E-45 D6's claim, now testable: terminal_status is DERIVED, so E-46
    landing changes it with no workflow edit.

    Follow the file's existing fixture and worker-setup pattern; register the
    eleven scan activities plus assessment_resolve_tree alongside the triage
    activities the init child already needs.
    """
    result = ...     # drive AssessmentWorkflow over a READY fixture repo
    assert result.terminal_status == PARTIAL
    assert result.scan is not None
    assert [s.signal for s in result.scan.signals] == list(SCAN_ORDER)
    ss1 = next(s for s in result.scan.signals
               if s.signal is ScanSignalId.SS1)
    assert ss1.source is SignalSource.EXTENDED
    assert ss1.producer is not None
```

Fill the `...` by copying the existing e2e's environment, client and worker construction verbatim — do not invent a second harness.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_scan_phase.py -v`
Expected: FAIL — `ImportError: cannot import name 'ScanOutcome'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/workflows/assessment.py`, add to the imports block:

```python
from ..assessment.activities import (
    AssessmentTree,
    AssessmentTreeInput,
    ScanSignalInput,
    assessment_resolve_tree,
    scan_ci,
    scan_config_infra,
    scan_coverage,
    scan_entrypoints,
    scan_frontend,
    scan_packages,
    scan_schema,
    scan_security_static,
    scan_sensitivity,
    scan_testability,
    scan_tests_inventory,
)
from ..assessment.scan.inherit import InheritedHalf, inherited_halves
from ..assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    ScanResult,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    family_of,
)
from ..assessment.scan.registry import SCAN_SIGNALS, WAVES
from .fanout import run_or_degrade
```

Add the activity options and the dispatch table:

```python
# Deterministic given a tree; the retry covers FS/git blips only. Mirrors
# triage's SIGNAL_ACT, which these signals are the Tier 2 analogue of.
SCAN_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=2)
)
TREE_ACT = dict(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)

# Registry `activity` names resolved to the callables. A name the registry
# declares and this table lacks is a boot-time KeyError in _scan rather than a
# silent skip, which is why the test in Task 12 asserts they agree.
SCAN_ACTIVITIES = {
    "scan_packages": scan_packages,
    "scan_schema": scan_schema,
    "scan_entrypoints": scan_entrypoints,
    "scan_frontend": scan_frontend,
    "scan_security_static": scan_security_static,
    "scan_config_infra": scan_config_infra,
    "scan_sensitivity": scan_sensitivity,
    "scan_tests_inventory": scan_tests_inventory,
    "scan_coverage": scan_coverage,
    "scan_testability": scan_testability,
    "scan_ci": scan_ci,
}


class ScanOutcome(BaseModel):
    """scan's two halves, mirroring InitOutcome: a failed phase yields a row
    but no artifact."""

    result: PhaseResult
    scan: ScanResult | None = None


def skipped_scan_signal(signal_id: ScanSignalId, reason: str) -> ScanSignalResult:
    """A signal that did not run. Its owed categories come from the artifact's
    declaration, so a failed signal reports not_collected for exactly those
    rather than leaving them unreported (the E-42 D8a discipline)."""
    nc = Measurement.not_collected(reason)
    return ScanSignalResult(
        signal=signal_id,
        family=family_of(signal_id),
        version=SCAN_SIGNALS[signal_id].version,
        source=SignalSource.COMPUTED,
        collected=nc,
        categories={k: nc for k in CATEGORIES[signal_id]},
    )


def fold_row(activity_row: ScanSignalResult, half: InheritedHalf | None) -> ScanSignalResult:
    """Union the activity's computed half with the inherited half (D7).

    The inherited half wins its OWN categories and nothing else -- it is the
    authority on what Tier 0 measured, and the activity is the authority on
    what this phase computed. Neither can overwrite the other's keys.
    """
    if half is None:
        return activity_row
    return activity_row.model_copy(
        update={
            "source": SignalSource.EXTENDED,
            "producer": half.producer,
            "categories": activity_row.categories | half.categories,
        }
    )
```

Replace `_scan`:

```python
async def _scan(self, inp: AssessmentInput, triage: RepoTriage) -> ScanOutcome:
    """Phase 2 (E-46). Thirteen signals: eleven activities across two
    waves, plus S5's merge and SS2's pure inheritance in workflow code.

    Nothing here executes the assessed repository's code -- every signal
    reads blob bytes at the pinned commit (NFR-9, D12).
    """
    try:
        tree: AssessmentTree = await workflow.execute_activity(
            assessment_resolve_tree,
            AssessmentTreeInput(repo_dir=inp.repo_dir, commit_sha=triage.commit_sha),
            **TREE_ACT,
        )
    except Exception as e:  # noqa: BLE001
        # Without a tree hash nothing can be memoized or reproduced, so a
        # scan that proceeded would be unverifiable.
        return ScanOutcome(
            result=PhaseResult(
                phase=PhaseId.SCAN,
                collected=Measurement.not_collected(
                    f"could not resolve the tree hash: {type(e).__name__}: {e}"[:300]
                ),
            )
        )

    halves = inherited_halves(triage)
    outputs: dict[ScanSignalId, SignalOutput] = {}

    for wave in WAVES:
        upstream = [c for out in outputs.values() for c in out.sources]
        arg = ScanSignalInput(
            repo_dir=inp.repo_dir,
            commit_sha=triage.commit_sha,
            tree_hash=tree.tree_hash,
            upstream=sorted(upstream, key=lambda c: (c.signal.value, c.local_id)),
        )
        results = await asyncio.gather(
            *[
                run_or_degrade(
                    SCAN_ACTIVITIES[SCAN_SIGNALS[sid].activity],
                    arg,
                    SCAN_ACT,
                    fallback=lambda sid=sid: SignalOutput(
                        row=skipped_scan_signal(sid, f"{sid.value} activity failed or timed out")
                    ),
                )
                for sid in wave
            ]
        )
        outputs.update(zip(wave, results))

    # SS2 runs no activity (D12): its row IS its inherited half.
    for sid in SCAN_ORDER:
        if sid in outputs or SCAN_SIGNALS[sid].activity:
            continue
        outputs[sid] = SignalOutput(
            row=skipped_scan_signal(sid, f"{sid.value} has no computed half")
        )

    rows = [fold_row(outputs[sid].row, halves.get(sid)) for sid in SCAN_ORDER]
    sources = sorted(
        (c for out in outputs.values() for c in out.sources),
        key=lambda c: (c.signal.value, c.local_id),
    )
    scan = ScanResult(
        signals=rows,
        sources=sources,
        candidates=[],  # S5's merge lands in plan 2
        data_sensitivity=sorted(
            (r for out in outputs.values() for r in out.data_sensitivity),
            key=lambda r: (r.classification.value, r.entity),
        ),
        testability=sorted(
            (f for out in outputs.values() for f in out.testability),
            key=lambda f: (f.path, f.pattern, f.key),
        ),
    )
    measured = sum(1 for r in rows if r.collected.state is CollectionState.MEASURED)
    return ScanOutcome(
        result=PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(float(measured))),
        scan=scan,
    )
```

Update `run()` to thread both halves through:

```python
self._status = "running"
scan_out = await self._scan(inp, init.triage)
rest = [
    scan_out.result,
    await self._discover(inp),
    await self._assess(inp),
    await self._report(inp),  # AFTER assess -- FR-911 dev. (a)
    await self._generate(inp),
    await self._finish(inp),
]
return self._done(assemble(inp.repo_dir, init, True, why, rest, scan=scan_out.scan))
```

Remove `PhaseId.SCAN` from `PHASE_OWNER` — the phase is built, so nothing owes it. Add `import asyncio` and `from datetime import timedelta` / `from temporalio.common import RetryPolicy` to the module imports if absent.

In `src/sdlc/worker.py`, register the twelve new activities beside the triage ones:

```python
from .assessment.activities import (
    assessment_resolve_tree,
    scan_ci,
    scan_config_infra,
    scan_coverage,
    scan_entrypoints,
    scan_frontend,
    scan_packages,
    scan_schema,
    scan_security_static,
    scan_sensitivity,
    scan_testability,
    scan_tests_inventory,
)
```

and add them to the `activities=[...]` list.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assessment_scan_phase.py tests/test_assessment_workflow.py tests/test_assessment_models.py -v`
Expected: PASS

Then the whole fast suite, to confirm nothing regressed:
Run: `pytest -q`
Expected: PASS

Then the temporal proof:
Run: `pytest -m temporal tests/test_assessment_workflow_e2e.py -v`
Expected: PASS — `terminal_status == "assessed:partial"`

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/assessment.py src/sdlc/worker.py tests/test_assessment_scan_phase.py tests/test_assessment_workflow_e2e.py
git commit -m "feat(scan): wire the scan phase; terminal_status now derives assessed:partial (E-46)"
```

---

### Task 16: Roadmap and spec status updates

**Files:**
- Modify: `ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md`

**Interfaces:**
- Consumes: nothing. Documentation only.
- Produces: nothing code depends on.

- [ ] **Step 1: Update ROADMAP.md**

Apply only the plan-1 subset of the spec's §11 table. Do **not** mark E-46 or FR-912 `[x]` — eleven signal bodies are still stubs.

- **§11 E-46** — change `[ ]` to `[ ] ⚠️` and append: *"Plan 1 landed 2026-08-12: contracts, `SCAN_SIGNALS`, the memoized activity seam, and the five inherited halves (`src/sdlc/assessment/scan/`). All thirteen rows report; eleven bodies are stubs naming plan 2 or 3. `terminal_status` now derives `assessed:partial`."*
- **§2 FR-912** — append: *"⚠️ Plan 1 of E-46 landed. The memo key is `(tree_hash, signal_version, rules_sha)` — `rules_sha` beyond the specified two terms, hashed transitively over shared rule modules and consumed signals, because a hand-maintained version int misses a real input (spec D10)."*
- **§2 FR-902** — append: *"Extended cross-tier by E-46 D2: an assessment signal that duplicates a triage signal **cites** it by `finding_identity` and copies nothing."*
- **§2 FR-903 / FR-911** — under FR-911, note the stub count dropped from six to five and `PHASE_OWNER` lost its `SCAN` entry.
- **§2 FR-103** — append: *"Clarified (E-46 D10): E-47a's `identity_registry_version` term applies to the `CapabilityMap`, not to E-46's signal keys — E-46 is a pure function of the tree."*
- **§3 NFR-9** — append: *"E-46 adds no new execution of repository code: every scan signal is a blob read at the pinned commit."*
- **§0 P6** — append: *"Its first phase body is under way (E-46 plan 1 of 3)."*
- **§14 Open questions** — add: *"**OQ-12 — S5 normalization is English-centric.** Layer-suffix stripping and singularization assume English identifiers, so a non-English codebase degrades to LOW-confidence single-source candidates. Recorded rather than solved: calibrating it needs the corpus SC-8 also needs."*

- [ ] **Step 2: Update the spec's status line**

Change the `Status` row to: `Design approved 2026-08-12; plan 1 of 3 implemented`.

- [ ] **Step 3: Verify the docs claim nothing the code does not do**

Run: `pytest -q && pytest -m temporal tests/test_assessment_workflow_e2e.py -q`
Expected: PASS. Confirm by reading `ROADMAP.md`'s E-46 entry that every claim in it is one the suite just proved — in particular that E-46 is **not** marked `[x]`.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md
git commit -m "docs: record E-46 plan 1 — scan seam and inherited halves land, bodies pending"
```

---

## Plan self-review

**Spec coverage (plan-1 scope only).** D1 §9 plan 1 → Tasks 1–15. D2 → Tasks 5, 13. D3 → Task 5. D6 → Tasks 7, 12, 15. D7 → Tasks 12, 13, 15. D8 → Task 3. D10 → Tasks 8, 9, 11. D13 → Task 2. D14 → Task 10. Contracts §4 → Tasks 1–6, 14. Phase run §5 → Task 15. Error handling §6 → Tasks 10, 15 (per-signal degradation, nothing raises out of `_scan`, `SCAN_ORDER` iteration, sorted payloads). Testing §7 properties 3, 4, 5 → Tasks 6, 9, 8. Roadmap §11 → Task 16.

**Deferred to plans 2–3, deliberately:** D4, D5, D9, D11, D12's computed halves, and §7's properties 1 (byte-identical `ScanResult` — needs real records to be meaningful), 2 (already covered by Task 3) and 6 (`finding_id` resolution against `Assessment.triage` — the citation exists after Task 13, but asserting it resolves belongs with E-51's absolute cross-reference check).

**Known rough edges, flagged rather than hidden:**

1. **Task 8 has an ordering dependency on its own Step 3b.** `rules_sha` cannot hash modules that do not exist, so the eleven stub modules are created inside Task 8 rather than Task 12. Task 12 then adds the *activities*, not the modules. This is called out in Task 8's step text.
2. **Task 13's test file contains one contorted line** (`cats = ... if False else ...`) carried over from drafting. Simplify it to a direct call when implementing; the assertion it makes is correct.
3. **Task 15's last test is a placeholder** and its step text says to delete it. `ScanOutcome`'s end-to-end shape is asserted in the temporal test instead.
4. **Task 15's temporal test has `...` for fixture setup**, deliberately: the instruction is to copy `tests/test_assessment_workflow_e2e.py`'s existing environment and worker construction verbatim rather than invent a second harness. Read that file before writing it.
5. **SS1/SS3 double-count `unauthenticated_app`** across two categories. Recorded in Task 13's commit message with the one-line narrowing if E-49 needs a disjoint partition.
6. **Task 10 changes a failure message.** The degradation reason no longer interpolates the exception, since `run_or_degrade`'s fallback takes no arguments. Temporal history retains the detail.
